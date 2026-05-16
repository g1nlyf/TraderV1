from __future__ import annotations

import asyncio
import json
from datetime import timedelta
from pathlib import Path

import pytest

from test_stage2_sprint3_signal_risk_paper import BASE_TIME, append_and_normalize_market, seeded_signal_with_thesis
from walletscarper.stage2.clock import FixedClock
from walletscarper.stage2.config_snapshots import ConfigSnapshotRepository
from walletscarper.stage2.domain import DomainRepository
from walletscarper.stage2.evaluation import DeterministicEvaluationService
from walletscarper.stage2.jobs import JobQueueService
from walletscarper.stage2.memory import MemoryService
from walletscarper.stage2.monitoring import MonitoringService
from walletscarper.stage2.paper_trading import Sprint3PaperTradingService
from walletscarper.stage2.reports import Sprint4ReportService
from walletscarper.stage2.reviews import PostTradeReviewService
from walletscarper.stage2.risk import DeterministicRiskService
from walletscarper.stage2.strategy import StrategyResearchService
from walletscarper.stage2.workers import WorkerPoolService


def run(coro):
    return asyncio.run(coro)


def test_monitoring_state_machine_worker_leases_capacity_and_priority(tmp_path: Path) -> None:
    async def scenario() -> None:
        ctx = await seeded_signal_with_thesis(tmp_path)
        monitoring = MonitoringService(ctx["database"], clock=ctx["clock"])
        workers = WorkerPoolService(ctx["database"], monitoring=monitoring, clock=ctx["clock"])
        limits_id = await workers.create_parallelism_config(
            {"max_active_token_monitoring_sessions": 1, "max_concurrent_worker_leases": 2},
            version_label="sprint4-test",
        )

        token_session_id = await monitoring.create_session(
            session_type="token_monitoring",
            subject_type="token_profile",
            subject_id=ctx["token_profile_id"],
            priority=100,
        )
        token_job_id = await monitoring.create_monitoring_job(
            token_session_id,
            job_type="monitor_token",
            worker_type="token_monitor",
            parallelism_config_id=limits_id,
        )
        second_token_session_id = await monitoring.create_session(
            session_type="token_monitoring",
            subject_type="token_profile",
            subject_id=f"{ctx['token_profile_id']}-2",
            priority=100,
        )
        second_token_job_id = await monitoring.create_monitoring_job(
            second_token_session_id,
            job_type="monitor_token",
            worker_type="token_monitor",
            parallelism_config_id=limits_id,
        )
        waiting = await ctx["database"].fetchone(
            "SELECT status FROM monitoring_sessions WHERE monitoring_session_id = ?",
            (second_token_session_id,),
        )
        delayed = await ctx["database"].fetchone("SELECT scheduled_at FROM jobs WHERE job_id = ?", (second_token_job_id,))
        assert waiting["status"] == "waiting"
        assert delayed["scheduled_at"] > ctx["clock"].now().isoformat()

        position_session_id = await monitoring.create_session(
            session_type="paper_position_monitoring",
            subject_type="paper_position",
            subject_id="paper-position-priority",
            priority=10,
        )
        position_job_id = await monitoring.create_monitoring_job(
            position_session_id,
            job_type="monitor_position",
            worker_type="position_monitor",
            parallelism_config_id=limits_id,
        )

        token_work = await workers.lease_next_work(worker_id="token-worker-1", worker_type="token_monitor", lease_seconds=60)
        assert token_work and token_work["job_id"] == token_job_id
        with pytest.raises(ValueError, match="Worker concurrent lease limit"):
            await workers.lease_next_work(worker_id="token-worker-1", worker_type="token_monitor", lease_seconds=60)

        position_work = await workers.lease_next_work(
            worker_id="position-worker-1",
            worker_type="position_monitor",
            lease_seconds=60,
        )
        assert position_work and position_work["job_id"] == position_job_id
        await workers.heartbeat_lease(position_work["worker_lease_id"], extend_seconds=120)
        heartbeat = await ctx["database"].fetchone(
            "SELECT lease_expires_at FROM worker_leases WHERE worker_lease_id = ?",
            (position_work["worker_lease_id"],),
        )
        assert heartbeat["lease_expires_at"] > position_work["lease_expires_at"]

        rows = await ctx["database"].fetchall(
            "SELECT * FROM monitoring_session_transitions WHERE monitoring_session_id = ? ORDER BY created_at",
            (token_session_id,),
        )
        assert [row["new_state"] for row in rows] == ["created", "queued", "active"]

        expired_clock = FixedClock(BASE_TIME + timedelta(minutes=3))
        expired_workers = WorkerPoolService(ctx["database"], clock=expired_clock)
        assert await expired_workers.expire_stale_leases() >= 2
        pending = await ctx["database"].fetchone("SELECT status FROM jobs WHERE job_id = ?", (token_job_id,))
        assert pending["status"] == "pending"

    run(scenario())


