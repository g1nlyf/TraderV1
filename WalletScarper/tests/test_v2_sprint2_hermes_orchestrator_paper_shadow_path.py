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
from walletscarper.stage2.hermes_integration import run_v2_tool
from walletscarper.stage2.ids import new_id
from walletscarper.stage2.orchestrator import HermesOrchestratorService
from walletscarper.stage2.orchestrator.smoke import run_orchestrator_smoke


BASE_TIME = datetime(2026, 5, 16, 14, 0, tzinfo=timezone.utc)


def run(coro):
    return asyncio.run(coro)


def test_agent_trading_decision_and_tracked_wallet_signal_are_auditable(tmp_path: Path) -> None:
    async def scenario() -> None:
        database, clock = await migrated_database(tmp_path)
        service = HermesOrchestratorService(database, clock=clock)
        event_id = await service.record_tracked_wallet_signal_event(
            wallet="wallet-a",
            token_mint="token-a",
            pool_address="pool-a",
            side="buy",
            observed_at=BASE_TIME.isoformat(),
            source_name="fixture",
            source_refs=["raw:tx-a"],
            cluster_refs=["cluster-1"],
            correlation_refs=["wallet-b"],
            input_mode="fixture",
        )
        event = await database.fetchone("SELECT * FROM tracked_wallet_signal_events WHERE tracked_wallet_signal_event_id = ?", (event_id,))
        assert event is not None
        assert "cluster_correlated_not_independent_confirmation" in json.loads(event["quality_flags_json"])

        decision_id = await service.record_agent_trading_decision(
            decision_type="wait",
            pre_action_reasoning="Evidence is clustered, so wait instead of treating it as independent confirmation.",
            created_by_agent="hermes",
            wallet_refs=["wallet-a"],
            token_refs=["token-a"],
            evidence_refs=[],
            linked_tracked_wallet_signal_event_id=event_id,
        )
        decision = await database.fetchone("SELECT * FROM agent_trading_decisions WHERE agent_trading_decision_id = ?", (decision_id,))
        assert decision is not None
        assert decision["decision_type"] == "wait"
        assert "missing_evidence_refs" not in json.loads(decision["uncertainties_json"])
        with pytest.raises(Exception, match="append-only"):
            await database.execute(
                "UPDATE agent_trading_decisions SET decision_type = 'signal' WHERE agent_trading_decision_id = ?",
                (decision_id,),
            )

        for decision_type in ["no_trade", "downgrade_wallet", "downgrade_token"]:
            extra_id = await service.record_agent_trading_decision(
                decision_type=decision_type,
                pre_action_reasoning=f"{decision_type} fixture decision",
                created_by_agent="hermes",
                evidence_refs=["fixture:evidence"],
            )
            assert extra_id
        weak_id = await service.record_agent_trading_decision(
            decision_type="wait",
            pre_action_reasoning="Weak fixture decision has no evidence.",
            created_by_agent="hermes",
        )
        weak = await database.fetchone("SELECT * FROM agent_trading_decisions WHERE agent_trading_decision_id = ?", (weak_id,))
        assert "missing_evidence_refs" in json.loads(weak["uncertainties_json"])

    run(scenario())


def test_signal_and_no_trade_tools_link_to_agent_decision_without_order_side_effect(tmp_path: Path) -> None:
    async def scenario() -> None:
        database, clock = await migrated_database(tmp_path)
        ctx = await seed_context(database, clock)
        no_trade_decision = await run_v2_tool(
            "agent.record_trading_decision",
            {
                "decision_type": "no_trade",
                "pre_action_reasoning": "Fixture evidence is insufficient for entry.",
                "created_by_agent": "hermes",
                "evidence_refs": [ctx["market_snapshot_id"]],
                "token_refs": [ctx["token_mint"]],
                "market_snapshot_refs": [ctx["market_snapshot_id"]],
            },
            database=database,
            clock=clock,
        )
        no_trade = await run_v2_tool(
            "signal.create_no_trade",
            {
                "agent_trading_decision_id": no_trade_decision["artifact_id"],
                "strategy_version_id": ctx["strategy_version_id"],
                "strategy_config_snapshot_id": ctx["strategy_config_snapshot_id"],
                "token_id": ctx["token_mint"],
                "market_snapshot_id": ctx["market_snapshot_id"],
                "reason": "Fixture no-trade path.",
                "source_refs": [ctx["market_snapshot_id"]],
                "confidence": "medium",
            },
            database=database,
            clock=clock,
        )
        assert no_trade["ok"] is True
        link = await database.fetchone(
            """
            SELECT * FROM agent_trading_decision_artifact_links
            WHERE agent_trading_decision_id = ? AND artifact_type = 'no_trade_signal'
            """,
            (no_trade_decision["artifact_id"],),
        )
        assert link is not None
        counts = await database.table_counts(["paper_orders", "paper_fills", "trade_outcomes"])
        assert counts == {"paper_orders": 0, "paper_fills": 0, "trade_outcomes": 0}

        signal_decision = await run_v2_tool(
            "agent.record_trading_decision",
            {
                "decision_type": "signal",
                "pre_action_reasoning": "Fixture entry decision.",
                "created_by_agent": "hermes",
                "evidence_refs": [ctx["market_snapshot_id"]],
                "token_refs": [ctx["token_mint"]],
                "market_snapshot_refs": [ctx["market_snapshot_id"]],
            },
            database=database,
            clock=clock,
        )
        signal = await create_signal_tool(database, clock, ctx, signal_decision["artifact_id"], with_thesis=True)
        assert signal["ok"] is True
        row = await database.fetchone("SELECT * FROM signals WHERE signal_id = ?", (signal["signal_id"],))
        assert f"agent_trading_decision:{signal_decision['artifact_id']}" in json.loads(row["source_refs_json"])

    run(scenario())


