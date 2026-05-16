from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class MonitoringSession(BaseModel):
    monitoring_session_id: str
    session_type: str
    subject_type: str
    subject_id: str
    status: str = "pending"
    priority: int = 100
    strategy_version_id: str | None = None
    started_at: datetime
    updated_at: datetime
    stopped_at: datetime | None = None
    stop_reason: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ConflictReview(BaseModel):
    conflict_review_id: str
    subject_type: str
    subject_id: str
    conflicting_action: str
    reason: str
    status: str = "open"
    resolution: str | None = None
    audit_event_id: str | None = None
    created_at: datetime
    resolved_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
