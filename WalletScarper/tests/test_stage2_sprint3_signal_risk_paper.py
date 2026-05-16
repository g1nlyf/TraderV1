from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from walletscarper.stage2.clock import FixedClock
from walletscarper.stage2.config import load_stage2_settings
from walletscarper.stage2.config_snapshots import ConfigSnapshotRepository
from walletscarper.stage2.db import Stage2Database
from walletscarper.stage2.domain import DomainRepository
from walletscarper.stage2.evaluation import DeterministicEvaluationService, OutcomeRejected
from walletscarper.stage2.events import RawSourceEventLog
from walletscarper.stage2.evidence import EvidenceNormalizer
from walletscarper.stage2.legacy_ingestion import map_dexscreener_payload, write_raw_source_event
from walletscarper.stage2.paper_trading import PaperOrderRejected, Sprint3PaperTradingService
from walletscarper.stage2.risk import DeterministicRiskService
from walletscarper.stage2.signals import SignalService
from walletscarper.stage2.token_intelligence import TokenIntelligenceService


BASE_TIME = datetime(2026, 5, 14, 12, 5, tzinfo=timezone.utc)


def run(coro):
    return asyncio.run(coro)


def test_signal_no_trade_and_thesis_lifecycle(tmp_path: Path) -> None:
    async def scenario() -> None:
        ctx = await seeded_context(tmp_path)
        service = SignalService(ctx["database"], ctx["domain"], clock=ctx["clock"])
        before = await ctx["database"].table_counts(["paper_orders", "risk_checks"])

        signal_id = await service.create_signal(signal_payload(ctx))
        no_trade_id = await service.create_no_trade_signal(
            {
                **signal_payload(ctx),
                "reason": "configured evidence prior says watch but skip entry",
                "observe_later": True,
                "quality_flags": ["watch_only"],
            }
        )
        thesis_id = await service.create_trade_thesis(signal_id, thesis_payload(ctx))
        after = await ctx["database"].table_counts(["paper_orders", "risk_checks"])
        no_trade = await ctx["database"].fetchone("SELECT * FROM no_trade_signals WHERE no_trade_signal_id = ?", (no_trade_id,))
        thesis_detail = await ctx["database"].fetchone("SELECT * FROM trade_thesis_details WHERE thesis_id = ?", (thesis_id,))

        assert before == after
        assert no_trade and no_trade["reason"].startswith("configured evidence prior")
        assert no_trade["observe_later"] == 1
        thesis_refs = json.loads(thesis_detail["evidence_refs_json"])
        assert thesis_detail and any("market_snapshot" in ref for ref in thesis_refs)
        with pytest.raises(Exception, match="append-only"):
            await ctx["database"].execute("UPDATE signals SET status = 'mutated' WHERE signal_id = ?", (signal_id,))
        with pytest.raises(Exception, match="append-only"):
            await ctx["database"].execute("UPDATE trade_theses SET entry_reason = 'mutated' WHERE thesis_id = ?", (thesis_id,))

        risk = DeterministicRiskService(ctx["database"], ctx["domain"], clock=ctx["clock"])
        signal_without_thesis = await service.create_signal(signal_payload(ctx, confidence="medium"))
        await risk.run_entry_risk_check(
            signal_id=signal_without_thesis,
            market_snapshot_id=ctx["market_snapshot_id"],
            risk_limit_snapshot_id=ctx["risk_limit_id"],
            config_snapshot_id=ctx["config_id"],
        )
        with pytest.raises(ValueError, match="after entry risk check"):
            await service.create_trade_thesis(signal_without_thesis, thesis_payload(ctx))

    run(scenario())


