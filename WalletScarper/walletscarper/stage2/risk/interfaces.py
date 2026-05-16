from __future__ import annotations

from typing import Protocol


class RiskService(Protocol):
    async def request_entry_risk_check(
        self,
        *,
        signal_id: str,
        market_snapshot_id: str | None,
        risk_limit_snapshot_id: str,
        config_snapshot_id: str,
    ) -> str:
        """Request a deterministic entry risk check for a signal."""

    async def run_entry_risk_check(
        self,
        *,
        signal_id: str,
        market_snapshot_id: str | None,
        risk_limit_snapshot_id: str,
        config_snapshot_id: str,
    ) -> str:
        """Create an authoritative deterministic entry RiskCheck."""

    async def request_exit_risk_check(
        self,
        *,
        exit_decision_id: str,
        market_snapshot_id: str | None,
        risk_limit_snapshot_id: str,
        config_snapshot_id: str,
    ) -> str:
        """Request a deterministic exit risk check for an exit decision."""

    async def run_exit_risk_check(
        self,
        *,
        exit_decision_id: str,
        market_snapshot_id: str | None,
        risk_limit_snapshot_id: str,
        config_snapshot_id: str,
    ) -> str:
        """Create an authoritative deterministic exit RiskCheck."""

    async def run_position_monitoring_risk_check(
        self,
        *,
        position_id: str,
        market_snapshot_id: str | None,
        risk_limit_snapshot_id: str,
        config_snapshot_id: str,
    ) -> str:
        """Create an authoritative deterministic position-monitoring RiskCheck."""

    async def retrieve_risk_result(self, risk_check_id: str) -> dict | None:
        """Return a stored authoritative risk check."""
