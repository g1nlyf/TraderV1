from __future__ import annotations

import asyncio
import logging
import signal as _signal

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from walletscarper.config import settings
from walletscarper.db import db
from walletscarper.services.backfill import BackfillService
from walletscarper.services.live_monitor import LiveMonitor
from walletscarper.services.pipeline import Pipeline
from walletscarper.services.stage2_scanner import Stage2ScannerService
from walletscarper.services.telegram import TelegramService
from walletscarper.services.wallet_tracker import WalletTracker
from walletscarper.services.wallet_trade_poller import WalletTradePollerService
from walletscarper.sources.bitquery_corecast import BitqueryCoreCastSource

log = logging.getLogger(__name__)


class WalletScarperScheduler:
    def __init__(self) -> None:
        self.scheduler = AsyncIOScheduler(timezone="UTC")
        self.pipeline = Pipeline()
        self.backfill = BackfillService()
        self.live = LiveMonitor()
        self.telegram = TelegramService()
        self.wallet_tracker = WalletTracker()
        self.bitquery = BitqueryCoreCastSource()
        self.stage2_scanner = Stage2ScannerService()
        self.wallet_trade_poller = WalletTradePollerService()

    async def start(self) -> None:
        await db.init()
        self._stop_event = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (_signal.SIGINT, _signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, self._stop_event.set)
            except (NotImplementedError, OSError):
                pass  # Windows asyncio signal handlers unsupported in some versions
        self.scheduler.add_job(self.pipeline.run_once, "interval", minutes=settings.discovery_interval_minutes, kwargs={"notify": True}, id="discovery", max_instances=1, coalesce=True)
        self.scheduler.add_job(self.backfill.run_backfill_batch, "interval", minutes=15, id="backfill", max_instances=1, coalesce=True)
        self.scheduler.add_job(self.live.tick, "interval", seconds=settings.live_monitor_interval_seconds, id="live_monitor", max_instances=1, coalesce=True)
        self.scheduler.add_job(self.wallet_trade_poller.tick, "interval", seconds=settings.live_monitor_interval_seconds, id="wallet_trade_poller", max_instances=1, coalesce=True)
        if settings.bitquery_configured:
            self.scheduler.add_job(
                self.bitquery.stream_dex_trades,
                "interval",
                seconds=settings.bitquery_stream_interval_seconds,
                kwargs={"seconds": settings.bitquery_stream_seconds},
                id="bitquery_stream",
                max_instances=1,
                coalesce=True,
            )
        self.scheduler.add_job(self.telegram.poll_commands, "interval", seconds=5, id="telegram_commands", max_instances=1, coalesce=True)
        self.scheduler.add_job(self.wallet_tracker.run_daily, "cron", hour=settings.daily_wallet_tracker_hour_utc, kwargs={"notify": True}, id="wallet_tracker")
        # Stage 2 intelligence jobs
        self.scheduler.add_job(self.stage2_scanner.run_token_scan, "interval", minutes=60, kwargs={"limit": 100}, id="stage2_token_scan", max_instances=1, coalesce=True)
        self.scheduler.add_job(self.stage2_scanner.run_wallet_extraction, "interval", hours=2, kwargs={"max_tokens": 20, "lookback_hours": 6}, id="stage2_wallet_extraction", max_instances=1, coalesce=True)
        self.scheduler.add_job(self.stage2_scanner.run_legacy_token_sync, "interval", hours=24, kwargs={"limit": 100}, id="stage2_legacy_token_sync", max_instances=1, coalesce=True)
        self.scheduler.add_job(self.stage2_scanner.run_hermes_signal_review, "interval", minutes=15, kwargs={"max_signals": 5}, id="stage2_hermes_signal_review", max_instances=1, coalesce=True)
        self.scheduler.start()
        log.info("scheduler started")
        await self.stage2_scanner.run_legacy_token_sync(limit=100)
        await self.pipeline.run_once(notify=True)
        await self.backfill.run_backfill_batch()
        if settings.bitquery_configured:
            asyncio.create_task(self.bitquery.stream_dex_trades(seconds=settings.bitquery_stream_seconds))
        await self._stop_event.wait()
        log.info("scheduler: shutdown signal received — stopping gracefully")
        self.scheduler.shutdown(wait=True)
        log.info("scheduler: stopped")
