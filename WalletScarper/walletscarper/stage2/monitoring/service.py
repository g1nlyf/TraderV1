from __future__ import annotations

from datetime import timedelta
from typing import Any

from walletscarper.stage2.clock import Clock, SystemClock, isoformat_utc
from walletscarper.stage2.db import Stage2Database
from walletscarper.stage2.db.json import dumps_json
from walletscarper.stage2.ids import new_id
from walletscarper.stage2.jobs import JobQueueService
from walletscarper.stage2.monitoring.repository import MonitoringRepository
from walletscarper.stage2.parallelism import DEFAULT_PARALLELISM_LIMITS, parse_json_object


TERMINAL_SESSION_STATES = {"completed", "failed", "expired", "archived"}
VALID_SESSION_STATES = TERMINAL_SESSION_STATES | {"created", "queued", "active", "waiting", "blocked", "pending"}
ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "pending": {"queued", "active", "waiting", "blocked", "completed", "failed", "expired", "archived"},
    "created": {"queued", "active", "waiting", "blocked", "completed", "failed", "expired", "archived"},
    "queued": {"active", "waiting", "blocked", "completed", "failed", "expired", "archived"},
    "waiting": {"queued", "active", "blocked", "completed", "failed", "expired", "archived"},
    "active": {"waiting", "blocked", "completed", "failed", "expired", "archived"},
    "blocked": {"queued", "waiting", "completed", "failed", "expired", "archived"},
    "completed": {"archived"},
    "failed": {"archived"},
    "expired": {"archived"},
    "archived": set(),
}


