from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

CheckScope = Literal["entry", "exit", "position_monitoring"]
RiskSubjectType = Literal["signal", "paper_order", "paper_position", "exit_decision"]
OrderSide = Literal["buy", "sell"]


class StrategyVersion(BaseModel):
    strategy_version_id: str
    strategy_config_snapshot_id: str
    parent_strategy_version_id: str | None = None
    mutation_proposal_id: str | None = None
    rules: dict[str, Any] = Field(default_factory=dict)
    params: dict[str, Any] = Field(default_factory=dict)
    agents: list[str] = Field(default_factory=list)
    created_at: datetime
    status: str = "experimental"


class Signal(BaseModel):
    signal_id: str
    created_at: datetime
    data_as_of: datetime
    token_id: str
    strategy_version_id: str
    strategy_config_snapshot_id: str
    promotion_criteria_snapshot_id: str | None = None
    source_refs: list[str] = Field(default_factory=list)
    confidence: str = "unknown"
    thesis_ref: str | None = None
    invalidation_condition: str
    expected_holding_time: str
    estimated_risk: dict[str, Any] = Field(default_factory=dict)
    estimated_slippage: float | None = None
    status: str = "candidate"


class NoTradeSignal(BaseModel):
    no_trade_signal_id: str
    created_at: datetime
    data_as_of: datetime
    token_id: str | None = None
    token_profile_id: str | None = None
    strategy_version_id: str
    strategy_config_snapshot_id: str
    promotion_criteria_snapshot_id: str | None = None
    reason: str
    source_refs: list[str] = Field(default_factory=list)
    confidence: str = "unknown"
    quality_flags: list[str] = Field(default_factory=list)
    observe_later: bool = False
    status: str = "logged"


class TradeThesis(BaseModel):
    thesis_id: str
    signal_id: str
    entry_reason: str
    exit_plan: str
    expected_holding_time: str
    proof_wrong: str
    context_snapshot_id: str | None = None
    created_at: datetime


class RiskCheck(BaseModel):
    risk_check_id: str
    check_scope: CheckScope
    subject_type: RiskSubjectType
    subject_id: str
    market_snapshot_id: str | None = None
    risk_limit_snapshot_id: str
    config_snapshot_id: str
    data_as_of: datetime
    passed: bool
    veto_reason: str | None = None
    warnings: list[str] = Field(default_factory=list)
    created_at: datetime
    created_by_service: str = "risk_service"


class PaperOrder(BaseModel):
    paper_order_id: str
    signal_id: str
    risk_check_id: str
    strategy_version_id: str
    side: OrderSide
    intended_size: float
    intended_price_ref: str | None = None
    created_at: datetime
    status: str = "created"


class PaperFill(BaseModel):
    paper_fill_id: str
    paper_order_id: str
    fill_time: datetime
    fill_price: float | None = None
    filled_size: float | None = None
    fees: float = 0
    slippage: float = 0
    latency_assumption: str
    liquidity_constraint: str
    failed_fill_reason: str | None = None
    market_snapshot_id: str | None = None


class PaperPosition(BaseModel):
    position_id: str
    token_id: str
    strategy_version_id: str
    entry_order_id: str
    entry_fill_id: str
    size: float
    cost_basis: float
    opened_at: datetime
    closed_at: datetime | None = None
    status: str = "open"


class ExitDecision(BaseModel):
    exit_decision_id: str
    position_id: str
    created_at: datetime
    data_as_of: datetime
    market_snapshot_id: str | None = None
    exit_reason: str
    exit_trigger: str
    expected_exit_logic: str
    created_by: str


class TradeOutcome(BaseModel):
    outcome_id: str
    position_id: str
    exit_decision_id: str
    gross_pnl: float
    net_pnl: float
    fees: float
    slippage: float
    duration_seconds: float
    max_drawdown: float
    calculated_at: datetime
    calculated_by_service: str = "evaluation_service"


class PostTradeReview(BaseModel):
    post_trade_review_id: str
    outcome_id: str
    position_id: str
    reviewer: str
    mistakes: list[str] = Field(default_factory=list)
    lessons: list[str] = Field(default_factory=list)
    hypothesis_update: dict[str, Any] = Field(default_factory=dict)
    evidence_refs: list[str] = Field(default_factory=list)
    created_at: datetime


class MemoryEntry(BaseModel):
    memory_entry_id: str
    claim: str
    evidence_grade: str
    source_refs: list[str] = Field(default_factory=list)
    status: str = "proposed"
    expires_at: datetime | None = None
    created_at: datetime
    created_by: str
    metadata: dict[str, Any] = Field(default_factory=dict)
