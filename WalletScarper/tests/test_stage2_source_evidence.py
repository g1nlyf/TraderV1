from __future__ import annotations

import asyncio
import json
from pathlib import Path

from walletscarper.services.trade_store import RawTrade
from walletscarper.stage2.config import load_stage2_settings
from walletscarper.stage2.db import Stage2Database
from walletscarper.stage2.events import RawSourceEventLog
from walletscarper.stage2.evidence import EvidenceNormalizer
from walletscarper.stage2.legacy_ingestion import map_bitquery_raw_trade, map_dexscreener_payload, write_raw_source_event
from walletscarper.stage2.sources import SourceRegistryRepository


def run(coro):
    return asyncio.run(coro)


def test_data_source_can_be_registered(tmp_path: Path) -> None:
    async def scenario() -> None:
        database = await migrated_database(tmp_path)
        repo = SourceRegistryRepository(database)

        source_id = await repo.register_data_source(
            source_name="dexscreener",
            source_type="market_profile",
            adapter_name="DexScreenerSource",
            interface_kind="api",
            reliability_tier="structured_api",
            allowed_for_high_confidence_evaluation=True,
            status="healthy",
            metadata={"stage": "test"},
        )
        row = await database.fetchone("SELECT * FROM data_sources WHERE data_source_id = ?", (source_id,))

        assert row is not None
        assert row["source_name"] == "dexscreener"
        assert row["interface_kind"] == "api"
        assert row["allowed_for_high_confidence_evaluation"] == 1
        assert json.loads(row["metadata_json"]) == {"stage": "test"}

    run(scenario())


def test_source_health_snapshot_records_states(tmp_path: Path) -> None:
    async def scenario() -> None:
        database = await migrated_database(tmp_path)
        repo = SourceRegistryRepository(database)
        source_id = await repo.register_data_source(
            source_name="geckoterminal",
            source_type="market_pool",
            adapter_name="GeckoTerminalSource",
            interface_kind="api",
        )

        for status in ("healthy", "degraded", "unavailable"):
            await repo.record_health_snapshot(
                source_name="geckoterminal",
                data_source_id=source_id,
                status=status,
                degradation_reason="synthetic" if status != "healthy" else None,
                confidence_impact="none" if status == "healthy" else "lower_confidence",
            )

        rows = await database.fetchall("SELECT status FROM source_health_snapshots ORDER BY observed_at, source_health_snapshot_id")
        assert [row["status"] for row in rows] == ["healthy", "degraded", "unavailable"]

    run(scenario())


def test_ingestion_run_records_counts_and_status(tmp_path: Path) -> None:
    async def scenario() -> None:
        database = await migrated_database(tmp_path)
        repo = SourceRegistryRepository(database)
        source_id = await repo.register_data_source(
            source_name="dexpaprika",
            source_type="pool_transaction",
            adapter_name="DexPaprikaSource",
            interface_kind="api",
        )

        run_id = await repo.start_ingestion_run(
            source_name="dexpaprika",
            adapter_name="DexPaprikaSource",
            data_source_id=source_id,
            correlation_id="corr-1",
        )
        await repo.finish_ingestion_run(
            ingestion_run_id=run_id,
            status="completed",
            events_seen=10,
            events_written=8,
            events_rejected=2,
            quality_summary={"missing_observed_at": 1},
        )
        row = await database.fetchone("SELECT * FROM ingestion_runs WHERE ingestion_run_id = ?", (run_id,))

        assert row is not None
        assert row["status"] == "completed"
        assert row["events_seen"] == 10
        assert row["events_written"] == 8
        assert row["events_rejected"] == 2
        assert json.loads(row["quality_summary_json"]) == {"missing_observed_at": 1}

    run(scenario())


