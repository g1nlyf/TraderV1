from __future__ import annotations

import logging

from walletscarper.config import settings
from walletscarper.db import db
from walletscarper.models import TokenCandidate, utc_now
from walletscarper.sources import DexScreenerSource, GeckoTerminalSource

log = logging.getLogger(__name__)


class DiscoveryService:
    def __init__(self) -> None:
        self.dexscreener = DexScreenerSource()
        self.gecko = GeckoTerminalSource()

    async def run(self) -> list[TokenCandidate]:
        candidates = await self.dexscreener.discover()
        candidates.extend(await self.gecko.discover_new_and_trending(pages=3))
        candidates = self._dedupe(candidates)
        enriched = [self._score(c) for c in candidates]
        filtered = [c for c in enriched if self._keep(c)]
        filtered.sort(key=lambda c: c.signal_score, reverse=True)
        for candidate in filtered:
            await self.store_candidate(candidate)
        log.info("discovery found %s candidates, kept %s", len(candidates), len(filtered))
        return filtered

    def _dedupe(self, candidates: list[TokenCandidate]) -> list[TokenCandidate]:
        by_pool: dict[str, TokenCandidate] = {}
        for c in candidates:
            key = c.pool_address or c.token_mint
            existing = by_pool.get(key)
            if not existing or c.signal_score > existing.signal_score or c.volume_1h > existing.volume_1h:
                by_pool[key] = c
        return list(by_pool.values())

    def _keep(self, c: TokenCandidate) -> bool:
        age = c.pair_age_minutes
        if age is None or age < 30 or age > settings.max_pair_age_minutes:
            return False
        if c.liquidity_usd < 5_000:
            return False
        return bool(c.pool_address)

    def _score(self, c: TokenCandidate) -> TokenCandidate:
        age = c.pair_age_minutes or 0
        age_score = 100 if settings.min_pair_age_minutes <= age <= 1440 else 50 if age <= settings.max_pair_age_minutes else 0
        liquidity_score = min(c.liquidity_usd / max(settings.min_liquidity_usd, 1) * 100, 100)
        volume_score = min(c.volume_1h / max(settings.min_volume_1h_usd, 1) * 100, 100)
        tx_score = min(c.txns_1h / max(settings.min_txns_1h, 1) * 100, 100)
        if c.buys_1h + c.sells_1h:
            buy_ratio = c.buys_1h / max(c.buys_1h + c.sells_1h, 1)
            buy_sell_score = max(0, min(100, 100 - abs(0.55 - buy_ratio) * 160))
        else:
            buy_sell_score = 0
        fdv_penalty = 20 if c.fdv and c.fdv > settings.max_fdv_usd else 0
        c.signal_score = max(0, min(100, volume_score * 0.30 + tx_score * 0.20 + liquidity_score * 0.15 + buy_sell_score * 0.15 + age_score * 0.20 - fdv_penalty))
        c.priority = "HIGH" if c.signal_score >= 75 else "MEDIUM" if c.signal_score >= 55 else "LOW" if c.signal_score >= 35 else "REJECTED"
        c.confidence = "medium" if c.priority in {"HIGH", "MEDIUM"} else "low"
        return c

    async def store_candidate(self, c: TokenCandidate) -> None:
        now = utc_now()
        await db.execute(
            """
            INSERT INTO tokens(mint, symbol, name, first_seen_at, last_seen_at, source)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(mint) DO UPDATE SET symbol=excluded.symbol, name=excluded.name, last_seen_at=excluded.last_seen_at
            """,
            (c.token_mint, c.symbol, c.name, now, now, c.source),
        )
        await db.execute(
            """
            INSERT INTO pools(pool_address, token_mint, quote_mint, dex_id, created_at, first_seen_at, last_seen_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(pool_address) DO UPDATE SET last_seen_at=excluded.last_seen_at
            """,
            (c.pool_address, c.token_mint, c.quote_mint, c.dex_id, c.pair_created_at, now, now),
        )
        await db.execute(
            """
            INSERT INTO token_snapshots(token_mint, pool_address, captured_at, price_usd, liquidity_usd,
              volume_5m, volume_1h, volume_6h, volume_24h, txns_5m, txns_1h, buys_1h, sells_1h,
              fdv, market_cap, signal_score, priority, source, source_confidence)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                c.token_mint,
                c.pool_address,
                now,
                c.price_usd,
                c.liquidity_usd,
                c.volume_5m,
                c.volume_1h,
                c.volume_6h,
                c.volume_24h,
                c.txns_5m,
                c.txns_1h,
                c.buys_1h,
                c.sells_1h,
                c.fdv,
                c.market_cap,
                c.signal_score,
                c.priority,
                c.source,
                c.confidence,
            ),
        )
