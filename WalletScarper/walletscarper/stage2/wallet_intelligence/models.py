from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class WalletTrade(BaseModel):
    wallet_trade_id: str
    wallet: str | None = None
    token_mint: str | None = None
    pool_address: str | None = None
    side: str | None = None
    token_amount: float | None = None
    quote_amount: float | None = None
    price_usd: float | None = None
    observed_at: datetime
    source_name: str
    raw_source_event_id: str
    market_snapshot_id: str | None = None
    fees_estimate: float | None = None
    confidence: str = "unknown"
    quality_flags: list[str] = Field(default_factory=list)
    reconstruction_method: str
    eligible_for_high_confidence_evaluation: bool = False
    created_at: datetime


class WalletMetricSnapshot(BaseModel):
    wallet_metric_snapshot_id: str
    wallet: str
    calculated_at: datetime
    trade_count: int = 0
    closed_trade_count: int = 0
    realized_pnl_estimate: float | None = None
    unrealized_inventory: dict[str, Any] = Field(default_factory=dict)
    net_pnl_estimate: float | None = None
    win_rate_estimate: float | None = None
    expectancy_estimate: float | None = None
    payoff_ratio: float | None = None
    average_win: float | None = None
    average_loss: float | None = None
    holding_time_summary: dict[str, Any] = Field(default_factory=dict)
    position_sizing_summary: dict[str, Any] = Field(default_factory=dict)
    sample_size: int = 0
    recency_seconds: float | None = None
    evidence_quality: str = "unknown"
    confidence: str = "unknown"
    quality_flags: list[str] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)
    candidate_evidence_only: bool = True
    created_at: datetime


class WalletProfile(BaseModel):
    wallet_profile_id: str
    wallet: str
    metrics_snapshot_id: str | None = None
    label: str
    label_confidence: str = "unknown"
    candidate_score: float | None = None
    evidence_quality: str = "unknown"
    degradation_status: str = "unknown"
    sample_size: int = 0
    recency_seconds: float | None = None
    source_refs: list[str] = Field(default_factory=list)
    explanation: dict[str, Any] = Field(default_factory=dict)
    included_reasons: list[str] = Field(default_factory=list)
    excluded_reasons: list[str] = Field(default_factory=list)
    last_updated_at: datetime
    candidate_evidence_only: bool = True
    created_at: datetime


class WalletCluster(BaseModel):
    wallet_cluster_id: str
    relation_type: str
    wallets: list[str] = Field(default_factory=list)
    token_mint: str | None = None
    evidence_refs: list[str] = Field(default_factory=list)
    confidence: str = "unknown"
    quality_flags: list[str] = Field(default_factory=list)
    flags: list[str] = Field(default_factory=list)
    created_at: datetime


class WalletTokenOutcome(BaseModel):
    wallet_token_outcome_id: str
    token_trade_corpus_id: str | None = None
    wallet: str
    token_mint: str
    pool_address: str | None = None
    buy_count: int = 0
    sell_count: int = 0
    realized_pnl_estimate: float | None = None
    roi_estimate: float | None = None
    roi_bucket: str | None = None
    notional_usd: float | None = None
    entry_time: datetime | None = None
    exit_time: datetime | None = None
    holding_seconds: float | None = None
    data_sufficiency: str = "insufficient"
    source_refs: list[str] = Field(default_factory=list)
    quality_flags: list[str] = Field(default_factory=list)
    eligible_for_agent_review: bool = False
    calculated_by_service: str = "wallet_token_outcome_service"
    created_at: datetime


class AgentWalletReview(BaseModel):
    agent_wallet_review_id: str
    wallet: str
    metrics_snapshot_id: str | None = None
    decision: str
    agent_rating: float | None = None
    copyability_rating: float | None = None
    pnl_quality: str = "unknown"
    winrate_quality: str = "unknown"
    behavior_profile: dict[str, Any] = Field(default_factory=dict)
    why_yes: list[str] = Field(default_factory=list)
    why_no: list[str] = Field(default_factory=list)
    demotion_triggers: list[str] = Field(default_factory=list)
    data_sufficiency: str
    observed_behavior: dict[str, Any] = Field(default_factory=dict)
    inferred_behavior: dict[str, Any] = Field(default_factory=dict)
    unknowns: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    created_by_agent: str
    created_at: datetime


class WalletForwardContribution(BaseModel):
    wallet_forward_contribution_id: str
    wallet: str
    strategy_version_id: str | None = None
    window_start: datetime | None = None
    window_end: datetime | None = None
    signal_count: int = 0
    paper_trade_count: int = 0
    net_pnl: float | None = None
    expectancy: float | None = None
    win_rate: float | None = None
    max_drawdown: float | None = None
    quality_flags: list[str] = Field(default_factory=list)
    calculated_by_service: str = "wallet_forward_contribution_service"
    calculated_at: datetime
