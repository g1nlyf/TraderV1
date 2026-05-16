from __future__ import annotations

from datetime import datetime
from typing import Any

from walletscarper.stage2.clock import Clock, SystemClock, isoformat_utc
from walletscarper.stage2.db import Stage2Database
from walletscarper.stage2.db.json import dumps_json
from walletscarper.stage2.ids import new_id
from walletscarper.stage2.sources.models import IngestionRunStatus, InterfaceKind, SourceHealthStatus


class SourceRegistryRepository:
    def __init__(self, database: Stage2Database, clock: Clock | None = None):
        self.database = database
        self.clock = clock or SystemClock()

    async def register_data_source(
        self,
        *,
        source_name: str,
        source_type: str,
        adapter_name: str,
        interface_kind: InterfaceKind,
        reliability_tier: str = "unknown",
        allowed_for_high_confidence_evaluation: bool = False,
        status: str = "unknown",
        notes: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        existing = await self.get_data_source_by_name(source_name)
        now = isoformat_utc(self.clock.now())
        if existing:
            await self.database.execute(
                """
                UPDATE data_sources
                SET source_type = ?, adapter_name = ?, reliability_tier = ?, interface_kind = ?,
                    allowed_for_high_confidence_evaluation = ?, status = ?, notes = ?,
                    metadata_json = ?, updated_at = ?
                WHERE source_name = ?
                """,
                (
                    source_type,
                    adapter_name,
                    reliability_tier,
                    interface_kind,
                    1 if allowed_for_high_confidence_evaluation else 0,
                    status,
                    notes,
                    dumps_json(metadata or {}),
                    now,
                    source_name,
                ),
            )
            return str(existing["data_source_id"])
        data_source_id = new_id("data_source")
        await self.database.execute(
            """
            INSERT INTO data_sources(
              data_source_id, source_name, source_type, adapter_name, reliability_tier,
              interface_kind, allowed_for_high_confidence_evaluation, status, notes,
              metadata_json, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data_source_id,
                source_name,
                source_type,
                adapter_name,
                reliability_tier,
                interface_kind,
                1 if allowed_for_high_confidence_evaluation else 0,
                status,
                notes,
                dumps_json(metadata or {}),
                now,
                now,
            ),
        )
        return data_source_id

    async def get_data_source_by_name(self, source_name: str) -> dict[str, Any] | None:
        return await self.database.fetchone("SELECT * FROM data_sources WHERE source_name = ?", (source_name,))

    async def latest_health_snapshot(self, source_name: str) -> dict[str, Any] | None:
        return await self.database.fetchone(
            """
            SELECT * FROM source_health_snapshots
            WHERE source_name = ?
            ORDER BY observed_at DESC, source_health_snapshot_id DESC
            LIMIT 1
            """,
            (source_name,),
        )

    async def get_or_register_default(self, *, source_name: str, source_type: str, adapter_name: str) -> dict[str, Any]:
        existing = await self.get_data_source_by_name(source_name)
        if existing:
            return existing
        defaults = _source_defaults(source_name, source_type, adapter_name)
        await self.register_data_source(**defaults)
        created = await self.get_data_source_by_name(source_name)
        if not created:
            raise RuntimeError(f"failed to register data source {source_name}")
        return created

    async def record_health_snapshot(
        self,
        *,
        source_name: str,
        status: SourceHealthStatus,
        data_source_id: str | None = None,
        observed_at: datetime | None = None,
        latency_ms: float | None = None,
        error_rate: float | None = None,
        rate_limit_state: dict[str, Any] | None = None,
        last_successful_event_at: datetime | None = None,
        degradation_reason: str | None = None,
        confidence_impact: str = "unknown",
        metadata: dict[str, Any] | None = None,
    ) -> str:
        snapshot_id = new_id("source_health")
        await self.database.execute(
            """
            INSERT INTO source_health_snapshots(
              source_health_snapshot_id, data_source_id, source_name, observed_at, status,
              latency_ms, error_rate, rate_limit_state_json, last_successful_event_at,
              degradation_reason, confidence_impact, metadata_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                snapshot_id,
                data_source_id,
                source_name,
                isoformat_utc(observed_at or self.clock.now()),
                status,
                latency_ms,
                error_rate,
                dumps_json(rate_limit_state or {}),
                isoformat_utc(last_successful_event_at) if last_successful_event_at else None,
                degradation_reason,
                confidence_impact,
                dumps_json(metadata or {}),
            ),
        )
        return snapshot_id

    async def start_ingestion_run(
        self,
        *,
        source_name: str,
        adapter_name: str,
        data_source_id: str | None = None,
        started_at: datetime | None = None,
        correlation_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        run_id = new_id("ingestion_run")
        await self.database.execute(
            """
            INSERT INTO ingestion_runs(
              ingestion_run_id, data_source_id, source_name, adapter_name, started_at,
              status, correlation_id, metadata_json
            )
            VALUES (?, ?, ?, ?, ?, 'running', ?, ?)
            """,
            (
                run_id,
                data_source_id,
                source_name,
                adapter_name,
                isoformat_utc(started_at or self.clock.now()),
                correlation_id,
                dumps_json(metadata or {}),
            ),
        )
        return run_id

    async def finish_ingestion_run(
        self,
        *,
        ingestion_run_id: str,
        status: IngestionRunStatus,
        events_seen: int,
        events_written: int,
        events_rejected: int,
        quality_summary: dict[str, Any] | None = None,
        error_summary: dict[str, Any] | None = None,
        finished_at: datetime | None = None,
    ) -> None:
        await self.database.execute(
            """
            UPDATE ingestion_runs
            SET finished_at = ?, status = ?, events_seen = ?, events_written = ?,
                events_rejected = ?, quality_summary_json = ?, error_summary_json = ?
            WHERE ingestion_run_id = ?
            """,
            (
                isoformat_utc(finished_at or self.clock.now()),
                status,
                events_seen,
                events_written,
                events_rejected,
                dumps_json(quality_summary or {}),
                dumps_json(error_summary or {}),
                ingestion_run_id,
            ),
        )


def _source_defaults(source_name: str, source_type: str, adapter_name: str) -> dict[str, Any]:
    defaults: dict[str, dict[str, Any]] = {
        "dexscreener": {
            "interface_kind": "api",
            "reliability_tier": "structured_api",
            "allowed_for_high_confidence_evaluation": True,
            "notes": "Legacy-mapped structured HTTP market/profile payloads.",
        },
        "geckoterminal": {
            "interface_kind": "api",
            "reliability_tier": "structured_api",
            "allowed_for_high_confidence_evaluation": True,
            "notes": "Legacy-mapped structured HTTP pool/trade payloads.",
        },
        "dexpaprika": {
            "interface_kind": "api",
            "reliability_tier": "structured_api",
            "allowed_for_high_confidence_evaluation": True,
            "notes": "Legacy-mapped structured HTTP pool transaction payloads.",
        },
        "bitquery_corecast": {
            "interface_kind": "stream",
            "reliability_tier": "degraded_timestamp_provenance",
            "allowed_for_high_confidence_evaluation": False,
            "status": "degraded",
            "notes": "Legacy RawTrade currently uses weak timestamp provenance.",
        },
        "solana_rpc": {
            "interface_kind": "rpc",
            "reliability_tier": "structured_rpc",
            "allowed_for_high_confidence_evaluation": True,
            "notes": "Read-only Solana RPC transaction payloads.",
        },
        "stage2_quote_observer": {
            "interface_kind": "api",
            "reliability_tier": "stage2_owned_observation",
            "allowed_for_high_confidence_evaluation": True,
            "notes": "Stage 2-owned observation-only quote snapshots for shadow-readiness evidence.",
        },
    }
    chosen = defaults.get(
        source_name,
        {
            "interface_kind": "legacy_mapped",
            "reliability_tier": "unknown",
            "allowed_for_high_confidence_evaluation": False,
            "notes": "Unrecognized legacy-mapped source.",
        },
    )
    return {
        "source_name": source_name,
        "source_type": source_type,
        "adapter_name": adapter_name,
        "status": chosen.get("status", "unknown"),
        "metadata": {"registered_by": "stage2_evidence_normalizer"},
        **chosen,
    }