class MonitoringService:
    """Deterministic Sprint 4 monitoring/session state machine.

    This service coordinates monitoring sessions and queue jobs. It records
    transitions and conflict artifacts, but it does not create signals, risk
    checks, paper ledger rows, outcomes, or strategy decisions.
    """

    def __init__(
        self,
        database: Stage2Database,
        *,
        repository: MonitoringRepository | None = None,
        job_queue: JobQueueService | None = None,
        clock: Clock | None = None,
    ) -> None:
        self.database = database
        self.clock = clock or SystemClock()
        self.repository = repository or MonitoringRepository(database, clock=self.clock)
        self.job_queue = job_queue or JobQueueService(database, clock=self.clock)

    async def create_session(
        self,
        *,
        session_type: str,
        subject_type: str,
        subject_id: str,
        priority: int = 100,
        strategy_version_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        actor: str = "monitoring_service",
    ) -> str:
        session_id = await self.repository.create_session(
            session_type=session_type,
            subject_type=subject_type,
            subject_id=subject_id,
            priority=priority,
            status="created",
            strategy_version_id=strategy_version_id,
            metadata=metadata or {},
        )
        await self._record_transition(
            session_id=session_id,
            previous_state="none",
            new_state="created",
            reason="session_created",
            actor=actor,
            metadata=metadata or {},
        )
        return session_id

    async def transition_session(
        self,
        session_id: str,
        new_state: str,
        *,
        reason: str,
        actor: str,
        related_job_id: str | None = None,
        audit_event_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        if new_state not in VALID_SESSION_STATES:
            raise ValueError(f"Invalid monitoring session state: {new_state}")
        session = await self._get_session(session_id)
        previous_state = str(session["status"])
        if previous_state in TERMINAL_SESSION_STATES and new_state != "archived":
            raise ValueError(f"Cannot transition terminal session {session_id} from {previous_state} to {new_state}.")
        if new_state not in ALLOWED_TRANSITIONS.get(previous_state, set()):
            raise ValueError(f"Invalid monitoring session transition {previous_state} -> {new_state}.")
        if new_state == "active":
            await self._assert_session_can_be_active(session, related_job_id)

        now = isoformat_utc(self.clock.now())
        stopped_at = now if new_state in TERMINAL_SESSION_STATES else session.get("stopped_at")
        stop_reason = reason if new_state in TERMINAL_SESSION_STATES else session.get("stop_reason")
        await self.database.execute(
            """
            UPDATE monitoring_sessions
            SET status = ?, updated_at = ?, stopped_at = ?, stop_reason = ?
            WHERE monitoring_session_id = ?
            """,
            (new_state, now, stopped_at, stop_reason, session_id),
        )
        return await self._record_transition(
            session_id=session_id,
            previous_state=previous_state,
            new_state=new_state,
            reason=reason,
            actor=actor,
            related_job_id=related_job_id,
            audit_event_id=audit_event_id,
            metadata=metadata or {},
        )

    async def create_monitoring_job(
        self,
        session_id: str,
        *,
        job_type: str,
        worker_type: str,
        priority: int | None = None,
        max_attempts: int = 3,
        payload: dict[str, Any] | None = None,
        parallelism_config_id: str | None = None,
    ) -> str:
        session = await self._get_session(session_id)
        if session["status"] in TERMINAL_SESSION_STATES:
            raise ValueError("Terminal monitoring sessions cannot receive new jobs.")

        duplicate = await self.database.fetchone(
            """
            SELECT job_id FROM jobs
            WHERE target_ref = ?
              AND worker_type = ?
              AND status IN ('pending', 'running')
            LIMIT 1
            """,
            (session["subject_id"], worker_type),
        )
        if duplicate:
            await self.create_conflict_review(
                subject_type=session["subject_type"],
                subject_id=session["subject_id"],
                conflicting_action="duplicate_monitoring_job",
                reason="A pending or running monitoring job already exists for this subject and worker type.",
                involved_refs=[session_id, duplicate["job_id"]],
            )
            raise ValueError("Duplicate active monitoring job detected.")

        limits = await self._limits(parallelism_config_id)
        if not await self._capacity_available(session, limits):
            scheduled_at = self.clock.now() + timedelta(minutes=5)
            await self.transition_session(
                session_id,
                "waiting",
                reason="parallelism_capacity_exhausted",
                actor="monitoring_service",
                metadata={"parallelism_config_id": parallelism_config_id},
            )
        else:
            scheduled_at = self.clock.now()
            if session["status"] == "created":
                await self.transition_session(session_id, "queued", reason="job_queued", actor="monitoring_service")

        resolved_priority = priority if priority is not None else self._priority_for(session["session_type"], limits)
        body = dict(payload or {})
        body.setdefault("monitoring_session_id", session_id)
        body.setdefault("session_type", session["session_type"])
        job_id = await self.job_queue.create_job(
            job_type=job_type,
            payload=body,
            worker_type=worker_type,
            target_ref=session["subject_id"],
            priority=resolved_priority,
            max_attempts=max_attempts,
            scheduled_at=scheduled_at,
        )
        return job_id

    async def complete_closed_position_sessions(self) -> int:
        rows = await self.database.fetchall(
            """
            SELECT ms.monitoring_session_id
            FROM monitoring_sessions ms
            JOIN paper_positions pp ON pp.position_id = ms.subject_id
            JOIN trade_outcomes tout ON tout.position_id = pp.position_id
            WHERE ms.subject_type = 'paper_position'
              AND ms.status NOT IN ('completed', 'failed', 'expired', 'archived')
            """
        )
        for row in rows:
            await self.transition_session(
                row["monitoring_session_id"],
                "completed",
                reason="position_has_trade_outcome",
                actor="monitoring_service",
            )
        return len(rows)

    async def create_conflict_review(
        self,
        *,
        subject_type: str,
        subject_id: str,
        conflicting_action: str,
        reason: str,
        involved_refs: list[str] | None = None,
        audit_event_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        conflict_id = new_id("conflict_review")
        await self.database.execute(
            """
            INSERT INTO conflict_reviews(
              conflict_review_id, subject_type, subject_id, conflicting_action,
              reason, status, audit_event_id, created_at, metadata_json,
              involved_refs_json
            )
            VALUES (?, ?, ?, ?, ?, 'open', ?, ?, ?, ?)
            """,
            (
                conflict_id,
                subject_type,
                subject_id,
                conflicting_action,
                reason,
                audit_event_id,
                isoformat_utc(self.clock.now()),
                dumps_json(metadata or {}),
                dumps_json(involved_refs or []),
            ),
        )
        return conflict_id

    async def resolve_conflict_review(
        self,
        conflict_review_id: str,
        *,
        resolution: str,
        resolver: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        row = await self.database.fetchone(
            "SELECT conflict_review_id FROM conflict_reviews WHERE conflict_review_id = ?",
            (conflict_review_id,),
        )
        if not row:
            raise ValueError(f"ConflictReview not found: {conflict_review_id}")
        await self.database.execute(
            """
            UPDATE conflict_reviews
            SET status = 'resolved', resolution = ?, resolver = ?,
                resolution_metadata_json = ?, resolved_at = ?
            WHERE conflict_review_id = ?
            """,
            (resolution, resolver, dumps_json(metadata or {}), isoformat_utc(self.clock.now()), conflict_review_id),
        )

    async def session_metrics(self) -> dict[str, Any]:
        rows = await self.database.fetchall(
            """
            SELECT session_type, status, COUNT(*) AS count
            FROM monitoring_sessions
            GROUP BY session_type, status
            ORDER BY session_type, status
            """
        )
        return {
            "sessions_by_type_and_status": [dict(row) for row in rows],
            "open_conflict_reviews": await self._count("conflict_reviews", "status = 'open'"),
        }

    async def _get_session(self, session_id: str) -> dict[str, Any]:
        session = await self.database.fetchone(
            "SELECT * FROM monitoring_sessions WHERE monitoring_session_id = ?",
            (session_id,),
        )
        if not session:
            raise ValueError(f"MonitoringSession not found: {session_id}")
        return session

    async def _record_transition(
        self,
        *,
        session_id: str,
        previous_state: str,
        new_state: str,
        reason: str,
        actor: str,
        related_job_id: str | None = None,
        audit_event_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        transition_id = new_id("monitoring_session_transition")
        await self.database.execute(
            """
            INSERT INTO monitoring_session_transitions(
              monitoring_session_transition_id, monitoring_session_id, previous_state,
              new_state, reason, actor, created_at, related_job_id,
              audit_event_id, metadata_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                transition_id,
                session_id,
                previous_state,
                new_state,
                reason,
                actor,
                isoformat_utc(self.clock.now()),
                related_job_id,
                audit_event_id,
                dumps_json(metadata or {}),
            ),
        )
        return transition_id

    async def _assert_session_can_be_active(self, session: dict[str, Any], related_job_id: str | None) -> None:
        if session["subject_type"] == "paper_position":
            closed = await self.database.fetchone(
                "SELECT outcome_id FROM trade_outcomes WHERE position_id = ? LIMIT 1",
                (session["subject_id"],),
            )
            if closed:
                raise ValueError("Closed paper positions cannot be reactivated for monitoring.")
        active = await self.database.fetchone(
            """
            SELECT j.job_id
            FROM jobs j
            WHERE j.target_ref = ?
              AND j.status = 'running'
              AND (? IS NULL OR j.job_id != ?)
            LIMIT 1
            """,
            (session["subject_id"], related_job_id, related_job_id),
        )
        if active:
            raise ValueError("Another worker/job already owns this active monitoring subject.")

    async def _capacity_available(self, session: dict[str, Any], limits: dict[str, int]) -> bool:
        key = {
            "token_monitoring": "max_active_token_monitoring_sessions",
            "wallet_cluster_monitoring": "max_active_wallet_cluster_sessions",
            "strategy_experiment": "max_active_strategy_experiments",
            "browser_research": "max_active_browser_research_jobs",
        }.get(str(session["session_type"]))
        if not key:
            return True
        row = await self.database.fetchone(
            """
            SELECT COUNT(*) AS count
            FROM monitoring_sessions
            WHERE session_type = ?
              AND status IN ('queued', 'active', 'waiting')
            """,
            (session["session_type"],),
        )
        return int(row["count"]) < int(limits.get(key, DEFAULT_PARALLELISM_LIMITS[key]))

    async def _limits(self, parallelism_config_id: str | None) -> dict[str, int]:
        limits = dict(DEFAULT_PARALLELISM_LIMITS)
        if parallelism_config_id:
            row = await self.database.fetchone(
                "SELECT limits_json FROM parallelism_configs WHERE parallelism_config_id = ?",
                (parallelism_config_id,),
            )
            if row:
                limits.update({k: int(v) for k, v in parse_json_object(row["limits_json"]).items() if isinstance(v, int)})
        return limits

    def _priority_for(self, session_type: str, limits: dict[str, int]) -> int:
        if session_type == "paper_position_monitoring":
            return int(limits["position_monitoring_priority"])
        if session_type == "strategy_experiment":
            return int(limits["strategy_experiment_priority"])
        if session_type == "wallet_cluster_monitoring":
            return int(limits["wallet_cluster_monitoring_priority"])
        return int(limits["token_monitoring_priority"])

    async def _count(self, table: str, where: str) -> int:
        row = await self.database.fetchone(f"SELECT COUNT(*) AS count FROM {table} WHERE {where}")
        return int(row["count"]) if row else 0

