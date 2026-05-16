from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class TokenCandidate:
    token_mint: str
    pool_address: str
    symbol: str = ""
    name: str = ""
    dex_id: str = ""
    quote_mint: str = ""
    pair_created_at: str | None = None
    pair_age_minutes: float | None = None
    price_usd: float = 0.0
    liquidity_usd: float = 0.0
    volume_5m: float = 0.0
    volume_1h: float = 0.0
    volume_6h: float = 0.0
    volume_24h: float = 0.0
    txns_5m: int = 0
    txns_1h: int = 0
    buys_1h: int = 0
    sells_1h: int = 0
    fdv: float = 0.0
    market_cap: float = 0.0
    source: str = "unknown"
    confidence: str = "unknown"
    signal_score: float = 0.0
    priority: str = "REJECTED"
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class NormalizedSwap:
    signature: str
    wallet: str
    token_mint: str
    pool_address: str
    side: str
    token_amount: float = 0.0
    quote_amount: float = 0.0
    price_usd: float | None = None
    block_time: str | None = None
    source: str = "unknown"
    confidence: str = "unknown"
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class WalletScore:
    wallet: str
    copyability_score: float
    confidence: str
    status: str
    realized_pnl_usd: float = 0.0
    winrate: float = 0.0
    median_roi: float = 0.0
    median_holding_minutes: float = 0.0
    total_trades: int = 0
    unique_tokens: int = 0
    risk_penalty: float = 0.0
    bot_score: float = 0.0
    human_score: float = 0.0
    sample_score: float = 0.0
    median_buy_usd: float = 0.0
    total_volume_usd: float = 0.0
    one_token_pnl_share: float = 0.0
    tx_per_token_median: float = 0.0
    reason: dict[str, Any] = field(default_factory=dict)