def test_raw_source_event_normalizes_to_token_candidate_and_market_snapshot(tmp_path: Path) -> None:
    async def scenario() -> None:
        database = await migrated_database(tmp_path)
        raw_id = await append_dexscreener_event(database)
        normalizer = EvidenceNormalizer(database)

        result = await normalizer.normalize_raw_source_event(raw_id)
        candidate = await database.fetchone("SELECT * FROM token_candidates WHERE token_candidate_id = ?", (result.token_candidate_ids[0],))
        snapshot = await database.fetchone("SELECT * FROM market_snapshots WHERE market_snapshot_id = ?", (result.market_snapshot_ids[0],))
        refs = await database.fetchall("SELECT * FROM normalized_evidence_refs WHERE raw_source_event_id = ?", (raw_id,))

        assert candidate is not None
        assert candidate["token_mint"] == "token-1"
        assert json.loads(candidate["raw_event_refs_json"]) == [raw_id]
        assert candidate["candidate_status"] == "discovered"
        assert snapshot is not None
        assert snapshot["raw_source_event_id"] == raw_id
        assert snapshot["pool_address"] == "pool-1"
        assert snapshot["price_usd"] == 0.25
        assert len(refs) == 2

    run(scenario())


def test_missing_fields_produce_quality_flags_and_no_high_confidence_evidence(tmp_path: Path) -> None:
    async def scenario() -> None:
        database = await migrated_database(tmp_path)
        raw_log = RawSourceEventLog(database)
        draft = map_dexscreener_payload({"pairAddress": "pool-missing-token", "chainId": "solana"})
        raw_id = await write_raw_source_event(draft, raw_log)

        result = await EvidenceNormalizer(database).normalize_raw_source_event(raw_id)
        candidate = await database.fetchone("SELECT * FROM token_candidates WHERE token_candidate_id = ?", (result.token_candidate_ids[0],))
        snapshot = await database.fetchone("SELECT * FROM market_snapshots WHERE market_snapshot_id = ?", (result.market_snapshot_ids[0],))
        flags = json.loads(snapshot["quality_flags_json"])

        assert "missing_observed_at" in flags
        assert "missing_token_mint" in flags
        assert "missing_price_usd" in flags
        assert candidate["eligible_for_high_confidence_evaluation"] == 0
        assert snapshot["eligible_for_high_confidence_evaluation"] == 0

    run(scenario())


def test_weak_bitquery_timestamp_provenance_is_flagged(tmp_path: Path) -> None:
    async def scenario() -> None:
        database = await migrated_database(tmp_path)
        raw_log = RawSourceEventLog(database)
        trade = RawTrade(
            signature="sig-bitquery",
            wallet="wallet",
            token_mint="token-weak",
            pool_address="pool-weak",
            block_time="2026-05-14T12:00:00+00:00",
            confidence="medium",
            raw={
                "signature": "sig-bitquery",
                "token_mint": "token-weak",
                "pool_address": "pool-weak",
                "price_usd": 0.1,
            },
        )
        raw_id = await write_raw_source_event(map_bitquery_raw_trade(trade), raw_log)

        result = await EvidenceNormalizer(database).normalize_raw_source_event(raw_id)
        snapshot = await database.fetchone("SELECT * FROM market_snapshots WHERE market_snapshot_id = ?", (result.market_snapshot_ids[0],))
        health = await database.fetchone("SELECT * FROM source_health_snapshots WHERE source_name = 'bitquery_corecast'")
        flags = json.loads(snapshot["quality_flags_json"])

        assert "legacy_bitquery_block_time_may_be_ingested_at" in flags
        assert "weak_timestamp_provenance" in flags
        assert snapshot["eligible_for_high_confidence_evaluation"] == 0
        assert health and health["status"] == "degraded"

    run(scenario())


def test_normalization_does_not_create_trading_or_paper_records(tmp_path: Path) -> None:
    async def scenario() -> None:
        database = await migrated_database(tmp_path)
        raw_id = await append_dexscreener_event(database)
        watched_tables = [
            "signals",
            "trade_theses",
            "risk_checks",
            "paper_orders",
            "paper_fills",
            "paper_positions",
            "trade_outcomes",
        ]
        before = await database.table_counts(watched_tables)

        await EvidenceNormalizer(database).normalize_raw_source_event(raw_id)
        after = await database.table_counts(watched_tables)

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


async def migrated_database(tmp_path: Path) -> Stage2Database:
    settings = load_stage2_settings(environment="test", database_path=tmp_path / "stage2.sqlite3")
    database = Stage2Database(settings)
    await database.migrate()
    return database
