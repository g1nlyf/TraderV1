"""Live wallet trade polling service.

Uses Helius RPC getSignaturesForAddress to fetch recent on-chain trades for all
tracked wallets, then writes new transactions to pool_transactions. LiveMonitor
picks them up on its next tick and emits Stage2 signals.

This replaces the polling gap where LiveMonitor only saw trades collected during
backfill. With this service, tracked wallets are polled live every scheduler tick.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from walletscarper.config import settings
from walletscarper.db import db
from walletscarper.models import utc_now
from walletscarper.sources.solana_rpc import SolanaRpcSource

log = logging.getLogger(__name__)


class WalletTradePollerService:
    def __init__(self) -> None:
        self.rpc = SolanaRpcSource()

    async def tick(self) -> dict[str, Any]:
        """Poll all active/probation tracked wallets for new on-chain trades.

        Returns summary with wallets_polled, new_trades, errors.
        """
        if not settings.helius_configured:
            log.debug("wallet_trade_poller: Helius not configured — skipping")
            return {"skipped": "no_helius_key", "wallets_polled": 0, "new_trades": 0, "errors": 0}

        wallets = await db.fetchall(
            """
            SELECT wallet, last_seen_signature
            FROM tracked_wallets
            WHERE status IN ('active', 'probation')
            ORDER BY copyability_score DESC
            LIMIT ?
            """,
            (settings.live_monitor_max_wallets_per_tick,),
        )

        new_trades = 0
        errors = 0
        for w in wallets:
            try:
                count = await self._poll_wallet(w["wallet"], w.get("last_seen_signature"))
                new_trades += count
            except Exception:
                log.warning("wallet_trade_poller: error for %s", w["wallet"][:8], exc_info=True)
                errors += 1

        if new_trades > 0:
            log.info("wallet_trade_poller: polled=%d new_trades=%d errors=%d", len(wallets), new_trades, errors)
        return {"wallets_polled": len(wallets), "new_trades": new_trades, "errors": errors}

    async def _poll_wallet(self, wallet: str, last_seen_sig: str | None) -> int:
        sigs = await self.rpc.get_signatures_for_address(
            wallet,
            limit=settings.wallet_trade_poll_signatures,
            until=last_seen_sig or None,
        )
        if not sigs:
            return 0

        new_count = 0
        for sig_info in sigs:
            sig = str(sig_info.get("signature") or "")
            if not sig:
                continue

            # Skip failed transactions
            if sig_info.get("err") is not None:
                continue

            # Skip already-known signatures
            existing = await db.fetchone("SELECT 1 FROM pool_transactions WHERE signature = ?", (sig,))
            if existing:
                continue

            swap = await self.rpc.parse_wallet_swap(sig)
            if not swap:
                continue
            if swap["wallet"] != wallet:
                continue
            if not swap.get("token_mint"):
                continue

            block_time = swap.get("block_time")
            await db.execute(
                """
                INSERT OR IGNORE INTO pool_transactions(
                  signature, pool_address, token_mint, wallet, side,
                  token_amount, quote_amount, price_usd, block_time,
                  source, source_confidence, completeness, raw_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    swap["signature"],
                    "",
                    swap["token_mint"],
                    swap["wallet"],
                    swap["side"],
                    swap.get("token_amount", 0.0),
                    swap.get("quote_amount", 0.0),
                    swap.get("price_usd", 0.0),
                    block_time,
                    "helius_rpc_live",
                    "high",
                    "full",
                    json.dumps({"helius_sig_info": sig_info}, ensure_ascii=False),
                ),
            )
            new_count += 1

        # Update last_checked_at for this wallet
        await db.execute(
            "UPDATE tracked_wallets SET last_checked_at = ? WHERE wallet = ?",
            (utc_now(), wallet),
        )
        return new_count
