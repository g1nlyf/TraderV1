from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

from walletscarper.services.trade_store import RawTrade
from walletscarper.stage2.config import load_stage2_settings
from walletscarper.stage2.db import Stage2Database
from walletscarper.stage2.events import RawSourceEventLog
from walletscarper.stage2.legacy_ingestion import (
    map_bitquery_raw_trade,
    map_dexpaprika_payload,
    map_dexscreener_payload,
    map_geckoterminal_payload,
    map_solana_rpc_transaction,
    write_raw_source_event,
)


def run(coro):
    return asyncio.run(coro)


def test_legacy_mappers_append_raw_source_events(tmp_path: Path) -> None:
    async def scenario() -> None:
        database = await migrated_database(tmp_path)
        raw_log = RawSourceEventLog(database)
        bitquery_trade = RawTrade(
            signature="corecast-signature-1",
            wallet="wallet-1",
            token_mint="token-1",
            block_time="2026-05-14T12:00:00+00:00",
            slot=123,
            confidence="medium",
            ingestion_run_id="run-1",
            raw={"signature": "corecast-signature-1", "slot": 123, "source": "bitquery_corecast"},
        )
        drafts = [
            map_dexscreener_payload(
                {
                    "pairAddress": "dex-pair-1",
                    "pairCreatedAt": 1778760000000,
                    "baseToken": {"address": "token-1"},
                    "confidence": "high",
                }
            ),
            map_geckoterminal_payload(
                {"id": "solana_pool_1", "attributes": {"address": "pool-1", "pool_created_at": "2026-05-14T12:01:00Z"}}
            ),
            map_dexpaprika_payload({"tx_hash": "tx-1", "block_time": "2026-05-14T12:02:00Z", "amount": "10"}),
            map_bitquery_raw_trade(bitquery_trade),
            map_solana_rpc_transaction({"slot": 123, "blockTime": 1778760180}, signature="rpc-signature-1"),
        ]

        ids = [await write_raw_source_event(draft, raw_log) for draft in drafts]
        rows = await database.fetchall("SELECT * FROM raw_source_events ORDER BY ingested_at, raw_source_event_id")

        assert len(ids) == 5
        assert len(rows) == 5
        assert {row["source_name"] for row in rows} == {
            "dexscreener",
            "geckoterminal",
            "dexpaprika",
            "bitquery_corecast",
            "solana_rpc",
        }

    run(scenario())


def test_writer_preserves_payload_and_quality_metadata(tmp_path: Path) -> None:
    async def scenario() -> None:
        database = await migrated_database(tmp_path)
        raw_log = RawSourceEventLog(database)
        payload = {
            "pairAddress": "dex-pair-2",
            "pairCreatedAt": 1778760000000,
            "baseToken": {"address": "token-2", "symbol": "TWO"},
            "nested": {"unchanged": True},
        }

        draft = map_dexscreener_payload(payload)
        event_id = await write_raw_source_event(draft, raw_log)
        row = await database.fetchone("SELECT * FROM raw_source_events WHERE raw_source_event_id = ?", (event_id,))

        assert row is not None
        assert json.loads(row["payload_json"]) == payload
        metadata = json.loads(row["quality_metadata_json"])
        assert metadata["raw_adapter_name"] == "DexScreenerSource"
        assert metadata["extraction_method"] == "legacy_payload_mapping"
        assert metadata["provenance"]["legacy_adapter"] == "DexScreenerSource"
        assert metadata["quality_flags"] == []
        assert row["confidence"] == "medium"
        assert row["observed_at"] == "2026-05-14T12:00:00+00:00"

    run(scenario())


def test_missing_observed_timestamp_adds_quality_flag(tmp_path: Path) -> None:
    async def scenario() -> None:
        database = await migrated_database(tmp_path)
        raw_log = RawSourceEventLog(database)
        draft = map_geckoterminal_payload({"id": "pool-without-time", "attributes": {"address": "pool-2"}})

        event_id = await write_raw_source_event(draft, raw_log)
        row = await database.fetchone("SELECT quality_metadata_json FROM raw_source_events WHERE raw_source_event_id = ?", (event_id,))
        metadata = json.loads(row["quality_metadata_json"])

        assert "missing_observed_at" in metadata["quality_flags"]

    run(scenario())


def test_solana_block_time_maps_to_utc_observed_timestamp() -> None:
    draft = map_solana_rpc_transaction({"slot": 999, "blockTime": 1778760180}, signature="rpc-signature-2")

    assert draft.observed_at == datetime(2026, 5, 14, 12, 3, tzinfo=timezone.utc)
    assert draft.external_id == "rpc-signature-2"
    assert draft.payload == {"slot": 999, "blockTime": 1778760180}


def test_legacy_ingestion_does_not_create_stage2_trading_records(tmp_path: Path) -> None:
    async def scenario() -> None:
        database = await migrated_database(tmp_path)
        raw_log = RawSourceEventLog(database)
        watched_tables = [
            "signals",
            "risk_checks",
            "paper_orders",
            "paper_fills",
            "paper_positions",
            "trade_outcomes",
        ]
        before = await database.table_counts(watched_tables)

        draft = map_dexpaprika_payload({"tx_hash": "tx-raw-only", "timestamp": "2026-05-14T12:03:00Z"})
        await write_raw_source_event(draft, raw_log)
        after = await database.table_counts(watched_tables)

        assert before == after
        assert await database.fetchone("SELECT COUNT(*) AS c FROM raw_source_events") == {"c": 1}

    run(scenario())


def test_legacy_ingestion_code_contains_no_live_execution_path() -> None:
    package_root = Path(__file__).resolve().parents[1] / "walletscarper" / "stage2" / "legacy_ingestion"
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
        "execute_trade",
        "order_placement",
        "live_order",
    ]
    offenders: list[str] = []
    for path in package_root.rglob("*.py"):
        text = path.read_text(encoding="utf-8").lower()
        for term in risky:
            if term in text:
                offenders.append(f"{path}:{term}")
    assert offenders == []


async def migrated_database(tmp_path: Path) -> Stage2Database:
    settings = load_stage2_settings(environment="test", database_path=tmp_path / "stage2.sqlite3")
    database = Stage2Database(settings)
    await database.migrate()
    return database
