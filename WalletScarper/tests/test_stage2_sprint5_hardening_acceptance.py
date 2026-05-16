from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from walletscarper.stage2.acceptance import (
    AcceptanceRunService,
    InvariantChecker,
    InvariantFinding,
    OperationalHealthService,
    ShadowModeAssessmentService,
    render_acceptance_report,
)
from walletscarper.stage2.clock import FixedClock
from walletscarper.stage2.config import load_stage2_settings
from walletscarper.stage2.config_snapshots import ConfigSnapshotRepository
from walletscarper.stage2.db import Stage2Database
from walletscarper.stage2.domain import DomainRepository


BASE_TIME = datetime(2026, 5, 14, 12, 0, tzinfo=timezone.utc)


def run(coro):
    return asyncio.run(coro)


async def sprint5_db(tmp_path: Path) -> tuple[Stage2Database, FixedClock]:
    clock = FixedClock(BASE_TIME)
    settings = load_stage2_settings(
        environment="test",
        database_path=tmp_path / "stage2_sprint5.sqlite3",
        app_version="test",
    )
    database = Stage2Database(settings, clock=clock)
    await database.migrate()
    return database, clock


def test_sprint5_migration_acceptance_tables_exist(tmp_path: Path) -> None:
    async def scenario() -> None:
        database, _clock = await sprint5_db(tmp_path)
        rows = await database.fetchall(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
              AND name IN (
                'acceptance_run_executions',
                'acceptance_run_events',
                'invariant_violations',
                'operational_health_snapshots',
                'shadow_mode_gap_reports',
                'final_acceptance_reports'
              )
            """
        )
        assert {row["name"] for row in rows} == {
            "acceptance_run_executions",
            "acceptance_run_events",
            "invariant_violations",
            "operational_health_snapshots",
            "shadow_mode_gap_reports",
            "final_acceptance_reports",
        }

    run(scenario())


def test_invariant_checker_records_authority_violation_without_repairing_state(tmp_path: Path) -> None:
    async def scenario() -> None:
        database, clock = await sprint5_db(tmp_path)
        snapshots = ConfigSnapshotRepository(database, clock=clock)
        config_id = await snapshots.create_config_snapshot(source="test", settings={"test": True})
        risk_limit_id = await snapshots.create_risk_limit_snapshot(config_snapshot_id=config_id, limits={})
        strategy_config_id = await snapshots.create_strategy_config_snapshot(
            config_snapshot_id=config_id,
            strategy_name="test",
            strategy_version_label="v1",
        )
        domain = DomainRepository(database, clock=clock)
        strategy_id = await domain.create_strategy_version(strategy_config_snapshot_id=strategy_config_id)
        signal_id = await domain.create_signal(
            token_id="token-1",
            strategy_version_id=strategy_id,
            strategy_config_snapshot_id=strategy_config_id,
            source_refs=["fixture-raw-ref"],
            confidence="medium",
        )
        await domain.create_risk_check(
            check_scope="entry",
            subject_type="signal",
            subject_id=signal_id,
            risk_limit_snapshot_id=risk_limit_id,
            config_snapshot_id=config_id,
            passed=True,
            created_by_service="manual_test_path",
        )

        result = await InvariantChecker(database, clock=clock).run_all(acceptance_run_id=None)
        violation = await database.fetchone(
            "SELECT * FROM invariant_violations WHERE invariant_name = 'authoritative_risk_checks_are_deterministic'"
        )
        risk_count = await database.table_counts(["risk_checks"])

        assert result["critical_count"] >= 1
        assert violation is not None
        assert risk_count["risk_checks"] == 1

    run(scenario())


def test_fixture_acceptance_run_records_e2e_paper_flow_gap_and_report(tmp_path: Path) -> None:
    async def scenario() -> None:
        database, clock = await sprint5_db(tmp_path)
        settings = load_stage2_settings(
            environment="test",
            database_path=tmp_path / "stage2_sprint5.sqlite3",
            app_version="test",
        )
        result = await AcceptanceRunService(database, settings=settings, clock=clock).run_acceptance(run_mode="fixture_replay")
        counts = await database.table_counts(
            [
                "raw_source_events",
                "token_profiles",
                "wallet_profiles",
                "signals",
                "no_trade_signals",
                "risk_checks",
                "paper_orders",
                "paper_fills",
                "paper_positions",
                "exit_decisions",
                "trade_outcomes",
                "post_trade_reviews",
                "memory_proposals",
                "memory_entries",
                "strategy_metric_snapshots",
                "strategy_decisions",
                "shadow_mode_gap_reports",
                "final_acceptance_reports",
            ]
        )
        failed_fill = await database.fetchone("SELECT * FROM paper_fills WHERE failed_fill_reason IS NOT NULL")
        decision = await database.fetchone("SELECT * FROM strategy_decisions")
        rendered = render_acceptance_report(result)

        assert result["status"] == "gap_report_required"
        assert result["decision"] == "accepted_with_gaps"
        assert result["invariant_result"]["critical_count"] == 0
        assert result["shadow"]["status"] == "gap_report_required"
        assert counts["raw_source_events"] >= 2
        assert counts["signals"] >= 2
        assert counts["no_trade_signals"] == 1
        assert counts["risk_checks"] >= 3
        assert counts["paper_orders"] >= 3
        assert counts["paper_fills"] >= 3
        assert counts["paper_positions"] == 1
        assert counts["exit_decisions"] == 1
        assert counts["trade_outcomes"] == 1
        assert counts["post_trade_reviews"] == 1
        assert counts["memory_proposals"] == 1
        assert counts["memory_entries"] == 1
        assert counts["strategy_metric_snapshots"] >= 1
        assert decision and decision["decision_type"] == "insufficient_data"
        assert failed_fill and failed_fill["failed_fill_reason"] == "stale_market_snapshot"
        assert counts["shadow_mode_gap_reports"] == 1
        assert counts["final_acceptance_reports"] == 1
        assert "failed_fills:" in rendered
        assert "shadow_status: gap_report_required" in rendered

    run(scenario())


def test_critical_invariant_violation_fails_acceptance_reporting(tmp_path: Path) -> None:
    async def scenario() -> None:
        database, clock = await sprint5_db(tmp_path)
        settings = load_stage2_settings(
            environment="test",
            database_path=tmp_path / "stage2_sprint5.sqlite3",
            app_version="test",
        )
        service = AcceptanceRunService(database, settings=settings, clock=clock)
        configured = await service.configure_run(run_mode="shadow_gap_assessment")
        invariant = InvariantChecker(database, clock=clock)
        await invariant.record_violation(
            acceptance_run_id=configured["acceptance_run_id"],
            finding=InvariantFinding(
                "test_critical_invariant",
                "critical",
                "synthetic critical violation for acceptance gating",
                "remediate synthetic fixture",
                {"fixture": True},
            ),
        )
        health = await OperationalHealthService(database, clock=clock).capture_snapshot(
            acceptance_run_id=configured["acceptance_run_id"]
        )
        shadow = await ShadowModeAssessmentService(database, clock=clock).assess(
            acceptance_run_id=configured["acceptance_run_id"]
        )
        final = await service.generate_final_report(
            configured=configured,
            run_mode="shadow_gap_assessment",
            fixture_result={"mode": "synthetic"},
            invariant_result={
                "status": "failed",
                "finding_count": 1,
                "critical_count": 1,
                "warning_count": 0,
                "findings": [],
            },
            health=health,
            shadow=shadow,
        )

        report = await database.fetchone(
            "SELECT * FROM final_acceptance_reports WHERE final_acceptance_report_id = ?",
            (final["final_acceptance_report_id"],),
        )
        assert final["decision"] == "rejected_blocked"
        assert report and report["decision"] == "rejected_blocked"

    run(scenario())


def test_shadow_assessment_gap_report_does_not_claim_stage3_ready(tmp_path: Path) -> None:
    async def scenario() -> None:
        database, clock = await sprint5_db(tmp_path)
        result = await ShadowModeAssessmentService(database, clock=clock).assess()
        report = await database.fetchone("SELECT * FROM shadow_mode_gap_reports")
        missing = set(json.loads(report["missing_capabilities_json"]))

        assert result["status"] == "gap_report_required"
        assert result["blocks_stage2_release"] is False
        assert result["blocks_stage3_progression"] is True
        assert "fresh_high_confidence_quote_stream" in missing
        assert "route_quality_model" in missing
        assert "fill_vs_quote_comparison" in missing

    run(scenario())


def test_append_only_acceptance_artifacts_are_protected(tmp_path: Path) -> None:
    async def scenario() -> None:
        database, clock = await sprint5_db(tmp_path)
        await InvariantChecker(database, clock=clock).record_violation(
            acceptance_run_id=None,
            finding=InvariantFinding(
                "append_only_fixture",
                "warning",
                "append-only fixture",
                "none",
                {},
            ),
        )
        row = await database.fetchone("SELECT invariant_violation_id FROM invariant_violations")
        with pytest.raises(Exception, match="append-only"):
            await database.execute(
                "UPDATE invariant_violations SET status = 'closed' WHERE invariant_violation_id = ?",
                (row["invariant_violation_id"],),
            )

    run(scenario())
