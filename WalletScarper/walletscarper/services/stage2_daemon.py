"""Stage 2 continuous worker daemon.

Standalone async daemon that runs the V2 intelligence loop independently of
the legacy WalletScarperScheduler.  Designed to be started via:

    python -m walletscarper stage2-run-daemon

Job schedule:
  - stage2_token_scan        every 60 min  — token.scan_universe (normalize raw events)
  - stage2_wallet_extraction every 2 hours — wallet.extract_from_token for new candidates
  - stage2_session_heartbeat every 5 min   — log open session stats, expire stale sessions
  - stage2_heartbeat         every 15 min  — emit a log line to confirm daemon is alive

The daemon is best-effort and gracefully handles Stage 2 unavailability.
"""

from __future__ import annotations

import asyncio
import logging
import signal as _signal

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from walletscarper.services.stage2_scanner import Stage2ScannerService

log = logging.getLogger(__name__)

_HEARTBEAT_INTERVAL_MINUTES = 15
_SESSION_HEARTBEAT_INTERVAL_MINUTES = 5
_TOKEN_SCAN_INTERVAL_MINUTES = 60
_WALLET_EXTRACTION_INTERVAL_HOURS = 2


class Stage2Daemon:
    """Continuous Stage 2 intelligence worker daemon.

    Uses APScheduler (AsyncIOScheduler) for job management.
    All jobs are best-effort: failures are logged and do not stop the daemon.
    """

    def __init__(self) -> None:
        self.scheduler = AsyncIOScheduler(timezone="UTC")
        self.scanner = Stage2ScannerService()
        self._stop_event = asyncio.Event()

    async def start(self) -> None:
        """Start the daemon and block until interrupted."""
        log.info("stage2_daemon: starting")

        # Register jobs
        self.scheduler.add_job(
            self.scanner.run_token_scan,
            "interval",
            minutes=_TOKEN_SCAN_INTERVAL_MINUTES,
            kwargs={"limit": 100},
            id="stage2_token_scan",
            max_instances=1,
            coalesce=True,
        )
        self.scheduler.add_job(
            self.scanner.run_wallet_extraction,
            "interval",
            hours=_WALLET_EXTRACTION_INTERVAL_HOURS,
            kwargs={"max_tokens": 30, "lookback_hours": 8},
            id="stage2_wallet_extraction",
            max_instances=1,
            coalesce=True,
        )
        self.scheduler.add_job(
            self._session_heartbeat,
            "interval",
            minutes=_SESSION_HEARTBEAT_INTERVAL_MINUTES,
            id="stage2_session_heartbeat",
            max_instances=1,
            coalesce=True,
        )
        self.scheduler.add_job(
            self._heartbeat,
            "interval",
            minutes=_HEARTBEAT_INTERVAL_MINUTES,
            id="stage2_heartbeat",
            max_instances=1,
            coalesce=True,
        )

        self.scheduler.start()
        log.info("stage2_daemon: scheduler started — running initial token scan")

        # Run immediately on startup
        await self.scanner.run_token_scan(limit=100)
        await self.scanner.run_wallet_extraction(max_tokens=30, lookback_hours=24)
        await self._session_heartbeat()

        # Register graceful shutdown on SIGINT / SIGTERM
        loop = asyncio.get_running_loop()
        for sig in (_signal.SIGINT, _signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, self._stop_event.set)
            except (NotImplementedError, OSError):
                pass  # Windows: signal handlers not supported in asyncio on some versions

        log.info("stage2_daemon: running. Press Ctrl+C to stop.")
        await self._stop_event.wait()
        await self.stop()

    async def stop(self) -> None:
        """Gracefully shut down the scheduler."""
        log.info("stage2_daemon: shutting down")
        self.scheduler.shutdown(wait=False)
        log.info("stage2_daemon: stopped")

    async def _heartbeat(self) -> None:
        """Emit a periodic log line to confirm the daemon is alive."""
        summary = await self.scanner._ensure_ready()
        log.info("stage2_daemon: heartbeat — Stage2 available=%s", summary)

    async def _session_heartbeat(self) -> None:
        """Log open session stats and perform maintenance."""
        try:
            if not await self.scanner._ensure_ready():
                return
            from walletscarper.stage2.token_intelligence.session import ActiveTokenSessionService
            session_service = ActiveTokenSessionService(self.scanner._database)
            summary = await session_service.session_summary()
            open_count = summary.get("sessions_by_status", {}).get("open", 0)
            log.info("stage2_daemon: session_heartbeat — open_sessions=%d stats=%s", open_count, summary)
        except Exception:
            log.debug("stage2_daemon: session_heartbeat failed", exc_info=True)
