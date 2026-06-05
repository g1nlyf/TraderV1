"""
Teacher Service — runs a strong model (GPT-4o or Claude Sonnet) as signal reviewer.

The teacher model:
  1. Receives a pending signal event
  2. Calls tools (wallet_profile_history, token_get_profile, agent_record_trading_decision)
  3. Each tool call is intercepted → executed against real stage2 DB → real result returned
  4. The FULL conversation (messages + tool results) is saved as a training example for fine-tuning

This produces high-quality training data:
  - Real context (real wallet metrics, real token profiles)
  - Strong-model reasoning (GPT-4o / Claude Sonnet)
  - Correct tool call sequences
  - Actual decisions written to DB (paper trades may result)

Usage:
  python scripts/teacher_service.py                          # process all pending
  python scripts/teacher_service.py --max-signals 5         # process at most 5
  python scripts/teacher_service.py --provider openai       # use GPT-4o
  python scripts/teacher_service.py --provider anthropic    # use Claude Sonnet
  python scripts/teacher_service.py --dry-run               # don't write to DB
"""
from __future__ import annotations

import argparse
import asyncio
import json
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
DB_PATH = WALLETSCARPER_ROOT / "data" / "stage2_foundation.sqlite3"
SESSIONS_DIR = ROOT / "finetune" / "data" / "sessions"
PROMPTS_DIR = ROOT / "finetune" / "prompts"

sys.path.insert(0, str(ROOT / "finetune"))
from tools.db_context import get_pending_signals, get_signal_full_context

TEACHER_SYSTEM_PROMPT = (PROMPTS_DIR / "teacher_system.md").read_text(encoding="utf-8")

# Tool schemas for teacher model (same as config/tools.json)
TOOLS = json.loads((ROOT / "finetune" / "config" / "tools.json").read_text(encoding="utf-8"))

# Map from OpenAI function name → stage2-v2-tool name
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

# Python env vars that cause venv mismatch
_STRIP_ENV = {"PYTHONHOME", "PYTHONPATH", "PYTHONEXECUTABLE"}


def _clean_env() -> dict[str, str]:
    return {k: v for k, v in os.environ.items() if k not in _STRIP_ENV}


def call_v2_tool(tool_name: str, payload: dict, dry_run: bool = False) -> dict:
    """Execute a stage2 v2 tool via WalletScarper CLI subprocess."""
    v2_name = TOOL_NAME_MAP.get(tool_name, tool_name)

    if dry_run and v2_name in (
        "agent.record_trading_decision", "signal.create", "risk.check_entry",
        "paper.create_order", "paper.simulate_fill",
    ):
        return {
            "tool": v2_name, "ok": True,
            "artifact_id": f"dry_run_{uuid.uuid4().hex[:8]}",
            "dry_run": True, "data_as_of": datetime.now(timezone.utc).isoformat(),
            "quality_flags": [], "confidence": "medium", "next_suggested_tools": [],
        }

    if not WALLETSCARPER_PYTHON.exists():
        return {"ok": False, "error": f"WalletScarper venv not found: {WALLETSCARPER_PYTHON}"}

    try:
        result = subprocess.run(
            [
                str(WALLETSCARPER_PYTHON), "-m", "walletscarper",
                "stage2-v2-tool", v2_name,
                "--payload-json", json.dumps(payload),
            ],
            cwd=str(WALLETSCARPER_ROOT),
            capture_output=True, text=True, timeout=60, check=False,
            env=_clean_env(),
        )
        if result.returncode != 0 and not result.stdout.strip():
            return {
                "ok": False,
                "error": f"Tool {v2_name} failed (rc={result.returncode})",
                "stderr": result.stderr.strip()[:500],
            }
        try:
            return json.loads(result.stdout.strip())
        except json.JSONDecodeError:
            return {"ok": False, "error": "non-JSON output", "raw": result.stdout.strip()[:500]}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"Tool {v2_name} timed out after 60s"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


