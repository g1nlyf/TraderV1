from __future__ import annotations

from typing import Any

from walletscarper.stage2.clock import Clock, SystemClock, isoformat_utc
from walletscarper.stage2.db import Stage2Database
from walletscarper.stage2.db.json import dumps_json
from walletscarper.stage2.ids import new_id


class AuditLog:
    def __init__(self, database: Stage2Database, clock: Clock | None = None):
        self.database = database
        self.clock = clock or SystemClock()

    async def append(
        self,
        *,
        actor: str,
        action: str,
        entity_type: str,
        entity_id: str,
        payload: dict[str, Any] | None = None,
        diff: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        correlation_id: str | None = None,
    ) -> str:
        event_id = new_id("audit_event")
        await self.database.execute(
            """
            INSERT INTO audit_events(
              audit_event_id, actor, action, entity_type, entity_id, created_at,
              payload_json, diff_json, metadata_json, correlation_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                actor,
                action,
                entity_type,
                entity_id,
                isoformat_utc(self.clock.now()),
                dumps_json(payload or {}),
                dumps_json(diff) if diff is not None else None,
                dumps_json(metadata or {}),
                correlation_id,
            ),
        )
        return event_id
