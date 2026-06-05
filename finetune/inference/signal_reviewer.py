"""
Fine-tuned model signal reviewer — drop-in replacement for AutonomousSignalReviewer.

2-TIER INFERENCE ARCHITECTURE:
  Tier 1 (every signal):  fine-tuned gemini-2.5-flash (europe-west4)
                          → calls tools → records decision
  Tier 2 (signal only):   gemini-2.5-pro (europe-west4)
                          → validates the trade, may override to no_trade

Rationale:
  - Rejections (no_trade) are low-stakes → fine-tuned flash is fast + cheap + reliable
  - Actual trades risk real paper money → pro validates with full context before commit

Usage:
  from finetune.inference.signal_reviewer import FineTunedSignalReviewer
  reviewer = FineTunedSignalReviewer(database=db)
  result = await reviewer.review_pending_signals(max_signals=5)

Env vars:
  VERTEX_PROJECT         GCP project ID (default: project-9eb04412-b304-4649-9ff)
  VERTEX_LOCATION        Region (default: europe-west4)
  FINETUNED_MODEL        Fine-tuned model ID after SFT completes
                         (default: gemini-2.5-flash until fine-tuned model available)
  PHASE2_BUDGET_ENABLED  Set to 1 to inject paper budget state into prompts
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
WALLETSCARPER_ROOT = ROOT / "WalletScarper"
WALLETSCARPER_PYTHON = WALLETSCARPER_ROOT / ".venv" / "Scripts" / "python.exe"
TOOLS_FILE = ROOT / "finetune" / "config" / "tools.json"
PROMPTS_DIR = ROOT / "finetune" / "prompts"

TOOLS_OPENAI = json.loads(TOOLS_FILE.read_text(encoding="utf-8"))
SYSTEM_PROMPT = (PROMPTS_DIR / "teacher_system.md").read_text(encoding="utf-8")

VERTEX_PROJECT = os.environ.get("VERTEX_PROJECT", "project-9eb04412-b304-4649-9ff")
VERTEX_LOCATION = os.environ.get("VERTEX_LOCATION", "europe-west4")

# Tier 1: fine-tuned flash — reads FINETUNED_MODEL env var, then .trained_model file, then base flash
def _resolve_tier1_model() -> str:
    if os.environ.get("FINETUNED_MODEL"):
        return os.environ["FINETUNED_MODEL"]
    _model_file = ROOT / "finetune" / "inference" / ".trained_model"
    if _model_file.exists():
        _m = _model_file.read_text(encoding="utf-8").strip()
        if _m:
            return _m
    return "gemini-2.5-flash"

TIER1_MODEL = _resolve_tier1_model()
# Tier 2: pro validator — only fires for signal decisions
TIER2_MODEL = "gemini-2.5-pro"

_PHASE2_ENABLED = os.environ.get("PHASE2_BUDGET_ENABLED", "").lower() in ("1", "true", "yes")

TOOL_NAME_MAP = {
    "wallet_profile_history": "wallet.profile_history",
    "token_get_profile": "token.get_profile",
    "agent_record_trading_decision": "agent.record_trading_decision",
    "signal_create": "signal.create",
    "risk_check_entry": "risk.check_entry",
    "paper_create_order": "paper.create_order",
    "paper_simulate_fill": "paper.simulate_fill",
    "market_get_token_snapshot": "market.get_token_snapshot",
}

_STRIP_ENV = {"PYTHONHOME", "PYTHONPATH", "PYTHONEXECUTABLE"}
log = logging.getLogger(__name__)


# ─── helpers ──────────────────────────────────────────────────────────────────

def _clean_env() -> dict[str, str]:
    return {k: v for k, v in os.environ.items() if k not in _STRIP_ENV}


def _call_v2_tool(tool_name: str, payload: dict) -> dict:
    v2_name = TOOL_NAME_MAP.get(tool_name, tool_name)
    if not WALLETSCARPER_PYTHON.exists():
        return {"ok": False, "error": f"venv missing: {WALLETSCARPER_PYTHON}"}
    try:
        result = subprocess.run(
            [str(WALLETSCARPER_PYTHON), "-m", "walletscarper",
             "stage2-v2-tool", v2_name, "--payload-json", json.dumps(payload)],
            cwd=str(WALLETSCARPER_ROOT),
            capture_output=True, text=True, timeout=60, check=False,
            env=_clean_env(),
        )
        if result.returncode != 0 and not result.stdout.strip():
            return {"ok": False, "error": f"rc={result.returncode}", "stderr": result.stderr[:300]}
        return json.loads(result.stdout.strip())
    except (subprocess.TimeoutExpired, json.JSONDecodeError, Exception) as exc:
        return {"ok": False, "error": str(exc)}


def _openai_to_gemini(messages: list[dict]) -> tuple[str | None, list[dict]]:
    """Convert OpenAI message list → (system_str, gemini_contents)."""
    system = None
    out = []
    id_to_name: dict[str, str] = {}
    for msg in messages:
        role = msg["role"]
        if role == "system":
            system = msg.get("content") or ""
        elif role == "user":
            text = msg.get("content") or ""
            if text:
                out.append({"role": "user", "parts": [{"text": text}]})
        elif role == "assistant":
            parts = []
            if msg.get("content"):
                parts.append({"text": msg["content"]})
            for tc in (msg.get("tool_calls") or []):
                fn = tc["function"]
                try:
                    args = json.loads(fn["arguments"])
                except Exception:
                    args = {}
                id_to_name[tc["id"]] = fn["name"]
                parts.append({"function_call": {"name": fn["name"], "args": args}})
            if parts:
                out.append({"role": "model", "parts": parts})
        elif role == "tool":
            fn_name = id_to_name.get(msg.get("tool_call_id", ""), "tool_result")
            try:
                content = json.loads(msg["content"])
            except Exception:
                content = {"text": str(msg.get("content", ""))}
            out.append({"role": "user",
                        "parts": [{"function_response": {"name": fn_name, "response": content}}]})
    return system, out


def _tools_to_gemini(tools: list[dict]) -> list[dict]:
    return [{"function_declarations": [
        {"name": t["function"]["name"],
         "description": t["function"].get("description", ""),
         "parameters": t["function"].get("parameters", {})}
        for t in tools
    ]}]


def _vertex_client():
    from google import genai
    return genai.Client(vertexai=True, project=VERTEX_PROJECT, location=VERTEX_LOCATION)


def _vertex_call_sync(client, model: str, messages: list[dict], tools: list[dict]) -> dict | None:
    """Synchronous Vertex call (run in executor for async contexts)."""
    system, gemini_msgs = _openai_to_gemini(messages)
    gemini_tools = _tools_to_gemini(tools)

    cfg: dict = {
        "temperature": 0.0,
        "max_output_tokens": 2000,
    }
    if gemini_tools and gemini_tools[0].get("function_declarations"):
        cfg["tools"] = gemini_tools
        cfg["tool_config"] = {"function_calling_config": {"mode": "AUTO"}}
    if system:
        cfg["system_instruction"] = system

    try:
        resp = client.models.generate_content(model=model, contents=gemini_msgs, config=cfg)
    except Exception as exc:
        log.warning("vertex call failed: %s", exc)
        return None

    cand = resp.candidates[0] if resp.candidates else None
    parts = (cand.content.parts if cand and cand.content else [])
    tool_calls = []
    text_content = None
    for part in parts:
        if hasattr(part, "function_call") and part.function_call and part.function_call.name:
            tool_calls.append({
                "id": f"call_{uuid.uuid4().hex[:8]}",
                "type": "function",
                "function": {
                    "name": part.function_call.name,
                    "arguments": json.dumps(dict(part.function_call.args or {})),
                },
            })
        if hasattr(part, "text") and part.text:
            text_content = part.text

    return {"message": {"role": "assistant", "content": text_content,
                        "tool_calls": tool_calls or None}}


# ─── main reviewer class ───────────────────────────────────────────────────────

class FineTunedSignalReviewer:
    """
    Drop-in replacement for AutonomousSignalReviewer.
    Uses 2-tier Vertex AI:
      Tier 1 → fine-tuned gemini-2.5-flash (tool calls + decision)
      Tier 2 → gemini-2.5-pro (validates if Tier 1 says signal)
    """

    def __init__(self, database: Any, model: str | None = None) -> None:
        self.database = database
        self.tier1_model = model or TIER1_MODEL
        self.tier2_model = TIER2_MODEL
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                self._client = _vertex_client()
            except Exception as exc:
                log.error("vertex client init failed: %s", exc)
        return self._client

    async def review_pending_signals(self, max_signals: int = 5) -> dict[str, Any]:
        signals = await self._pending_signals(max_signals)
        if not signals:
            return {"signals_reviewed": 0, "decisions_recorded": 0, "errors": 0}

        reviewed = recorded = errors = 0
        for signal in signals:
            try:
                decision_id = await self._review_one(signal)
                reviewed += 1
                if decision_id:
                    recorded += 1
            except Exception:
                log.warning("review failed for %s",
                            signal.get("tracked_wallet_signal_event_id", "?"), exc_info=True)
                errors += 1

        log.info("review: reviewed=%d recorded=%d errors=%d", reviewed, recorded, errors)
        return {"signals_reviewed": reviewed, "decisions_recorded": recorded, "errors": errors}

    async def _review_one(self, signal: dict) -> str | None:
        signal_id = str(signal["tracked_wallet_signal_event_id"])
        t0 = time.perf_counter()
        client = self._get_client()
        if not client:
            return None

        # ── Phase 2: inject budget state ──────────────────────────────────────
        budget_block = ""
        if _PHASE2_ENABLED:
            try:
                _finetune_path = str(ROOT / "finetune")
                if _finetune_path not in sys.path:
                    sys.path.insert(0, _finetune_path)
                from tools.budget_state import get_budget_state, format_budget_context
                state = await get_budget_state()
                if state.get("circuit_broken"):
                    log.warning("circuit breaker active — skipping signal %s", signal_id[:12])
                    return None
                budget_block = "\n\n" + format_budget_context(state)
            except Exception as exc:
                log.warning("budget state failed: %s", exc)

        user_message = (
            f"AUTONOMOUS SIGNAL REVIEW\n\n"
            f"Signal event:\n"
            f"  tracked_wallet_signal_event_id: {signal_id}\n"
            f"  wallet: {signal.get('wallet', '')}\n"
            f"  token_mint: {signal.get('token_mint', '')}\n"
            f"  side: {signal.get('side', '')}\n"
            f"  observed_at: {signal.get('observed_at', '')}\n"
            f"{budget_block}\n"
            f"Execute the required tool sequence and record your decision."
        )

        messages: list[dict] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ]

        # ── TIER 1: fine-tuned flash ───────────────────────────────────────────
        decision_recorded = False
        decision_type: str | None = None

        for turn in range(10):
            resp = await asyncio.get_event_loop().run_in_executor(
                None, lambda: _vertex_call_sync(client, self.tier1_model, messages, TOOLS_OPENAI)
            )
            if not resp:
                break

            msg = resp["message"]
            tool_calls = msg.get("tool_calls") or []
            assistant_entry: dict = {"role": "assistant", "content": msg.get("content")}
            if tool_calls:
                assistant_entry["tool_calls"] = tool_calls
            messages.append(assistant_entry)

            if not tool_calls:
                break

            for tc in tool_calls:
                fn_name = tc["function"]["name"]
                tc_id = tc["id"]
                try:
                    args = json.loads(tc["function"]["arguments"] or "{}")
                except Exception:
                    args = {}

                if fn_name == "agent_record_trading_decision":
                    args.setdefault("linked_tracked_wallet_signal_event_id", signal_id)
                    decision_recorded = True
                    decision_type = args.get("decision_type")

                result = await asyncio.get_event_loop().run_in_executor(
                    None, lambda fn=fn_name, a=args: _call_v2_tool(fn, a)
                )
                messages.append({"role": "tool", "tool_call_id": tc_id,
                                 "content": json.dumps(result, default=str)})

            if decision_recorded and turn >= 2:
                break

        t1 = time.perf_counter()
        market_called = any(
            tc["function"]["name"] == "market_get_token_snapshot"
            for msg in messages
            if msg.get("role") == "assistant"
            for tc in (msg.get("tool_calls") or [])
        )
        log.info("tier1: signal=%s decision=%s model=%s market_snapshot=%s (%.1fs)",
                 signal_id[:12], decision_type, self.tier1_model, market_called, t1 - t0)

        if not decision_recorded:
            return None

        # ── TIER 2: pro validates actual trades ────────────────────────────────
        if decision_type == "signal":
            confirmed = await self._tier2_validate(client, signal_id, messages)
            if not confirmed:
                log.info("tier2: pro overrode signal→no_trade for %s", signal_id[:12])
                await self._override_decision(signal_id, "no_trade",
                                              "Tier2 pro validator overrode flash signal decision")
                return None
            log.info("tier2: pro confirmed signal for %s (%.1fs total)",
                     signal_id[:12], time.perf_counter() - t0)

        decision_id = await self._find_decision(signal_id)
        # ── Save session JSON for training flywheel ────────────────────────────
        await self._save_session(signal_id, messages, decision_type or "no_trade", t1 - t0)
        return decision_id

    async def _save_session(
        self, signal_id: str, messages: list[dict], decision_type: str, elapsed: float
    ) -> None:
        """Persist the full conversation as a session JSON for future retraining."""
        try:
            sessions_dir = ROOT / "finetune" / "data" / "sessions"
            sessions_dir.mkdir(parents=True, exist_ok=True)
            ts = datetime.now(timezone.utc)
            fname = ts.strftime("%Y%m%d_%H%M%S") + f"_live_{signal_id[:16]}.json"
            session = {
                "session_id": str(uuid.uuid4()),
                "signal_id": signal_id,
                "model": self.tier1_model,
                "provider": "vertex_live",
                "timestamp": ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "elapsed_seconds": round(elapsed, 2),
                "decision_recorded": True,
                "outcome_label": None,   # will be set by outcome_tracker after 4h
                "messages": messages,
            }
            (sessions_dir / fname).write_text(
                json.dumps(session, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            log.info("session saved: %s (%s)", fname, decision_type)
        except Exception as exc:
            log.warning("failed to save session for %s: %s", signal_id[:12], exc)

    async def _tier2_validate(self, client, signal_id: str, tier1_messages: list[dict]) -> bool:
        """
        Run gemini-2.5-pro with full Tier 1 conversation context.
        Pro answers: CONFIRM or OVERRIDE.
        Returns True = confirmed signal, False = override to no_trade.
        """
        validation_prompt = (
            "You are a senior risk manager reviewing a junior analyst's trading signal decision.\n\n"
            "The analyst (above conversation) reviewed the signal and decided: SIGNAL (trade).\n\n"
            "Review their complete reasoning including:\n"
            "1. Wallet quality: win_rate AND payoff_ratio AND net_pnl (high win rate with negative PnL = red flag)\n"
            "2. Token safety: liquidity, market cap, quality flags\n"
            "3. Entry timing: market snapshot price_change_1h (>50% = possibly late), buy/sell ratio\n"
            "4. Signal age: was this signal fresh when evaluated?\n\n"
            "Respond with EXACTLY one word:\n"
            "  CONFIRM — if the signal is well-supported across all dimensions\n"
            "  OVERRIDE — if you see: negative net PnL, late entry (token already pumped), distribution phase, "
            "or any other red flag\n\n"
            "Be conservative. When in doubt: OVERRIDE."
        )

        validation_messages = tier1_messages + [
            {"role": "user", "content": validation_prompt}
        ]

        try:
            resp = await asyncio.get_event_loop().run_in_executor(
                None, lambda: _vertex_call_sync(
                    client, self.tier2_model, validation_messages, []  # no tools for validator
                )
            )
            if not resp:
                log.warning("tier2: pro call failed — defaulting to OVERRIDE (safe)")
                return False

            answer = (resp["message"].get("content") or "").strip().upper()
            log.info("tier2: pro answer=%r for signal=%s", answer, signal_id[:12])
            return answer == "CONFIRM"
        except Exception as exc:
            log.warning("tier2 failed: %s — defaulting OVERRIDE", exc)
            return False

    async def _override_decision(self, signal_id: str, new_type: str, reason: str) -> None:
        """Update the most recent decision for this signal to no_trade."""
        try:
            await self.database.execute(
                """
                UPDATE agent_trading_decisions
                SET decision_type = ?, pre_action_reasoning = COALESCE(pre_action_reasoning, '') || ? || char(10) || ?
                WHERE linked_tracked_wallet_signal_event_id = ?
                  AND rowid = (
                    SELECT rowid FROM agent_trading_decisions
                    WHERE linked_tracked_wallet_signal_event_id = ?
                    ORDER BY created_at DESC LIMIT 1
                  )
                """,
                (new_type, "\n[Tier2 Pro Override]", reason, signal_id, signal_id),
            )
        except Exception as exc:
            log.warning("override decision failed: %s", exc)

    async def _pending_signals(self, limit: int) -> list[dict]:
        return await self.database.fetchall(
            """
            SELECT s.*
            FROM tracked_wallet_signal_events s
            WHERE s.input_mode = 'real_source'
              AND NOT EXISTS (
                SELECT 1 FROM agent_trading_decisions d
                WHERE d.linked_tracked_wallet_signal_event_id = s.tracked_wallet_signal_event_id
              )
            ORDER BY s.observed_at DESC, s.created_at DESC
            LIMIT ?
            """,
            (limit,),
        )

    async def _find_decision(self, signal_id: str) -> str | None:
        row = await self.database.fetchone(
            """
            SELECT agent_trading_decision_id
            FROM agent_trading_decisions
            WHERE linked_tracked_wallet_signal_event_id = ?
            ORDER BY created_at DESC LIMIT 1
            """,
            (signal_id,),
        )
        return str(row["agent_trading_decision_id"]) if row else None
