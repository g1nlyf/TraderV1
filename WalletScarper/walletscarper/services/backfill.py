from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from walletscarper.config import settings
from walletscarper.db import db
from walletscarper.models import TokenCandidate, utc_now
from walletscarper.services.discovery import DiscoveryService
from walletscarper.services.transactions import TransactionService


class BackfillService:
    def __init__(self) -> None:
        self.discovery = DiscoveryService()
        self.transactions = TransactionService()

    async def enqueue_discovered(self, candidates: list[TokenCandidate]) -> None:
        for c in candidates:
            await db.execute(
                """
                INSERT INTO backfill_queue(pool_address, token_mint, priority, status, attempts, created_at, updated_at)
                VALUES (?, ?, ?, 'pending', 0, ?, ?)
                ON CONFLICT(pool_address) DO UPDATE SET priority=MAX(backfill_queue.priority, excluded.priority), updated_at=excluded.updated_at
                """,
                (c.pool_address, c.token_mint, c.signal_score, utc_now(), utc_now()),
            )

    async def run_backfill_batch(self, limit: int | None = None) -> int:
        rows = await db.fetchall(
            """
            SELECT q.pool_address, q.token_mint, q.priority, p.dex_id, t.symbol, t.name
            FROM backfill_queue q
            LEFT JOIN pools p ON p.pool_address=q.pool_address
            LEFT JOIN tokens t ON t.mint=q.token_mint
            WHERE q.status IN ('pending','retry')
            ORDER BY q.priority DESC, q.updated_at ASC
            LIMIT ?
            """,
            (limit or settings.backfill_token_limit,),
        )
        sem = asyncio.Semaphore(settings.backfill_workers)
        total = 0

        async def one(row: dict) -> int:
            async with sem:
                candidate = TokenCandidate(token_mint=row["token_mint"], pool_address=row["pool_address"], symbol=row.get("symbol") or "", name=row.get("name") or "", dex_id=row.get("dex_id") or "", signal_score=float(row.get("priority") or 0))
                await db.execute("UPDATE backfill_queue SET status='running', attempts=attempts+1, last_attempt_at=?, updated_at=? WHERE pool_address=?", (utc_now(), utc_now(), candidate.pool_address))
                try:
                    swaps = await self.transactions.collect_for_token(candidate)
                    await db.execute("UPDATE backfill_queue SET status='done', updated_at=?, last_error=NULL WHERE pool_address=?", (utc_now(), candidate.pool_address))
                    return len(swaps)
                except Exception as exc:
                    await db.execute("UPDATE backfill_queue SET status='retry', updated_at=?, last_error=? WHERE pool_address=?", (utc_now(), str(exc)[:300], candidate.pool_address))
                    return 0

        for count in await asyncio.gather(*(one(row) for row in rows)):
            total += count
        return total