def test_risk_order_fill_gates_block_invalid_paths(tmp_path: Path) -> None:
    async def scenario() -> None:
        database, clock = await migrated_database(tmp_path)
        ctx = await seed_context(database, clock)
        decision = await run_v2_tool(
            "agent.record_trading_decision",
            {
                "decision_type": "signal",
                "pre_action_reasoning": "Fixture signal without thesis should be risk-vetoed.",
                "created_by_agent": "hermes",
                "evidence_refs": [ctx["market_snapshot_id"]],
            },
            database=database,
            clock=clock,
        )
        signal = await create_signal_tool(database, clock, ctx, decision["artifact_id"], with_thesis=False)
        risk = await run_v2_tool(
            "risk.check_entry",
            {
                "signal_id": signal["signal_id"],
                "market_snapshot_id": ctx["market_snapshot_id"],
                "risk_limit_snapshot_id": ctx["risk_limit_snapshot_id"],
                "config_snapshot_id": ctx["config_snapshot_id"],
            },
            database=database,
            clock=clock,
        )
        assert risk["risk_check"]["passed"] == 0
        assert "missing_trade_thesis" in risk["blocked_reason"]
        order = await run_v2_tool(
            "paper.create_order",
            {"signal_id": signal["signal_id"], "risk_check_id": risk["artifact_id"], "intended_size": 10},
            database=database,
            clock=clock,
        )
        assert order["ok"] is False

        decision2 = await run_v2_tool(
            "agent.record_trading_decision",
            {
                "decision_type": "signal",
                "pre_action_reasoning": "Fixture signal with thesis can pass risk.",
                "created_by_agent": "hermes",
                "evidence_refs": [ctx["market_snapshot_id"]],
            },
            database=database,
            clock=clock,
        )
        signal2 = await create_signal_tool(database, clock, ctx, decision2["artifact_id"], with_thesis=True)
        risk2 = await run_v2_tool(
            "risk.check_entry",
            {
                "signal_id": signal2["signal_id"],
                "market_snapshot_id": ctx["market_snapshot_id"],
                "risk_limit_snapshot_id": ctx["risk_limit_snapshot_id"],
                "config_snapshot_id": ctx["config_snapshot_id"],
            },
            database=database,
            clock=clock,
        )
        order2 = await run_v2_tool(
            "paper.create_order",
            {"signal_id": signal2["signal_id"], "risk_check_id": risk2["artifact_id"], "intended_size": 10},
            database=database,
            clock=clock,
        )
        missing_fill = await run_v2_tool(
            "paper.simulate_fill",
            {"paper_order_id": order2["artifact_id"], "market_snapshot_id": "missing-market"},
            database=database,
            clock=clock,
        )
        assert missing_fill["ok"] is True
        assert missing_fill["blocked_reason"] == "missing_market_snapshot"
        assert missing_fill["paper_position_id"] is None

    run(scenario())


