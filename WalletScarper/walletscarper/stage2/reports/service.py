from __future__ import annotations

from typing import Any

from walletscarper.stage2.clock import Clock, SystemClock, isoformat_utc
from walletscarper.stage2.db import Stage2Database
from walletscarper.stage2.monitoring import MonitoringService
from walletscarper.stage2.strategy import StrategyResearchService
from walletscarper.stage2.workers import WorkerPoolService


class Sprint4ReportService:
    """Read-only queue/session/strategy reporting surface for Sprint 4."""

    def __init__(self, database: Stage2Database, *, clock: Clock | None = None):
        self.database = database
        self.clock = clock or SystemClock()
        self.workers = WorkerPoolService(database, clock=self.clock)
        self.monitoring = MonitoringService(database, clock=self.clock)
        self.strategy = StrategyResearchService(database, clock=self.clock)

    async def snapshot(self) -> dict[str, Any]:
        queue = await self.workers.queue_metrics()
        sessions = await self.monitoring.session_metrics()
        latest_leaderboard = await self.database.fetchall(
            """
            SELECT sms.*
            FROM strategy_metric_snapshots sms
            JOIN (
              SELECT strategy_version_id, MAX(calculated_at) AS calculated_at
              FROM strategy_metric_snapshots
              GROUP BY strategy_version_id
            ) latest
              ON latest.strategy_version_id = sms.strategy_version_id
             AND latest.calculated_at = sms.calculated_at
            ORDER BY sms.net_pnl DESC, sms.closed_trade_count DESC
            """
        )
        return {
            "generated_at": isoformat_utc(self.clock.now()),
            "queue": queue,
            "sessions": sessions,
            "open_paper_positions_monitored": await self._open_monitored_positions(),
            "strategy_experiments_by_status": await self._counts("strategy_experiments", "status"),
            "latest_leaderboard_v1": [dict(row) for row in latest_leaderboard],
            "strategy_decisions_by_type": await self._counts("strategy_decisions", "decision_type"),
            "post_trade_review_count": await self._count_all("post_trade_reviews"),
            "memory_proposals_by_status": await self._counts("memory_proposals", "status"),
            "memory_curation_count": await self._count_all("memory_curation_events"),
            "conflict_reviews_by_status": await self._counts("conflict_reviews", "status"),
            "warnings": await self._warnings(latest_leaderboard),
        }

    async def _open_monitored_positions(self) -> int:
        row = await self.database.fetchone(
            """
            SELECT COUNT(DISTINCT pp.position_id) AS count
            FROM paper_positions pp
            JOIN monitoring_sessions ms ON ms.subject_id = pp.position_id
            WHERE ms.subject_type = 'paper_position'
              AND ms.status IN ('queued', 'active', 'waiting', 'blocked')
              AND pp.position_id NOT IN (SELECT position_id FROM trade_outcomes)
            """
        )
        return int(row["count"]) if row else 0

    async def _counts(self, table: str, column: str) -> list[dict[str, Any]]:
        return await self.database.fetchall(
            f"SELECT {column} AS key, COUNT(*) AS count FROM {table} GROUP BY {column} ORDER BY {column}"
        )

    async def _count_all(self, table: str) -> int:
        row = await self.database.fetchone(f"SELECT COUNT(*) AS count FROM {table}")
        return int(row["count"]) if row else 0

    async def _warnings(self, leaderboard: list[dict[str, Any]]) -> list[str]:
        warnings: list[str] = []
        failed_jobs = await self.database.fetchone("SELECT COUNT(*) AS count FROM jobs WHERE status = 'failed'")
        if failed_jobs and int(failed_jobs["count"]):
            warnings.append("failed_jobs_present")
        for row in leaderboard:
            if row.get("sample_size_warning"):
                warnings.append(f"{row['strategy_version_id']}:low_sample_size")
            if int(row.get("degraded_outcome_count") or 0):
                warnings.append(f"{row['strategy_version_id']}:degraded_outcomes")
            if row.get("concentration_warning"):
                warnings.append(f"{row['strategy_version_id']}:concentration_warning")
        return warnings

