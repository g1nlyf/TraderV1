from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

BrowserExtractionStatus = Literal["success", "failed"]


class BrowserExtraction(BaseModel):
    browser_extraction_id: str
    source_url: str
    source_name: str | None = None
    raw_source_event_id: str | None = None
    extracted_at: datetime
    parser_name: str
    parser_version: str
    status: BrowserExtractionStatus
    raw_html_ref: str | None = None
    screenshot_ref: str | None = None
    snapshot_ref: str | None = None
    extracted_fields: dict[str, Any] = Field(default_factory=dict)
    confidence_score: float = 0
    degradation_reason: str | None = None
    quality_flags: list[str] = Field(default_factory=list)
    eligible_for_high_confidence_evaluation: bool = False
    created_at: datetime
