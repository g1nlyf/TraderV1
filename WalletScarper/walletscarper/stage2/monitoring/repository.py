from __future__ import annotations

from typing import Any

from walletscarper.stage2.clock import Clock, SystemClock, isoformat_utc
from walletscarper.stage2.db import Stage2Database
from walletscarper.stage2.db.json import dumps_json
from walletscarper.stage2.ids import new_id


class MonitoringRepository:
    def __init__(self, database: Stage2Database, clock: Clock | None = None):
        self.database = database
        self.clock = clock or SystemClock()

    async def create_session(
        self,
        *,
        session_type: str,
        subject_type: str,
        subject_id: str,
        priority: int = 100,
        status: str = "pending",
        strategy_version_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        now = isoformat_utc(self.clock.now())
        session_id = new_id("monitoring_session")
        await self.database.execute(
            """
            INSERT INTO monitoring_sessions(
              monitoring_session_id, session_type, subject_type, subject_id,
              status, priority, strategy_version_id, started_at, updated_at, metadata_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                session_type,
                subject_type,
                subject_id,
                status,
                priority,
                strategy_version_id,
                now,
                now,
                dumps_json(metadata or {}),
            ),
        )
        return session_id

    async def create_conflict_review(
        self,
        *,
        subject_type: str,
        subject_id: str,
        conflicting_action: str,
        reason: str,
        audit_event_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        conflict_id = new_id("conflict_review")
        await self.database.execute(
            """
            INSERT INTO conflict_reviews(
              conflict_review_id, subject_type, subject_id, conflicting_action,
              reason, status, audit_event_id, created_at, metadata_json
            )
            VALUES (?, ?, ?, ?, ?, 'open', ?, ?, ?)
            """,
            (
                conflict_id,
                subject_type,
                subject_id,
                conflicting_action,
                reason,
                audit_event_id,
                isoformat_utc(self.clock.now()),
                dumps_json(metadata or {}),
            ),
        )
        return conflict_id
