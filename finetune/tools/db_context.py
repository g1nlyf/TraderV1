"""
Read-only context queries for signal review.
Used by teacher_service and review_context CLI.
No WalletScarper imports — pure aiosqlite.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import aiosqlite

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "WalletScarper" / "data" / "stage2_foundation.sqlite3"
LEGACY_DB_PATH = ROOT / "WalletScarper" / "data" / "walletscarper.sqlite3"


def _loads(raw: Any) -> Any:
    if not raw or not isinstance(raw, str):
        return raw
    try:
        return json.loads(raw)
    except Exception:
        return raw


async def get_pending_signals(limit: int = 20) -> list[dict]:
    """All real_source signals without a recorded decision."""
    async with aiosqlite.connect(str(DB_PATH)) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            """
            SELECT
                e.tracked_wallet_signal_event_id,
                e.wallet,
                e.token_mint,
                e.side,
                e.observed_at,
                e.source_name,
                e.data_sufficiency,
                e.input_mode,
                (strftime('%s','now') - strftime('%s', e.observed_at)) / 60 AS age_minutes
            FROM tracked_wallet_signal_events e
            WHERE e.input_mode = 'real_source'
              AND NOT EXISTS (
                SELECT 1 FROM agent_trading_decisions d
                WHERE d.linked_tracked_wallet_signal_event_id = e.tracked_wallet_signal_event_id
              )
            ORDER BY e.observed_at DESC
            LIMIT ?
            """,
            (limit,),
        )
        return [dict(r) for r in await cur.fetchall()]


async def get_all_signals_with_decisions(limit: int = 100) -> list[dict]:
    """All real_source signals with their decisions (for context/training)."""
    async with aiosqlite.connect(str(DB_PATH)) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            """
            SELECT
                e.*,
                d.decision_type,
                d.pre_action_reasoning,
                d.created_at AS decision_at,
                d.agent_trading_decision_id
            FROM tracked_wallet_signal_events e
            LEFT JOIN agent_trading_decisions d
              ON d.linked_tracked_wallet_signal_event_id = e.tracked_wallet_signal_event_id
            WHERE e.input_mode = 'real_source'
            ORDER BY e.observed_at DESC
            LIMIT ?
            """,
            (limit,),
        )
        return [dict(r) for r in await cur.fetchall()]


async def get_signal_full_context(signal_id: str) -> dict:
    """Full context for a single signal: event + wallet metrics + token profile + portfolio state."""
    async with aiosqlite.connect(str(DB_PATH)) as db:
        db.row_factory = aiosqlite.Row

        # Signal event
        cur = await db.execute(
            "SELECT * FROM tracked_wallet_signal_events WHERE tracked_wallet_signal_event_id = ?",
            (signal_id,),
        )
        event = dict(await cur.fetchone() or {})

        if not event:
            return {"error": f"Signal {signal_id} not found"}

        wallet = event.get("wallet", "")
        token_mint = event.get("token_mint", "")

        # Wallet metrics
        wallet_metrics = None
        if wallet:
            cur = await db.execute(
                """
                SELECT * FROM wallet_metric_snapshots
                WHERE wallet = ?
                ORDER BY calculated_at DESC, created_at DESC LIMIT 1
                """,
                (wallet,),
            )
            row = await cur.fetchone()
            if row:
                wallet_metrics = dict(row)
                for k in ("holding_time_summary_json", "position_sizing_summary_json",
                          "source_refs_json", "quality_flags_json"):
                    if k in wallet_metrics:
                        wallet_metrics[k.replace("_json", "")] = _loads(wallet_metrics.pop(k))

        # Wallet agent review (if any)
        wallet_review = None
        if wallet:
            cur = await db.execute(
                """
                SELECT * FROM agent_wallet_reviews
                WHERE wallet = ?
                ORDER BY created_at DESC LIMIT 1
                """,
                (wallet,),
            )
            row = await cur.fetchone()
            if row:
                wallet_review = dict(row)
                for k in ("why_yes_json", "why_no_json", "unknowns_json",
                          "demotion_triggers_json", "behavior_profile_json"):
                    if k in wallet_review:
                        wallet_review[k.replace("_json", "")] = _loads(wallet_review.pop(k))

        # Token profile
        token_profile = None
        if token_mint:
            cur = await db.execute(
                """
                SELECT * FROM token_profiles
                WHERE token_mint = ?
                ORDER BY latest_observed_at DESC, created_at DESC LIMIT 1
                """,
                (token_mint,),
            )
            row = await cur.fetchone()
            if row:
                token_profile = dict(row)
                for k in ("quality_flags_json", "source_refs_json"):
                    if k in token_profile:
                        token_profile[k.replace("_json", "")] = _loads(token_profile.pop(k))

        # Portfolio state
        cur = await db.execute(
            "SELECT COUNT(*) AS n FROM paper_positions WHERE status = 'open'"
        )
        open_positions = (await cur.fetchone() or {})["n"]

        cur = await db.execute(
            "SELECT COUNT(*) AS n FROM agent_trading_decisions WHERE created_at >= datetime('now', '-1 hour')"
        )
        decisions_1h = (await cur.fetchone() or {})["n"]

        # Recent decisions on this wallet
        recent_wallet_decisions: list[dict] = []
        if wallet:
            cur = await db.execute(
                """
                SELECT d.decision_type, d.pre_action_reasoning, d.created_at
                FROM agent_trading_decisions d
                JOIN tracked_wallet_signal_events e
                  ON d.linked_tracked_wallet_signal_event_id = e.tracked_wallet_signal_event_id
                WHERE e.wallet = ?
                ORDER BY d.created_at DESC LIMIT 5
                """,
                (wallet,),
            )
            recent_wallet_decisions = [dict(r) for r in await cur.fetchall()]

        return {
            "signal_event": event,
            "wallet_metrics": wallet_metrics,
            "wallet_review": wallet_review,
            "token_profile": token_profile,
            "portfolio_state": {
                "open_positions": open_positions,
                "decisions_last_hour": decisions_1h,
            },
            "recent_wallet_decisions": recent_wallet_decisions,
        }


async def get_open_positions_summary() -> list[dict]:
    async with aiosqlite.connect(str(DB_PATH)) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            """
            SELECT position_id, token_id, size, cost_basis, opened_at, status
            FROM paper_positions WHERE status = 'open'
            ORDER BY opened_at DESC
            """
        )
        return [dict(r) for r in await cur.fetchall()]


async def get_closed_positions_without_outcome_label(limit: int = 50) -> list[dict]:
    """Closed positions that don't yet have a training quality label."""
    async with aiosqlite.connect(str(DB_PATH)) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            """
            SELECT
                p.position_id,
                p.token_id,
                p.cost_basis,
                p.size,
                p.opened_at,
                p.closed_at,
                o.pnl_usd,
                o.pnl_pct,
                o.trade_outcome_id,
                d.agent_trading_decision_id,
                d.decision_type,
                d.pre_action_reasoning,
                e.tracked_wallet_signal_event_id,
                e.wallet,
                e.token_mint
            FROM paper_positions p
            JOIN paper_fills f ON f.paper_fill_id = (
                SELECT pf.paper_fill_id FROM paper_fills pf
                WHERE pf.position_id = p.position_id
                AND pf.side = 'buy'
                ORDER BY pf.fill_time ASC LIMIT 1
            )
            JOIN paper_orders po ON po.paper_order_id = f.paper_order_id
            JOIN signals s ON s.signal_id = po.signal_id
            JOIN agent_trading_decisions d ON d.linked_signal_id = s.signal_id
               OR d.agent_trading_decision_id IN (
                 SELECT da.agent_trading_decision_id FROM decision_artifacts da
                 WHERE da.artifact_type = 'signal' AND da.artifact_id = s.signal_id
               )
            LEFT JOIN tracked_wallet_signal_events e
              ON d.linked_tracked_wallet_signal_event_id = e.tracked_wallet_signal_event_id
            LEFT JOIN trade_outcomes o ON o.position_id = p.position_id
            WHERE p.status = 'closed'
              AND o.trade_outcome_id IS NOT NULL
            ORDER BY p.closed_at DESC
            LIMIT ?
            """,
            (limit,),
        )
        return [dict(r) for r in await cur.fetchall()]