def test_entry_risk_and_paper_order_guards(tmp_path: Path) -> None:
    async def scenario() -> None:
        ctx = await seeded_signal_with_thesis(tmp_path)
        risk = DeterministicRiskService(ctx["database"], ctx["domain"], clock=ctx["clock"])
        paper = Sprint3PaperTradingService(ctx["database"], ctx["domain"], clock=ctx["clock"])

        risk_id = await risk.run_entry_risk_check(
            signal_id=ctx["signal_id"],
            market_snapshot_id=ctx["market_snapshot_id"],
            risk_limit_snapshot_id=ctx["risk_limit_id"],
            config_snapshot_id=ctx["config_id"],
        )
        risk_row = await ctx["database"].fetchone("SELECT * FROM risk_checks WHERE risk_check_id = ?", (risk_id,))
        assert risk_row and risk_row["passed"] == 1
        order_id = await paper.create_paper_order(signal_id=ctx["signal_id"], risk_check_id=risk_id)
        assert await ctx["database"].fetchone("SELECT * FROM paper_orders WHERE paper_order_id = ?", (order_id,))

        with pytest.raises(PaperOrderRejected, match="already has"):
            await paper.create_paper_order(signal_id=ctx["signal_id"], risk_check_id=risk_id)

        other_signal = await SignalService(ctx["database"], ctx["domain"], clock=ctx["clock"]).create_signal(
            signal_payload(ctx, confidence="medium")
        )
        await SignalService(ctx["database"], ctx["domain"], clock=ctx["clock"]).create_trade_thesis(other_signal, thesis_payload(ctx))
        manual_risk = await ctx["domain"].create_risk_check(
            check_scope="entry",
            subject_type="signal",
            subject_id=other_signal,
            risk_limit_snapshot_id=ctx["risk_limit_id"],
            config_snapshot_id=ctx["config_id"],
            passed=True,
            created_by_service="llm_proposal",
        )
        with pytest.raises(PaperOrderRejected, match="not authoritative"):
            await paper.create_paper_order(signal_id=other_signal, risk_check_id=manual_risk)

        stale_ctx = await seeded_signal_with_thesis(tmp_path / "stale", max_stale_seconds=60)
        stale_risk = DeterministicRiskService(
            stale_ctx["database"],
            stale_ctx["domain"],
            clock=FixedClock(BASE_TIME + timedelta(hours=2)),
        )
        stale_risk_id = await stale_risk.run_entry_risk_check(
            signal_id=stale_ctx["signal_id"],
            market_snapshot_id=stale_ctx["market_snapshot_id"],
            risk_limit_snapshot_id=stale_ctx["risk_limit_id"],
            config_snapshot_id=stale_ctx["config_id"],
        )
        stale = await stale_ctx["database"].fetchone("SELECT * FROM risk_checks WHERE risk_check_id = ?", (stale_risk_id,))
        assert stale["passed"] == 0
        assert "stale_market_snapshot" in stale["veto_reason"]

    run(scenario())


