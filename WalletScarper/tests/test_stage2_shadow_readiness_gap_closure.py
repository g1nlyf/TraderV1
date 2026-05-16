from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from walletscarper import __main__ as cli
from walletscarper.stage2.acceptance import ShadowModeAssessmentService
from walletscarper.stage2.clock import FixedClock
from walletscarper.stage2.config import load_stage2_settings
from walletscarper.stage2.config_snapshots import ConfigSnapshotRepository
from walletscarper.stage2.db import Stage2Database
from walletscarper.stage2.domain import DomainRepository
from walletscarper.stage2.evaluation import DeterministicEvaluationService
from walletscarper.stage2.paper_trading import Sprint3PaperTradingService
from walletscarper.stage2.risk import DeterministicRiskService
from walletscarper.stage2.shadow_readiness import (
    FillQuoteComparisonService,
    LiveDataAcceptanceWindowService,
    QuoteObservationService,
    RouteQualityService,
)
from walletscarper.stage2.signals import SignalService


BASE_TIME = datetime(2026, 5, 15, 12, 0, tzinfo=timezone.utc)


def run(coro):
    return asyncio.run(coro)


async def shadow_db(tmp_path: Path, *, clock: FixedClock | None = None) -> tuple[Stage2Database, FixedClock]:
    fixed = clock or FixedClock(BASE_TIME)
    settings = load_stage2_settings(
        environment="test",
        database_path=tmp_path / "stage2_shadow_readiness.sqlite3",
        app_version="test",
    )
    database = Stage2Database(settings, clock=fixed)
    await database.migrate()
    return database, fixed


