from __future__ import annotations

from typing import Protocol


class PaperTradingService(Protocol):
    async def create_paper_order(
        self,
        *,
        signal_id: str,
        risk_check_id: str,
        side: str = "buy",
        intended_size: float | None = None,
        intended_price_ref: str | None = None,
    ) -> str:
        """Create a paper order from a signal and passed entry risk check."""

    async def simulate_entry_fill(self, *, paper_order_id: str, market_snapshot_id: str) -> str:
        """Simulate a conservative paper-only entry fill."""

    async def open_position_from_fill(self, *, paper_fill_id: str) -> str:
        """Open a paper position from a successful entry fill."""

    async def create_exit_decision(self, *, position_id: str, payload: dict) -> str:
        """Create a timestamped exit decision before any exit fill."""

    async def execute_paper_exit(self, *, exit_decision_id: str, risk_check_id: str) -> str:
        """Create a conservative paper-only exit fill for an approved exit decision."""