def test_entry_fill_position_monitoring_and_failed_fills(tmp_path: Path) -> None:
    async def scenario() -> None:
        ctx = await seeded_signal_with_thesis(tmp_path, max_fill_stale_seconds=3600)
        risk = DeterministicRiskService(ctx["database"], ctx["domain"], clock=ctx["clock"])
        paper = Sprint3PaperTradingService(ctx["database"], ctx["domain"], clock=ctx["clock"])
        risk_id = await risk.run_entry_risk_check(
            signal_id=ctx["signal_id"],
            market_snapshot_id=ctx["market_snapshot_id"],
            risk_limit_snapshot_id=ctx["risk_limit_id"],
            config_snapshot_id=ctx["config_id"],
        )
        order_id = await paper.create_paper_order(signal_id=ctx["signal_id"], risk_check_id=risk_id)

        fill_id = await paper.simulate_entry_fill(paper_order_id=order_id, market_snapshot_id=ctx["market_snapshot_id"])
        fill = await ctx["database"].fetchone("SELECT * FROM paper_fills WHERE paper_fill_id = ?", (fill_id,))
        assert fill["failed_fill_reason"] is None
        assert fill["filled_size"] == pytest.approx(10)
        assert fill["fees"] > 0
        assert fill["slippage"] > 0
        assert "latency" in fill["latency_assumption"]

        position_id = await paper.open_position_from_fill(paper_fill_id=fill_id)
        assert await ctx["database"].fetchone("SELECT * FROM paper_positions WHERE position_id = ?", (position_id,))
        assert await ctx["database"].fetchone("SELECT * FROM monitoring_sessions WHERE subject_id = ?", (position_id,))
        assert await ctx["database"].fetchone("SELECT * FROM jobs WHERE target_ref = ?", (position_id,))
        monitor_risk_id = await risk.run_position_monitoring_risk_check(
            position_id=position_id,
            market_snapshot_id=ctx["market_snapshot_id"],
            risk_limit_snapshot_id=ctx["risk_limit_id"],
            config_snapshot_id=ctx["config_id"],
        )
        monitor = await ctx["database"].fetchone("SELECT * FROM risk_checks WHERE risk_check_id = ?", (monitor_risk_id,))
        assert monitor["check_scope"] == "position_monitoring"

        stale_ctx = await seeded_signal_with_thesis(tmp_path / "failed", max_fill_stale_seconds=60)
        stale_risk = DeterministicRiskService(stale_ctx["database"], stale_ctx["domain"], clock=stale_ctx["clock"])
        stale_paper = Sprint3PaperTradingService(
            stale_ctx["database"],
            stale_ctx["domain"],
            clock=FixedClock(BASE_TIME + timedelta(hours=2)),
        )
        stale_risk_id = await stale_risk.run_entry_risk_check(
            signal_id=stale_ctx["signal_id"],
            market_snapshot_id=stale_ctx["market_snapshot_id"],
            risk_limit_snapshot_id=stale_ctx["risk_limit_id"],
            config_snapshot_id=stale_ctx["config_id"],
        )
        stale_order_id = await Sprint3PaperTradingService(
            stale_ctx["database"], stale_ctx["domain"], clock=stale_ctx["clock"]
        ).create_paper_order(signal_id=stale_ctx["signal_id"], risk_check_id=stale_risk_id)
        failed_fill_id = await stale_paper.simulate_entry_fill(
            paper_order_id=stale_order_id,
            market_snapshot_id=stale_ctx["market_snapshot_id"],
        )
        failed = await stale_ctx["database"].fetchone("SELECT * FROM paper_fills WHERE paper_fill_id = ?", (failed_fill_id,))
        assert failed["failed_fill_reason"] == "stale_market_snapshot"
        with pytest.raises(PaperOrderRejected, match="Failed fill"):
            await stale_paper.open_position_from_fill(paper_fill_id=failed_fill_id)

        cap_ctx = await seeded_signal_with_thesis(tmp_path / "cap")
        cap_risk = DeterministicRiskService(cap_ctx["database"], cap_ctx["domain"], clock=cap_ctx["clock"])
        cap_paper = Sprint3PaperTradingService(cap_ctx["database"], cap_ctx["domain"], clock=cap_ctx["clock"])
        cap_risk_id = await cap_risk.run_entry_risk_check(
            signal_id=cap_ctx["signal_id"],
            market_snapshot_id=cap_ctx["market_snapshot_id"],
            risk_limit_snapshot_id=cap_ctx["risk_limit_id"],
            config_snapshot_id=cap_ctx["config_id"],
        )
        cap_order_id = await cap_paper.create_paper_order(
            signal_id=cap_ctx["signal_id"],
            risk_check_id=cap_risk_id,
            intended_size=10000,
        )
        capped_fill_id = await cap_paper.simulate_entry_fill(
            paper_order_id=cap_order_id,
            market_snapshot_id=cap_ctx["market_snapshot_id"],
        )
        capped = await cap_ctx["database"].fetchone("SELECT * FROM paper_fills WHERE paper_fill_id = ?", (capped_fill_id,))
        assert capped["failed_fill_reason"] is None
        assert capped["filled_size"] < 10000
        assert "filled_size" in capped["liquidity_constraint"]

    run(scenario())


