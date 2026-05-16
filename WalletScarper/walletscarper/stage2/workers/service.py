from __future__ import annotations

import hashlib
import json
from datetime import timedelta
from typing import Any

from walletscarper.stage2.clock import Clock, SystemClock, isoformat_utc
from walletscarper.stage2.db import Stage2Database
from walletscarper.stage2.db.json import dumps_json
from walletscarper.stage2.ids import new_id
from walletscarper.stage2.jobs import JobQueueService
from walletscarper.stage2.monitoring import MonitoringService
from walletscarper.stage2.parallelism import DEFAULT_PARALLELISM_LIMITS, parse_json_object


ALLOWED_WORKER_TYPES = {
    "token_monitor",
    "position_monitor",
    "wallet_cluster_monitor",
    "strategy_experiment",
    "post_trade_review",
    "memory_curator",
}


class WorkerPoolService:
    """Bounded worker-pool facade over the durable Stage 2 job queue."""

    def __init__(
        self,
        database: Stage2Database,
        *,
        job_queue: JobQueueService | None = None,
        monitoring: MonitoringService | None = None,
        clock: Clock | None = None,
    ) -> None:
        self.database = database
        self.clock = clock or SystemClock()
        self.job_queue = job_queue or JobQueueService(database, clock=self.clock)
        self.monitoring = monitoring or MonitoringService(database, job_queue=self.job_queue, clock=self.clock)

    async def create_parallelism_config(
        self,
        limits: dict[str, int] | None = None,
        *,
        version_label: str = "sprint4-default",
        source: str = "stage2_worker_pool",
        notes: str | None = None,
    ) -> str:
        merged = dict(DEFAULT_PARALLELISM_LIMITS)
        merged.update(limits or {})
        canonical = json.dumps(merged, sort_keys=True, separators=(",", ":"))
        content_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        existing = await self.database.fetchone(
            "SELECT parallelism_config_id FROM parallelism_configs WHERE content_hash = ?",
            (content_hash,),
        )
        if existing:
            return str(existing["parallelism_config_id"])
        config_id = new_id("parallelism_config")
        await self.database.execute(
            """
            INSERT INTO parallelism_configs(
              parallelism_config_id, version_label, content_hash, limits_json,
              source, notes, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                config_id,
                version_label,
                content_hash,
                dumps_json(merged),
                source,
                notes,
                isoformat_utc(self.clock.now()),
            ),
        )
        return config_id

    async def register_worker(
        self,
        *,
        worker_id: str,
        worker_type: str,
        max_concurrent_leases: int = 1,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        if worker_type not in ALLOWED_WORKER_TYPES:
            raise ValueError(f"Unsupported worker type: {worker_type}")
        now = isoformat_utc(self.clock.now())
        existing = await self.database.fetchone("SELECT worker_id FROM worker_registry WHERE worker_id = ?", (worker_id,))
        if existing:
            await self.database.execute(
                """
                UPDATE worker_registry
                SET worker_type = ?, status = 'active', last_heartbeat_at = ?,
                    max_concurrent_leases = ?, metadata_json = ?
                WHERE worker_id = ?
                """,
                (worker_type, now, max_concurrent_leases, dumps_json(metadata or {}), worker_id),
            )
        else:
            await self.database.execute(
                """
                INSERT INTO worker_registry(
                  worker_id, worker_type, status, registered_at, last_heartbeat_at,
                  max_concurrent_leases, metadata_json
                )
                VALUES (?, ?, 'active', ?, ?, ?, ?)
                """,
                (worker_id, worker_type, now, now, max_concurrent_leases, dumps_json(metadata or {})),
            )
        return worker_id

    async def heartbeat_worker(self, worker_id: str) -> None:
        await self.database.execute(
            "UPDATE worker_registry SET last_heartbeat_at = ?, status = 'active' WHERE worker_id = ?",
            (isoformat_utc(self.clock.now()), worker_id),
        )

    async def heartbeat_lease(self, worker_lease_id: str, *, extend_seconds: int | None = None) -> None:
        lease = await self.database.fetchone(
            """
            SELECT wl.*, j.status AS job_status
            FROM worker_leases wl
            JOIN jobs j ON j.job_id = wl.job_id
            WHERE wl.worker_lease_id = ?
            """,
            (worker_lease_id,),
        )
        if not lease:
            raise ValueError(f"WorkerLease not found: {worker_lease_id}")
        if lease["job_status"] != "running":
            raise ValueError("Cannot heartbeat a lease whose job is not running.")
        now = self.clock.now()
        expires_at = now + timedelta(seconds=extend_seconds or 30)
        await self.database.execute(
            "UPDATE worker_leases SET heartbeat_at = ?, lease_expires_at = ? WHERE worker_lease_id = ?",
            (isoformat_utc(now), isoformat_utc(expires_at), worker_lease_id),
        )
        await self.heartbeat_worker(str(lease["worker_id"]))

    async def lease_next_work(
        self,
        *,
        worker_id: str,
        worker_type: str,
        parallelism_config_id: str | None = None,
        lease_seconds: int | None = None,
    ) -> dict[str, Any] | None:
        await self.register_worker(worker_id=worker_id, worker_type=worker_type)
        await self.job_queue.expire_stale_leases()
        limits = await self._limits(parallelism_config_id)
        await self._assert_worker_capacity(worker_id=worker_id, limits=limits)

        job = await self.job_queue.lease_next_job(
            worker_id=worker_id,
            worker_type=worker_type,
            lease_seconds=lease_seconds,
        )
        if not job:
            return None
        payload = parse_json_object(job.get("payload_json"))
        session_id = payload.get("monitoring_session_id")
        if session_id:
            try:
                await self.monitoring.transition_session(
                    str(session_id),
                    "active",
                    reason="worker_lease_acquired",
                    actor=worker_id,
                    related_job_id=str(job["job_id"]),
                    metadata={"worker_type": worker_type},
                )
            except Exception:
                await self.job_queue.block_job(str(job["job_id"]), "session_activation_failed")
                raise
        return job

    async def complete_work(
        self,
        *,
        job_id: str,
        worker_id: str,
        artifact_type: str = "worker_output",
        artifact_ref: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> str:
        artifact_id = await self.record_worker_artifact(
            job_id=job_id,
            worker_id=worker_id,
            artifact_type=artifact_type,
            artifact_ref=artifact_ref,
            payload=payload or {},
            authoritative=False,
        )
        await self.job_queue.complete_job(job_id, artifact_ref=artifact_id)
        await self._transition_session_from_job(job_id, "waiting", "job_completed", worker_id)
        return artifact_id

    async def fail_work(self, *, job_id: str, worker_id: str, failure_reason: str) -> None:
        await self.job_queue.fail_job(job_id, failure_reason)
        await self._transition_session_from_job(job_id, "failed", failure_reason, worker_id)

    async def block_work(self, *, job_id: str, worker_id: str, conflict_ref: str) -> None:
        await self.job_queue.block_job(job_id, conflict_ref)
        await self._transition_session_from_job(job_id, "blocked", conflict_ref, worker_id)

    async def expire_stale_leases(self) -> int:
        expired = await self.job_queue.expire_stale_leases()
        rows = await self.database.fetchall(
            """
            SELECT j.job_id, j.payload_json, j.status
            FROM jobs j
            WHERE j.status IN ('pending', 'failed')
            """
        )
        for row in rows:
            payload = parse_json_object(row["payload_json"])
            session_id = payload.get("monitoring_session_id")
            if not session_id:
                continue
            new_state = "queued" if row["status"] == "pending" else "failed"
            try:
                await self.monitoring.transition_session(
                    str(session_id),
                    new_state,
                    reason="worker_lease_expired",
                    actor="worker_pool",
                    related_job_id=str(row["job_id"]),
                )
            except ValueError:
                pass
        return expired

    async def record_worker_artifact(
        self,
        *,
        job_id: str | None,
        worker_id: str,
        artifact_type: str,
        artifact_ref: str | None = None,
        payload: dict[str, Any] | None = None,
        authoritative: bool = False,
    ) -> str:
        artifact_id = new_id("worker_artifact")
        await self.database.execute(
            """
            INSERT INTO worker_artifacts(
              worker_artifact_id, job_id, worker_id, artifact_type, artifact_ref,
              payload_json, authoritative, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                artifact_id,
                job_id,
                worker_id,
                artifact_type,
                artifact_ref,
                dumps_json(payload or {}),
                1 if authoritative else 0,
                isoformat_utc(self.clock.now()),
            ),
        )
        return artifact_id

    async def queue_metrics(self) -> dict[str, Any]:
        job_rows = await self.database.fetchall(
            """
            SELECT COALESCE(worker_type, 'unassigned') AS worker_type, status, COUNT(*) AS count
            FROM jobs
            GROUP BY COALESCE(worker_type, 'unassigned'), status
            ORDER BY worker_type, status
            """
        )
        lease_rows = await self.database.fetchall(
            """
            SELECT
              SUM(CASE WHEN j.status = 'running' THEN 1 ELSE 0 END) AS active_leases,
              SUM(CASE WHEN wl.lease_expires_at <= ? THEN 1 ELSE 0 END) AS expired_leases
            FROM worker_leases wl
            JOIN jobs j ON j.job_id = wl.job_id
            """,
            (isoformat_utc(self.clock.now()),),
        )
        worker_rows = await self.database.fetchall(
            """
            SELECT worker_type, status, COUNT(*) AS count
            FROM worker_registry
            GROUP BY worker_type, status
            ORDER BY worker_type, status
            """
        )
        return {
            "jobs_by_worker_type_and_status": [dict(row) for row in job_rows],
            "workers_by_type_and_status": [dict(row) for row in worker_rows],
            "active_leases": int((lease_rows[0] or {}).get("active_leases") or 0) if lease_rows else 0,
            "expired_leases": int((lease_rows[0] or {}).get("expired_leases") or 0) if lease_rows else 0,
        }

    async def _transition_session_from_job(self, job_id: str, new_state: str, reason: str, actor: str) -> None:
        job = await self.database.fetchone("SELECT payload_json FROM jobs WHERE job_id = ?", (job_id,))
        if not job:
            return
        session_id = parse_json_object(job["payload_json"]).get("monitoring_session_id")
        if not session_id:
            return
        try:
            await self.monitoring.transition_session(
                str(session_id),
                new_state,
                reason=reason,
                actor=actor,
                related_job_id=job_id,
            )
        except ValueError:
            return

    async def _assert_worker_capacity(self, *, worker_id: str, limits: dict[str, int]) -> None:
        global_row = await self.database.fetchone(
            """
            SELECT COUNT(*) AS count
            FROM worker_leases wl
            JOIN jobs j ON j.job_id = wl.job_id
            WHERE j.status = 'running'
            """
        )
        if int(global_row["count"]) >= int(limits["max_concurrent_worker_leases"]):
            raise ValueError("Max concurrent worker leases reached.")

        worker = await self.database.fetchone(
            "SELECT max_concurrent_leases FROM worker_registry WHERE worker_id = ?",
            (worker_id,),
        )
        worker_limit = int(worker["max_concurrent_leases"]) if worker else 1
        worker_row = await self.database.fetchone(
            """
            SELECT COUNT(*) AS count
            FROM worker_leases wl
            JOIN jobs j ON j.job_id = wl.job_id
            WHERE j.status = 'running' AND wl.worker_id = ?
            """,
            (worker_id,),
        )
        if int(worker_row["count"]) >= worker_limit:
            raise ValueError("Worker concurrent lease limit reached.")

    async def _limits(self, parallelism_config_id: str | None) -> dict[str, int]:
        limits = dict(DEFAULT_PARALLELISM_LIMITS)
        if parallelism_config_id:
            row = await self.database.fetchone(
                "SELECT limits_json FROM parallelism_configs WHERE parallelism_config_id = ?",
                (parallelism_config_id,),
            )
            if row:
                parsed = parse_json_object(row["limits_json"])
                limits.update({key: int(value) for key, value in parsed.items() if isinstance(value, int)})
        return limits

