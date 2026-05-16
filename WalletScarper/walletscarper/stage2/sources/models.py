from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

InterfaceKind = Literal["api", "rpc", "browser", "stream", "fixture", "legacy_mapped"]
SourceHealthStatus = Literal["healthy", "degraded", "unavailable", "unknown"]
IngestionRunStatus = Literal["running", "completed", "failed", "degraded", "aborted"]


class DataSource(BaseModel):
    data_source_id: str
    source_name: str
    source_type: str
    adapter_name: str
    reliability_tier: str = "unknown"
    interface_kind: InterfaceKind
    allowed_for_high_confidence_evaluation: bool
    status: str = "unknown"
    notes: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class SourceHealthSnapshot(BaseModel):
    source_health_snapshot_id: str
    data_source_id: str | None = None
    source_name: str
    observed_at: datetime
    status: SourceHealthStatus
    latency_ms: float | None = None
    error_rate: float | None = None
    rate_limit_state: dict[str, Any] = Field(default_factory=dict)
    last_successful_event_at: datetime | None = None
    degradation_reason: str | None = None
    confidence_impact: str = "unknown"
    metadata: dict[str, Any] = Field(default_factory=dict)


class IngestionRun(BaseModel):
    ingestion_run_id: str
    data_source_id: str | None = None
    source_name: str
    adapter_name: str
    started_at: datetime
    finished_at: datetime | None = None
    status: IngestionRunStatus = "running"
    events_seen: int = 0
    events_written: int = 0
    events_rejected: int = 0
    quality_summary: dict[str, Any] = Field(default_factory=dict)
    error_summary: dict[str, Any] = Field(default_factory=dict)
    correlation_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