def test_shadow_readiness_migration_tables_exist(tmp_path: Path) -> None:
    async def scenario() -> None:
        database, _clock = await shadow_db(tmp_path)
        rows = await database.fetchall(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
              AND name IN (
                'quote_observations',
                'source_latency_samples',
                'route_quality_evidence',
                'fill_quote_comparisons',
                'live_data_acceptance_windows'
              )
            """
        )
        assert {row["name"] for row in rows} == {
            "quote_observations",
            "source_latency_samples",
            "route_quality_evidence",
            "fill_quote_comparisons",
            "live_data_acceptance_windows",
        }

    run(scenario())


def test_quote_capture_is_observation_only_and_normalizes_market_evidence(tmp_path: Path) -> None:
    async def scenario() -> None:
        database, clock = await shadow_db(tmp_path)
        before = await database.table_counts(["signals", "risk_checks", "paper_orders", "paper_fills", "trade_outcomes"])

        quote_id = await QuoteObservationService(database, clock=clock).record_quote_observation(
            source_name="stage2_quote_observer",
            token_mint="quote-token-1",
            pool_address="quote-pool-1",
            price_usd=1.25,
            liquidity_usd=50_000,
            observed_at=BASE_TIME - timedelta(seconds=2),
            response_latency_ms=85,
            confidence="high",
            provenance={"adapter_boundary": "test_observation_only"},
        )

        after = await database.table_counts(
            [
                "raw_source_events",
                "market_snapshots",
                "normalized_evidence_refs",
                "quote_observations",
                "source_latency_samples",
                "signals",
                "risk_checks",
                "paper_orders",
                "paper_fills",
                "trade_outcomes",
            ]
        )
        quote = await database.fetchone("SELECT * FROM quote_observations WHERE quote_observation_id = ?", (quote_id,))
        market = await database.fetchone("SELECT * FROM market_snapshots WHERE market_snapshot_id = ?", (quote["market_snapshot_id"],))
        latency = await database.fetchone("SELECT * FROM source_latency_samples WHERE quote_observation_id = ?", (quote_id,))

        assert after["raw_source_events"] == 1
        assert after["market_snapshots"] == 1
        assert after["normalized_evidence_refs"] >= 1
        assert after["quote_observations"] == 1
        assert after["source_latency_samples"] == 1
        assert {key: after[key] for key in before} == before
        assert quote["eligible_for_shadow_comparison"] == 1
        assert quote["latency_ms"] >= 2000
        assert quote["response_latency_ms"] == 85
        assert market["price_usd"] == pytest.approx(1.25)
        assert market["eligible_for_high_confidence_evaluation"] == 1
        assert latency["source_name"] == "stage2_quote_observer"

    run(scenario())


def test_stale_quote_degrades_confidence_and_shadow_eligibility(tmp_path: Path) -> None:
    async def scenario() -> None:
        database, clock = await shadow_db(tmp_path)
        quote_id = await QuoteObservationService(database, clock=clock).record_quote_observation(
            source_name="stage2_quote_observer",
            token_mint="quote-token-1",
            pool_address="quote-pool-1",
            price_usd=1.25,
            liquidity_usd=50_000,
            observed_at=BASE_TIME - timedelta(minutes=30),
            response_latency_ms=None,
            confidence="high",
            max_quote_age_seconds=300,
        )
        quote = await database.fetchone("SELECT * FROM quote_observations WHERE quote_observation_id = ?", (quote_id,))
        market = await database.fetchone("SELECT * FROM market_snapshots WHERE market_snapshot_id = ?", (quote["market_snapshot_id"],))
        flags = set(json.loads(quote["quality_flags_json"]))

        assert quote["confidence"] == "low"
        assert quote["eligible_for_shadow_comparison"] == 0
        assert "stale_source_data" in flags
        assert market["eligible_for_high_confidence_evaluation"] == 0

    run(scenario())


def test_route_quality_missing_evidence_keeps_gap_open(tmp_path: Path) -> None:
    async def scenario() -> None:
        database, clock = await shadow_db(tmp_path)
        quote_id = await QuoteObservationService(database, clock=clock).record_quote_observation(
            source_name="stage2_quote_observer",
            token_mint="quote-token-1",
            pool_address="quote-pool-1",
            price_usd=1.25,
            liquidity_usd=None,
            observed_at=BASE_TIME - timedelta(seconds=1),
            response_latency_ms=50,
            confidence="high",
        )
        route_id = await RouteQualityService(database, clock=clock).record_route_quality(
            quote_observation_id=quote_id,
            route_depth_usd=None,
            spread_bps=None,
            independent_quote_count=1,
        )
        route = await database.fetchone("SELECT * FROM route_quality_evidence WHERE route_quality_evidence_id = ?", (route_id,))
        assessment = await ShadowModeAssessmentService(database, clock=clock).assess()
        missing = {gap["missing_capability"] for gap in assessment["gaps"]}

        assert route["sufficient_for_shadow_comparison"] == 0
        assert "route_quality_model" in missing
        assert assessment["status"] == "gap_report_required"

    run(scenario())


def test_fill_vs_quote_comparison_is_append_only_and_does_not_rewrite_outcome(tmp_path: Path) -> None:
    async def scenario() -> None:
        ctx = await paper_trade_context(tmp_path)
        database = ctx["database"]
        outcome_before = await database.fetchone("SELECT * FROM trade_outcomes WHERE outcome_id = ?", (ctx["outcome_id"],))
        fill_before = await database.fetchone("SELECT * FROM paper_fills WHERE paper_fill_id = ?", (ctx["exit_fill_id"],))

        quote_id = await QuoteObservationService(database, clock=ctx["exit_clock"]).record_quote_observation(
            source_name="stage2_quote_observer",
            token_mint="paper-token-1",
            pool_address="paper-pool-1",
            price_usd=1.49,
            liquidity_usd=80_000,
            observed_at=BASE_TIME + timedelta(minutes=5, seconds=-1),
            response_latency_ms=40,
            confidence="high",
        )
        route_id = await RouteQualityService(database, clock=ctx["exit_clock"]).record_route_quality(
            quote_observation_id=quote_id,
            route_depth_usd=5_000,
            spread_bps=25,
            independent_quote_count=2,
        )
        comparison_id = await FillQuoteComparisonService(database, clock=ctx["exit_clock"]).compare_fill_to_quote(
            paper_fill_id=ctx["exit_fill_id"],
            quote_observation_id=quote_id,
            route_quality_evidence_id=route_id,
            max_quote_age_seconds=10,
        )

        comparison = await database.fetchone(
            "SELECT * FROM fill_quote_comparisons WHERE fill_quote_comparison_id = ?",
            (comparison_id,),
        )
        outcome_after = await database.fetchone("SELECT * FROM trade_outcomes WHERE outcome_id = ?", (ctx["outcome_id"],))
        fill_after = await database.fetchone("SELECT * FROM paper_fills WHERE paper_fill_id = ?", (ctx["exit_fill_id"],))

        assert comparison["status"] == "passed"
        assert comparison["difference_bps"] is not None
        assert dict(outcome_after) == dict(outcome_before)
        assert dict(fill_after) == dict(fill_before)
        with pytest.raises(Exception, match="append-only"):
            await database.execute(
                "UPDATE fill_quote_comparisons SET status = 'mutated' WHERE fill_quote_comparison_id = ?",
                (comparison_id,),
            )

    run(scenario())


def test_live_data_acceptance_window_fails_closed_without_comparison_evidence(tmp_path: Path) -> None:
    async def scenario() -> None:
        database, clock = await shadow_db(tmp_path)
        quote_id = await QuoteObservationService(database, clock=clock).record_quote_observation(
            source_name="stage2_quote_observer",
            token_mint="quote-token-1",
            pool_address="quote-pool-1",
            price_usd=1.25,
            liquidity_usd=50_000,
            observed_at=BASE_TIME - timedelta(seconds=1),
            response_latency_ms=60,
            confidence="high",
        )
        await RouteQualityService(database, clock=clock).record_route_quality(
            quote_observation_id=quote_id,
            route_depth_usd=5_000,
            spread_bps=30,
            independent_quote_count=2,
        )
        window_id = await LiveDataAcceptanceWindowService(database, clock=clock).run_observation_window(
            source_names=["stage2_quote_observer"],
            token_mints=["quote-token-1"],
            min_fresh_quotes=1,
            require_fill_comparisons=True,
        )
        window = await database.fetchone(
            "SELECT * FROM live_data_acceptance_windows WHERE live_data_acceptance_window_id = ?",
            (window_id,),
        )
        gaps = set(json.loads(window["gaps_json"]))

        assert window["status"] == "gap_report_required"
        assert "fill_vs_quote_comparison" in gaps
        assert window["quotes_seen"] == 1

    run(scenario())


def test_all_free_calibration_writes_independent_source_evidence(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    database_path = tmp_path / "all_free.sqlite3"

    async def fake_fetch(source_name: str, token_mint: str, pool_address: str | None) -> dict[str, object] | None:
        now = datetime.now(timezone.utc)
        prices = {"dexscreener": 1.0, "geckoterminal": 1.01, "dexpaprika": 1.005}
        return {
            "source_name": source_name,
            "adapter_name": f"{source_name}_fixture",
            "endpoint": f"fixture://{source_name}",
            "token_mint": token_mint,
            "pool_address": pool_address or "pool-1",
            "price_usd": prices[source_name],
            "liquidity_usd": 60_000,
            "route_depth_usd": 5_000,
            "response_latency_ms": 25,
            "observed_at": now if source_name == "dexpaprika" else None,
            "confidence": "high" if source_name == "dexpaprika" else "medium",
            "quality_flags": [] if source_name == "dexpaprika" else ["source_timestamp_not_provided"],
            "source_timestamp_note": "fixture timestamp",
        }

    monkeypatch.setattr(cli, "_fetch_source_quote", fake_fetch)

    async def scenario() -> None:
        result = await cli._run_calibration_window(
            token_mint="token-1",
            pool_address="pool-1",
            source="all_free",
            selected_sources=["dexscreener", "geckoterminal", "dexpaprika"],
            duration_seconds=300,
            interval_seconds=1,
            max_samples=1,
            database_path=database_path,
        )
        settings = load_stage2_settings(environment="test", database_path=database_path, app_version="test")
        database = Stage2Database(settings)
        quotes = await database.fetchall("SELECT * FROM quote_observations ORDER BY source_name")
        routes = await database.fetchall("SELECT * FROM route_quality_evidence ORDER BY created_at, route_quality_evidence_id")
        counts = await database.table_counts(["signals", "risk_checks", "paper_orders", "paper_fills", "trade_outcomes"])
        window = await database.fetchone("SELECT * FROM live_data_acceptance_windows WHERE live_data_acceptance_window_id = ?", (result["live_data_acceptance_window_id"],))
        metrics = json.loads(window["metrics_json"])

        assert result["status"] == "gap_report_required"
        assert result["failures"] == []
        assert len(quotes) == 3
        assert len(routes) == 3
        assert {row["source_name"] for row in quotes} == {"dexscreener", "geckoterminal", "dexpaprika"}
        assert any(int(row["sufficient_for_shadow_comparison"]) == 1 for row in routes)
        assert metrics["independent_quote_evidence_present"] is True
        assert counts == {"signals": 0, "risk_checks": 0, "paper_orders": 0, "paper_fills": 0, "trade_outcomes": 0}

    run(scenario())


def test_all_free_independent_source_failure_degrades_health_without_crashing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    database_path = tmp_path / "all_free_failure.sqlite3"

    async def fake_fetch(source_name: str, token_mint: str, pool_address: str | None) -> dict[str, object] | None:
        if source_name == "geckoterminal":
            raise cli.CalibrationSourceError(
                "rate_limited",
                source_name="geckoterminal",
                status_code=429,
                rate_limited=True,
                latency_ms=10,
            )
        if source_name == "dexpaprika":
            return None
        return {
            "source_name": source_name,
            "adapter_name": "fixture",
            "endpoint": "fixture://dexscreener",
            "token_mint": token_mint,
            "pool_address": pool_address or "pool-1",
            "price_usd": 1.0,
            "liquidity_usd": 60_000,
            "route_depth_usd": 5_000,
            "response_latency_ms": 20,
            "observed_at": None,
            "confidence": "medium",
            "quality_flags": ["source_timestamp_not_provided"],
        }

    monkeypatch.setattr(cli, "_fetch_source_quote", fake_fetch)

    async def scenario() -> None:
        result = await cli._run_calibration_window(
            token_mint="token-1",
            pool_address="pool-1",
            source="all_free",
            selected_sources=["dexscreener", "geckoterminal", "dexpaprika"],
            duration_seconds=300,
            interval_seconds=1,
            max_samples=1,
            database_path=database_path,
        )
        settings = load_stage2_settings(environment="test", database_path=database_path, app_version="test")
        database = Stage2Database(settings)
        gecko_health = await database.fetchone(
            "SELECT * FROM source_health_snapshots WHERE source_name = 'geckoterminal' ORDER BY observed_at DESC LIMIT 1"
        )
        paprika_health = await database.fetchone(
            "SELECT * FROM source_health_snapshots WHERE source_name = 'dexpaprika' ORDER BY observed_at DESC LIMIT 1"
        )

        assert result["status"] == "gap_report_required"
        assert {failure["source"] for failure in result["failures"]} == {"geckoterminal", "dexpaprika"}
        assert gecko_health["status"] == "degraded"
        assert paprika_health["status"] == "degraded"
        assert json.loads(gecko_health["rate_limit_state_json"])["rate_limited"] is True

    run(scenario())


def test_missing_independent_quote_keeps_fill_comparison_gap_open(tmp_path: Path) -> None:
    async def scenario() -> None:
        database, clock = await shadow_db(tmp_path)
        quote_id = await QuoteObservationService(database, clock=clock).record_quote_observation(
            source_name="stage2_quote_observer",
            token_mint="quote-token-1",
            pool_address="quote-pool-1",
            price_usd=1.25,
            liquidity_usd=50_000,
            observed_at=BASE_TIME - timedelta(seconds=1),
            response_latency_ms=60,
            confidence="high",
        )
        route_id = await RouteQualityService(database, clock=clock).record_route_quality(
            quote_observation_id=quote_id,
            route_depth_usd=5_000,
            spread_bps=30,
            independent_quote_count=0,
        )
        comparison_ids = await FillQuoteComparisonService(database, clock=clock).compare_recent_fills_for_quote(
            quote_observation_id=quote_id,
            route_quality_evidence_id=route_id,
        )
        window_id = await LiveDataAcceptanceWindowService(database, clock=clock).run_observation_window(
            source_names=["stage2_quote_observer"],
            token_mints=["quote-token-1"],
            min_fresh_quotes=1,
            require_fill_comparisons=True,
        )
        window = await database.fetchone("SELECT * FROM live_data_acceptance_windows WHERE live_data_acceptance_window_id = ?", (window_id,))
        gaps = set(json.loads(window["gaps_json"]))

        assert comparison_ids == []
        assert "fill_vs_quote_comparison" in gaps

    run(scenario())


def test_valid_independent_quote_creates_comparison_without_mutating_trade_truth(tmp_path: Path) -> None:
    async def scenario() -> None:
        ctx = await paper_trade_context(tmp_path)
        database = ctx["database"]
        outcome_before = await database.fetchone("SELECT * FROM trade_outcomes WHERE outcome_id = ?", (ctx["outcome_id"],))
        fill_before = await database.fetchone("SELECT * FROM paper_fills WHERE paper_fill_id = ?", (ctx["exit_fill_id"],))

        quote_id = await QuoteObservationService(database, clock=ctx["exit_clock"]).record_quote_observation(
            source_name="dexpaprika",
            token_mint="paper-token-1",
            pool_address="paper-pool-1",
            price_usd=1.49,
            liquidity_usd=90_000,
            observed_at=BASE_TIME + timedelta(minutes=5, seconds=-1),
            response_latency_ms=35,
            confidence="high",
        )
        route_id = await RouteQualityService(database, clock=ctx["exit_clock"]).record_route_quality(
            quote_observation_id=quote_id,
            route_depth_usd=5_000,
            spread_bps=20,
            independent_quote_count=1,
        )
        comparison_ids = await FillQuoteComparisonService(database, clock=ctx["exit_clock"]).compare_recent_fills_for_quote(
            quote_observation_id=quote_id,
            route_quality_evidence_id=route_id,
            max_quote_age_seconds=10,
        )
        comparison = await database.fetchone(
            "SELECT * FROM fill_quote_comparisons WHERE fill_quote_comparison_id = ?",
            (comparison_ids[0],),
        )
        outcome_after = await database.fetchone("SELECT * FROM trade_outcomes WHERE outcome_id = ?", (ctx["outcome_id"],))
        fill_after = await database.fetchone("SELECT * FROM paper_fills WHERE paper_fill_id = ?", (ctx["exit_fill_id"],))

        assert len(comparison_ids) == 1
        assert comparison["status"] == "passed"
        assert dict(outcome_after) == dict(outcome_before)
        assert dict(fill_after) == dict(fill_before)

    run(scenario())


def test_shadow_readiness_runtime_has_no_execution_or_credential_path_terms() -> None:
    stage2_root = Path(__file__).resolve().parents[1] / "walletscarper" / "stage2"
    prohibited = [
        "_".join(["private", "key"]),
        "_".join(["secret", "key"]),
        "seed" + " phrase",
        "sign" + "Transaction",
        "send" + "Transaction",
        "Versioned" + "Transaction",
        ("swa" + "p") + " adapter",
        "dex" + " transaction",
        "jup" + "iter",
        "ray" + "dium",
    ]
    findings: list[str] = []
    for path in stage2_root.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore").lower()
        for term in prohibited:
            if term.lower() in text:
                findings.append(f"{path}:{term}")

    assert findings == []


async def paper_trade_context(tmp_path: Path) -> dict:
    clock = FixedClock(BASE_TIME)
    database, _ = await shadow_db(tmp_path, clock=clock)
    snapshots = ConfigSnapshotRepository(database, clock=clock)
    config_id = await snapshots.create_config_snapshot(source="test", settings={"shadow": True})
    risk_limit_id = await snapshots.create_risk_limit_snapshot(
        config_snapshot_id=config_id,
        source="shadow-test",
        limits={
            "max_stale_seconds": 3600,
            "max_fill_stale_seconds": 3600,
            "min_liquidity_usd": 1000,
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
        strategy_name="shadow-readiness-paper-fixture",
        strategy_version_label="v0",
    )
    domain = DomainRepository(database, clock=clock)
    strategy_version_id = await domain.create_strategy_version(strategy_config_snapshot_id=strategy_config_id)
    entry_quote_id = await QuoteObservationService(database, clock=clock).record_quote_observation(
        source_name="stage2_quote_observer",
        token_mint="paper-token-1",
        pool_address="paper-pool-1",
        price_usd=1.0,
        liquidity_usd=50_000,
        observed_at=BASE_TIME - timedelta(seconds=1),
        response_latency_ms=50,
        confidence="high",
    )
    entry_quote = await database.fetchone("SELECT * FROM quote_observations WHERE quote_observation_id = ?", (entry_quote_id,))
    signal_id = await SignalService(database, domain, clock=clock).create_signal(
        {
            "token_id": "paper-token-1",
            "market_snapshot_id": entry_quote["market_snapshot_id"],
            "strategy_version_id": strategy_version_id,
            "strategy_config_snapshot_id": strategy_config_id,
            "confidence": "high",
            "invalidation_condition": "fixture invalidation",
            "expected_holding_time": "5m",
            "estimated_risk": {"intended_size": 10},
            "estimated_slippage": 50,
        }
    )
    await SignalService(database, domain, clock=clock).create_trade_thesis(
        signal_id,
        {
            "why_token": "quote evidence exists",
            "why_now": "fresh quote",
            "planned_exit_logic": "fixture exit",
            "invalidation_condition": "stale quote",
            "wrong_condition": "fill comparison fails",
            "uncopyable_risk": "shadow evidence only",
            "expected_holding_time": "5m",
        },
    )
    risk_id = await DeterministicRiskService(database, domain, clock=clock).run_entry_risk_check(
        signal_id=signal_id,
        market_snapshot_id=entry_quote["market_snapshot_id"],
        risk_limit_snapshot_id=risk_limit_id,
        config_snapshot_id=config_id,
    )
    paper = Sprint3PaperTradingService(database, domain, clock=clock)
    order_id = await paper.create_paper_order(signal_id=signal_id, risk_check_id=risk_id)
    entry_fill_id = await paper.simulate_entry_fill(
        paper_order_id=order_id,
        market_snapshot_id=entry_quote["market_snapshot_id"],
    )
    position_id = await paper.open_position_from_fill(paper_fill_id=entry_fill_id)

    exit_clock = FixedClock(BASE_TIME + timedelta(minutes=5))
    exit_quote_id = await QuoteObservationService(database, clock=exit_clock).record_quote_observation(
        source_name="stage2_quote_observer",
        token_mint="paper-token-1",
        pool_address="paper-pool-1",
        price_usd=1.5,
        liquidity_usd=80_000,
        observed_at=BASE_TIME + timedelta(minutes=5, seconds=-2),
        response_latency_ms=45,
        confidence="high",
    )
    exit_quote = await database.fetchone("SELECT * FROM quote_observations WHERE quote_observation_id = ?", (exit_quote_id,))
    exit_paper = Sprint3PaperTradingService(database, domain, clock=exit_clock)
    exit_decision_id = await exit_paper.create_exit_decision(
        position_id=position_id,
        payload={
            "market_snapshot_id": exit_quote["market_snapshot_id"],
            "exit_reason": "fixture target",
            "exit_trigger": "price target",
            "expected_exit_logic": "paper sell",
            "created_by": "test",
        },
    )
    exit_risk_id = await DeterministicRiskService(database, domain, clock=exit_clock).run_exit_risk_check(
        exit_decision_id=exit_decision_id,
        market_snapshot_id=exit_quote["market_snapshot_id"],
        risk_limit_snapshot_id=risk_limit_id,
        config_snapshot_id=config_id,
    )
    exit_fill_id = await exit_paper.execute_paper_exit(exit_decision_id=exit_decision_id, risk_check_id=exit_risk_id)
    outcome_id = await DeterministicEvaluationService(database, clock=exit_clock).calculate_trade_outcome(position_id=position_id)
    return {
        "database": database,
        "exit_clock": exit_clock,
        "exit_fill_id": exit_fill_id,
        "outcome_id": outcome_id,
    }
