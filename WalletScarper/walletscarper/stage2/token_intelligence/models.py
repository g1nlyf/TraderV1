from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class TokenProfile(BaseModel):
    token_profile_id: str
    token_candidate_id: str | None = None
    token_mint: str | None = None
    pool_address: str | None = None
    chain: str | None = None
    ecosystem: str | None = None
    symbol: str | None = None
    name: str | None = None
    discovered_at: datetime | None = None
    latest_observed_at: datetime
    age_seconds: float | None = None
    market_cap: float | None = None
    fdv: float | None = None
    liquidity_usd: float | None = None
    volume_24h: float | None = None
    txns_1h: int | None = None
    holder_count: int | None = None
    top_holder_concentration: float | None = None
    source_refs: list[str] = Field(default_factory=list)
    evidence_quality: str = "unknown"
    confidence: str = "unknown"
    quality_flags: list[str] = Field(default_factory=list)
    degradation_status: str = "unknown"
    eligible_for_high_confidence_evaluation: bool = False
    created_at: datetime


class TokenTriageDecision(BaseModel):
    token_triage_decision_id: str
    token_profile_id: str
    token_candidate_id: str | None = None
    token_triage_config_id: str
    decision_status: str
    reasons: list[str] = Field(default_factory=list)
    bucket_assignments: dict[str, Any] = Field(default_factory=dict)
    no_trade_reason: str | None = None
    confidence: str = "unknown"
    quality_flags: list[str] = Field(default_factory=list)
    created_at: datetime


class TokenAgentDecision(BaseModel):
    token_agent_decision_id: str
    token_profile_id: str | None = None
    token_mint: str | None = None
    pool_address: str | None = None
    decision_type: str
    reasons: list[str] = Field(default_factory=list)
    uncertainties: list[str] = Field(default_factory=list)
    requested_tool_calls: list[Any] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    confidence: str = "unknown"
    expires_at: datetime | None = None
    created_by_agent: str
    created_at: datetime


class TokenTradeCorpus(BaseModel):
    token_trade_corpus_id: str
    token_mint: str
    pool_address: str | None = None
    window_start: datetime | None = None
    window_end: datetime | None = None
    source_names: list[str] = Field(default_factory=list)
    trade_count: int = 0
    wallet_count: int = 0
    coverage_estimate: float = 0
    data_sufficiency: str = "insufficient"
    quality_flags: list[str] = Field(default_factory=list)
    raw_event_refs: list[str] = Field(default_factory=list)
    created_by_service: str = "token_trade_corpus_service"
    created_at: datetime
