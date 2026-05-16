from __future__ import annotations

from datetime import datetime
from typing import Any

from walletscarper.stage2.clock import Clock, SystemClock, isoformat_utc
from walletscarper.stage2.db import Stage2Database
from walletscarper.stage2.ids import new_id


class OutcomeRejected(ValueError):
    pass


class DeterministicEvaluationService:
    """Deterministic Sprint 3 evaluation boundary for canonical paper outcomes."""

    def __init__(self, database: Stage2Database, clock: Clock | None = None):
        self.database = database
        self.clock = clock or SystemClock()

    async def calculate_trade_outcome(self, *, position_id: str) -> str:
        existing = await self.database.fetchone("SELECT outcome_id FROM trade_outcomes WHERE position_id = ?", (position_id,))
        if existing:
            return str(existing["outcome_id"])
        position = await self.database.fetchone("SELECT * FROM paper_positions WHERE position_id = ?", (position_id,))
        if not position:
            raise OutcomeRejected(f"PaperPosition not found: {position_id}")
        entry_fill = await self.database.fetchone(
            "SELECT * FROM paper_fills WHERE paper_fill_id = ?",
            (position["entry_fill_id"],),
        )
        if not entry_fill or entry_fill.get("failed_fill_reason") or entry_fill.get("fill_price") is None:
            raise OutcomeRejected("TradeOutcome requires a successful entry fill.")
        exit_bundle = await self._exit_bundle(position_id)
        if not exit_bundle:
            raise OutcomeRejected("TradeOutcome requires a successful exit fill and ExitDecision.")
        exit_fill = exit_bundle["fill"]
        exit_decision = exit_bundle["exit_decision"]
        if exit_fill.get("failed_fill_reason") or exit_fill.get("fill_price") is None:
            raise OutcomeRejected("TradeOutcome requires a successful exit fill.")
        entry_time = _parse_time(entry_fill["fill_time"])
        exit_time = _parse_time(exit_fill["fill_time"])
        if not entry_time or not exit_time:
            raise OutcomeRejected("TradeOutcome requires timestamped fills.")
        if _parse_time(exit_decision["created_at"]) and _parse_time(exit_decision["created_at"]) > exit_time:
            raise OutcomeRejected("ExitDecision cannot be after exit fill.")

        size = float(position["size"])
        gross = (float(exit_fill["fill_price"]) - float(entry_fill["fill_price"])) * size
        fees = float(entry_fill["fees"] or 0) + float(exit_fill["fees"] or 0)
        slippage = float(entry_fill["slippage"] or 0) + float(exit_fill["slippage"] or 0)
        net = gross - fees
        duration = max(0.0, (exit_time - entry_time).total_seconds())
        max_drawdown = min(0.0, net)
        outcome_id = new_id("trade_outcome")
        await self.database.execute(
            """
            INSERT INTO trade_outcomes(
              outcome_id, position_id, exit_decision_id, gross_pnl, net_pnl,
              fees, slippage, duration_seconds, max_drawdown, calculated_at,
              calculated_by_service
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'evaluation_service')
            """,
            (
                outcome_id,
                position_id,
                exit_decision["exit_decision_id"],
                gross,
                net,
                fees,
                slippage,
                duration,
                max_drawdown,
                isoformat_utc(self.clock.now()),
            ),
        )
        return outcome_id

    async def calculate_strategy_metrics(self, *, strategy_version_id: str) -> dict[str, Any]:
        rows = await self.database.fetchall(
            """
            SELECT o.*
            FROM trade_outcomes o
            JOIN paper_positions p ON p.position_id = o.position_id
            WHERE p.strategy_version_id = ?
            """,
            (strategy_version_id,),
        )
        count = len(rows)
        net = sum(float(row["net_pnl"]) for row in rows)
        return {
            "strategy_version_id": strategy_version_id,
            "closed_trade_count": count,
            "realized_net_pnl": net,
            "expectancy": net / count if count else None,
            "promotion_decision": "not_implemented_sprint3",
        }

    async def produce_leaderboard(self, *, criteria_snapshot_id: str | None = None) -> list[dict[str, Any]]:
        from walletscarper.stage2.strategy import StrategyResearchService

        return await StrategyResearchService(self.database, clock=self.clock).leaderboard_v1(
            promotion_criteria_snapshot_id=criteria_snapshot_id
        )

    async def baseline_dashboard_snapshot(self) -> dict[str, Any]:
        counts = await self.database.table_counts(
            [
                "signals",
                "no_trade_signals",
                "risk_checks",
                "paper_orders",
                "paper_fills",
                "paper_positions",
                "trade_outcomes",
                "rejected_trade_logs",
                "missed_opportunity_logs",
            ]
        )
        risk_rows = await self.database.fetchall("SELECT passed FROM risk_checks")
        fills = await self.database.fetchall("SELECT failed_fill_reason FROM paper_fills")
        outcomes = await self.database.fetchall("SELECT net_pnl, max_drawdown FROM trade_outcomes")
        open_positions = await self.database.fetchall(
            """
            SELECT p.position_id
            FROM paper_positions p
            LEFT JOIN trade_outcomes o ON o.position_id = p.position_id
            WHERE o.outcome_id IS NULL
            """
        )
        closed = len(outcomes)
        net = sum(float(row["net_pnl"]) for row in outcomes)
        warnings: list[str] = []
        if counts["signals"] and not counts["trade_outcomes"]:
            warnings.append("signals_exist_without_closed_outcomes")
        if any(row.get("failed_fill_reason") for row in fills):
            warnings.append("failed_fills_present")
        return {
            "signals": counts["signals"],
            "no_trade_signals": counts["no_trade_signals"],
            "risk_approved": sum(1 for row in risk_rows if int(row["passed"]) == 1),
            "risk_vetoed": sum(1 for row in risk_rows if int(row["passed"]) == 0),
            "paper_orders": counts["paper_orders"],
            "successful_fills": sum(1 for row in fills if not row.get("failed_fill_reason")),
            "failed_fills": sum(1 for row in fills if row.get("failed_fill_reason")),
            "open_positions": len(open_positions),
            "closed_positions": closed,
            "realized_net_pnl": net,
            "expectancy": net / closed if closed else None,
            "basic_drawdown": min((float(row["max_drawdown"]) for row in outcomes), default=0.0),
            "rejected_trade_logs": counts["rejected_trade_logs"],
            "missed_opportunity_logs": counts["missed_opportunity_logs"],
            "warnings": warnings,
            "strategy_promotion": "not_implemented_sprint3",
        }

    async def _exit_bundle(self, position_id: str) -> dict[str, Any] | None:
        rows = await self.database.fetchall(
            """
            SELECT ed.exit_decision_id, pf.paper_fill_id
            FROM exit_decisions ed
            JOIN risk_checks rc
              ON rc.subject_type = 'exit_decision'
             AND rc.subject_id = ed.exit_decision_id
             AND rc.check_scope = 'exit'
            JOIN paper_orders po ON po.risk_check_id = rc.risk_check_id
            JOIN paper_fills pf ON pf.paper_order_id = po.paper_order_id
            WHERE ed.position_id = ?
            ORDER BY pf.fill_time DESC, pf.paper_fill_id DESC
            LIMIT 1
            """,
            (position_id,),
        )
        if not rows:
            return None
        row = rows[0]
        exit_decision = await self.database.fetchone(
            "SELECT * FROM exit_decisions WHERE exit_decision_id = ?",
            (row["exit_decision_id"],),
        )
        fill = await self.database.fetchone("SELECT * FROM paper_fills WHERE paper_fill_id = ?", (row["paper_fill_id"],))
        if not exit_decision or not fill:
            return None
        return {"exit_decision": exit_decision, "fill": fill}


Sprint1EvaluationService = DeterministicEvaluationService


def _parse_time(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
