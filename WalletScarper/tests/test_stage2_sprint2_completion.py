from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from walletscarper.stage2.browser import BrowserExtractionRepository
from walletscarper.stage2.clock import FixedClock
from walletscarper.stage2.config import load_stage2_settings
from walletscarper.stage2.db import Stage2Database
from walletscarper.stage2.events import RawSourceEventLog
from walletscarper.stage2.evidence import EvidenceNormalizer
from walletscarper.stage2.legacy_ingestion import map_dexpaprika_payload, map_dexscreener_payload, write_raw_source_event
from walletscarper.stage2.sources import SourceHealthService
from walletscarper.stage2.token_intelligence import TokenIntelligenceService
from walletscarper.stage2.wallet_intelligence import WalletIntelligenceService


def run(coro):
    return asyncio.run(coro)


def test_source_health_automation_marks_stale_and_degrades_downstream_confidence(tmp_path: Path) -> None:
    async def scenario() -> None:
        base = datetime(2026, 5, 14, 12, 30, tzinfo=timezone.utc)
        database = await migrated_database(tmp_path, clock=FixedClock(base))
        health = SourceHealthService(database, clock=FixedClock(base), stale_after_seconds=60)
        await health.record_success(
            source_name="dexscreener",
            source_type="market_profile",
            adapter_name="DexScreenerSource",
            latency_ms=120,
            event_time=base - timedelta(minutes=10),
            rate_limit_state={"remaining": 10},
        )
        latest = await database.fetchone("SELECT * FROM source_health_snapshots WHERE source_name = 'dexscreener'")
        assert latest and latest["status"] == "degraded"
        assert "stale" in latest["degradation_reason"]

        raw_id = await append_dexscreener_event(database)
        result = await EvidenceNormalizer(database, clock=FixedClock(base)).normalize_raw_source_event(raw_id)
        snapshot = await database.fetchone("SELECT * FROM market_snapshots WHERE market_snapshot_id = ?", (result.market_snapshot_ids[0],))
        flags = json.loads(snapshot["quality_flags_json"])
        assert "source_degraded" in flags
        assert "stale_source_data" in flags
        assert snapshot["eligible_for_high_confidence_evaluation"] == 0

    run(scenario())


def test_source_health_failure_records_unavailable_without_normal_evidence(tmp_path: Path) -> None:
    async def scenario() -> None:
        database = await migrated_database(tmp_path)
        health = SourceHealthService(database)
        await health.record_failure(
            source_name="geckoterminal",
            source_type="market_pool",
            adapter_name="GeckoTerminalSource",
            degradation_reason="rate limit exceeded",
            error_rate=1.0,
            rate_limit_state={"limited": True},
        )
        source = await database.fetchone("SELECT * FROM data_sources WHERE source_name = 'geckoterminal'")
        snapshot = await database.fetchone("SELECT * FROM source_health_snapshots WHERE source_name = 'geckoterminal'")
        assert source and source["status"] == "unavailable"
        assert snapshot and snapshot["confidence_impact"] == "prevents_normal_confidence"

    run(scenario())


def test_browser_extraction_success_and_failure_are_non_canonical_and_fail_closed(tmp_path: Path) -> None:
    async def scenario() -> None:
        database = await migrated_database(tmp_path)
        repo = BrowserExtractionRepository(database)
        success_id = await repo.record_success(
            source_url="https://example.invalid/token",
            parser_name="test-parser",
            parser_version="v1",
            extracted_fields={"social_context": "synthetic"},
            confidence_score=0.7,
            screenshot_ref="screenshots/test.png",
        )
        failure_id = await repo.record_failure(
            source_url="https://example.invalid/broken",
            parser_name="test-parser",
            parser_version="v1",
            degradation_reason="layout changed",
            raw_html_ref="snapshots/broken.html",
        )

        success = await database.fetchone("SELECT * FROM browser_extractions WHERE browser_extraction_id = ?", (success_id,))
        failure = await database.fetchone("SELECT * FROM browser_extractions WHERE browser_extraction_id = ?", (failure_id,))
        counts = await database.table_counts(["token_candidates", "market_snapshots"])
        assert success["eligible_for_high_confidence_evaluation"] == 0
        assert "browser_non_canonical" in json.loads(success["quality_flags_json"])
        assert failure["status"] == "failed"
        assert json.loads(failure["extracted_fields_json"]) == {}
        assert "parser_failed" in json.loads(failure["quality_flags_json"])
        assert counts == {"token_candidates": 0, "market_snapshots": 0}

    run(scenario())


