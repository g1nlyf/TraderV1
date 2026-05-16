from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class RawSourceEventDraft(BaseModel):
    source_name: str
    source_type: str
    external_id: str | None = None
    observed_at: datetime | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    provenance: dict[str, Any] = Field(default_factory=dict)
    confidence: str = "unknown"
    extraction_method: str
    quality_flags: list[str] = Field(default_factory=list)
    raw_adapter_name: str

    def quality_metadata(self) -> dict[str, Any]:
        return {
            "provenance": self.provenance,
            "extraction_method": self.extraction_method,
            "quality_flags": self.quality_flags,
            "raw_adapter_name": self.raw_adapter_name,
            "mapped_by": "walletscarper.stage2.legacy_ingestion",
        }