async def review_signal_with_teacher(
    signal_id: str,
    provider: str,
    model: str,
    dry_run: bool = False,
) -> dict:
    """Run teacher model on one signal. Returns session data (conversation + decision)."""
    ctx = await get_signal_full_context(signal_id)
    if "error" in ctx:
        return {"ok": False, "error": ctx["error"]}

    event = ctx["signal_event"]
    user_message = (
        f"AUTONOMOUS SIGNAL REVIEW\n\n"
        f"Signal event:\n"
        f"  tracked_wallet_signal_event_id: {event.get('tracked_wallet_signal_event_id')}\n"
        f"  wallet: {event.get('wallet')}\n"
        f"  token_mint: {event.get('token_mint')}\n"
        f"  side: {event.get('side')}\n"
        f"  observed_at: {event.get('observed_at')}\n"
        f"  source: {event.get('source_name')}\n"
        f"  data_sufficiency: {event.get('data_sufficiency')}\n\n"
        f"Execute the required tool sequence and record your decision."
    )

    messages: list[dict] = [
        {"role": "system", "content": TEACHER_SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ]

    tool_calls_made: list[dict] = []
    decision_recorded = False
    max_turns = 10
    t0 = time.perf_counter()

    for turn in range(max_turns):
        response = await _call_llm(provider, model, messages, TOOLS)
        if not response:
            break

        # Extract assistant message
        assistant_msg = response.get("message", {})
        tool_calls = assistant_msg.get("tool_calls") or []

        messages.append({"role": "assistant", **_clean_message(assistant_msg)})

        if not tool_calls:
            # No more tool calls — model finished
            break

        # Execute each tool call
        for tc in tool_calls:
            fn = tc.get("function", {})
            fn_name = fn.get("name", "")
            tc_id = tc.get("id", f"call_{uuid.uuid4().hex[:8]}")

            try:
                args = json.loads(fn.get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}

            # Inject signal_id for decision recording
            if fn_name == "agent_record_trading_decision":
                args.setdefault(
                    "linked_tracked_wallet_signal_event_id",
                    str(event.get("tracked_wallet_signal_event_id")),
                )
                decision_recorded = True

            result = call_v2_tool(fn_name, args, dry_run=dry_run)
            tool_calls_made.append({"name": fn_name, "args": args, "result": result})

            messages.append({
                "role": "tool",
                "tool_call_id": tc_id,
                "content": json.dumps(result, default=str),
            })

        # Stop if we've recorded a decision (minimum requirement)
        if decision_recorded and turn >= 2:
            break

    elapsed = time.perf_counter() - t0

    return {
        "ok": True,
        "signal_id": signal_id,
        "wallet": event.get("wallet"),
        "token_mint": event.get("token_mint"),
        "decision_recorded": decision_recorded,
        "tool_calls_made": [t["name"] for t in tool_calls_made],
        "elapsed_seconds": round(elapsed, 1),
        "provider": provider,
        "model": model,
        "messages": messages,  # Full conversation for training data
        "dry_run": dry_run,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def _clean_message(msg: dict) -> dict:
    """Strip None values from assistant message for clean JSONL."""
    return {k: v for k, v in msg.items() if v is not None and k != "role"}


VERTEX_PROJECT = os.environ.get("VERTEX_PROJECT", "project-9eb04412-b304-4649-9ff")
VERTEX_LOCATION = os.environ.get("VERTEX_LOCATION", "europe-west4")


def _openai_msgs_to_gemini(messages: list[dict]) -> tuple[str | None, list[dict]]:
    """Convert OpenAI-format messages → Gemini format. Returns (system, gemini_messages)."""
    system = None
    out = []
    tool_id_to_name: dict[str, str] = {}

    for msg in messages:
        role = msg["role"]
        if role == "system":
            system = msg.get("content") or ""
        elif role == "user":
            out.append({"role": "user", "parts": [{"text": msg.get("content") or ""}]})
        elif role == "assistant":
            parts = []
            if msg.get("content"):
                parts.append({"text": msg["content"]})
            for tc in (msg.get("tool_calls") or []):
                fn = tc["function"]
                try:
                    args = json.loads(fn["arguments"])
                except (json.JSONDecodeError, TypeError):
                    args = {}
                tool_id_to_name[tc["id"]] = fn["name"]
                parts.append({"function_call": {"name": fn["name"], "args": args}})
            if parts:
                out.append({"role": "model", "parts": parts})
        elif role == "tool":
            tc_id = msg.get("tool_call_id", "")
            fn_name = tool_id_to_name.get(tc_id, "tool_result")
            try:
                content = json.loads(msg["content"])
            except (json.JSONDecodeError, TypeError):
                content = {"text": str(msg.get("content", ""))}
            out.append({
                "role": "user",
                "parts": [{"function_response": {"name": fn_name, "response": content}}],
            })
    return system, out


def _tools_to_gemini(tools: list[dict]) -> list[dict]:
    """Convert OpenAI function schemas → Gemini FunctionDeclaration list."""
    declarations = []
    for t in tools:
        fn = t["function"]
        declarations.append({
            "name": fn["name"],
            "description": fn.get("description", ""),
            "parameters": fn.get("parameters", {}),
        })
    return [{"function_declarations": declarations}]


async def _call_llm(
    provider: str, model: str, messages: list[dict], tools: list[dict]
) -> dict | None:
    if provider in ("openai", "openrouter"):
        return await _call_openai(model, messages, tools, use_openrouter=(provider == "openrouter"))
    elif provider == "anthropic":
        return await _call_anthropic(model, messages, tools)
    elif provider == "vertex":
        return await _call_vertex(model, messages, tools)
    else:
        raise ValueError(f"Unknown provider: {provider}")


async def _call_vertex(model: str, messages: list[dict], tools: list[dict]) -> dict | None:
    """Google Vertex AI via google-genai SDK. Uses ADC (gcloud auth application-default login)."""
    try:
        from google import genai as gai
        from google.genai import types as gtypes
    except ImportError:
        print("[ERROR] google-cloud-aiplatform not installed. Run: py -m pip install google-cloud-aiplatform")
        return None

    system, gemini_msgs = _openai_msgs_to_gemini(messages)
    gemini_tools = _tools_to_gemini(tools)

    try:
        client = gai.Client(vertexai=True, project=VERTEX_PROJECT, location=VERTEX_LOCATION)

        config_kwargs: dict = {
            "tools": gemini_tools,
            "tool_config": {"function_calling_config": {"mode": "AUTO"}},
            "temperature": 0.0,
            "max_output_tokens": 2000,
        }
        if system:
            config_kwargs["system_instruction"] = system

        resp = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: client.models.generate_content(
                model=model,
                contents=gemini_msgs,
                config=config_kwargs,
            ),
        )

        candidate = resp.candidates[0]
        parts = candidate.content.parts if candidate.content else []

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

        return {
            "message": {
                "role": "assistant",
                "content": text_content,
                "tool_calls": tool_calls or None,
            }
        }
    except Exception as exc:
        print(f"[ERROR] Vertex call failed: {exc}")
        return None


async def _call_openai(
    model: str, messages: list[dict], tools: list[dict], use_openrouter: bool = False
) -> dict | None:
    """Supports OpenAI directly OR OpenRouter."""
    try:
        from openai import AsyncOpenAI
    except ImportError:
        print("[ERROR] openai package not installed. Run: pip install openai")
        return None

    if use_openrouter:
        key = os.environ.get("OPENROUTER_API_KEY")
        if not key:
            print("[ERROR] OPENROUTER_API_KEY not set")
            return None
        client = AsyncOpenAI(
            api_key=key,
            base_url="https://openrouter.ai/api/v1",
            default_headers={
                "HTTP-Referer": "https://github.com/TraderV1",
                "X-Title": "TraderV1-Teacher",
            },
        )
    else:
        client = AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

    try:
        resp = await client.chat.completions.create(
            model=model,
            messages=messages,
            tools=tools,
            tool_choice="auto",
            temperature=0.1,
            max_tokens=2000,
        )
        msg = resp.choices[0].message
        return {
            "message": {
                "role": "assistant",
                "content": msg.content,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                    }
                    for tc in (msg.tool_calls or [])
                ] or None,
            }
        }
    except Exception as exc:
        print(f"[ERROR] LLM call failed: {exc}")
        return None