def test_token_profile_and_triage_use_configurable_bucket_priors_without_trading_records(tmp_path: Path) -> None:
    async def scenario() -> None:
        database = await migrated_database(tmp_path)
        raw_id = await append_dexscreener_event(database)
        result = await EvidenceNormalizer(database).normalize_raw_source_event(raw_id)
        service = TokenIntelligenceService(database)
        watched_tables = ["signals", "trade_theses", "risk_checks", "paper_orders", "paper_fills", "paper_positions", "trade_outcomes"]
        before = await database.table_counts(watched_tables)

        profile_id = await service.create_profile_from_candidate(result.token_candidate_ids[0])
        config_id = await service.create_default_triage_config()
        decision_id = await service.triage_token_profile(profile_id, config_id)
        after = await database.table_counts(watched_tables)
        profile = await database.fetchone("SELECT * FROM token_profiles WHERE token_profile_id = ?", (profile_id,))
        decision = await database.fetchone("SELECT * FROM token_triage_decisions WHERE token_triage_decision_id = ?", (decision_id,))
        config = await database.fetchone("SELECT * FROM token_triage_configs WHERE token_triage_config_id = ?", (config_id,))

        assert before == after
        assert profile["token_mint"] == "token-1"
        assert profile["evidence_quality"] in {"medium", "high"}
        assert decision["decision_status"] == "watching"
        assert "liquidity" in json.loads(decision["bucket_assignments_json"])
        assert "Configurable" in config["notes"]

    run(scenario())


def test_incomplete_token_profile_is_degraded_not_invented(tmp_path: Path) -> None:
    async def scenario() -> None:
        database = await migrated_database(tmp_path)
        raw_log = RawSourceEventLog(database)
        raw_id = await write_raw_source_event(map_dexscreener_payload({"pairAddress": "pool-only", "chainId": "solana"}), raw_log)
        result = await EvidenceNormalizer(database).normalize_raw_source_event(raw_id)
        profile_id = await TokenIntelligenceService(database).create_profile_from_candidate(result.token_candidate_ids[0])
        profile = await database.fetchone("SELECT * FROM token_profiles WHERE token_profile_id = ?", (profile_id,))
        flags = json.loads(profile["quality_flags_json"])

        assert profile["token_mint"] is None
        assert "missing_token_mint" in flags
        assert profile["evidence_quality"] == "low"
        assert profile["eligible_for_high_confidence_evaluation"] == 0

    run(scenario())


def test_token_discovery_pipeline_scans_raw_events_without_trading_decisions(tmp_path: Path) -> None:
    async def scenario() -> None:
        database = await migrated_database(tmp_path)
        await append_dexscreener_event(database)
        watched_tables = ["signals", "trade_theses", "risk_checks", "paper_orders", "paper_fills", "paper_positions", "trade_outcomes"]
        before = await database.table_counts(watched_tables)

        summary = await TokenIntelligenceService(database).scan_token_candidates_from_raw_events(limit=10)
        after = await database.table_counts(watched_tables)

        assert summary["raw_events_seen"] == 1
        assert summary["token_candidates_created"] == 1
        assert summary["profiles_created"] == 1
        assert summary["triage_decisions_created"] == 1
        assert summary["trading_decisions_created"] == 0
        assert before == after

    run(scenario())


def test_wallet_trade_reconstruction_from_observed_events_and_incomplete_degradation(tmp_path: Path) -> None:
    async def scenario() -> None:
        database = await migrated_database(tmp_path)
        complete_raw_id = await append_dexpaprika_trade(
            database,
            signature="tx-complete",
            wallet="wallet-a",
            side="buy",
            token_amount=10,
            price_usd=1.0,
        )
        incomplete_raw_id = await append_dexpaprika_trade(
            database,
            signature="tx-incomplete",
            wallet="wallet-b",
            side=None,
            token_amount=5,
            price_usd=None,
        )
        normalizer = EvidenceNormalizer(database)
        await normalizer.normalize_raw_source_event(complete_raw_id)
        await normalizer.normalize_raw_source_event(incomplete_raw_id)
        service = WalletIntelligenceService(database)

        complete_trade_id = await service.reconstruct_wallet_trade_from_raw_event(complete_raw_id)
        incomplete_trade_id = await service.reconstruct_wallet_trade_from_raw_event(incomplete_raw_id)
        complete = await database.fetchone("SELECT * FROM wallet_trades WHERE wallet_trade_id = ?", (complete_trade_id,))
        incomplete = await database.fetchone("SELECT * FROM wallet_trades WHERE wallet_trade_id = ?", (incomplete_trade_id,))

        assert complete["wallet"] == "wallet-a"
        assert complete["side"] == "buy"
        assert complete["raw_source_event_id"] == complete_raw_id
        assert complete["eligible_for_high_confidence_evaluation"] == 1
        flags = json.loads(incomplete["quality_flags_json"])
        assert "uncertain_side" in flags
        assert "missing_price_usd" in flags
        assert incomplete["confidence"] == "low"
        assert incomplete["eligible_for_high_confidence_evaluation"] == 0

    run(scenario())


