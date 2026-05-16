"""Hermes autonomous signal review service.

Polls unreviewed tracked_wallet_signal_events, calls the configured LLM (via
OpenRouter / Hermes provider settings), records AgentTradingDecision, and
optionally runs the deterministic risk + paper path when decision_type == 'signal'.

This is the missing Brick-3 loop: raw wallet buy/sell signal → Hermes AI
analysis → paper trade decision → deterministic ledger path.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from walletscarper.stage2.db import Stage2Database

log = logging.getLogger(__name__)

_HERMES_DECISION_SCHEMA = """
Return ONLY a JSON object with these fields:
{
  "decision_type": "signal" | "no_trade" | "wait" | "downgrade_wallet",
  "pre_action_reasoning": "<concise explanation, 2-5 sentences>",
  "confidence": "high" | "medium" | "low",
  "uncertainties": ["<list of key unknowns>"],
  "wallet_assessment": "<1-2 sentences on wallet quality>",
  "token_assessment": "<1-2 sentences on token quality>",
  "signal_strength": "strong" | "moderate" | "weak" | "absent"
}
decision_type rules:
- "signal": wallet is high-quality, token looks tradeable, signal is fresh and real
- "no_trade": signal exists but quality or conditions insufficient
- "wait": need more data before deciding
- "downgrade_wallet": wallet is showing poor quality or inconsistent behavior
"""


class HermesSignalReviewService:
    """Autonomous Hermes review loop for tracked wallet signal events.

    Queries unreviewed signals (those without a linked AgentTradingDecision),
    calls the LLM, and records decisions through the deterministic V2 tool path.
    """

    def __init__(self, database: Stage2Database) -> None:
        self.database = database

    async def review_pending_signals(self, max_signals: int = 5) -> dict[str, Any]:
        """Review up to max_signals unreviewed wallet signal events.

        Returns a summary dict with signals_reviewed, decisions_recorded, errors.
        """
        from walletscarper.config import settings

        if not settings.hermes_enabled or not settings.hermes_api_key:
            log.debug("hermes_review: Hermes not enabled or no API key — skipping")
            return {"signals_reviewed": 0, "decisions_recorded": 0, "errors": 0, "skipped": "hermes_disabled"}

        signals = await self._pending_signals(max_signals)
        if not signals:
            log.debug("hermes_review: no pending signals")
            return {"signals_reviewed": 0, "decisions_recorded": 0, "errors": 0}

        reviewed = 0
        recorded = 0
        errors = 0
        for signal in signals:
            try:
                decision = await self._review_one_signal(signal, settings=settings)
                if decision:
                    recorded += 1
                reviewed += 1
            except Exception:
                log.warning("hermes_review: failed for signal %s", signal.get("tracked_wallet_signal_event_id"), exc_info=True)
                errors += 1

        log.info("hermes_review: reviewed=%d recorded=%d errors=%d", reviewed, recorded, errors)
        return {"signals_reviewed": reviewed, "decisions_recorded": recorded, "errors": errors}

    async def _pending_signals(self, limit: int) -> list[dict[str, Any]]:
        """Return signal events not yet linked to any AgentTradingDecision."""
        return await self.database.fetchall(
            """
            SELECT s.*
            FROM tracked_wallet_signal_events s
            WHERE s.input_mode = 'real_source'
              AND NOT EXISTS (
                SELECT 1
                FROM agent_trading_decisions d
                WHERE d.linked_tracked_wallet_signal_event_id = s.tracked_wallet_signal_event_id
              )
            ORDER BY s.observed_at DESC, s.created_at DESC
            LIMIT ?
            """,
            (limit,),
        )

    async def _review_one_signal(self, signal: dict[str, Any], *, settings: Any) -> str | None:
        """Review one signal event and record an AgentTradingDecision. Returns decision_id or None."""
        signal_id = str(signal["tracked_wallet_signal_event_id"])
        wallet = str(signal.get("wallet") or "")
        token_mint = str(signal.get("token_mint") or "")
        side = str(signal.get("side") or "")

        context = await self._build_context(signal)
        llm_response = await self._call_hermes_llm(context, settings=settings)
        if not llm_response:
            log.debug("hermes_review: LLM returned empty for signal %s", signal_id)
            return None

        decision_type = str(llm_response.get("decision_type") or "no_trade")
        if decision_type not in {"signal", "no_trade", "wait", "downgrade_wallet"}:
            decision_type = "no_trade"

        from walletscarper.stage2.hermes_integration.v2_tools import run_v2_tool

        decision_result = await run_v2_tool(
            "agent.record_trading_decision",
            {
                "decision_type": decision_type,
                "pre_action_reasoning": str(llm_response.get("pre_action_reasoning") or "")[:2000],
                "created_by_agent": "hermes_autonomous",
                "linked_tracked_wallet_signal_event_id": signal_id,
                "uncertainties": list(llm_response.get("uncertainties") or [])[:10],
                "evidence_refs": [f"tracked_wallet_signal_event:{signal_id}"],
                "quality_flags": [],
            },
            database=self.database,
        )

        if not decision_result.get("ok"):
            log.warning("hermes_review: agent.record_trading_decision failed: %s", decision_result.get("blocked_reason"))
            return None

        decision_id = str(decision_result.get("artifact_id") or "")
        log.info(
            "hermes_review: wallet=%s token=%s side=%s decision=%s id=%s",
            wallet[:8],
            token_mint[:8],
            side,
            decision_type,
            decision_id[:12],
        )

        if decision_type == "signal":
            await self._run_paper_path(decision_id, signal, llm_response)

        return decision_id

    async def _run_paper_path(self, decision_id: str, signal: dict[str, Any], llm_response: dict[str, Any]) -> None:
        """Run signal → risk → paper path after an AI 'signal' decision."""
        from walletscarper.stage2.hermes_integration.v2_tools import run_v2_tool

        token_mint = str(signal.get("token_mint") or "")
        wallet = str(signal.get("wallet") or "")

        # Create signal
        signal_result = await run_v2_tool(
            "signal.create",
            {
                "agent_trading_decision_id": decision_id,
                "token_mint": token_mint,
                "wallet": wallet,
                "side": str(signal.get("side") or "buy"),
                "signal_type": "wallet_follow",
                "source_refs": [f"tracked_wallet_signal_event:{signal['tracked_wallet_signal_event_id']}"],
                "confidence": str(llm_response.get("confidence") or "low"),
                "thesis": {
                    "signal_strength": str(llm_response.get("signal_strength") or "moderate"),
                    "wallet_assessment": str(llm_response.get("wallet_assessment") or "")[:500],
                    "token_assessment": str(llm_response.get("token_assessment") or "")[:500],
                },
            },
            database=self.database,
        )
        if not signal_result.get("ok"):
            log.debug("hermes_review: signal.create blocked: %s", signal_result.get("blocked_reason"))
            return

        signal_id = str(signal_result.get("artifact_id") or "")

        # Risk check (deterministic)
        risk_result = await run_v2_tool(
            "risk.check_entry",
            {
                "signal_id": signal_id,
                "risk_limit_snapshot_id": "",
                "config_snapshot_id": "",
            },
            database=self.database,
        )
        if not risk_result.get("ok") or not risk_result.get("risk_check", {}).get("passed"):
            log.debug(
                "hermes_review: risk.check_entry blocked: %s",
                risk_result.get("blocked_reason") or (risk_result.get("risk_check") or {}).get("veto_reason"),
            )
            return

        risk_id = str(risk_result.get("artifact_id") or "")

        # Paper order
        order_result = await run_v2_tool(
            "paper.create_order",
            {
                "signal_id": signal_id,
                "risk_check_id": risk_id,
                "agent_trading_decision_id": decision_id,
            },
            database=self.database,
        )
        if not order_result.get("ok"):
            log.debug("hermes_review: paper.create_order blocked: %s", order_result.get("blocked_reason"))
            return

        order_id = str(order_result.get("artifact_id") or "")

        # Paper fill
        fill_result = await run_v2_tool(
            "paper.simulate_fill",
            {
                "paper_order_id": order_id,
                "market_snapshot_id": "",
                "agent_trading_decision_id": decision_id,
            },
            database=self.database,
        )
        if fill_result.get("ok"):
            position_id = fill_result.get("paper_position_id")
            log.info("hermes_review: paper position opened: %s", position_id)

    async def _build_context(self, signal: dict[str, Any]) -> dict[str, Any]:
        """Build structured context dict for the LLM from signal + wallet + token data."""
        wallet = str(signal.get("wallet") or "")
        token_mint = str(signal.get("token_mint") or "")

        wallet_metrics = await self._latest_wallet_metrics(wallet)
        token_profile = await self._latest_token_profile(token_mint)
        wallet_outcome = await self._latest_wallet_outcome(wallet, token_mint)

        return {
            "signal": {
                "event_id": signal.get("tracked_wallet_signal_event_id"),
                "wallet": wallet,
                "token_mint": token_mint,
                "side": signal.get("side"),
                "observed_at": str(signal.get("observed_at") or ""),
                "source_name": signal.get("source_name"),
                "input_mode": signal.get("input_mode"),
                "data_sufficiency": signal.get("data_sufficiency"),
            },
            "wallet_metrics": wallet_metrics,
            "token_profile": token_profile,
            "wallet_token_outcome": wallet_outcome,
        }

    async def _call_hermes_llm(self, context: dict[str, Any], *, settings: Any) -> dict[str, Any] | None:
        """Call the configured LLM with Hermes system prompt + context. Returns parsed JSON or None."""
        import httpx

        system_prompt = _hermes_system_prompt(settings)
        user_message = (
            "Analyze this wallet signal event and decide whether to paper-trade follow it.\n\n"
            f"Context:\n{json.dumps(context, ensure_ascii=False, default=str, indent=2)}\n\n"
            f"{_HERMES_DECISION_SCHEMA}"
        )

        body = {
            "model": settings.hermes_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            "temperature": 0.2,
            "max_tokens": 600,
            "response_format": {"type": "json_object"},
        }
        headers = {
            "Authorization": f"Bearer {settings.hermes_api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "http://localhost",
            "X-Title": "TraderV1-Hermes",
        }

        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=45) as client:
                response = await client.post(settings.hermes_base_url.rstrip("/") + "/chat/completions", json=body, headers=headers)
            elapsed = time.perf_counter() - started
            if response.status_code == 429:
                log.warning("hermes_review: LLM rate limited (%.1fs)", elapsed)
                return None
            if response.status_code >= 400:
                log.warning("hermes_review: LLM HTTP %d (%.1fs)", response.status_code, elapsed)
                return None
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            parsed = json.loads(content)
            if not isinstance(parsed, dict):
                return None
            log.debug("hermes_review: LLM responded in %.1fs", elapsed)
            return parsed
        except (httpx.HTTPError, json.JSONDecodeError, KeyError, IndexError) as exc:
            log.warning("hermes_review: LLM call failed: %s", exc)
            return None

    async def _latest_wallet_metrics(self, wallet: str) -> dict[str, Any]:
        if not wallet:
            return {}
        row = await self.database.fetchone(
            """
            SELECT wallet, trade_count, closed_trade_count, realized_pnl_estimate,
                   net_pnl_estimate, win_rate_estimate, payoff_ratio,
                   evidence_quality, confidence, sample_size, calculated_at
            FROM wallet_metric_snapshots
            WHERE wallet = ?
            ORDER BY calculated_at DESC, created_at DESC
            LIMIT 1
            """,
            (wallet,),
        )
        if row:
            return dict(row)
        # Fallback to legacy wallet_scores
        try:
            from walletscarper.db import db as legacy_db

            legacy = await legacy_db.fetchone(
                """
                SELECT wallet, copyability_score, winrate, realized_pnl_usd, median_roi,
                       total_trades, bot_score, human_score, confidence
                FROM wallet_scores
                WHERE wallet = ?
                ORDER BY scored_at DESC
                LIMIT 1
                """,
                (wallet,),
            )
            if legacy:
                return {
                    "wallet": legacy["wallet"],
                    "copyability_score": legacy["copyability_score"],
                    "winrate": legacy["winrate"],
                    "realized_pnl_usd": legacy["realized_pnl_usd"],
                    "median_roi": legacy["median_roi"],
                    "total_trades": legacy["total_trades"],
                    "bot_score": legacy["bot_score"],
                    "confidence": legacy["confidence"],
                    "source": "legacy_wallet_scores",
                }
        except Exception:
            pass
        return {}

    async def _latest_token_profile(self, token_mint: str) -> dict[str, Any]:
        if not token_mint:
            return {}
        row = await self.database.fetchone(
            """
            SELECT token_mint, pool_address, symbol, name, market_cap, liquidity_usd,
                   volume_24h, txns_1h, evidence_quality, confidence, latest_observed_at
            FROM token_profiles
            WHERE token_mint = ?
            ORDER BY latest_observed_at DESC, created_at DESC
            LIMIT 1
            """,
            (token_mint,),
        )
        return dict(row) if row else {}

    async def _latest_wallet_outcome(self, wallet: str, token_mint: str) -> dict[str, Any]:
        if not wallet or not token_mint:
            return {}
        row = await self.database.fetchone(
            """
            SELECT wallet, token_mint, roi_estimate, roi_bucket, realized_pnl_estimate,
                   buy_count, sell_count, data_sufficiency, eligible_for_agent_review
            FROM wallet_token_outcomes
            WHERE wallet = ? AND token_mint = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (wallet, token_mint),
        )
        return dict(row) if row else {}


def _hermes_system_prompt(settings: Any) -> str:
    """Build the Hermes system prompt from config file or fallback."""
    try:
        from pathlib import Path

        prompt_path = Path("config/hermes/system-prompt.md")
        if prompt_path.exists():
            return prompt_path.read_text(encoding="utf-8")
    except Exception:
        pass
    return (
        "You are Hermes, Trading Research Director for TraderV1 Solana memecoin paper-trading. "
        "Analyze wallet signals and decide whether to follow them in paper trading. "
        "Be conservative. Prefer no_trade over risky signals. "
        "Treat historical wallet data as candidate evidence only."
    )
