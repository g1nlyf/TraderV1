from __future__ import annotations

import json
import logging
from typing import Any

from walletscarper.config import settings
from walletscarper.db import db
from walletscarper.models import NormalizedSwap, TokenCandidate
from walletscarper.services.trade_store import RawTrade, TradeStore
from walletscarper.sources import DexPaprikaSource, GeckoTerminalSource, SolanaRpcSource

log = logging.getLogger(__name__)


class TransactionService:
    def __init__(self) -> None:
        self.dexpaprika = DexPaprikaSource()
        self.gecko = GeckoTerminalSource()
        self.rpc = SolanaRpcSource()
        self.trade_store = TradeStore()

    async def collect_for_token(self, candidate: TokenCandidate) -> list[NormalizedSwap]:
        if not candidate.pool_address:
            return []
        raw = await self.dexpaprika.pool_transactions(candidate.pool_address, settings.max_transactions_per_pool)
        source = "dexpaprika"
        if not raw:
            raw = await self.gecko.pool_trades(candidate.pool_address, settings.max_transactions_per_pool)
            source = "geckoterminal"
        swaps: list[NormalizedSwap] = []
        rpc_resolutions = 0
        rpc_limit = settings.max_rpc_transactions_per_pool if settings.rpc_url else 0
        for item in raw[: settings.max_transactions_per_pool]:
            allow_rpc = rpc_resolutions < rpc_limit
            swap, used_rpc = await self._normalize(item, candidate, source, allow_rpc)
            if used_rpc:
                rpc_resolutions += 1
            if swap:
                swaps.append(swap)
        await self.trade_store.store_many(
            [
                RawTrade(
                    signature=s.signature,
                    wallet=s.wallet,
                    token_mint=s.token_mint,
                    pool_address=s.pool_address,
                    side=s.side,
                    token_amount=s.token_amount,
                    quote_amount=s.quote_amount,
                    price_usd=s.price_usd,
                    block_time=s.block_time,
                    source=s.source,
                    confidence=s.confidence,
                    raw=s.raw,
                )
                for s in swaps
            ]
        )
        log.info("collected %s swaps for %s", len(swaps), candidate.symbol or candidate.token_mint)
        return swaps

    async def _normalize(self, item: dict[str, Any], c: TokenCandidate, source: str, allow_rpc: bool) -> tuple[NormalizedSwap | None, bool]:
        attrs = item.get("attributes") if isinstance(item.get("attributes"), dict) else item
        signature = attrs.get("tx_hash") or attrs.get("txHash") or attrs.get("transaction_hash") or attrs.get("signature") or attrs.get("hash") or item.get("id")
        if not signature:
            return None, False
        wallet = attrs.get("wallet") or attrs.get("maker") or attrs.get("trader") or attrs.get("user") or attrs.get("sender")
        side = str(attrs.get("side") or attrs.get("type") or attrs.get("kind") or "").lower()
        if side not in {"buy", "sell"}:
            side = "buy" if "buy" in side else "sell" if "sell" in side else ""
        token_amount = self._float_first(attrs, ("token_amount", "base_amount", "amount", "amount_in", "amountOut", "volume"))
        quote_amount = self._float_first(attrs, ("quote_amount", "quote_volume", "amount_usd", "volume_usd", "volume_in_usd"))
        price_usd = self._float_first(attrs, ("price_usd", "price", "price_to_usd"))
        inferred = self._infer_dexpaprika_side(attrs, c.token_mint)
        if inferred:
            side = inferred
            token_amount = abs(float(attrs.get("volume_0") or attrs.get("amount_0") or token_amount or 0))
            if str(attrs.get("token_1")) in {"So11111111111111111111111111111111111111112", "11111111111111111111111111111111"}:
                quote_amount = abs(float(attrs.get("volume_1") or attrs.get("amount_1") or 0)) * abs(float(attrs.get("price_1_usd") or 0))
            price_usd = abs(float(attrs.get("price_0_usd") or price_usd or 0))
        block_time = attrs.get("block_time") or attrs.get("timestamp") or attrs.get("created_at")
        used_rpc = False
        if not wallet and allow_rpc and len(str(signature)) > 20:
            try:
                used_rpc = True
                signer, _mint, inferred_side, inferred_time = await self.rpc.infer_signer_and_token_buy(str(signature))
                wallet = signer or wallet
                side = side or inferred_side or ""
                block_time = block_time or inferred_time
            except Exception:
                pass
        if not wallet or not side:
            return None, used_rpc
        return NormalizedSwap(
            signature=str(signature),
            wallet=str(wallet),
            token_mint=c.token_mint,
            pool_address=c.pool_address,
            side=side,
            token_amount=token_amount,
            quote_amount=quote_amount,
            price_usd=price_usd or c.price_usd,
            block_time=str(block_time) if block_time else None,
            source=source,
            confidence="medium" if wallet and side else "low",
            raw=item,
        ), used_rpc

    def _float_first(self, attrs: dict[str, Any], keys: tuple[str, ...]) -> float:
        for key in keys:
            value = attrs.get(key)
            if isinstance(value, dict):
                value = value.get("usd") or value.get("value")
            try:
                if value is not None:
                    return abs(float(value))
            except Exception:
                continue
        return 0.0

    def _infer_dexpaprika_side(self, attrs: dict[str, Any], token_mint: str) -> str:
        if str(attrs.get("token_0")) != token_mint:
            return ""
        try:
            amount_0 = float(attrs.get("amount_0") or 0)
        except Exception:
            return ""
        if amount_0 < 0:
            return "buy"
        if amount_0 > 0:
            return "sell"
        return ""

    async def store_swap(self, swap: NormalizedSwap) -> None:
        await db.execute(
            """
            INSERT OR IGNORE INTO pool_transactions(signature, pool_address, token_mint, wallet, side, token_amount,
              quote_amount, price_usd, block_time, source, source_confidence, completeness, raw_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                swap.signature,
                swap.pool_address,
                swap.token_mint,
                swap.wallet,
                swap.side,
                swap.token_amount,
                swap.quote_amount,
                swap.price_usd,
                swap.block_time,
                swap.source,
                swap.confidence,
                "partial",
                json.dumps(swap.raw, ensure_ascii=False),
            ),
        )