def test_orchestrator_smoke_links_exit_outcome_review_memory_and_wallet_report(tmp_path: Path) -> None:
    async def scenario() -> None:
        settings = load_stage2_settings(environment="test", database_path=tmp_path / "stage2.sqlite3")
        database = Stage2Database(settings, clock=FixedClock(BASE_TIME))
        result = await run_orchestrator_smoke(settings=settings, database=database, mode="fixture", clock=FixedClock(BASE_TIME))
        assert result["ok"] is True
        outcome_id = result["exit_fill_and_outcome"]["trade_outcome_id"]
        outcome = await database.fetchone("SELECT * FROM trade_outcomes WHERE outcome_id = ?", (outcome_id,))
        assert outcome is not None
        assert outcome["calculated_by_service"] == "evaluation_service"

        review_id = result["post_trade_review"]["artifact_id"]
        review = await database.fetchone("SELECT * FROM post_trade_review_details WHERE post_trade_review_id = ?", (review_id,))
        assert review is not None
        memory_id = result["memory_proposal"]["artifact_id"]
        memory = await database.fetchone("SELECT * FROM memory_proposals WHERE memory_proposal_id = ?", (memory_id,))
        assert memory is not None
        assert review_id in json.loads(memory["review_refs_json"])

        report = result["wallet_report"]["wallet_report"]
        assert report["linked_outcome_count"] == 1
        assert "fixture_or_smoke_signal_evidence" in report["quality_flags"]
        links = await database.fetchall(
            "SELECT artifact_type FROM agent_trading_decision_artifact_links WHERE artifact_type IN ('trade_outcome', 'post_trade_review', 'memory_proposal', 'wallet_contribution_report')"
        )
        assert {"trade_outcome", "post_trade_review", "memory_proposal", "wallet_contribution_report"} <= {
            row["artifact_type"] for row in links
        }

    run(scenario())


def test_exit_requires_exit_decision_and_exit_risk(tmp_path: Path) -> None:
    async def scenario() -> None:
        database, clock = await migrated_database(tmp_path)
        ctx = await seed_context(database, clock)
        decision = await run_v2_tool(
            "agent.record_trading_decision",
            {
                "decision_type": "signal",
                "pre_action_reasoning": "Fixture entry.",
                "created_by_agent": "hermes",
                "evidence_refs": [ctx["market_snapshot_id"]],
            },
            database=database,
            clock=clock,
        )
        signal = await create_signal_tool(database, clock, ctx, decision["artifact_id"], with_thesis=True)
        risk = await run_v2_tool(
            "risk.check_entry",
            {
                "signal_id": signal["signal_id"],
                "market_snapshot_id": ctx["market_snapshot_id"],
                "risk_limit_snapshot_id": ctx["risk_limit_snapshot_id"],
                "config_snapshot_id": ctx["config_snapshot_id"],
            },
            database=database,
            clock=clock,
        )
        order = await run_v2_tool(
            "paper.create_order",
            {"signal_id": signal["signal_id"], "risk_check_id": risk["artifact_id"], "intended_size": 10},
            database=database,
            clock=clock,
        )
        fill = await run_v2_tool(
            "paper.simulate_fill",
            {"paper_order_id": order["artifact_id"], "market_snapshot_id": ctx["market_snapshot_id"]},
            database=database,
            clock=clock,
        )
        blocked_exit = await run_v2_tool(
            "paper.execute_exit",
            {"exit_decision_id": "missing-exit", "risk_check_id": risk["artifact_id"]},
            database=database,
            clock=clock,
        )
        assert blocked_exit["ok"] is False
        exit_decision = await run_v2_tool(
            "paper.create_exit_decision",
            {
                "position_id": fill["paper_position_id"],
                "market_snapshot_id": ctx["market_snapshot_id"],
                "exit_reason": "fixture exit",
                "exit_trigger": "test",
                "expected_exit_logic": "fixture",
            },
            database=database,
            clock=clock,
        )
        wrong_risk_exit = await run_v2_tool(
            "paper.execute_exit",
            {"exit_decision_id": exit_decision["artifact_id"], "risk_check_id": risk["artifact_id"]},
            database=database,
            clock=clock,
        )
        assert wrong_risk_exit["ok"] is False
        assert "exit RiskCheck" in wrong_risk_exit["blocked_reason"]

    run(scenario())


async def migrated_database(tmp_path: Path) -> tuple[Stage2Database, FixedClock]:
    clock = FixedClock(BASE_TIME)
    settings = load_stage2_settings(environment="test", database_path=tmp_path / "stage2.sqlite3")
    database = Stage2Database(settings, clock=clock)
    await database.migrate()
    return database, clock


