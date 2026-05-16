from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class AuditEvent(BaseModel):
    audit_event_id: str
    actor: str
    action: str
    entity_type: str
    entity_id: str
    created_at: datetime
    payload: dict[str, Any] = Field(default_factory=dict)
    diff: dict[str, Any] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    correlation_id: str | None = None
