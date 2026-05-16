from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from walletscarper.stage2.audit import AuditLog
from walletscarper.stage2.clock import FixedClock
from walletscarper.stage2.config import load_stage2_settings
from walletscarper.stage2.config_snapshots import ConfigSnapshotRepository
from walletscarper.stage2.db import Stage2Database
from walletscarper.stage2.db.migrations import MIGRATIONS
from walletscarper.stage2.domain import (
    DomainRepository,
    MemoryEntry,
    PaperFill,
    PaperOrder,
    PaperPosition,
    PostTradeReview,
    RiskCheck,
    Signal,
    StrategyVersion,
    TradeOutcome,
    TradeThesis,
)
from walletscarper.stage2.events import RawSourceEventLog
from walletscarper.stage2.hermes_integration import project_health_check
from walletscarper.stage2.jobs import JobQueueService
from walletscarper.stage2.monitoring import MonitoringRepository
from walletscarper.stage2.paper_trading import PaperOrderRejected, Sprint1PaperTradingService


def run(coro):
    return asyncio.run(coro)


def test_config_loads_in_test_environment(tmp_path: Path) -> None:
    settings = load_stage2_settings(environment="test", database_path=tmp_path / "stage2.sqlite3")
    assert settings.environment == "test"
    assert settings.is_test
    assert settings.database_url.endswith("stage2.sqlite3")
    assert settings.feature_flags["trading_workflows_enabled"] is False


def test_migration_database_setup_works(tmp_path: Path) -> None:
    async def scenario() -> None:
        database = await migrated_database(tmp_path)
        row = await database.fetchone("SELECT COUNT(*) AS c FROM stage2_schema_migrations")
        assert row and row["c"] == len(MIGRATIONS)
        tables = await database.fetchall("SELECT name FROM sqlite_master WHERE type='table'")
        names = {row["name"] for row in tables}
        required = {
            "raw_source_events",
            "audit_events",
            "config_snapshots",
            "risk_limit_snapshots",
            "strategy_config_snapshots",
            "promotion_criteria_snapshots",
            "acceptance_runs",
            "signals",
            "trade_theses",
            "risk_checks",
            "paper_orders",
            "paper_fills",
            "paper_positions",
            "exit_decisions",
            "trade_outcomes",
            "post_trade_reviews",
            "memory_entries",
            "jobs",
            "worker_leases",
            "monitoring_sessions",
            "conflict_reviews",
        }
        assert required.issubset(names)

    run(scenario())


def test_config_snapshot_creation_and_immutability(tmp_path: Path) -> None:
    async def scenario() -> None:
        database = await migrated_database(tmp_path)
        settings = load_stage2_settings(environment="test", database_path=database.path)
        repo = ConfigSnapshotRepository(database)
        config_id = await repo.create_config_snapshot(source="test", settings=settings)
        risk_id = await repo.create_risk_limit_snapshot(config_snapshot_id=config_id, limits={"max_open_positions": 1})
        strategy_id = await repo.create_strategy_config_snapshot(
            config_snapshot_id=config_id,
            strategy_name="sprint1-contract-only",
            strategy_version_label="v0",
            thresholds={"min_confidence": "not-configured"},
        )
        criteria_id = await repo.create_promotion_criteria_snapshot(
            config_snapshot_id=config_id,
            criteria={"min_forward_paper_trades": 100}
        )
        run_id = await repo.create_acceptance_run(
            config_snapshot_id=config_id,
            risk_limit_snapshot_id=risk_id,
            promotion_criteria_snapshot_id=criteria_id,
        )

        assert config_id and risk_id and strategy_id and criteria_id and run_id
        with pytest.raises(Exception, match="append-only"):
            await database.execute(
                "UPDATE config_snapshots SET source = 'mutated' WHERE config_snapshot_id = ?",
                (config_id,),
            )

    run(scenario())


def test_raw_source_and_audit_events_are_append_only(tmp_path: Path) -> None:
    async def scenario() -> None:
        database = await migrated_database(tmp_path)
        raw_log = RawSourceEventLog(database)
        audit = AuditLog(database)
        raw_id = await raw_log.append(
            source_name="test_source",
            source_type="unit_test",
            external_id="evt-1",
            payload={"value": 1},
            confidence="high",
            quality_metadata={"completeness": "synthetic"},
        )
        audit_id = await audit.append(
            actor="test",
            action="created",
            entity_type="raw_source_event",
            entity_id=raw_id,
            payload={"raw_id": raw_id},
        )

        with pytest.raises(Exception, match="append-only"):
            await database.execute("DELETE FROM raw_source_events WHERE raw_source_event_id = ?", (raw_id,))
        with pytest.raises(Exception, match="append-only"):
            await database.execute("UPDATE audit_events SET action = 'mutated' WHERE audit_event_id = ?", (audit_id,))

    run(scenario())