def test_exit_decision_exit_risk_trade_outcome_and_dashboard(tmp_path: Path) -> None:
    async def scenario() -> None:
        ctx = await seeded_signal_with_thesis(tmp_path)
        entry_risk = DeterministicRiskService(ctx["database"], ctx["domain"], clock=ctx["clock"])
        entry_paper = Sprint3PaperTradingService(ctx["database"], ctx["domain"], clock=ctx["clock"])
        risk_id = await entry_risk.run_entry_risk_check(
            signal_id=ctx["signal_id"],
            market_snapshot_id=ctx["market_snapshot_id"],
            risk_limit_snapshot_id=ctx["risk_limit_id"],
            config_snapshot_id=ctx["config_id"],
        )
        order_id = await entry_paper.create_paper_order(signal_id=ctx["signal_id"], risk_check_id=risk_id)
        entry_fill_id = await entry_paper.simulate_entry_fill(paper_order_id=order_id, market_snapshot_id=ctx["market_snapshot_id"])
        position_id = await entry_paper.open_position_from_fill(paper_fill_id=entry_fill_id)

        assert not hasattr(Sprint3PaperTradingService, "close_position")
        outcome_service = DeterministicEvaluationService(ctx["database"], clock=ctx["clock"])
        with pytest.raises(OutcomeRejected, match="exit fill"):
            await outcome_service.calculate_trade_outcome(position_id=position_id)

        exit_clock = FixedClock(BASE_TIME + timedelta(minutes=5))
        exit_snapshot_id = await append_and_normalize_market(ctx["database"], price_usd=1.5, observed_at=BASE_TIME + timedelta(minutes=1))
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
        with pytest.raises(PaperOrderRejected, match="requires an existing RiskCheck"):
            await exit_paper.execute_paper_exit(exit_decision_id=exit_decision_id, risk_check_id="missing")
        exit_risk_id = await exit_risk.run_exit_risk_check(
            exit_decision_id=exit_decision_id,
            market_snapshot_id=exit_snapshot_id,
            risk_limit_snapshot_id=ctx["risk_limit_id"],
            config_snapshot_id=ctx["config_id"],
        )
        exit_fill_id = await exit_paper.execute_paper_exit(exit_decision_id=exit_decision_id, risk_check_id=exit_risk_id)
        exit_fill = await ctx["database"].fetchone("SELECT * FROM paper_fills WHERE paper_fill_id = ?", (exit_fill_id,))
        assert exit_fill["failed_fill_reason"] is None
        assert exit_fill["fees"] > 0
        assert exit_fill["slippage"] > 0

        outcome_id = await DeterministicEvaluationService(ctx["database"], clock=exit_clock).calculate_trade_outcome(position_id=position_id)
        outcome = await ctx["database"].fetchone("SELECT * FROM trade_outcomes WHERE outcome_id = ?", (outcome_id,))
        entry_fill = await ctx["database"].fetchone("SELECT * FROM paper_fills WHERE paper_fill_id = ?", (entry_fill_id,))
        expected_gross = (exit_fill["fill_price"] - entry_fill["fill_price"]) * 10
        expected_fees = entry_fill["fees"] + exit_fill["fees"]
        assert outcome["gross_pnl"] == pytest.approx(expected_gross)
        assert outcome["net_pnl"] == pytest.approx(expected_gross - expected_fees)
        assert outcome["fees"] == pytest.approx(expected_fees)
        assert outcome["slippage"] == pytest.approx(entry_fill["slippage"] + exit_fill["slippage"])
        assert outcome["duration_seconds"] > 0
        with pytest.raises(Exception, match="evaluation_service"):
            await ctx["database"].execute(
                """
                INSERT INTO trade_outcomes(
                  outcome_id, position_id, exit_decision_id, gross_pnl, net_pnl,
                  fees, slippage, duration_seconds, max_drawdown, calculated_at,
                  calculated_by_service
                )
                VALUES ('manual', ?, ?, 0, 0, 0, 0, 0, 0, ?, 'hermes')
                """,
                (position_id, exit_decision_id, exit_clock.now().isoformat()),
            )

        dashboard = await DeterministicEvaluationService(ctx["database"], clock=exit_clock).baseline_dashboard_snapshot()
        assert dashboard["signals"] == 1
        assert dashboard["risk_approved"] >= 2
        assert dashboard["paper_orders"] == 2
        assert dashboard["successful_fills"] == 2
        assert dashboard["closed_positions"] == 1
        assert dashboard["realized_net_pnl"] == pytest.approx(outcome["net_pnl"])
        assert dashboard["strategy_promotion"] == "not_implemented_sprint3"

    run(scenario())