async def _call_anthropic(model: str, messages: list[dict], tools: list[dict]) -> dict | None:
    try:
        import anthropic
    except ImportError:
        print("[ERROR] anthropic package not installed. Run: pip install anthropic")
        return None

    client = anthropic.AsyncAnthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

    # Convert tools to Anthropic format
    anthropic_tools = []
    for t in tools:
        fn = t["function"]
        anthropic_tools.append({
            "name": fn["name"],
            "description": fn["description"],
            "input_schema": fn["parameters"],
        })

    # Separate system from messages
    system = next((m["content"] for m in messages if m["role"] == "system"), "")
    non_system = [m for m in messages if m["role"] != "system"]

    # Convert tool results to Anthropic format
    anthropic_messages = []
    for m in non_system:
        if m["role"] == "tool":
            # Anthropic expects tool results as user messages
            anthropic_messages.append({
                "role": "user",
                "content": [{
                    "type": "tool_result",
                    "tool_use_id": m.get("tool_call_id", ""),
                    "content": m.get("content", ""),
                }],
            })
        elif m["role"] == "assistant" and m.get("tool_calls"):
            tc_content = []
            if m.get("content"):
                tc_content.append({"type": "text", "text": m["content"]})
            for tc in m["tool_calls"]:
                fn = tc["function"]
                try:
                    args = json.loads(fn["arguments"])
                except json.JSONDecodeError:
                    args = {}
                tc_content.append({
                    "type": "tool_use",
                    "id": tc["id"],
                    "name": fn["name"],
                    "input": args,
                })
            anthropic_messages.append({"role": "assistant", "content": tc_content})
        else:
            anthropic_messages.append(m)

    try:
        resp = await client.messages.create(
            model=model,
            system=system,
            messages=anthropic_messages,
            tools=anthropic_tools,
            max_tokens=2000,
            temperature=0,
        )

        tool_calls = []
        text_content = None
        for block in resp.content:
            if block.type == "tool_use":
                tool_calls.append({
                    "id": block.id,
                    "type": "function",
                    "function": {
                        "name": block.name,
                        "arguments": json.dumps(block.input),
                    },
                })
            elif block.type == "text":
                text_content = block.text

        return {
            "message": {
                "role": "assistant",
                "content": text_content,
                "tool_calls": tool_calls or None,
            }
        }
    except Exception as exc:
        print(f"[ERROR] Anthropic call failed: {exc}")
        return None


