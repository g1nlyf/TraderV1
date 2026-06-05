"""
Decision Record — atomic unit of the TraderV1 dataset (schema v2.0).

One record carries everything needed for SFT, DPO, off-policy eval and P&L
attribution. See blueprint §D.1.

Design rules:
  - Point-in-time: every *_features block uses only data <= `timestamp`.
  - Outcome block is filled later (after the horizon), never at decision time.
  - `source` ∈ {replay, shadow, live, bootstrap}. bootstrap = formula-labelled,
    must NOT be mixed with ground-truth outcomes when building reward-filtered sets.
  - provenance.propensity + provenance.exploration enable off-policy correction.

The text-to-text SFT projection (`to_sft_example`) MUST match the format used by
build_reward_filtered_dataset.py so replay-generated and session-generated data
are interchangeable.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any

SCHEMA_VERSION = "2.0"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ── sub-blocks ───────────────────────────────────────────────────────────────────

@dataclass
class SignalBlock:
    wallet: str
    token_mint: str
    side: str = "buy"
    observed_at: str = ""
    copy_latency_sec: float | None = None


@dataclass
class WalletFeatures:
    scalars: dict[str, Any] = field(default_factory=dict)          # win_rate, payoff, trade_count, net_pnl
    style_embedding: list[float] = field(default_factory=list)      # learned (empty until trained)
    style_tags: list[str] = field(default_factory=list)            # human-readable archetype tags
    form_state: dict[str, Any] = field(default_factory=dict)        # hot_cold, streak
    intent: str | None = None                                       # accumulation|fomo|rotation|exit_liquidity
    syndicate_id: str | None = None
    syndicate_size: int = 1
    alpha_half_life_days: float | None = None
    post_discovery_validated: bool = False                          # survivorship guard (#59)
    buy_size_vs_liquidity: float | None = None                      # #58 conviction proxy


@dataclass
class TokenFeatures:
    liquidity_usd: float | None = None
    market_cap: float | None = None
    lifecycle_phase: str | None = None                              # bonding|migrating|post_migration|mature
    microstructure: dict[str, Any] = field(default_factory=dict)    # txns_5m, holder_count, volume
    flow_5m: dict[str, Any] = field(default_factory=dict)


@dataclass
class MarketFeatures:
    price_usd: float | None = None
    cohort_net_flow: float | None = None                            # #57
    impact_at_size: dict[str, float] = field(default_factory=dict)  # #50


@dataclass
class DecisionBlock:
    type: str = "no_trade"                                          # signal|no_trade|wait
    confidence_calibrated: float | None = None                      # true P(+expectancy) — #44
    confidence_tier: str | None = None                              # high|medium|low (legacy)
    max_profitable_size_usd: float | None = None                    # #50
    action_distribution: dict[str, float] = field(default_factory=dict)
    outcome_quantiles: dict[str, float] = field(default_factory=dict)  # #40
    reasoning: str = ""


@dataclass
class ExecutionBlock:
    sim_fill_price: float | None = None
    slippage_bps: float | None = None
    fees_usd: float | None = None
    latency_sec: float | None = None


@dataclass
class OutcomeBlock:
    exit_rule_applied: str | None = None
    realized_pnl_net: float | None = None                           # north-star reward (after costs)
    label: str | None = None                                        # excellent|good|marginal|loss|good_no_trade|...
    counterfactual_no_trade_pnl: float | None = None                # #37
    checkpoints: dict[str, float] = field(default_factory=dict)


@dataclass
class Provenance:
    feature_schema_version: str = SCHEMA_VERSION
    propensity: float | None = None
    exploration: bool = False


# ── the record ───────────────────────────────────────────────────────────────────

@dataclass
class DecisionRecord:
    signal: SignalBlock
    decision_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    schema_version: str = SCHEMA_VERSION
    model_version: str = "unknown"
    timestamp: str = field(default_factory=_now)
    source: str = "replay"                                          # replay|shadow|live|bootstrap
    regime: dict[str, Any] = field(default_factory=dict)
    wallet_features: WalletFeatures = field(default_factory=WalletFeatures)
    token_features: TokenFeatures = field(default_factory=TokenFeatures)
    market_features: MarketFeatures = field(default_factory=MarketFeatures)
    decision: DecisionBlock = field(default_factory=DecisionBlock)
    execution: ExecutionBlock = field(default_factory=ExecutionBlock)
    outcome: OutcomeBlock = field(default_factory=OutcomeBlock)
    provenance: Provenance = field(default_factory=Provenance)

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, default=str)

    # ── text-to-text SFT projection (must match build_reward_filtered_dataset) ──
    def to_sft_example(self, system_prompt: str) -> dict:
        s = self.signal
        parts = [
            "AUTONOMOUS SIGNAL REVIEW",
            "",
            "Signal event:",
            f"  wallet: {s.wallet}",
            f"  token_mint: {s.token_mint}",
            f"  side: {s.side}",
            f"  observed_at: {s.observed_at}",
            "",
            "EVIDENCE:",
            "--- WALLET PROFILE ---",
            json.dumps(self.wallet_features.scalars, ensure_ascii=False),
        ]
        if self.wallet_features.style_tags:
            parts.append(f"wallet_style: {', '.join(self.wallet_features.style_tags)}")
        if self.wallet_features.intent:
            parts.append(f"wallet_intent: {self.wallet_features.intent}")
        parts += [
            "--- TOKEN PROFILE ---",
            json.dumps({
                "liquidity_usd": self.token_features.liquidity_usd,
                "market_cap": self.token_features.market_cap,
                "lifecycle_phase": self.token_features.lifecycle_phase,
                **self.token_features.microstructure,
            }, ensure_ascii=False),
            "--- MARKET SNAPSHOT ---",
            json.dumps({
                "price_usd": self.market_features.price_usd,
                "cohort_net_flow": self.market_features.cohort_net_flow,
                **self.token_features.flow_5m,
            }, ensure_ascii=False),
            "",
            "Review the evidence and output your decision as JSON "
            "with keys: decision_type, confidence, pre_action_reasoning.",
        ]
        user_text = "\n".join(parts)
        model_text = json.dumps({
            "decision_type": self.decision.type,
            "confidence": self.decision.confidence_tier,
            "pre_action_reasoning": self.decision.reasoning,
        }, ensure_ascii=False, indent=2)
        return {
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "contents": [
                {"role": "user", "parts": [{"text": user_text}]},
                {"role": "model", "parts": [{"text": model_text}]},
            ],
        }


# ── JSON Schema (for validation / documentation) ─────────────────────────────────

JSON_SCHEMA: dict = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "TraderV1 Decision Record",
    "type": "object",
    "required": ["decision_id", "schema_version", "timestamp", "source", "signal"],
    "properties": {
        "decision_id": {"type": "string"},
        "schema_version": {"const": SCHEMA_VERSION},
        "source": {"enum": ["replay", "shadow", "live", "bootstrap"]},
        "signal": {
            "type": "object",
            "required": ["wallet", "token_mint", "side"],
        },
        "outcome": {
            "type": "object",
            "properties": {"realized_pnl_net": {"type": ["number", "null"]}},
        },
        "provenance": {
            "type": "object",
            "properties": {
                "propensity": {"type": ["number", "null"]},
                "exploration": {"type": "boolean"},
            },
        },
    },
}


if __name__ == "__main__":
    # Self-test: build a record, project to SFT, validate roundtrip.
    rec = DecisionRecord(
        signal=SignalBlock(wallet="W123", token_mint="T456", observed_at=_now()),
        source="replay",
        wallet_features=WalletFeatures(
            scalars={"win_rate": 0.62, "payoff": 3.1, "trade_count": 88, "net_pnl": 12000},
            style_tags=["dip_buyer", "patient"], intent="accumulation",
            post_discovery_validated=True, buy_size_vs_liquidity=0.018,
        ),
        token_features=TokenFeatures(liquidity_usd=72000, market_cap=2_400_000,
                                     lifecycle_phase="post_migration"),
        decision=DecisionBlock(type="signal", confidence_tier="high",
                               reasoning="Composite high; elite wallet, clean token."),
        outcome=OutcomeBlock(realized_pnl_net=0.14, label="good"),
        provenance=Provenance(propensity=0.5, exploration=False),
    )
    ex = rec.to_sft_example("SYSTEM POLICY")
    print("Record OK. decision_id:", rec.decision_id)
    print("SFT user[:200]:", ex["contents"][0]["parts"][0]["text"][:200])
    print("SFT model:", ex["contents"][1]["parts"][0]["text"])