def test_conflict_review_resolution_does_not_rewrite_history(tmp_path: Path) -> None:
    async def scenario() -> None:
        ctx = await seeded_signal_with_thesis(tmp_path)
        monitoring = MonitoringService(ctx["database"], clock=ctx["clock"])
        session_id = await monitoring.create_session(
            session_type="paper_position_monitoring",
            subject_type="paper_position",
            subject_id="duplicate-position",
        )
        await monitoring.create_monitoring_job(session_id, job_type="monitor_position", worker_type="position_monitor")
        duplicate_session_id = await monitoring.create_session(
            session_type="paper_position_monitoring",
            subject_type="paper_position",
            subject_id="duplicate-position",
        )
        with pytest.raises(ValueError, match="Duplicate"):
            await monitoring.create_monitoring_job(
                duplicate_session_id,
                job_type="monitor_position",
                worker_type="position_monitor",
            )
        conflict = await ctx["database"].fetchone("SELECT * FROM conflict_reviews WHERE subject_id = 'duplicate-position'")
        assert conflict and conflict["status"] == "open"
        before = await ctx["database"].table_counts(["trade_outcomes", "risk_checks", "paper_fills"])
        await monitoring.resolve_conflict_review(
            conflict["conflict_review_id"],
            resolution="ledger_state_wins",
            resolver="conflict_review_service",
        )
        after = await ctx["database"].table_counts(["trade_outcomes", "risk_checks", "paper_fills"])
        resolved = await ctx["database"].fetchone(
            "SELECT * FROM conflict_reviews WHERE conflict_review_id = ?",
            (conflict["conflict_review_id"],),
        )
        assert before == after
        assert resolved["status"] == "resolved"
        assert resolved["resolver"] == "conflict_review_service"

    run(scenario())