def test_core_domain_contract_models_exist() -> None:
    now = datetime.now(timezone.utc)
    StrategyVersion(strategy_version_id="sv", strategy_config_snapshot_id="sc", created_at=now)
    Signal(
        signal_id="sig",
        created_at=now,
        data_as_of=now,
        token_id="token",
        strategy_version_id="sv",
        strategy_config_snapshot_id="sc",
        invalidation_condition="invalid",
        expected_holding_time="5m",
    )
    TradeThesis(
        thesis_id="thesis",
        signal_id="sig",
        entry_reason="pre-trade reason",
        exit_plan="exit plan",
        expected_holding_time="5m",
        proof_wrong="proof",
        created_at=now,
    )
    RiskCheck(
        risk_check_id="risk",
        check_scope="entry",
        subject_type="signal",
        subject_id="sig",
        risk_limit_snapshot_id="rl",
        config_snapshot_id="cfg",
        data_as_of=now,
        passed=True,
        created_at=now,
    )
    PaperOrder(
        paper_order_id="po",
        signal_id="sig",
        risk_check_id="risk",
        strategy_version_id="sv",
        side="buy",
        intended_size=1,
        created_at=now,
    )
    PaperFill(
        paper_fill_id="pf",
        paper_order_id="po",
        fill_time=now,
        latency_assumption="not-yet-implemented",
        liquidity_constraint="not-yet-implemented",
    )
    PaperPosition(
        position_id="pos",
        token_id="token",
        strategy_version_id="sv",
        entry_order_id="po",
        entry_fill_id="pf",
        size=1,
        cost_basis=1,
        opened_at=now,
    )
    TradeOutcome(
        outcome_id="out",
        position_id="pos",
        exit_decision_id="exit",
        gross_pnl=0,
        net_pnl=0,
        fees=0,
        slippage=0,
        duration_seconds=0,
        max_drawdown=0,
        calculated_at=now,
    )
    PostTradeReview(outcome_id="out", post_trade_review_id="review", position_id="pos", reviewer="test", created_at=now)
    MemoryEntry(memory_entry_id="mem", claim="claim", evidence_grade="synthetic", created_at=now, created_by="test")


def test_paper_order_requires_passed_matching_risk_check(tmp_path: Path) -> None:
    async def scenario() -> None:
        database, config_id, risk_limit_id, strategy_config_id, signal_id = await seeded_signal(tmp_path)
        domain = DomainRepository(database)
        service = Sprint1PaperTradingService(database, domain)

        with pytest.raises(PaperOrderRejected, match="existing RiskCheck"):
            await service.create_paper_order(signal_id=signal_id, risk_check_id="missing", side="buy", intended_size=1)

        failed_risk = await domain.create_risk_check(
            check_scope="entry",
            subject_type="signal",
            subject_id=signal_id,
            risk_limit_snapshot_id=risk_limit_id,
            config_snapshot_id=config_id,
            passed=False,
            veto_reason="synthetic veto",
        )
        with pytest.raises(PaperOrderRejected, match="passed RiskCheck"):
            await service.create_paper_order(signal_id=signal_id, risk_check_id=failed_risk, side="buy", intended_size=1)

        other_signal = await domain.create_signal(
            token_id="other",
            strategy_version_id=(await database.fetchone("SELECT strategy_version_id FROM strategy_versions"))["strategy_version_id"],
            strategy_config_snapshot_id=strategy_config_id,
            invalidation_condition="invalid",
            expected_holding_time="5m",
        )
        incompatible_risk = await domain.create_risk_check(
            check_scope="entry",
            subject_type="signal",
            subject_id=other_signal,
            risk_limit_snapshot_id=risk_limit_id,
            config_snapshot_id=config_id,
            passed=True,
        )
        with pytest.raises(PaperOrderRejected, match="does not belong"):
            await service.create_paper_order(signal_id=signal_id, risk_check_id=incompatible_risk, side="buy", intended_size=1)

        passed_risk = await domain.create_risk_check(
            check_scope="entry",
            subject_type="signal",
            subject_id=signal_id,
            risk_limit_snapshot_id=risk_limit_id,
            config_snapshot_id=config_id,
            passed=True,
        )
        order_id = await service.create_paper_order(
            signal_id=signal_id,
            risk_check_id=passed_risk,
            side="buy",
            intended_size=1,
            intended_price_ref="market_snapshot:future",
        )
        assert await database.fetchone("SELECT * FROM paper_orders WHERE paper_order_id = ?", (order_id,))

    run(scenario())


