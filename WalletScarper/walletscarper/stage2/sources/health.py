from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from walletscarper.stage2.clock import Clock, SystemClock, isoformat_utc
from walletscarper.stage2.db import Stage2Database
from walletscarper.stage2.sources.repository import SourceRegistryRepository


class SourceHealthService:
    def __init__(self, database: Stage2Database, clock: Clock | None = None, stale_after_seconds: int = 300):
        self.database = database
        self.clock = clock or SystemClock()
        self.stale_after_seconds = stale_after_seconds
        self.registry = SourceRegistryRepository(database, clock=self.clock)

    async def record_success(
        self,
        *,
        source_name: str,
        source_type: str,
        adapter_name: str,
        latency_ms: float | None = None,
        event_time: datetime | None = None,
        rate_limit_state: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        source = await self.registry.get_or_register_default(
            source_name=source_name,
            source_type=source_type,
            adapter_name=adapter_name,
        )
        now = self.clock.now()
        age = (now - event_time).total_seconds() if event_time else None
        stale = age is not None and age > self.stale_after_seconds
        status = "degraded" if stale else "healthy"
        reason = f"last successful event is stale by {int(age)} seconds" if stale and age is not None else None
        await self.database.execute(
            "UPDATE data_sources SET status = ?, updated_at = ? WHERE data_source_id = ?",
            (status, isoformat_utc(now), source["data_source_id"]),
        )
        return await self.registry.record_health_snapshot(
            source_name=source_name,
            data_source_id=str(source["data_source_id"]),
            status=status,
            observed_at=now,
            latency_ms=latency_ms,
            rate_limit_state=rate_limit_state,
            last_successful_event_at=event_time or now,
            degradation_reason=reason,
            confidence_impact="lower_confidence" if stale else "none",
            metadata=metadata,
        )

    async def record_failure(
        self,
        *,
        source_name: str,
        source_type: str,
        adapter_name: str,
        degradation_reason: str,
        unavailable: bool = True,
        latency_ms: float | None = None,
        error_rate: float | None = None,
        rate_limit_state: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        source = await self.registry.get_or_register_default(
            source_name=source_name,
            source_type=source_type,
            adapter_name=adapter_name,
        )
        status = "unavailable" if unavailable else "degraded"
        now = self.clock.now()
        latest = await self.registry.latest_health_snapshot(source_name)
        last_success = latest.get("last_successful_event_at") if latest else None
        await self.database.execute(
            "UPDATE data_sources SET status = ?, updated_at = ? WHERE data_source_id = ?",
            (status, isoformat_utc(now), source["data_source_id"]),
        )
        return await self.registry.record_health_snapshot(
            source_name=source_name,
            data_source_id=str(source["data_source_id"]),
            status=status,
            observed_at=now,
            latency_ms=latency_ms,
            error_rate=error_rate,
            rate_limit_state=rate_limit_state,
            last_successful_event_at=_parse_time(last_success),
            degradation_reason=degradation_reason,
            confidence_impact="prevents_normal_confidence" if unavailable else "lower_confidence",
            metadata=metadata,
        )

    async def quality_flags_for_source(self, source_name: str) -> list[str]:
        latest = await self.registry.latest_health_snapshot(source_name)
        if not latest:
            return []
        status = str(latest["status"])
        flags: list[str] = []
        if status == "degraded":
            flags.append("source_degraded")
        elif status == "unavailable":
            flags.append("source_unavailable")
        elif status == "unknown":
            flags.append("source_health_unknown")
        reason = str(latest.get("degradation_reason") or "")
        if "stale" in reason.lower():
            flags.append("stale_source_data")
        return flags


def _parse_time(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