def test_wallet_metrics_profile_and_cluster_are_candidate_evidence_only(tmp_path: Path) -> None:
    async def scenario() -> None:
        database = await migrated_database(tmp_path)
        buy_raw_id = await append_dexpaprika_trade(database, signature="tx-buy", wallet="wallet-c", side="buy", token_amount=10, price_usd=1.0)
        sell_raw_id = await append_dexpaprika_trade(database, signature="tx-sell", wallet="wallet-c", side="sell", token_amount=10, price_usd=1.5)
        await EvidenceNormalizer(database).normalize_raw_source_event(buy_raw_id)
        await EvidenceNormalizer(database).normalize_raw_source_event(sell_raw_id)
        service = WalletIntelligenceService(database)
        buy_trade_id = await service.reconstruct_wallet_trade_from_raw_event(buy_raw_id)
        sell_trade_id = await service.reconstruct_wallet_trade_from_raw_event(sell_raw_id)

        metric_id = await service.calculate_wallet_metrics("wallet-c")
        profile_id = await service.create_wallet_profile("wallet-c", metric_id)
        cluster_id = await service.create_wallet_cluster(
            wallets=["wallet-c", "wallet-d"],
            relation_type="repeated_same_token_participation",
            token_mint="token-1",
            evidence_refs=[buy_trade_id, sell_trade_id],
            confidence="medium",
            flags=["possible_coordination"],
        )

        metric = await database.fetchone("SELECT * FROM wallet_metric_snapshots WHERE wallet_metric_snapshot_id = ?", (metric_id,))
        profile = await database.fetchone("SELECT * FROM wallet_profiles WHERE wallet_profile_id = ?", (profile_id,))
        cluster = await database.fetchone("SELECT * FROM wallet_clusters WHERE wallet_cluster_id = ?", (cluster_id,))
        assert metric["candidate_evidence_only"] == 1
        assert metric["closed_trade_count"] == 1
        assert metric["realized_pnl_estimate"] == 5.0
        assert profile["candidate_evidence_only"] == 1
        assert profile["label"] in {"unknown_insufficient_evidence", "smart_money_candidate", "noisy_wallet"}
        assert json.loads(cluster["wallets_json"]) == ["wallet-c", "wallet-d"]
        assert "possible_coordination" in json.loads(cluster["flags_json"])

    run(scenario())


def test_sprint2_does_not_migrate_legacy_paper_or_create_trading_truth(tmp_path: Path) -> None:
    async def scenario() -> None:
        database = await migrated_database(tmp_path)
        tables = await database.fetchall("SELECT name FROM sqlite_master WHERE type='table'")
        table_names = {row["name"] for row in tables}
        watched_tables = ["signals", "trade_theses", "risk_checks", "paper_orders", "paper_fills", "paper_positions", "trade_outcomes"]
        before = await database.table_counts(watched_tables)

        raw_id = await append_dexpaprika_trade(database, signature="tx-guard", wallet="wallet-z", side="buy", token_amount=1, price_usd=1)
        await EvidenceNormalizer(database).normalize_raw_source_event(raw_id)
        service = WalletIntelligenceService(database)
        await service.reconstruct_wallet_trade_from_raw_event(raw_id)
        await service.calculate_wallet_metrics("wallet-z")
        after = await database.table_counts(watched_tables)

        assert "paper_trades" not in table_names
        assert before == after

    run(scenario())


async def append_dexscreener_event(database: Stage2Database) -> str:
    raw_log = RawSourceEventLog(database)
    payload = {
        "chainId": "solana",
        "pairAddress": "pool-1",
        "pairCreatedAt": 1778760000000,
        "baseToken": {"address": "token-1", "symbol": "ONE", "name": "One Token"},
        "priceUsd": "0.25",
        "liquidity": {"usd": 50000},
        "volume": {"m5": 1000, "h1": 5000, "h6": 10000, "h24": 25000},
        "marketCap": 250000,
        "fdv": 300000,
        "txns": {"m5": {"buys": 2, "sells": 3}, "h1": {"buys": 10, "sells": 11}},
    }
    return await write_raw_source_event(map_dexscreener_payload(payload), raw_log)


async def append_dexpaprika_trade(
    database: Stage2Database,
    *,
    signature: str,
    wallet: str,
    side: str | None,
    token_amount: float,
    price_usd: float | None,
) -> str:
    raw_log = RawSourceEventLog(database)
    payload = {
        "tx_hash": signature,
        "block_time": "2026-05-14T12:05:00Z",
        "wallet": wallet,
        "token_mint": "token-1",
        "pool_address": "pool-1",
        "token_amount": token_amount,
    }
    if side is not None:
        payload["side"] = side
    if price_usd is not None:
        payload["price_usd"] = price_usd
    return await write_raw_source_event(map_dexpaprika_payload(payload), raw_log)


async def migrated_database(tmp_path: Path, clock: FixedClock | None = None) -> Stage2Database:
    settings = load_stage2_settings(environment="test", database_path=tmp_path / "stage2.sqlite3")
    database = Stage2Database(settings, clock=clock)
    await database.migrate()
    return database
