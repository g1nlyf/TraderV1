from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ConfigSnapshot(BaseModel):
    config_snapshot_id: str
    created_at: datetime
    source: str
    content_hash: str
    environment: str
    app_version: str
    settings: dict[str, Any] = Field(default_factory=dict)
    build_info: dict[str, Any] = Field(default_factory=dict)


class RiskLimitSnapshot(BaseModel):
    risk_limit_snapshot_id: str
    config_snapshot_id: str | None = None
    created_at: datetime
    source: str
    content_hash: str
    limits: dict[str, Any] = Field(default_factory=dict)


class StrategyConfigSnapshot(BaseModel):
    strategy_config_snapshot_id: str
    config_snapshot_id: str | None = None
    strategy_name: str
    strategy_version_label: str
    created_at: datetime
    content_hash: str
    weights: dict[str, Any] = Field(default_factory=dict)
    thresholds: dict[str, Any] = Field(default_factory=dict)
    signal_rules: dict[str, Any] = Field(default_factory=dict)
    exit_rules: dict[str, Any] = Field(default_factory=dict)
    no_trade_rules: dict[str, Any] = Field(default_factory=dict)


class PromotionCriteriaSnapshot(BaseModel):
    promotion_criteria_snapshot_id: str
    config_snapshot_id: str | None = None
    created_at: datetime
    source: str
    content_hash: str
    criteria: dict[str, Any] = Field(default_factory=dict)


class AcceptanceRun(BaseModel):
    acceptance_run_id: str
    config_snapshot_id: str
    risk_limit_snapshot_id: str | None = None
    promotion_criteria_snapshot_id: str | None = None
    created_at: datetime
    acceptance_window_started_at: datetime | None = None
    acceptance_window_ended_at: datetime | None = None
    completed_at: datetime | None = None
    invariant_violations: list[str] = Field(default_factory=list)
    result: str = "pending"
    gap_report: dict[str, Any] | None = None
