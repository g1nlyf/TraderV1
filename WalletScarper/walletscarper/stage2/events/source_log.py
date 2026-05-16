from __future__ import annotations

from datetime import datetime
from typing import Any

from walletscarper.stage2.clock import Clock, SystemClock, isoformat_utc
from walletscarper.stage2.db import Stage2Database
from walletscarper.stage2.db.json import dumps_json
from walletscarper.stage2.ids import new_id


class RawSourceEventLog:
    def __init__(self, database: Stage2Database, clock: Clock | None = None):
        self.database = database
        self.clock = clock or SystemClock()

    async def append(
        self,
        *,
        source_name: str,
        source_type: str,
        payload: dict[str, Any],
        observed_at: datetime | None = None,
        external_id: str | None = None,
        confidence: str = "unknown",
        quality_metadata: dict[str, Any] | None = None,
    ) -> str:
        now = self.clock.now()
        event_id = new_id("raw_source_event")
        await self.database.execute(
            """
            INSERT INTO raw_source_events(
              raw_source_event_id, source_name, source_type, external_id, payload_json,
              observed_at, ingested_at, confidence, quality_metadata_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                source_name,
                source_type,
                external_id,
                dumps_json(payload),
                isoformat_utc(observed_at or now),
                isoformat_utc(now),
                confidence,
                dumps_json(quality_metadata or {}),
            ),
        )
        return event_id
