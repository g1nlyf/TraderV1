from __future__ import annotations

from datetime import timedelta
from typing import Any

from walletscarper.stage2.clock import Clock, SystemClock, isoformat_utc
from walletscarper.stage2.config import Stage2Settings
from walletscarper.stage2.config_snapshots import ConfigSnapshotRepository
from walletscarper.stage2.db import Stage2Database
from walletscarper.stage2.db.json import dumps_json
from walletscarper.stage2.domain import DomainRepository
from walletscarper.stage2.hermes_integration.v2_tools import run_v2_tool
from walletscarper.stage2.ids import new_id


async def run_orchestrator_smoke(
    *,
    settings: Stage2Settings,
    database: Stage2Database,
    mode: str = "fixture",
    clock: Clock | None = None,
) -> dict[str, Any]:
    if mode not in {"fixture", "smoke"}:
        raise ValueError("stage2-v2-orchestrator-smoke currently supports fixture or smoke mode only")
    resolved_clock = clock or SystemClock()
    await database.migrate()
    seed = await _seed_fixture_context(settings=settings, database=database, clock=resolved_clock, mode=mode)
    wallet = seed["wallet"]
    token = seed["token_mint"]
    pool = seed["pool_address"]
    entry_market = seed["entry_market_snapshot_id"]
    exit_market = seed["exit_market_snapshot_id"]
    base_payload = {"input_mode": mode}

    buy_event = await run_v2_tool(
        "wallet.record_signal_event",
        {
            **base_payload,
            "wallet": wallet,
            "token_mint": token,
            "pool_address": pool,
            "side": "buy",
            "observed_at": seed["entry_observed_at"],
            "source_name": f"{mode}_tracked_wallet_signal",
            "source_refs": [f"market_snapshot:{entry_market}", seed["token_agent_decision_id"], seed["agent_wallet_review_id"]],
            "latency_metadata": {"mode": mode, "latency_ms": 250},
            "data_sufficiency": "partial",
        },
        settings=settings,
        database=database,
        clock=resolved_clock,
    )
    decision = await run_v2_tool(
        "agent.record_trading_decision",
        {
            "decision_type": "signal",
            "pre_action_reasoning": "Fixture tracked wallet buy plus fresh market evidence supports a paper research entry.",
            "created_by_agent": "hermes",
            "wallet_refs": [wallet, seed["agent_wallet_review_id"]],
            "token_refs": [token, seed["token_agent_decision_id"]],
            "market_snapshot_refs": [entry_market],
            "source_quality_summary": {"mode": mode, "market_snapshot": "fixture_high_confidence"},
            "evidence_refs": [buy_event["artifact_id"], entry_market, seed["token_agent_decision_id"], seed["agent_wallet_review_id"]],
            "data_as_of": seed["entry_observed_at"],
            "linked_tracked_wallet_signal_event_id": buy_event["artifact_id"],
            "quality_flags": [f"{mode}_orchestrator_smoke"],
        },
        settings=settings,
        database=database,
        clock=resolved_clock,
    )
    signal = await run_v2_tool(
        "signal.create",
        {
            "agent_trading_decision_id": decision["artifact_id"],
            "strategy_version_id": seed["strategy_version_id"],
            "strategy_config_snapshot_id": seed["strategy_config_snapshot_id"],
            "token_id": token,
            "market_snapshot_id": entry_market,
            "source_refs": [buy_event["artifact_id"], entry_market],
            "confidence": "medium",
            "invalidation_condition": "fixture exit signal or market deterioration",
            "expected_holding_time": "fixture smoke interval",
            "estimated_risk": {"intended_size": 10},
            "estimated_slippage": 50,
            "data_as_of": seed["entry_observed_at"],
            "thesis": {
                "why_token": "Token has fixture market evidence for smoke validation.",
                "why_now": "Tracked wallet fixture buy is being tested as one evidence input.",
                "planned_exit_logic": "Exit on fixture tracked wallet sell or deteriorating market evidence.",
                "invalidation_condition": "Risk veto, stale data, or failed fill.",
                "wrong_condition": "Fixture path fails deterministic gates.",
                "uncopyable_risk": "Fixture evidence is not real market proof.",
                "expected_holding_time": "fixture smoke interval",
                "evidence_refs": [buy_event["artifact_id"], entry_market],
            },
        },
        settings=settings,
        database=database,
        clock=resolved_clock,
    )
    entry_risk = await run_v2_tool(
        "risk.check_entry",
        {
            "signal_id": signal["signal_id"],
            "market_snapshot_id": entry_market,
            "risk_limit_snapshot_id": seed["risk_limit_snapshot_id"],
            "config_snapshot_id": seed["config_snapshot_id"],
        },
        settings=settings,
        database=database,
        clock=resolved_clock,
    )
    order = await run_v2_tool(
        "paper.create_order",
        {
            "agent_trading_decision_id": decision["artifact_id"],
            "signal_id": signal["signal_id"],
            "risk_check_id": entry_risk["artifact_id"],
            "intended_size": 10,
        },
        settings=settings,
        database=database,
        clock=resolved_clock,
    )
    fill = await run_v2_tool(
        "paper.simulate_fill",
        {
            "agent_trading_decision_id": decision["artifact_id"],
            "paper_order_id": order["artifact_id"],
            "market_snapshot_id": entry_market,
        },
        settings=settings,
        database=database,
        clock=resolved_clock,
    )
    sell_event = await run_v2_tool(
        "wallet.record_signal_event",
        {
            **base_payload,
            "wallet": wallet,
            "token_mint": token,
            "pool_address": pool,
            "side": "sell",
            "observed_at": seed["exit_observed_at"],
            "source_name": f"{mode}_tracked_wallet_signal",
            "source_refs": [f"market_snapshot:{exit_market}", buy_event["artifact_id"]],
            "latency_metadata": {"mode": mode, "latency_ms": 300},
            "data_sufficiency": "partial",
        },
        settings=settings,
        database=database,
        clock=resolved_clock,
    )
    exit_decision = await run_v2_tool(
        "agent.record_trading_decision",
        {
            "decision_type": "exit",
            "pre_action_reasoning": "Fixture tracked wallet sell supports a paper exit review before deterministic exit risk.",
            "created_by_agent": "hermes",
            "wallet_refs": [wallet, seed["agent_wallet_review_id"]],
            "token_refs": [token, seed["token_agent_decision_id"]],
            "market_snapshot_refs": [exit_market],
            "source_quality_summary": {"mode": mode, "market_snapshot": "fixture_high_confidence"},
            "evidence_refs": [sell_event["artifact_id"], exit_market, signal["signal_id"]],
            "data_as_of": seed["exit_observed_at"],
            "linked_tracked_wallet_signal_event_id": sell_event["artifact_id"],
            "quality_flags": [f"{mode}_orchestrator_smoke"],
        },
        settings=settings,
        database=database,
        clock=resolved_clock,
    )
    exit_record = await run_v2_tool(
        "paper.create_exit_decision",
        {
            "agent_trading_decision_id": exit_decision["artifact_id"],
            "position_id": fill["paper_position_id"],
            "market_snapshot_id": exit_market,
            "data_as_of": seed["exit_observed_at"],
            "exit_reason": "fixture tracked wallet sell evidence",
            "exit_trigger": "tracked_wallet_sell_fixture",
            "expected_exit_logic": "simulate deterministic paper exit after passed exit risk",
            "created_by": "hermes",
        },
        settings=settings,
        database=database,
        clock=resolved_clock,
    )
    exit_risk = await run_v2_tool(
        "risk.check_exit",
        {
            "exit_decision_id": exit_record["artifact_id"],
            "market_snapshot_id": exit_market,
            "risk_limit_snapshot_id": seed["risk_limit_snapshot_id"],
            "config_snapshot_id": seed["config_snapshot_id"],
        },
        settings=settings,
        database=database,
        clock=resolved_clock,
    )
    exit_fill = await run_v2_tool(
        "paper.execute_exit",
        {
            "agent_trading_decision_id": exit_decision["artifact_id"],
            "exit_decision_id": exit_record["artifact_id"],
            "risk_check_id": exit_risk["artifact_id"],
        },
        settings=settings,
        database=database,
        clock=resolved_clock,
    )
    review = await run_v2_tool(
        "review.create_post_trade",
        {
            "agent_trading_decision_id": exit_decision["artifact_id"],
            "outcome_id": exit_fill["trade_outcome_id"],
            "reviewer": "hermes",
            "source_quality_issues": [f"{mode}_not_real_source_evidence"],
            "lessons": ["Fixture smoke proves the typed path, not market profitability."],
            "evidence_refs": [decision["artifact_id"], exit_decision["artifact_id"], sell_event["artifact_id"]],
            "exit_matched_plan": True,
        },
        settings=settings,
        database=database,
        clock=resolved_clock,
    )
    memory = await run_v2_tool(
        "memory.propose",
        {
            "agent_trading_decision_id": exit_decision["artifact_id"],
            "claim": "Fixture smoke path completed; do not treat fixture PnL as real market edge.",
            "memory_type": "warning",
            "evidence_refs": [exit_fill["trade_outcome_id"]],
            "review_refs": [review["artifact_id"]],
            "strategy_refs": [seed["strategy_version_id"]],
            "confidence": "medium",
            "validity_scope": {"mode": mode, "truth_boundary": "fixture_or_smoke_only"},
            "created_by": "hermes",
        },
        settings=settings,
        database=database,
        clock=resolved_clock,
    )
    wallet_report = await run_v2_tool(
        "metrics.wallet_report",
        {
            "agent_trading_decision_id": exit_decision["artifact_id"],
            "wallet": wallet,
            "strategy_version_id": seed["strategy_version_id"],
        },
        settings=settings,
        database=database,
        clock=resolved_clock,
    )
    return {
        "ok": all(item.get("ok") for item in [buy_event, decision, signal, entry_risk, order, fill, sell_event, exit_decision, exit_record, exit_risk, exit_fill, review, memory, wallet_report]),
        "mode": mode,
        "truth_boundary": f"{mode} orchestrator smoke only; not real market profitability evidence",
        "seed": seed,
        "tracked_wallet_buy_signal": buy_event,
        "entry_agent_decision": decision,
        "signal": signal,
        "entry_risk": entry_risk,
        "paper_order": order,
        "entry_fill": fill,
        "tracked_wallet_sell_signal": sell_event,
        "exit_agent_decision": exit_decision,
        "exit_decision": exit_record,
        "exit_risk": exit_risk,
        "exit_fill_and_outcome": exit_fill,
        "post_trade_review": review,
        "memory_proposal": memory,
        "wallet_report": wallet_report,
    }