def save_session(session: dict) -> Path:
    """Save teacher session as training example."""
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    signal_id = str(session.get("signal_id") or "unknown")[:12]
    filename = f"{ts}_{signal_id}.json"
    path = SESSIONS_DIR / filename
    path.write_text(json.dumps(session, indent=2, default=str), encoding="utf-8")
    return path


async def run_teacher(
    max_signals: int = 10,
    provider: str = "openai",
    model: str = "",
    dry_run: bool = False,
) -> None:
    if not model:
        defaults = {
            "openai": "gpt-4o",
            "openrouter": "openrouter/owl-alpha",
            "anthropic": "claude-sonnet-4-6",
            "vertex": "gemini-2.5-pro",  # strongest EU teacher
        }
        model = defaults.get(provider, "gpt-4o")

    # Check API key / credentials
    if provider == "openai" and not os.environ.get("OPENAI_API_KEY"):
        print("[ERROR] OPENAI_API_KEY not set")
        sys.exit(1)
    if provider == "openrouter" and not os.environ.get("OPENROUTER_API_KEY"):
        print("[ERROR] OPENROUTER_API_KEY not set")
        sys.exit(1)
    if provider == "anthropic" and not os.environ.get("ANTHROPIC_API_KEY"):
        print("[ERROR] ANTHROPIC_API_KEY not set")
        sys.exit(1)
    if provider == "vertex":
        adc = Path.home() / "AppData" / "Roaming" / "gcloud" / "application_default_credentials.json"
        if not adc.exists():
            print("[ERROR] Vertex AI: ADC not found. Run: gcloud auth application-default login")
            sys.exit(1)
        print(f"[teacher] Vertex AI: project={VERTEX_PROJECT} location={VERTEX_LOCATION} model={model}")

    pending = await get_pending_signals(limit=max_signals)
    if not pending:
        print("[teacher] No pending signals to review.")
        return

    print(f"[teacher] Provider: {provider} / {model}")
    print(f"[teacher] Processing {len(pending)} pending signals (dry_run={dry_run})")
    print()

    results = {"ok": 0, "failed": 0, "no_decision": 0}

    for i, sig in enumerate(pending, 1):
        sid = str(sig.get("tracked_wallet_signal_event_id") or "")
        wallet = str(sig.get("wallet") or "")[:12]
        token = str(sig.get("token_mint") or "")[:12]
        print(f"[{i}/{len(pending)}] signal={sid[:16]}.. wallet={wallet} token={token}", end=" ", flush=True)

        session = await review_signal_with_teacher(
            signal_id=sid,
            provider=provider,
            model=model,
            dry_run=dry_run,
        )

        if not session.get("ok"):
            print(f"ERROR: {session.get('error')}")
            results["failed"] += 1
            continue

        decision_ok = session.get("decision_recorded", False)
        tools_used = ", ".join(session.get("tool_calls_made") or [])
        elapsed = session.get("elapsed_seconds", 0)

        if decision_ok:
            print(f"✓ ({elapsed}s) tools=[{tools_used}]")
            results["ok"] += 1
        else:
            print(f"⚠ no decision recorded ({elapsed}s) tools=[{tools_used}]")
            results["no_decision"] += 1

        saved_path = save_session(session)
        print(f"   saved → {saved_path.name}")

    print(f"\n[teacher] Done: ok={results['ok']} no_decision={results['no_decision']} failed={results['failed']}")
    print(f"[teacher] Sessions saved to: {SESSIONS_DIR.relative_to(ROOT)}")
    print("[teacher] Run scripts/05_label_outcomes.py after paper trades close to add outcome labels.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Teacher model signal reviewer")
    parser.add_argument("--max-signals", type=int, default=10)
    parser.add_argument("--provider", choices=["openai", "openrouter", "anthropic", "vertex"], default="vertex")
    parser.add_argument("--model", default="", help="Override model name")
    parser.add_argument("--dry-run", action="store_true", help="Don't write to DB")
    args = parser.parse_args()

    asyncio.run(run_teacher(
        max_signals=args.max_signals,
        provider=args.provider,
        model=args.model,
        dry_run=args.dry_run,
    ))


if __name__ == "__main__":
    main()
