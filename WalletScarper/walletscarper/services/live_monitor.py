from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from walletscarper.config import settings
from walletscarper.db import db
from walletscarper.models import utc_now
from walletscarper.services.stage2_bridge import Stage2WalletSignalBridge
from walletscarper.services.telegram import TelegramService


class LiveMonitor:
    def __init__(self) -> None:
        self.telegram = TelegramService()
        self._stage2_signal = Stage2WalletSignalBridge()

    async def tick(self) -> None:
        wallets = await db.fetchall(
            """
            SELECT wallet, last_seen_signature
            FROM tracked_wallets
            WHERE status IN ('active','probation')
            ORDER BY copyability_score DESC
            LIMIT ?
            """,
            (settings.live_monitor_max_wallets_per_tick,),
        )
        for wallet in wallets:
            await self._scan_wallet(wallet["wallet"], wallet.get("last_seen_signature"))

    async def _scan_wallet(self, wallet: str, last_seen_signature: str | None) -> None:
        row = await db.fetchone(
            """
            SELECT signature, token_mint, side, block_time, source
            FROM pool_transactions
            WHERE wallet=? AND side IN ('buy','sell')
            ORDER BY block_time DESC
            LIMIT 1
            """,
            (wallet,),
        )
        if not row:
            return
        sig = row["signature"]
        await db.execute("UPDATE tracked_wallets SET last_checked_at=?, last_seen_signature=COALESCE(last_seen_signature, ?) WHERE wallet=?", (utc_now(), sig, wallet))
        if last_seen_signature and sig != last_seen_signature and row["side"] == "buy":
            signal_id = await self._log_signal(wallet, row)
            await self._paper_entry(signal_id, wallet, row)
            await self._stage2_signal.emit_wallet_signal(
                wallet,
                row["token_mint"],
                row["side"],
                signature=row["signature"],
                block_time=row.get("block_time"),
                source=row.get("source"),
            )
            await db.execute("UPDATE tracked_wallets SET last_seen_signature=?, last_checked_at=? WHERE wallet=?", (sig, utc_now(), wallet))
            await self.telegram.send_transaction_alert(wallet, row["token_mint"], row["side"], sig)

    async def _log_signal(self, wallet: str, row: dict) -> int:
        await db.execute(
            """
            INSERT OR IGNORE INTO signal_log(wallet, signature, token_mint, side, block_time, detected_at, detection_lag_seconds, source, paper_trade_created, raw_json)
            VALUES (?, ?, ?, ?, ?, ?, 0, ?, 0, ?)
            """,
            (wallet, row["signature"], row["token_mint"], row["side"], row["block_time"], utc_now(), row["source"], json.dumps(dict(row), ensure_ascii=False, default=str)),
        )
        signal = await db.fetchone("SELECT id FROM signal_log WHERE wallet=? AND signature=?", (wallet, row["signature"]))
        return int(signal["id"]) if signal else 0

    async def _paper_entry(self, signal_id: int, wallet: str, row: dict) -> None:
        if not signal_id:
            return
        entry_at = datetime.now(timezone.utc) + timedelta(seconds=settings.paper_entry_delay_seconds)
        await db.execute(
            """
            INSERT INTO paper_trades(signal_id, wallet, token_mint, created_at, simulated_entry_at, entry_slippage_bps, fee_bps, exit_strategy, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'compare_follow_tp_sl_time', 'open')
            """,
            (signal_id, wallet, row["token_mint"], utc_now(), entry_at.isoformat(), settings.paper_slippage_bps, settings.paper_fee_bps),
        )
        await db.execute("UPDATE signal_log SET paper_trade_created=1 WHERE id=?", (signal_id,))