def test_job_lease_acquisition_double_lease_expiry_and_max_attempts(tmp_path: Path) -> None:
    async def scenario() -> None:
        base_time = datetime(2026, 5, 14, tzinfo=timezone.utc)
        database = await migrated_database(tmp_path, FixedClock(base_time))
        settings = load_stage2_settings(environment="test", database_path=database.path, job_lease_seconds=1)
        queue = JobQueueService(database, settings=settings, clock=FixedClock(base_time))
        job_id = await queue.create_job(job_type="token_watch", payload={"token": "T"}, priority=10, max_attempts=2)
        first = await queue.lease_next_job(worker_id="worker-a", worker_type="token")
        assert first and first["job_id"] == job_id
        assert await queue.lease_next_job(worker_id="worker-b", worker_type="token") is None

        later_queue = JobQueueService(database, settings=settings, clock=FixedClock(base_time + timedelta(seconds=2)))
        second = await later_queue.lease_next_job(worker_id="worker-b", worker_type="token")
        assert second and second["job_id"] == job_id
        row = await database.fetchone("SELECT attempts, status FROM jobs WHERE job_id = ?", (job_id,))
        assert row == {"attempts": 2, "status": "running"}

        expired_queue = JobQueueService(database, settings=settings, clock=FixedClock(base_time + timedelta(seconds=4)))
        assert await expired_queue.expire_stale_leases() == 1
        assert await expired_queue.lease_next_job(worker_id="worker-c", worker_type="token") is None
        row = await database.fetchone("SELECT attempts, status FROM jobs WHERE job_id = ?", (job_id,))
        assert row == {"attempts": 2, "status": "failed"}

    run(scenario())


def test_monitoring_session_and_conflict_review_skeleton(tmp_path: Path) -> None:
    async def scenario() -> None:
        database = await migrated_database(tmp_path)
        repo = MonitoringRepository(database)
        session_id = await repo.create_session(
            session_type="token_watch",
            subject_type="token",
            subject_id="token-1",
            metadata={"scope": "sprint1"},
        )
        conflict_id = await repo.create_conflict_review(
            subject_type="signal",
            subject_id="signal-1",
            conflicting_action="create_paper_order",
            reason="synthetic conflict",
        )
        assert await database.fetchone("SELECT * FROM monitoring_sessions WHERE monitoring_session_id = ?", (session_id,))
        assert await database.fetchone("SELECT * FROM conflict_reviews WHERE conflict_review_id = ?", (conflict_id,))

    run(scenario())


def test_project_health_check_is_harmless_and_read_only(tmp_path: Path) -> None:
    async def scenario() -> None:
        database = await migrated_database(tmp_path)
        tables = ["jobs", "audit_events", "raw_source_events", "risk_checks", "paper_orders", "paper_fills"]
        before = await database.table_counts(tables)
        settings = load_stage2_settings(environment="test", database_path=database.path)
        result = await project_health_check(settings=settings, database=database)
        after = await database.table_counts(tables)
        assert result["tool"] == "project.health_check"
        assert result["database_connectivity"] == "ok"
        assert result["migration_status"] == "current"
        assert before == after

    run(scenario())


def test_no_live_execution_private_key_signer_swap_or_dex_path_added() -> None:
    package_root = Path(__file__).resolve().parents[1] / "walletscarper"
    risky = [
        "private_key",
        "secret_key",
        "seed phrase",
        "signtransaction",
        "sendtransaction",
        "versionedtransaction",
        "swap adapter",
        "dex transaction",
        "jupiter",
        "raydium",
    ]
    offenders: list[str] = []
    for path in package_root.rglob("*.py"):
        text = path.read_text(encoding="utf-8").lower()
        for term in risky:
            if term in text:
                offenders.append(f"{path}:{term}")
    assert offenders == []


async def migrated_database(tmp_path: Path, clock: FixedClock | None = None) -> Stage2Database:
    settings = load_stage2_settings(environment="test", database_path=tmp_path / "stage2.sqlite3")
    database = Stage2Database(settings, clock=clock)
    await database.migrate()
    return database


async def seeded_signal(tmp_path: Path) -> tuple[Stage2Database, str, str, str, str]:
    database = await migrated_database(tmp_path)
    settings = load_stage2_settings(environment="test", database_path=database.path)
    snapshots = ConfigSnapshotRepository(database)
    config_id = await snapshots.create_config_snapshot(source="test", settings=settings)
    risk_limit_id = await snapshots.create_risk_limit_snapshot(config_snapshot_id=config_id, limits={"max_open_positions": 1})
    strategy_config_id = await snapshots.create_strategy_config_snapshot(
        config_snapshot_id=config_id,
        strategy_name="contract-only",
        strategy_version_label="v0",
    )
    domain = DomainRepository(database)
    strategy_version_id = await domain.create_strategy_version(strategy_config_snapshot_id=strategy_config_id)
    signal_id = await domain.create_signal(
        token_id="token-1",
        strategy_version_id=strategy_version_id,
        strategy_config_snapshot_id=strategy_config_id,
        invalidation_condition="invalid",
        expected_holding_time="5m",
    )
    await domain.create_trade_thesis(
        signal_id=signal_id,
        entry_reason="pre-entry synthetic thesis",
        exit_plan="exit later",
        expected_holding_time="5m",
        proof_wrong="invalidated",
    )
    return database, config_id, risk_limit_id, strategy_config_id, signal_id