async def _seed_fixture_context(
    *,
    settings: Stage2Settings,
    database: Stage2Database,
    clock: Clock,
    mode: str,
) -> dict[str, Any]:
    now = clock.now()
    token = f"v2-sprint2-{mode}-token"
    pool = f"v2-sprint2-{mode}-pool"
    wallet = f"v2-sprint2-{mode}-wallet"
    stamp = str(int(now.timestamp() * 1000))
    snapshots = ConfigSnapshotRepository(database, clock=clock)
    config_id = await snapshots.create_config_snapshot(
        source=f"v2_sprint2_{mode}_smoke_{stamp}",
        settings=settings,
        build_info={"v2_sprint2_smoke": True, "mode": mode, "stamp": stamp},
    )
    risk_id = await snapshots.create_risk_limit_snapshot(
        config_snapshot_id=config_id,
        source=f"v2_sprint2_{mode}_smoke_{stamp}",
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
        strategy_name="v2-sprint2-hermes-orchestrator-smoke",
        strategy_version_label=f"{mode}-{stamp}",
        thresholds={"fixture_path": True, "paper_only": True},
        signal_rules={"agent_decision_required": True},
        exit_rules={"exit_decision_before_fill": True},
        no_trade_rules={"no_trade_is_first_class": True},
    )
    strategy_version_id = await DomainRepository(database, clock=clock).create_strategy_version(
        strategy_config_snapshot_id=strategy_config_id,
        rules={"v2_sprint2_smoke": True, "mode": mode},
        params={"paper_only": True},
        agents=["hermes"],
    )
    entry_observed = now - timedelta(seconds=10)
    exit_observed = now - timedelta(seconds=2)
    entry_market_id = await _insert_market_snapshot(
        database=database,
        token_mint=token,
        pool_address=pool,
        observed_at=isoformat_utc(entry_observed),
        price_usd=1.0,
        liquidity_usd=50_000,
        mode=mode,
    )
    exit_market_id = await _insert_market_snapshot(
        database=database,
        token_mint=token,
        pool_address=pool,
        observed_at=isoformat_utc(exit_observed),
        price_usd=1.2,
        liquidity_usd=55_000,
        mode=mode,
    )
    token_decision = await run_v2_tool(
        "token.record_agent_decision",
        {
            "decision_type": "active_watch",
            "created_by_agent": "hermes",
            "token_mint": token,
            "pool_address": pool,
            "reasons": ["Fixture token selected for V2 Sprint 2 orchestrator smoke."],
            "evidence_refs": [entry_market_id],
            "confidence": "medium",
        },
        settings=settings,
        database=database,
        clock=clock,
    )
    wallet_review = await run_v2_tool(
        "wallet.record_agent_review",
        {
            "wallet": wallet,
            "decision": "probation",
            "created_by_agent": "hermes",
            "agent_rating": 0.5,
            "copyability_rating": 0.5,
            "pnl_quality": "unknown",
            "winrate_quality": "unknown",
            "why_yes": ["Fixture wallet used to validate orchestration."],
            "why_no": ["Fixture history is not real wallet history."],
            "demotion_triggers": ["No real forward evidence."],
            "data_sufficiency": "partial",
            "observed_behavior": {"mode": mode},
            "unknowns": ["fixture-only wallet evidence"],
            "evidence_refs": [entry_market_id],
        },
        settings=settings,
        database=database,
        clock=clock,
    )
    return {
        "config_snapshot_id": config_id,
        "risk_limit_snapshot_id": risk_id,
        "strategy_config_snapshot_id": strategy_config_id,
        "strategy_version_id": strategy_version_id,
        "entry_market_snapshot_id": entry_market_id,
        "exit_market_snapshot_id": exit_market_id,
        "entry_observed_at": isoformat_utc(entry_observed),
        "exit_observed_at": isoformat_utc(exit_observed),
        "token_agent_decision_id": token_decision["artifact_id"],
        "agent_wallet_review_id": wallet_review["artifact_id"],
        "token_mint": token,
        "pool_address": pool,
        "wallet": wallet,
    }


