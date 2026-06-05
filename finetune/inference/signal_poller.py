"""
signal_poller.py — Polls WalletScarper DB every 30s for new signals.

Reads tracked_wallet_signal_events that have no corresponding agent_trading_decision,
calls FineTunedSignalReviewer to process them.

Usage:
  python finetune/inference/signal_poller.py
  python finetune/inference/signal_poller.py --interval 30 --max-per-tick 5
  python finetune/inference/signal_poller.py --dry-run   # print signals, don't process

Env vars:
  VERTEX_PROJECT          (default: project-9eb04412-b304-4649-9ff)
  VERTEX_LOCATION         (default: europe-west4)
  FINETUNED_MODEL         (default: gemini-2.5-flash)
  POLL_INTERVAL_SECONDS   (default: 30)
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

# ── stdout encoding ────────────────────────────────────────────────────────────
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ── path setup ─────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[2]
WALLETSCARPER_ROOT = ROOT / "WalletScarper"
DB_PATH = WALLETSCARPER_ROOT / "data" / "stage2_foundation.sqlite3"

# Add roots so imports resolve
for _p in (str(ROOT), str(WALLETSCARPER_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# ── aiosqlite import ───────────────────────────────────────────────────────────
try:
    import aiosqlite
except ImportError:
    print(
        "[poller] ERROR: aiosqlite not installed.\n"
        "  Install it in the WalletScarper venv:\n"
        f"    {WALLETSCARPER_ROOT / '.venv' / 'Scripts' / 'pip.exe'} install aiosqlite\n"
        "  Or in the current environment: pip install aiosqlite",
        file=sys.stderr,
    )
    sys.exit(1)

# ── logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
log = logging.getLogger(__name__)


# ── thin async DB wrapper ──────────────────────────────────────────────────────

class AsyncDB:
    """Minimal async SQLite wrapper compatible with FineTunedSignalReviewer expectations."""

    def __init__(self, path: Path) -> None:
        self.path = path

    async def fetchall(self, sql: str, params: tuple = ()) -> list[dict]:
        async with aiosqlite.connect(self.path) as conn:
            conn.row_factory = aiosqlite.Row
            cursor = await conn.execute(sql, params)
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    async def fetchone(self, sql: str, params: tuple = ()) -> dict | None:
        async with aiosqlite.connect(self.path) as conn:
            conn.row_factory = aiosqlite.Row
            cursor = await conn.execute(sql, params)
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def execute(self, sql: str, params: tuple = ()) -> None:
        async with aiosqlite.connect(self.path) as conn:
            await conn.execute(sql, params)
            await conn.commit()


# ── dry-run helper ─────────────────────────────────────────────────────────────

async def _query_pending(db: AsyncDB, limit: int) -> list[dict]:
    return await db.fetchall(
        """
        SELECT s.*
        FROM tracked_wallet_signal_events s
        WHERE s.input_mode = 'real_source'
          AND NOT EXISTS (
            SELECT 1 FROM agent_trading_decisions d
            WHERE d.linked_tracked_wallet_signal_event_id = s.tracked_wallet_signal_event_id
          )
        ORDER BY s.observed_at DESC, s.created_at DESC
        LIMIT ?
        """,
        (limit,),
    )


# ── main loop ──────────────────────────────────────────────────────────────────

async def main_loop(
    interval: int,
    max_per_tick: int,
    dry_run: bool,
) -> None:
    if not DB_PATH.exists():
        log.error("DB not found: %s", DB_PATH)
        sys.exit(1)

    db = AsyncDB(DB_PATH)

    if dry_run:
        log.info("[poller] DRY-RUN mode — querying pending signals, no reviewing")
    else:
        # Lazy import so missing google-cloud-aiplatform only errors at runtime
        try:
            from finetune.inference.signal_reviewer import FineTunedSignalReviewer
        except ImportError:
            # Try alternate import path (ROOT already on sys.path)
            try:
                sys.path.insert(0, str(ROOT / "finetune"))
                from inference.signal_reviewer import FineTunedSignalReviewer  # type: ignore
            except ImportError as exc:
                log.error("Cannot import FineTunedSignalReviewer: %s", exc)
                sys.exit(1)

        reviewer = FineTunedSignalReviewer(database=db)
        log.info(
            "[poller] starting — interval=%ds max_per_tick=%d db=%s",
            interval,
            max_per_tick,
            DB_PATH,
        )

    tick = 0
    while True:
        tick += 1
        try:
            if dry_run:
                signals = await _query_pending(db, max_per_tick)
                if signals:
                    log.info("[poller] dry-run tick=%d: %d pending signal(s)", tick, len(signals))
                    for s in signals:
                        log.info(
                            "  signal_id=%.16s wallet=%.12s... token=%.12s... observed=%s",
                            s.get("tracked_wallet_signal_event_id", "?"),
                            s.get("wallet", "?"),
                            s.get("token_mint", "?"),
                            s.get("observed_at", "?"),
                        )
                else:
                    log.info("[poller] dry-run tick=%d: no pending signals", tick)
            else:
                result = await reviewer.review_pending_signals(max_signals=max_per_tick)
                reviewed = result.get("signals_reviewed", 0)
                recorded = result.get("decisions_recorded", 0)
                errors = result.get("errors", 0)
                log.info(
                    "[poller] tick=%d: reviewed=%d recorded=%d errors=%d",
                    tick,
                    reviewed,
                    recorded,
                    errors,
                )

        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.warning("[poller] tick=%d: unexpected error: %s", tick, exc, exc_info=True)

        await asyncio.sleep(interval)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Poll WalletScarper DB for new signals and run FineTunedSignalReviewer",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=int(os.environ.get("POLL_INTERVAL_SECONDS", "30")),
        help="Poll interval in seconds",
    )
    parser.add_argument(
        "--max-per-tick",
        type=int,
        default=5,
        help="Maximum signals to process per tick",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print pending signals without processing them",
    )
    return parser.parse_args()


async def _run(args: argparse.Namespace) -> None:
    try:
        await main_loop(
            interval=args.interval,
            max_per_tick=args.max_per_tick,
            dry_run=args.dry_run,
        )
    except KeyboardInterrupt:
        log.info("[poller] stopped")


def main() -> None:
    args = parse_args()
    try:
        asyncio.run(_run(args))
    except KeyboardInterrupt:
        log.info("[poller] stopped")


if __name__ == "__main__":
    main()
