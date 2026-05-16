from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class RawSourceEvent(BaseModel):
    raw_source_event_id: str
    source_name: str
    source_type: str
    external_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    observed_at: datetime
    ingested_at: datetime
    confidence: str = "unknown"
    quality_metadata: dict[str, Any] = Field(default_factory=dict)
