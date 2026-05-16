from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from walletscarper.stage2.clock import Clock, SystemClock, isoformat_utc
from walletscarper.stage2.config import Stage2Settings, load_stage2_settings
from walletscarper.stage2.db import Stage2Database
from walletscarper.stage2.db.json import dumps_json
from walletscarper.stage2.ids import new_id


class JobQueueService:
    def __init__(self, database: Stage2Database, *, settings: Stage2Settings | None = None, clock: Clock | None = None):
        self.database = database
        self.settings = settings or load_stage2_settings()
        self.clock = clock or SystemClock()

    async def create_job(
        self,
        *,
        job_type: str,
        payload: dict[str, Any] | None = None,
        worker_type: str | None = None,
        target_ref: str | None = None,
        priority: int = 100,
        max_attempts: int = 3,
        scheduled_at: datetime | None = None,
        output_schema: dict[str, Any] | None = None,
    ) -> str:
        now = self.clock.now()
        job_id = new_id("job")
        await self.database.execute(
            """
            INSERT INTO jobs(
              job_id, job_type, worker_type, target_ref, status, priority, payload_json,
              output_schema_json, attempts, max_attempts, scheduled_at, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, 'pending', ?, ?, ?, 0, ?, ?, ?, ?)
            """,
            (
                job_id,
                job_type,
                worker_type,
                target_ref,
                priority,
                dumps_json(payload or {}),
                dumps_json(output_schema or {}),
                max_attempts,
                isoformat_utc(scheduled_at or now),
                isoformat_utc(now),
                isoformat_utc(now),
            ),
        )
        return job_id

    async def lease_next_job(
        self,
        *,
        worker_id: str,
        worker_type: str | None = None,
        lease_seconds: int | None = None,
    ) -> dict[str, Any] | None:
        now = self.clock.now()
        expires_at = now + timedelta(seconds=lease_seconds or self.settings.job_lease_seconds)
        conn = await self.database.connect()
        try:
            await conn.execute("BEGIN IMMEDIATE")
            await self._expire_stale_leases(conn, now)
            worker_filter = ""
            params: list[Any] = [isoformat_utc(now)]
            if worker_type is not None:
                worker_filter = "AND (worker_type IS NULL OR worker_type = ?)"
                params.append(worker_type)
            rows = await conn.execute_fetchall(
                f"""
                SELECT * FROM jobs
                WHERE status = 'pending'
                  AND scheduled_at <= ?
                  AND attempts < max_attempts
                  {worker_filter}
                ORDER BY priority ASC, scheduled_at ASC, created_at ASC
                LIMIT 1
                """,
                tuple(params),
            )
            if not rows:
                await conn.commit()
                return None
            job = dict(rows[0])
            lease_id = new_id("worker_lease")
            await conn.execute(
                """
                INSERT INTO worker_leases(
                  worker_lease_id, job_id, worker_id, lease_acquired_at,
                  lease_expires_at, heartbeat_at, metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    lease_id,
                    job["job_id"],
                    worker_id,
                    isoformat_utc(now),
                    isoformat_utc(expires_at),
                    isoformat_utc(now),
                    dumps_json({"worker_type": worker_type}),
                ),
            )
            await conn.execute(
                "UPDATE jobs SET status = 'running', attempts = attempts + 1, updated_at = ? WHERE job_id = ?",
                (isoformat_utc(now), job["job_id"]),
            )
            await conn.commit()
            job["worker_lease_id"] = lease_id
            job["lease_expires_at"] = isoformat_utc(expires_at)
            job["attempts"] = int(job["attempts"]) + 1
            job["status"] = "running"
            return job
        except Exception:
            await conn.rollback()
            raise
        finally:
            await conn.close()

    async def expire_stale_leases(self) -> int:
        conn = await self.database.connect()
        try:
            await conn.execute("BEGIN IMMEDIATE")
            expired = await self._expire_stale_leases(conn, self.clock.now())
            await conn.commit()
            return expired
        except Exception:
            await conn.rollback()
            raise
        finally:
            await conn.close()

    async def _expire_stale_leases(self, conn: Any, now: datetime) -> int:
        now_text = isoformat_utc(now)
        rows = await conn.execute_fetchall(
            """
            SELECT j.job_id, j.attempts, j.max_attempts
            FROM jobs j
            JOIN worker_leases wl ON wl.job_id = j.job_id
            WHERE j.status = 'running'
              AND wl.lease_expires_at = (
                SELECT MAX(lease_expires_at) FROM worker_leases WHERE job_id = j.job_id
              )
              AND wl.lease_expires_at <= ?
            """,
            (now_text,),
        )
        for row in rows:
            next_status = "failed" if int(row["attempts"]) >= int(row["max_attempts"]) else "pending"
            await conn.execute(
                "UPDATE jobs SET status = ?, updated_at = ? WHERE job_id = ?",
                (next_status, now_text, row["job_id"]),
            )
        return len(rows)

    async def complete_job(self, job_id: str, artifact_ref: str | None = None) -> None:
        await self.database.execute(
            "UPDATE jobs SET status = 'completed', updated_at = ?, last_error = ? WHERE job_id = ?",
            (isoformat_utc(self.clock.now()), artifact_ref, job_id),
        )

    async def fail_job(self, job_id: str, failure_reason: str) -> None:
        await self.database.execute(
            "UPDATE jobs SET status = 'failed', updated_at = ?, last_error = ? WHERE job_id = ?",
            (isoformat_utc(self.clock.now()), failure_reason, job_id),
        )

    async def block_job(self, job_id: str, conflict_ref: str) -> None:
        await self.database.execute(
            "UPDATE jobs SET status = 'blocked', updated_at = ?, last_error = ? WHERE job_id = ?",
            (isoformat_utc(self.clock.now()), conflict_ref, job_id),
        )


def parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value).astimezone(timezone.utc)
