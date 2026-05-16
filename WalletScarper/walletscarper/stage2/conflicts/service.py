from __future__ import annotations

from typing import Any

from walletscarper.stage2.db import Stage2Database
from walletscarper.stage2.monitoring import MonitoringService


class ConflictReviewService:
    """Conflict review facade with deterministic resolution precedence."""

    PRECEDENCE = ("risk_veto", "ledger_state", "deterministic_metrics", "source_quality", "narrative_review")

    def __init__(self, database: Stage2Database, monitoring: MonitoringService | None = None):
        self.database = database
        self.monitoring = monitoring or MonitoringService(database)

    async def create_conflict(
        self,
        *,
        subject_type: str,
        subject_id: str,
        conflicting_action: str,
        reason: str,
        involved_refs: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        return await self.monitoring.create_conflict_review(
            subject_type=subject_type,
            subject_id=subject_id,
            conflicting_action=conflicting_action,
            reason=reason,
            involved_refs=involved_refs or [],
            metadata=metadata or {},
        )

    async def resolve_conflict(
        self,
        conflict_review_id: str,
        *,
        resolver: str,
        winning_basis: str,
        resolution: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if winning_basis not in self.PRECEDENCE:
            raise ValueError(f"Unsupported conflict resolution basis: {winning_basis}")
        await self.monitoring.resolve_conflict_review(
            conflict_review_id,
            resolution=resolution or f"{winning_basis}_wins",
            resolver=resolver,
            metadata={"winning_basis": winning_basis, **(metadata or {})},
        )