def test_rejected_and_missed_trade_logging_and_boundary_tables(tmp_path: Path) -> None:
    async def scenario() -> None:
        ctx = await seeded_context(tmp_path, confidence="low")
        signal_service = SignalService(ctx["database"], ctx["domain"], clock=ctx["clock"])
        signal_id = await signal_service.create_signal(signal_payload(ctx, confidence="low"))
        await signal_service.create_trade_thesis(signal_id, thesis_payload(ctx))
        risk_id = await DeterministicRiskService(ctx["database"], ctx["domain"], clock=ctx["clock"]).run_entry_risk_check(
            signal_id=signal_id,
            market_snapshot_id=ctx["market_snapshot_id"],
            risk_limit_snapshot_id=ctx["risk_limit_id"],
            config_snapshot_id=ctx["config_id"],
        )
        risk = await ctx["database"].fetchone("SELECT * FROM risk_checks WHERE risk_check_id = ?", (risk_id,))
        assert risk["passed"] == 0
        assert "low_market_snapshot_confidence" in risk["veto_reason"]

        await signal_service.create_no_trade_signal({**signal_payload(ctx, confidence="low"), "reason": "insufficient quality", "observe_later": True})
        counts = await ctx["database"].table_counts(
            [
                "rejected_trade_logs",
                "missed_opportunity_logs",
                "paper_orders",
                "paper_fills",
                "paper_positions",
                "trade_outcomes",
            ]
        )
        assert counts["rejected_trade_logs"] >= 2
        assert counts["missed_opportunity_logs"] == 1
        assert counts["paper_orders"] == 0
        assert counts["paper_fills"] == 0
        assert counts["paper_positions"] == 0
        assert counts["trade_outcomes"] == 0

    run(scenario())


async def seeded_signal_with_thesis(
    tmp_path: Path,
    *,
    max_stale_seconds: int = 3600,
    max_fill_stale_seconds: int = 3600,
    confidence: str = "high",
) -> dict:
    ctx = await seeded_context(
        tmp_path,
        max_stale_seconds=max_stale_seconds,
        max_fill_stale_seconds=max_fill_stale_seconds,
        confidence=confidence,
    )
    signal_service = SignalService(ctx["database"], ctx["domain"], clock=ctx["clock"])
    signal_id = await signal_service.create_signal(signal_payload(ctx, confidence=confidence))
    await signal_service.create_trade_thesis(signal_id, thesis_payload(ctx))
    ctx["signal_id"] = signal_id
    return ctx