async def seed_context(database: Stage2Database, clock: FixedClock) -> dict[str, str]:
    settings = load_stage2_settings(environment="test", database_path=database.path, app_version="test")
    snapshots = ConfigSnapshotRepository(database, clock=clock)
    config_id = await snapshots.create_config_snapshot(source=new_id("test_config"), settings=settings)
    risk_id = await snapshots.create_risk_limit_snapshot(
        config_snapshot_id=config_id,
        source=new_id("test_risk"),
        limits={
            "max_stale_seconds": 3600,
            "max_fill_stale_seconds": 3600,
            "min_liquidity_usd": 1000,
            "allow_low_confidence": False,
            "allow_degraded_sources": False,
            "max_estimated_slippage_bps": 500,
            "max_open_paper_positions": 5,
            "max_position_notional_usd": 100000,
            "max_liquidity_fraction": 0.1,
            "fill_slippage_bps": 50,
            "paper_fee_bps": 25,
            "fill_latency_ms": 1500,
        },
    )
    strategy_config_id = await snapshots.create_strategy_config_snapshot(
        config_snapshot_id=config_id,
        strategy_name=new_id("test_strategy"),
        strategy_version_label=new_id("v"),
        thresholds={"test": True},
        signal_rules={"agent_decision_required": True},
        exit_rules={"exit_decision_required": True},
    )
    strategy_version_id = await DomainRepository(database, clock=clock).create_strategy_version(
        strategy_config_snapshot_id=strategy_config_id,
        rules={"test": True},
        params={"paper_only": True},
        agents=["hermes"],
    )
    market_id = await seed_market(database, clock, token_mint="token-test", pool_address="pool-test", price_usd=1.0)
    return {
        "config_snapshot_id": config_id,
        "risk_limit_snapshot_id": risk_id,
        "strategy_config_snapshot_id": strategy_config_id,
        "strategy_version_id": strategy_version_id,
        "market_snapshot_id": market_id,
        "token_mint": "token-test",
    }


async def create_signal_tool(
    database: Stage2Database,
    clock: FixedClock,
    ctx: dict[str, str],
    decision_id: str,
    *,
    with_thesis: bool,
) -> dict:
    payload = {
        "agent_trading_decision_id": decision_id,
        "strategy_version_id": ctx["strategy_version_id"],
        "strategy_config_snapshot_id": ctx["strategy_config_snapshot_id"],
        "token_id": ctx["token_mint"],
        "market_snapshot_id": ctx["market_snapshot_id"],
        "source_refs": [ctx["market_snapshot_id"]],
        "confidence": "medium",
        "invalidation_condition": "fixture invalidation",
        "expected_holding_time": "fixture",
        "estimated_risk": {"intended_size": 10},
        "estimated_slippage": 50,
    }
    if with_thesis:
        payload["thesis"] = {
            "why_token": "fixture token",
            "why_now": "fixture timing",
            "planned_exit_logic": "fixture exit",
            "invalidation_condition": "fixture invalidation",
            "wrong_condition": "fixture wrong",
            "uncopyable_risk": "fixture risk",
            "expected_holding_time": "fixture",
            "evidence_refs": [ctx["market_snapshot_id"]],
        }
    return await run_v2_tool("signal.create", payload, database=database, clock=clock)


async def seed_market(
    database: Stage2Database,
    clock: FixedClock,
    *,
    token_mint: str,
    pool_address: str,
    price_usd: float,
) -> str:
    raw_id = new_id("raw")
    market_id = new_id("market")
    observed = (BASE_TIME - timedelta(seconds=5)).isoformat()
    await database.execute(
        """
        INSERT INTO raw_source_events(
          raw_source_event_id, source_name, source_type, external_id, payload_json,
          observed_at, ingested_at, confidence, quality_metadata_json
        )
        VALUES (?, 'fixture', 'fixture_market', ?, '{}', ?, ?, 'high', '{}')
        """,
        (raw_id, raw_id, observed, observed),
    )
    await database.execute(
        """
        INSERT INTO market_snapshots(
          market_snapshot_id, token_mint, pool_address, chain, observed_at,
          source_name, raw_source_event_id, price_usd, liquidity_usd, volume_5m,
          volume_1h, volume_6h, volume_24h, market_cap, fdv, txns_5m,
          txns_1h, holder_count, confidence, quality_flags_json,
          eligible_for_high_confidence_evaluation, created_at
        )
        VALUES (?, ?, ?, 'solana', ?, 'fixture', ?, ?, 50000, 1000, 5000, 10000,
                25000, 250000, 300000, 5, 21, 100, 'high', '[]', 1, ?)
        """,
        (market_id, token_mint, pool_address, observed, raw_id, price_usd, observed),
    )
    return market_id
