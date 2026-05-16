from __future__ import annotations

from typing import Protocol


class EvaluationService(Protocol):
    async def calculate_trade_outcome(self, *, position_id: str) -> str:
        """Calculate canonical paper TradeOutcome from fills/costs."""

    async def calculate_strategy_metrics(self, *, strategy_version_id: str) -> dict:
        """Future deterministic strategy metrics boundary."""

    async def produce_leaderboard(self, *, criteria_snapshot_id: str | None = None) -> list[dict]:
        """Future deterministic leaderboard boundary."""

    async def baseline_dashboard_snapshot(self) -> dict:
        """Return read-only Sprint 3 baseline workflow metrics."""
