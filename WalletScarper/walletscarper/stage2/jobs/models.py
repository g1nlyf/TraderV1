from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class Job(BaseModel):
    job_id: str
    job_type: str
    worker_type: str | None = None
    target_ref: str | None = None
    status: str
    priority: int = 100
    payload: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    attempts: int = 0
    max_attempts: int = 3
    scheduled_at: datetime
    created_at: datetime
    updated_at: datetime
    last_error: str | None = None


class WorkerLease(BaseModel):
    worker_lease_id: str
    job_id: str
    worker_id: str
    lease_acquired_at: datetime
    lease_expires_at: datetime
    heartbeat_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)
