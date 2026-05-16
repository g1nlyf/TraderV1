from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

CandidateStatus = Literal["discovered", "triage_pending", "watching", "archived", "rejected"]


class TokenCandidate(BaseModel):
    token_candidate_id: str
    token_mint: str | None = None
    chain: str | None = None
    ecosystem: str | None = None
    symbol: str | None = None
    name: str | None = None
    discovered_at: datetime
    data_source_id: str | None = None
    source_names: list[str] = Field(default_factory=list)
    raw_event_refs: list[str] = Field(default_factory=list)
    confidence: str = "unknown"
    quality_flags: list[str] = Field(default_factory=list)
    candidate_status: CandidateStatus = "discovered"
    rejection_reason: str | None = None
    eligible_for_high_confidence_evaluation: bool = False
    created_at: datetime


class MarketSnapshot(BaseModel):
    market_snapshot_id: str
    token_candidate_id: str | None = None
    token_mint: str | None = None
    pool_address: str | None = None
    chain: str | None = None
    observed_at: datetime
    data_source_id: str | None = None
    source_name: str
    raw_source_event_id: str
    price_usd: float | None = None
    liquidity_usd: float | None = None
    volume_5m: float | None = None
    volume_1h: float | None = None
    volume_6h: float | None = None
    volume_24h: float | None = None
    market_cap: float | None = None
    fdv: float | None = None
    txns_5m: int | None = None
    txns_1h: int | None = None
    holder_count: int | None = None
    confidence: str = "unknown"
    quality_flags: list[str] = Field(default_factory=list)
    eligible_for_high_confidence_evaluation: bool = False
    created_at: datetime


class NormalizationResult(BaseModel):
    raw_source_event_id: str
    token_candidate_ids: list[str] = Field(default_factory=list)
    market_snapshot_ids: list[str] = Field(default_factory=list)
    evidence_ref_ids: list[str] = Field(default_factory=list)
    quality_flags: list[str] = Field(default_factory=list)