async def _insert_market_snapshot(
    *,
    database: Stage2Database,
    token_mint: str,
    pool_address: str,
    observed_at: str,
    price_usd: float,
    liquidity_usd: float,
    mode: str,
) -> str:
    raw_id = new_id("raw_source_event")
    market_id = new_id("market_snapshot")
    await database.execute(
        """
        INSERT INTO raw_source_events(
          raw_source_event_id, source_name, source_type, external_id, payload_json,
          observed_at, ingested_at, confidence, quality_metadata_json
        )
        VALUES (?, ?, 'fixture_market_snapshot', ?, ?, ?, ?, 'high', ?)
        """,
        (
            raw_id,
            f"v2_sprint2_{mode}_smoke",
            raw_id,
            dumps_json({"mode": mode, "token_mint": token_mint, "pool_address": pool_address, "price_usd": price_usd}),
            observed_at,
            observed_at,
            dumps_json({"quality_flags": [f"{mode}_market_evidence"]}),
        ),
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
        VALUES (?, ?, ?, 'solana', ?, ?, ?, ?, ?, 1000, 5000, 10000, 25000,
                250000, 300000, 5, 21, 100, 'high', ?, 1, ?)
        """,
        (
            market_id,
            token_mint,
            pool_address,
            observed_at,
            f"v2_sprint2_{mode}_smoke",
            raw_id,
            price_usd,
            liquidity_usd,
            dumps_json([f"{mode}_market_evidence"]),
            observed_at,
        ),
    )
    return market_id
