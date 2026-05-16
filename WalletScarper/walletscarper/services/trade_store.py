from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from walletscarper.db import db


@dataclass(slots=True)
class RawTrade:
    signature: str
    wallet: str
    token_mint: str
    pool_address: str = ""
    dex_id: str = ""
    side: str = ""
    token_amount: float = 0.0
    quote_amount: float = 0.0
    price_usd: float | None = None
    block_time: str | None = None
    slot: int | None = None
    source: str = "unknown"
    confidence: str = "unknown"
    ingestion_run_id: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


class TradeStore:
    async def store_raw_trade(self, trade: RawTrade) -> None:
        await self.store_many([trade])

    async def store_many(self, trades: list[RawTrade]) -> int:
        if not trades:
            return 0
        conn = await db.connect()
        try:
            await conn.executemany(
                """
                INSERT OR IGNORE INTO raw_trades(signature, wallet, token_mint, pool_address, dex_id, side,
                  token_amount, quote_amount, price_usd, block_time, slot, source, source_confidence,
                  ingestion_run_id, raw_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [self._raw_params(trade) for trade in trades],
            )
            await conn.executemany(
                """
                INSERT OR IGNORE INTO pool_transactions(signature, pool_address, token_mint, wallet, side, token_amount,
                  quote_amount, price_usd, block_time, source, source_confidence, completeness, raw_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'partial', ?)
                """,
                [self._pool_params(trade) for trade in trades],
            )
            await conn.commit()
        finally:
            await conn.close()
        return len(trades)

    def _raw_params(self, trade: RawTrade) -> tuple[Any, ...]:
        return (
            trade.signature,
            trade.wallet,
            trade.token_mint,
            trade.pool_address,
            trade.dex_id,
            trade.side,
            trade.token_amount,
            trade.quote_amount,
            trade.price_usd,
            trade.block_time,
            trade.slot,
            trade.source,
            trade.confidence,
            trade.ingestion_run_id,
            json.dumps(trade.raw, ensure_ascii=False, default=str),
        )

    def _pool_params(self, trade: RawTrade) -> tuple[Any, ...]:
        return (
            trade.signature,
            trade.pool_address,
            trade.token_mint,
            trade.wallet,
            trade.side,
            trade.token_amount,
            trade.quote_amount,
            trade.price_usd,
            trade.block_time,
            trade.source,
            trade.confidence,
            json.dumps(trade.raw, ensure_ascii=False, default=str),
        )