async def seeded_context(
    tmp_path: Path,
    *,
    max_stale_seconds: int = 3600,
    max_fill_stale_seconds: int = 3600,
    confidence: str = "high",
) -> dict:
    clock = FixedClock(BASE_TIME)
    settings = load_stage2_settings(environment="test", database_path=tmp_path / "stage2.sqlite3")
    database = Stage2Database(settings, clock=clock)
    await database.migrate()
    snapshots = ConfigSnapshotRepository(database, clock=clock)
    config_id = await snapshots.create_config_snapshot(source="test", settings=settings)
    limits = {
        "max_stale_seconds": max_stale_seconds,
        "max_fill_stale_seconds": max_fill_stale_seconds,
        "min_liquidity_usd": 1000,
        "max_estimated_slippage_bps": 500,
        "max_open_paper_positions": 5,
        "max_position_notional_usd": 100000,
        "max_liquidity_fraction": 0.1,
        "fill_slippage_bps": 50,
        "paper_fee_bps": 25,
        "fill_latency_ms": 1500,
    }
    risk_limit_id = await snapshots.create_risk_limit_snapshot(config_snapshot_id=config_id, limits=limits, source="sprint3-test")
    strategy_config_id = await snapshots.create_strategy_config_snapshot(
        config_snapshot_id=config_id,
        strategy_name="sprint3-paper-research",
        strategy_version_label="v0",
        thresholds={"evidence_only": True},
        signal_rules={"source": "sprint2_evidence"},
        exit_rules={"paper_only": True},
    )
    domain = DomainRepository(database, clock=clock)
    strategy_version_id = await domain.create_strategy_version(
        strategy_config_snapshot_id=strategy_config_id,
        rules={"sprint3": "paper_workflow_only"},
        params={"paper_only": True},
    )
    market_snapshot_id = await append_and_normalize_market(database, price_usd=1.0, confidence=confidence)
    market = await database.fetchone("SELECT * FROM market_snapshots WHERE market_snapshot_id = ?", (market_snapshot_id,))
    candidate_id = market["token_candidate_id"]
    profile_id = await TokenIntelligenceService(database, clock=clock).create_profile_from_candidate(candidate_id)
    return {
        "database": database,
        "clock": clock,
        "domain": domain,
        "config_id": config_id,
        "risk_limit_id": risk_limit_id,
        "strategy_config_id": strategy_config_id,
        "strategy_version_id": strategy_version_id,
        "market_snapshot_id": market_snapshot_id,
        "token_candidate_id": candidate_id,
        "token_profile_id": profile_id,
        "token_id": "token-1",
    }


async def append_and_normalize_market(
    database: Stage2Database,
    *,
    price_usd: float,
    observed_at: datetime = BASE_TIME - timedelta(minutes=5),
    confidence: str = "high",
) -> str:
    raw_log = RawSourceEventLog(database)
    payload = {
        "chainId": "solana",
        "pairAddress": f"pool-1-{int(price_usd * 1000)}",
        "pairCreatedAt": int(observed_at.timestamp() * 1000),
        "baseToken": {"address": "token-1", "symbol": "ONE", "name": "One Token"},
        "priceUsd": str(price_usd),
        "liquidity": {"usd": 50000},
        "volume": {"m5": 1000, "h1": 5000, "h6": 10000, "h24": 25000},
        "marketCap": 250000,
        "fdv": 300000,
        "txns": {"m5": {"buys": 2, "sells": 3}, "h1": {"buys": 10, "sells": 11}},
        "confidence": confidence,
    }
    raw_id = await write_raw_source_event(map_dexscreener_payload(payload), raw_log)
    result = await EvidenceNormalizer(database).normalize_raw_source_event(raw_id)
    return result.market_snapshot_ids[0]


def signal_payload(ctx: dict, *, confidence: str = "high") -> dict:
    return {
        "token_profile_id": ctx["token_profile_id"],
        "market_snapshot_id": ctx["market_snapshot_id"],
        "strategy_version_id": ctx["strategy_version_id"],
        "strategy_config_snapshot_id": ctx["strategy_config_id"],
        "confidence": confidence,
        "invalidation_condition": "liquidity collapses or source confidence degrades",
        "expected_holding_time": "5m-30m",
        "estimated_risk": {"intended_size": 10, "risk_notes": "bounded paper test"},
        "estimated_slippage": 50,
        "source_refs": [ctx["market_snapshot_id"]],
    }


def thesis_payload(ctx: dict) -> dict:
    return {
        "why_token": "Sprint 2 profile has timestamped source-linked market evidence.",
        "why_now": "Market snapshot is fresh relative to configured risk limits.",
        "evidence_refs": [ctx["token_profile_id"], ctx["market_snapshot_id"]],
        "planned_exit_logic": "Exit on target, invalidation, or stale data warning.",
        "invalidation_condition": "Liquidity or source quality degrades.",
        "wrong_condition": "Paper exit cannot be simulated with current evidence.",
        "uncopyable_risk": "Thin liquidity and latency could make copyability poor.",
        "expected_holding_time": "5m-30m",
    }