def test_strategy_mutations_experiments_leaderboard_and_decisions(tmp_path: Path) -> None:
    async def scenario() -> None:
        ctx = await closed_trade_context(tmp_path)
        snapshots = ConfigSnapshotRepository(ctx["database"], clock=ctx["clock"])
        criteria_id = await snapshots.create_promotion_criteria_snapshot(
            config_snapshot_id=ctx["config_id"],
            source="sprint4-test",
            criteria={
                "min_closed_trades": 5,
                "min_net_expectancy": 0,
                "min_cumulative_net_pnl": 0,
                "max_degraded_outcomes": 0,
            },
        )
        service = StrategyResearchService(ctx["database"], clock=ctx["clock"])
        proposal_id = await service.create_mutation_proposal(
            parent_strategy_version_id=ctx["strategy_version_id"],
            mutation_type="no_trade_filter",
            hypothesis="Skip low confidence token buckets.",
            changed_assumptions={"minimum_source_confidence": "medium"},
            expected_effect="Fewer failed fills from low quality evidence.",
            target_buckets={"source_confidence": ["medium", "high"]},
            proposed_budget={"max_paper_trades": 10},
            promotion_criteria_snapshot_id=criteria_id,
            created_by="strategy_research_service",
        )
        with pytest.raises(ValueError, match="Forbidden"):
            await service.create_mutation_proposal(
                parent_strategy_version_id=ctx["strategy_version_id"],
                mutation_type="pnl_calculation",
                hypothesis="Bad mutation",
                changed_assumptions={"pnl_calculation": "rewrite"},
                expected_effect="forbidden",
                target_buckets={},
                proposed_budget={"max_paper_trades": 1},
                promotion_criteria_snapshot_id=criteria_id,
                created_by="test",
            )
        child_strategy_id = await service.create_strategy_version_from_proposal(
            proposal_id,
            strategy_config_snapshot_id=ctx["strategy_config_id"],
        )
        child = await ctx["database"].fetchone("SELECT * FROM strategy_versions WHERE strategy_version_id = ?", (child_strategy_id,))
        assert child["parent_strategy_version_id"] == ctx["strategy_version_id"]
        assert child["mutation_proposal_id"] == proposal_id

        with pytest.raises(ValueError, match="budget"):
            await service.create_strategy_experiment(
                strategy_version_id=child_strategy_id,
                strategy_config_snapshot_id=ctx["strategy_config_id"],
                promotion_criteria_snapshot_id=criteria_id,
                budget={},
            )
        experiment_id = await service.create_strategy_experiment(
            strategy_version_id=child_strategy_id,
            strategy_config_snapshot_id=ctx["strategy_config_id"],
            promotion_criteria_snapshot_id=criteria_id,
            budget={"max_paper_trades": 10},
            mutation_proposal_id=proposal_id,
        )
        assert await ctx["database"].fetchone("SELECT * FROM strategy_experiments WHERE strategy_experiment_id = ?", (experiment_id,))

        snapshot_id = await service.create_metric_snapshot(ctx["strategy_version_id"], promotion_criteria_snapshot_id=criteria_id)
        snapshot = await ctx["database"].fetchone("SELECT * FROM strategy_metric_snapshots WHERE strategy_metric_snapshot_id = ?", (snapshot_id,))
        assert snapshot["closed_trade_count"] == 1
        assert snapshot["net_pnl"] > 0
        assert snapshot["sample_size_warning"]
        assert "trade_outcomes" in snapshot["metrics_json"]

        decision_id = await service.decide_strategy(
            strategy_version_id=ctx["strategy_version_id"],
            promotion_criteria_snapshot_id=criteria_id,
            metrics_snapshot_id=snapshot_id,
        )
        decision = await ctx["database"].fetchone("SELECT * FROM strategy_decisions WHERE strategy_decision_id = ?", (decision_id,))
        assert decision["decision_type"] == "insufficient_data"

        permissive_criteria_id = await snapshots.create_promotion_criteria_snapshot(
            config_snapshot_id=ctx["config_id"],
            source="sprint4-test",
            criteria={"min_closed_trades": 1, "min_net_expectancy": 0, "min_cumulative_net_pnl": 0},
        )
        permissive_snapshot_id = await service.create_metric_snapshot(
            ctx["strategy_version_id"],
            promotion_criteria_snapshot_id=permissive_criteria_id,
        )
        promote_id = await service.decide_strategy(
            strategy_version_id=ctx["strategy_version_id"],
            promotion_criteria_snapshot_id=permissive_criteria_id,
            metrics_snapshot_id=permissive_snapshot_id,
        )
        promote = await ctx["database"].fetchone("SELECT * FROM strategy_decisions WHERE strategy_decision_id = ?", (promote_id,))
        assert promote["decision_type"] == "promote"

        leaderboard = await service.leaderboard_v1(promotion_criteria_snapshot_id=permissive_criteria_id)
        assert any(row["strategy_version_id"] == ctx["strategy_version_id"] for row in leaderboard)

    run(scenario())


def test_post_trade_review_and_memory_curation_are_append_only_artifacts(tmp_path: Path) -> None:
    async def scenario() -> None:
        ctx = await closed_trade_context(tmp_path)
        review_service = PostTradeReviewService(ctx["database"], clock=ctx["clock"])
        review_id = await review_service.create_post_trade_review(
            outcome_id=ctx["outcome_id"],
            reviewer="post_trade_review_service",
            lessons=["Conservative slippage materially affected net result."],
            hindsight_claims=["This was obvious after the outcome."],
        )
        review = await ctx["database"].fetchone("SELECT * FROM post_trade_review_details WHERE post_trade_review_id = ?", (review_id,))
        assert review["signal_id"] == ctx["signal_id"]
        assert review["thesis_id"] == ctx["thesis_id"]
        assert "unsupported_hindsight_storytelling" in review["hindsight_flags_json"]
        with pytest.raises(Exception, match="append-only"):
            await ctx["database"].execute(
                "UPDATE post_trade_review_details SET created_by = 'mutated' WHERE post_trade_review_id = ?",
                (review_id,),
            )

        memory = MemoryService(ctx["database"], clock=ctx["clock"])
        proposal_id = await memory.propose_memory(
            claim="Latency/slippage assumptions must stay visible in reviews.",
            memory_type="lesson",
            evidence_refs=[ctx["outcome_id"]],
            review_refs=[review_id],
            strategy_refs=[ctx["strategy_version_id"]],
            confidence="medium",
            validity_scope={"strategy_version_id": ctx["strategy_version_id"]},
            created_by="post_trade_review_service",
        )
        curation_id = await memory.curate_memory(
            memory_proposal_id=proposal_id,
            action="accept",
            curator="memory_curator",
            reason="Linked to deterministic outcome and review.",
        )
        curation = await ctx["database"].fetchone("SELECT * FROM memory_curation_events WHERE memory_curation_event_id = ?", (curation_id,))
        proposal = await ctx["database"].fetchone("SELECT * FROM memory_proposals WHERE memory_proposal_id = ?", (proposal_id,))
        assert curation["action"] == "accept"
        assert proposal["status"] == "accepted"
        counts = await ctx["database"].table_counts(["trade_outcomes", "risk_checks", "paper_fills"])
        assert counts["trade_outcomes"] == 1
        assert counts["risk_checks"] >= 2
        assert counts["paper_fills"] == 2

    run(scenario())


