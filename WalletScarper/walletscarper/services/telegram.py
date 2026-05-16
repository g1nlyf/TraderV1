from __future__ import annotations

import html
import json
import logging
from datetime import datetime, timezone
from typing import Any

from walletscarper.config import settings
from walletscarper.db import db
from walletscarper.http_client import HttpClient
from walletscarper.models import utc_now

log = logging.getLogger(__name__)


class TelegramService:
    def __init__(self) -> None:
        self.http = HttpClient("telegram", timeout=25)

    async def send(self, text: str, chat_id: str | None = None, notification_type: str = "telegram") -> bool:
        if not settings.telegram_configured:
            return False
        target = chat_id or settings.telegram_chat_id
        if not target:
            chats = await db.fetchall("SELECT chat_id FROM telegram_chat_settings")
            if chats:
                target = str(chats[0]["chat_id"])
        if not target:
            return False
        url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
        payload = {"chat_id": target, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}
        result = await self.http.post_json(url, payload)
        ok = bool(isinstance(result, dict) and result.get("ok"))
        await db.insert_notification(notification_type, {"chat_id": target, "preview": text[:500]}, "sent" if ok else "failed", None if ok else json.dumps(result, default=str)[:500])
        return ok

    async def poll_commands(self) -> None:
        if not settings.telegram_configured:
            return
        row = await db.fetchone("SELECT payload_json FROM notification_log WHERE notification_type='telegram_offset' ORDER BY id DESC LIMIT 1")
        offset = 0
        if row:
            try:
                offset = int(json.loads(row["payload_json"]).get("offset", 0))
            except Exception:
                offset = 0
        url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/getUpdates"
        data = await self.http.post_json(url, {"timeout": 1, "offset": offset + 1})
        if not isinstance(data, dict) or not data.get("ok"):
            return
        max_update = offset
        for update in data.get("result", []):
            max_update = max(max_update, int(update.get("update_id", 0)))
            message = update.get("message") or update.get("edited_message") or {}
            text = str(message.get("text") or "").strip()
            chat = message.get("chat") or {}
            chat_id = str(chat.get("id") or "")
            if chat_id:
                await self._ensure_chat(chat_id)
            if text and chat_id:
                await self._handle_command(chat_id, text)
        if max_update > offset:
            await db.insert_notification("telegram_offset", {"offset": max_update}, "stored")

    async def _handle_command(self, chat_id: str, text: str) -> None:
        cmd = text.split()[0].lower()
        if cmd in {"/start", "/help"}:
            await self.send(self._help_text(), chat_id, "telegram_help")
        elif cmd in {"/flash_top", "/top", "/top10"}:
            await self.send(await self.render_top_wallets(limit=10), chat_id, "telegram_top")
        elif cmd == "/tracked":
            await self.send(await self.render_tracked_wallets(limit=20), chat_id, "telegram_tracked")
        elif cmd == "/digest":
            await self.send(await self.render_digest_text(), chat_id, "telegram_digest_manual")
        elif cmd == "/status":
            await self.send(await self.render_status(), chat_id, "telegram_status")
        elif cmd == "/settings":
            await self.send(await self.render_settings(chat_id), chat_id, "telegram_settings")
        elif cmd == "/tx_on":
            await db.execute("UPDATE telegram_chat_settings SET live_alerts_enabled=1, updated_at=? WHERE chat_id=?", (utc_now(), chat_id))
            await self.send("Live transaction alerts включены. Основной рейтинг кошельков остается доступен через /flash_top.", chat_id, "telegram_settings")
        elif cmd == "/tx_off":
            await db.execute("UPDATE telegram_chat_settings SET live_alerts_enabled=0, updated_at=? WHERE chat_id=?", (utc_now(), chat_id))
            await self.send("Live transaction alerts выключены. Это дефолтный режим.", chat_id, "telegram_settings")
        elif cmd == "/interval":
            parts = text.split()
            if len(parts) >= 2 and parts[1].isdigit():
                minutes = max(15, min(240, int(parts[1])))
                await db.execute("UPDATE telegram_chat_settings SET digest_interval_minutes=?, updated_at=? WHERE chat_id=?", (minutes, utc_now(), chat_id))
                await self.send(f"Digest interval: {minutes} минут.", chat_id, "telegram_settings")
        else:
            await self.send("Не понял команду. Используй /help.", chat_id, "telegram_help")

    async def _ensure_chat(self, chat_id: str) -> None:
        await db.execute(
            """
            INSERT INTO telegram_chat_settings(chat_id, created_at, updated_at, digest_enabled, digest_interval_minutes, live_alerts_enabled, daily_reminder_enabled, language)
            VALUES (?, ?, ?, 1, ?, 0, 1, 'ru')
            ON CONFLICT(chat_id) DO UPDATE SET updated_at=excluded.updated_at
            """,
            (chat_id, utc_now(), utc_now(), settings.digest_interval_minutes),
        )

    async def render_digest_text(self) -> str:
        latest = await db.fetchone("SELECT * FROM run_summaries ORDER BY id DESC LIMIT 1")
        top = await self._leaderboard_rows(3)
        lines = ["<b>WalletScarper digest</b>"]
        if latest:
            lines.append(f"Tokens: {latest['tokens_checked']} checked, {latest['tokens_deep_analyzed']} deep")
            lines.append(f"Wallets scored: {latest['wallet_candidates_found']}; added: {latest['tracked_wallets_added']}")
        lines.append("")
        lines.append("<b>Top wallets</b>")
        lines.extend(self._wallet_lines(top))
        return "\n".join(lines)

    async def render_top_wallets(self, limit: int = 10) -> str:
        rows = await self._leaderboard_rows(limit)
        lines = [f"<b>Top {limit} wallets by copyability</b>"]
        lines.extend(self._wallet_lines(rows))
        return "\n".join(lines)

    async def render_tracked_wallets(self, limit: int = 20) -> str:
        rows = await db.fetchall(
            """
            SELECT tw.wallet, tw.status, tw.copyability_score, ws.winrate, ws.realized_pnl_usd, ws.median_holding_minutes,
              ws.median_buy_usd, ws.human_score, ws.bot_score, ws.unique_tokens, ws.total_trades, ws.confidence
            FROM tracked_wallets tw
            LEFT JOIN wallet_scores ws ON ws.wallet=tw.wallet
            ORDER BY tw.status, tw.copyability_score DESC
            LIMIT ?
            """,
            (limit,),
        )
        lines = [f"<b>Tracked wallets ({len(rows)})</b>"]
        lines.extend(self._wallet_lines(rows))
        return "\n".join(lines)

    async def render_status(self) -> str:
        stats = await db.fetchone("SELECT COUNT(*) AS trades, COUNT(DISTINCT wallet) AS wallets, COUNT(DISTINCT token_mint) AS tokens FROM raw_trades")
        tracked = await db.fetchone("SELECT COUNT(*) AS c FROM tracked_wallets WHERE status IN ('active','probation')")
        sources = await db.fetchall("SELECT source, status, confidence FROM source_health ORDER BY source")
        lines = ["<b>Status</b>"]
        lines.append(f"Trades: {stats['trades'] if stats else 0}; wallets: {stats['wallets'] if stats else 0}; tokens: {stats['tokens'] if stats else 0}")
        lines.append(f"Tracked active/probation: {tracked['c'] if tracked else 0}")
        lines.append("")
        for src in sources:
            lines.append(f"{html.escape(src['source'])}: {html.escape(src['status'])} / {html.escape(src['confidence'])}")
        return "\n".join(lines)

    async def render_settings(self, chat_id: str) -> str:
        row = await db.fetchone("SELECT * FROM telegram_chat_settings WHERE chat_id=?", (chat_id,))
        if not row:
            await self._ensure_chat(chat_id)
            row = await db.fetchone("SELECT * FROM telegram_chat_settings WHERE chat_id=?", (chat_id,))
        return (
            "<b>Settings</b>\n"
            f"Digest: {'on' if row['digest_enabled'] else 'off'} every {row['digest_interval_minutes']} min\n"
            f"Live tx alerts: {'on' if row['live_alerts_enabled'] else 'off'}\n"
            "Commands: /flash_top /tracked /digest /status /tx_on /tx_off /interval 60"
        )

    async def send_transaction_alert(self, wallet: str, token_mint: str, side: str, signature: str) -> None:
        chats = await db.fetchall("SELECT chat_id FROM telegram_chat_settings WHERE live_alerts_enabled=1")
        for chat in chats:
            await self.send(
                f"<b>Tracked wallet {html.escape(side)}</b>\n{self._wallet_link(wallet)}\nToken: <code>{html.escape(token_mint)}</code>\nSig: <code>{html.escape(signature)}</code>",
                str(chat["chat_id"]),
                "live_tx_alert",
            )

    async def _leaderboard_rows(self, limit: int) -> list[dict[str, Any]]:
        return await db.fetchall(
            """
            SELECT wl.rank, wl.wallet, wl.copyability_score, wl.status, ws.winrate, ws.realized_pnl_usd,
              ws.median_holding_minutes, ws.median_buy_usd, ws.human_score, ws.bot_score, ws.unique_tokens,
              ws.total_trades, ws.confidence
            FROM wallet_leaderboard wl
            LEFT JOIN wallet_scores ws ON ws.wallet=wl.wallet
            ORDER BY wl.rank
            LIMIT ?
            """,
            (limit,),
        )

    def _wallet_lines(self, rows: list[dict[str, Any]]) -> list[str]:
        if not rows:
            return ["No wallets yet."]
        lines: list[str] = []
        for row in rows:
            rank = f"#{row.get('rank')} " if row.get("rank") else ""
            lines.append(
                f"{rank}{self._wallet_link(row['wallet'])}\n"
                f"score {self._num(row.get('copyability_score'))} | {html.escape(str(row.get('status') or ''))} | conf {html.escape(str(row.get('confidence') or ''))}\n"
                f"win {self._pct(row.get('winrate'))} | pnl ${self._num(row.get('realized_pnl_usd'))} | hold {self._num(row.get('median_holding_minutes'))}m | buy ${self._num(row.get('median_buy_usd'))}\n"
                f"human {self._num(row.get('human_score'))} | bot {self._num(row.get('bot_score'))} | tokens {row.get('unique_tokens') or 0} | trades {row.get('total_trades') or 0}"
            )
        return lines

    def _wallet_link(self, wallet: str) -> str:
        safe = html.escape(wallet)
        return f'<a href="https://gmgn.ai/sol/address/{safe}"><code>{safe}</code></a>'

    def _num(self, value: Any) -> str:
        try:
            return f"{float(value or 0):.1f}"
        except Exception:
            return "0.0"

    def _pct(self, value: Any) -> str:
        try:
            return f"{float(value or 0) * 100:.1f}%"
        except Exception:
            return "0.0%"

    def _help_text(self) -> str:
        return (
            "<b>WalletScarper</b>\n"
            "Главный режим: рейтинг кошельков, а не поток транзакций.\n\n"
            "/flash_top - топ кошельков\n"
            "/tracked - отслеживаемые кошельки\n"
            "/digest - свежий дайджест\n"
            "/status - состояние системы\n"
            "/settings - настройки\n"
            "/interval 60 - интервал дайджеста\n"
            "/tx_on и /tx_off - отдельный режим live transaction alerts"
        )