def test_sprint4_report_and_boundaries_do_not_start_sprint5_or_live_execution(tmp_path: Path) -> None:
    async def scenario() -> None:
        ctx = await closed_trade_context(tmp_path)
        strategy = StrategyResearchService(ctx["database"], clock=ctx["clock"])
        await strategy.leaderboard_v1()
        report = await Sprint4ReportService(ctx["database"], clock=ctx["clock"]).snapshot()
        assert "latest_leaderboard_v1" in report
        assert "queue" in report
        counts = await ctx["database"].table_counts(
            ["signals", "risk_checks", "paper_orders", "paper_fills", "paper_positions", "trade_outcomes"]
        )
        assert counts["signals"] == 1
        assert counts["risk_checks"] >= 2
        assert counts["paper_orders"] == 2
        assert counts["paper_fills"] == 2
        assert counts["paper_positions"] == 1
        assert counts["trade_outcomes"] == 1

    run(scenario())


async def closed_trade_context(tmp_path: Path) -> dict:
    ctx = await seeded_signal_with_thesis(tmp_path, max_fill_stale_seconds=3600)
    risk = DeterministicRiskService(ctx["database"], ctx["domain"], clock=ctx["clock"])
    paper = Sprint3PaperTradingService(ctx["database"], ctx["domain"], clock=ctx["clock"])
    entry_risk_id = await risk.run_entry_risk_check(
        signal_id=ctx["signal_id"],
        market_snapshot_id=ctx["market_snapshot_id"],
        risk_limit_snapshot_id=ctx["risk_limit_id"],
        config_snapshot_id=ctx["config_id"],
    )
    order_id = await paper.create_paper_order(signal_id=ctx["signal_id"], risk_check_id=entry_risk_id)
    entry_fill_id = await paper.simulate_entry_fill(paper_order_id=order_id, market_snapshot_id=ctx["market_snapshot_id"])
    position_id = await paper.open_position_from_fill(paper_fill_id=entry_fill_id)
    exit_snapshot_id = await append_and_normalize_market(
        ctx["database"],
        price_usd=1.5,
        observed_at=BASE_TIME + timedelta(minutes=1),
    )
    exit_clock = FixedClock(BASE_TIME + timedelta(minutes=5))
    exit_paper = Sprint3PaperTradingService(ctx["database"], ctx["domain"], clock=exit_clock)
    exit_risk = DeterministicRiskService(ctx["database"], ctx["domain"], clock=exit_clock)
    exit_decision_id = await exit_paper.create_exit_decision(
        position_id=position_id,
        payload={
            "market_snapshot_id": exit_snapshot_id,
            "exit_reason": "planned target reached",
            "exit_trigger": "target_price",
            "expected_exit_logic": "paper-only conservative exit",
            "created_by": "paper_exit_policy",
        },
    )
    exit_risk_id = await exit_risk.run_exit_risk_check(
        exit_decision_id=exit_decision_id,
        market_snapshot_id=exit_snapshot_id,
        risk_limit_snapshot_id=ctx["risk_limit_id"],
        config_snapshot_id=ctx["config_id"],
    )
    await exit_paper.execute_paper_exit(exit_decision_id=exit_decision_id, risk_check_id=exit_risk_id)
    outcome_id = await DeterministicEvaluationService(ctx["database"], clock=exit_clock).calculate_trade_outcome(
        position_id=position_id
    )
    thesis = await ctx["database"].fetchone("SELECT thesis_id FROM trade_theses WHERE signal_id = ?", (ctx["signal_id"],))
    ctx.update(
        {
            "position_id": position_id,
            "exit_decision_id": exit_decision_id,
            "outcome_id": outcome_id,
            "thesis_id": thesis["thesis_id"],
            "clock": exit_clock,
        }
    )
    return ctx

