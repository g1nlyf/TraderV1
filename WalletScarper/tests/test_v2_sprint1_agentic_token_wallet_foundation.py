from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from walletscarper.stage2.clock import FixedClock
from walletscarper.stage2.config import load_stage2_settings
from walletscarper.stage2.db import Stage2Database
from walletscarper.stage2.hermes_integration import run_v2_tool
from walletscarper.stage2.token_intelligence import TokenIntelligenceService
from walletscarper.stage2.wallet_intelligence import WalletIntelligenceService
from walletscarper.stage2.wallet_intelligence import service as wallet_service_module


BASE_TIME = datetime(2026, 5, 16, 12, 0, tzinfo=timezone.utc)
TOKEN = "token-v2"
POOL = "pool-v2"


def run(coro):
    return asyncio.run(coro)


def test_v2_migration_tables_exist_and_agent_records_are_append_only(tmp_path: Path) -> None:
    async def scenario() -> None:
        database = await migrated_database(tmp_path)
        tables = await database.fetchall(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
              AND name IN (
                'token_agent_decisions', 'token_trade_corpora', 'wallet_token_outcomes',
                'agent_wallet_reviews', 'wallet_forward_contributions',
                'active_token_sessions', 'agent_trading_decisions'
              )
            """
        )
        assert {row["name"] for row in tables} == {
            "token_agent_decisions",
            "token_trade_corpora",
            "wallet_token_outcomes",
            "agent_wallet_reviews",
            "wallet_forward_contributions",
            "active_token_sessions",
            "agent_trading_decisions",
        }

        decision_id = await TokenIntelligenceService(database).record_token_agent_decision(
            decision_type="passive_watch",
            created_by_agent="test-hermes",
            token_mint=TOKEN,
            reasons=["fixture decision"],
            evidence_refs=["fixture:market"],
        )
        with pytest.raises(Exception, match="append-only"):
            await database.execute(
                "UPDATE token_agent_decisions SET confidence = 'high' WHERE token_agent_decision_id = ?",
                (decision_id,),
            )

        review_id = await WalletIntelligenceService(database).record_agent_wallet_review(
            wallet="wallet-review",
            decision="watch",
            created_by_agent="test-hermes",
            data_sufficiency="insufficient",
            why_no=["weak history"],
            unknowns=["interesting wallet, insufficient data"],
        )
        with pytest.raises(Exception, match="append-only"):
            await database.execute("DELETE FROM agent_wallet_reviews WHERE agent_wallet_review_id = ?", (review_id,))

    run(scenario())


def test_token_agent_decision_stores_uncertainties_without_paper_side_effects(tmp_path: Path) -> None:
    async def scenario() -> None:
        database = await migrated_database(tmp_path)
        before = await database.table_counts(["paper_orders", "paper_fills", "risk_checks", "trade_outcomes"])
        decision_id = await TokenIntelligenceService(database).record_token_agent_decision(
            decision_type="deep_parse",
            created_by_agent="hermes",
            token_mint=TOKEN,
            reasons=["market profile looks worth deeper parsing"],
            uncertainties=[],
            evidence_refs=[],
            confidence="low",
        )
        row = await database.fetchone("SELECT * FROM token_agent_decisions WHERE token_agent_decision_id = ?", (decision_id,))
        assert row is not None
        assert row["decision_type"] == "deep_parse"
        assert "missing_evidence_refs" in json.loads(row["uncertainties_json"])
        after = await database.table_counts(["paper_orders", "paper_fills", "risk_checks", "trade_outcomes"])
        assert after == before

    run(scenario())


def test_scan_universe_does_not_reprocess_raw_only_events(tmp_path: Path) -> None:
    async def scenario() -> None:
        database = await migrated_database(tmp_path)
        await database.execute(
            """
            INSERT INTO raw_source_events(
              raw_source_event_id, source_name, source_type, external_id, payload_json,
              observed_at, ingested_at, confidence, quality_metadata_json
            )
            VALUES ('raw-unsupported-once', 'unsupported_source', 'unsupported_event', 'external-1',
                    '{}', ?, ?, 'medium', '{}')
            """,
            (BASE_TIME.isoformat(), BASE_TIME.isoformat()),
        )
        service = TokenIntelligenceService(database, clock=FixedClock(BASE_TIME))

        first = await service.scan_token_candidates_from_raw_events(limit=10)
        second = await service.scan_token_candidates_from_raw_events(limit=10)
        refs = await database.fetchall(
            "SELECT * FROM normalized_evidence_refs WHERE raw_source_event_id = ?",
            ("raw-unsupported-once",),
        )

        assert first["raw_events_seen"] == 1
        assert second["raw_events_seen"] == 0
        assert len(refs) == 1
        assert refs[0]["normalized_type"] == "raw_only"

    run(scenario())


def test_token_trade_corpus_extracts_wallets_and_calculates_outcomes(tmp_path: Path) -> None:
    async def scenario() -> None:
        database = await migrated_database(tmp_path)
        await seed_trade(database, "trade-a-buy", "wallet-a", "buy", 100, 100, 1.0, BASE_TIME)
        await seed_trade(database, "trade-a-sell", "wallet-a", "sell", 100, 160, 1.6, BASE_TIME + timedelta(minutes=10))
        await seed_trade(database, "trade-b-buy", "wallet-b", "buy", 50, 50, 1.0, BASE_TIME + timedelta(minutes=1))
        await seed_market_snapshot(database, "market-v2", BASE_TIME)

        token_service = TokenIntelligenceService(database, clock=FixedClock(BASE_TIME + timedelta(minutes=11)))
        corpus = await token_service.build_token_trade_corpus(token_mint=TOKEN, pool_address=POOL)
        assert corpus["trade_count"] == 3
        assert corpus["wallet_count"] == 2
        assert corpus["data_sufficiency"] == "partial"
        assert "partial_coverage" in corpus["quality_flags"]

        extracted = await token_service.extract_wallet_candidates_from_corpus(corpus["token_trade_corpus_id"])
        wallets = {item["wallet"]: item for item in extracted["wallet_candidates"]}
        assert set(wallets) == {"wallet-a", "wallet-b"}
        assert wallets["wallet-a"]["data_sufficiency"] == "partial"
        assert wallets["wallet-b"]["data_sufficiency"] == "insufficient"
        assert "incomplete_buy_sell_path" in wallets["wallet-b"]["quality_flags"]

        tool_outcomes = await run_v2_tool(
            "wallet.calculate_token_outcomes",
            {"token_trade_corpus_id": corpus["token_trade_corpus_id"]},
            database=database,
            clock=FixedClock(BASE_TIME + timedelta(minutes=11)),
        )
        assert tool_outcomes["ok"] is True
        assert tool_outcomes["wallet_outcomes_created"] == 2
        assert tool_outcomes["eligible_wallet_count"] == 1
        assert tool_outcomes["eligible_wallets_for_review"] == ["wallet-a"]

        wallet_service = WalletIntelligenceService(database, clock=FixedClock(BASE_TIME + timedelta(minutes=12)))
        outcome_result = await wallet_service.calculate_wallet_token_outcomes(corpus["token_trade_corpus_id"])
        outcomes = {item["wallet"]: item for item in outcome_result["outcomes"]}
        assert outcomes["wallet-a"]["realized_pnl_estimate"] == pytest.approx(60.0)
        assert outcomes["wallet-a"]["roi_estimate"] == pytest.approx(0.6)
        assert outcomes["wallet-a"]["roi_bucket"] == "50_100"
        assert outcomes["wallet-a"]["data_sufficiency"] == "sufficient"
        assert outcomes["wallet-a"]["eligible_for_agent_review"] is True
        assert outcomes["wallet-b"]["data_sufficiency"] == "partial"
        assert outcomes["wallet-b"]["eligible_for_agent_review"] is False

    run(scenario())


def test_wallet_profiler_and_reviews_do_not_invent_personality_for_weak_history(tmp_path: Path) -> None:
    async def scenario() -> None:
        database = await migrated_database(tmp_path)
        await seed_trade(database, "trade-c-buy", "wallet-c", "buy", 10, 10, 1.0, BASE_TIME)
        service = WalletIntelligenceService(database, clock=FixedClock(BASE_TIME + timedelta(minutes=2)))

        profile = await service.profile_wallet_history_v2("wallet-c")
        assert profile["data_sufficiency"] == "insufficient"
        assert profile["inferred_behavior"] == {}
        assert "interesting wallet, insufficient data" in profile["unknowns"]

        review_id = await service.record_agent_wallet_review(
            wallet="wallet-c",
            decision="watch",
            created_by_agent="hermes",
            metrics_snapshot_id=profile["metrics_snapshot_id"],
            agent_rating=0.45,
            copyability_rating=0.2,
            pnl_quality="unknown",
            winrate_quality="unknown",
            why_yes=["profitable token interaction is interesting"],
            why_no=["history sample is too weak"],
            demotion_triggers=["no repeatable positive history after more data"],
            data_sufficiency="insufficient",
            observed_behavior=profile["observed_behavior"],
            inferred_behavior={"personality": "should be cleared"},
            unknowns=[],
            evidence_refs=profile["source_refs"],
        )
        review = await database.fetchone("SELECT * FROM agent_wallet_reviews WHERE agent_wallet_review_id = ?", (review_id,))
        assert review is not None
        assert json.loads(review["inferred_behavior_json"]) == {}
        assert "interesting wallet, insufficient data" in json.loads(review["unknowns_json"])
        for decision in ["elite", "probation", "reject", "archive"]:
            extra_id = await service.record_agent_wallet_review(
                wallet=f"wallet-{decision}",
                decision=decision,
                created_by_agent="hermes",
                data_sufficiency="partial",
                why_yes=["fixture positive evidence"] if decision in {"elite", "probation"} else [],
                why_no=["fixture exclusion reason"] if decision in {"reject", "archive"} else [],
                demotion_triggers=["source quality degrades"],
                unknowns=["fixture source-depth unknown"],
            )
            assert extra_id

        contribution_id = await service.create_wallet_forward_contribution_placeholder(wallet="wallet-c")
        contribution = await database.fetchone(
            "SELECT * FROM wallet_forward_contributions WHERE wallet_forward_contribution_id = ?",
            (contribution_id,),
        )
        assert contribution is not None
        assert contribution["signal_count"] == 0
        assert contribution["paper_trade_count"] == 0
        assert contribution["net_pnl"] is None
        assert "sprint1_no_forward_metrics_fabricated" in json.loads(contribution["quality_flags_json"])

    run(scenario())


def test_wallet_profile_history_uses_legacy_pool_transactions_when_stage2_trades_are_absent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_legacy_wallet_trades(wallet: str) -> list[dict]:
        assert wallet == "legacy-wallet"
        return [
            {
                "signature": "legacy-buy",
                "token_mint": TOKEN,
                "wallet": wallet,
                "side": "buy",
                "token_amount": 100,
                "quote_amount": 100,
                "price_usd": 1.0,
                "block_time": BASE_TIME.isoformat(),
            },
            {
                "signature": "legacy-sell",
                "token_mint": TOKEN,
                "wallet": wallet,
                "side": "sell",
                "token_amount": 100,
                "quote_amount": 160,
                "price_usd": 1.6,
                "block_time": (BASE_TIME + timedelta(minutes=10)).isoformat(),
            },
        ]

    async def scenario() -> None:
        database = await migrated_database(tmp_path)
        monkeypatch.setattr(wallet_service_module, "_fetch_legacy_wallet_trades", fake_legacy_wallet_trades)

        profile = await WalletIntelligenceService(database, clock=FixedClock(BASE_TIME + timedelta(minutes=11))).profile_wallet_history_v2(
            "legacy-wallet"
        )

        assert profile["closed_trade_count"] == 1
        assert profile["total_pnl_estimate"] == pytest.approx(60.0)
        assert profile["win_rate_estimate"] == pytest.approx(1.0)
        assert "legacy_adapter_source" in profile["quality_flags"]
        assert profile["data_sufficiency"] == "partial"

    run(scenario())


def test_v2_hermes_tools_are_structured_and_do_not_mutate_trading_tables(tmp_path: Path) -> None:
    async def scenario() -> None:
        database = await migrated_database(tmp_path)
        await seed_trade(database, "trade-tool-buy", "wallet-tool", "buy", 100, 100, 1.0, BASE_TIME)
        before = await guarded_counts(database)

        token_result = await run_v2_tool(
            "token.request_deep_parse",
            {"token_mint": TOKEN, "pool_address": POOL},
            database=database,
            clock=FixedClock(BASE_TIME + timedelta(minutes=5)),
        )
        assert token_result["ok"] is True
        assert token_result["artifact_id"]
        assert isinstance(token_result["quality_flags"], list)

        wallet_result = await run_v2_tool(
            "wallet.extract_from_token",
            {"token_trade_corpus_id": token_result["artifact_id"]},
            database=database,
            clock=FixedClock(BASE_TIME + timedelta(minutes=6)),
        )
        assert wallet_result["ok"] is True
        assert wallet_result["artifact_id"] == token_result["artifact_id"]
        assert wallet_result["extracted"]["wallet_count"] == 1

        review_result = await run_v2_tool(
            "wallet.record_agent_review",
            {
                "wallet": "wallet-tool",
                "decision": "watch",
                "created_by_agent": "hermes",
                "data_sufficiency": "insufficient",
                "why_no": ["single observed buy only"],
                "unknowns": ["interesting wallet, insufficient data"],
            },
            database=database,
            clock=FixedClock(BASE_TIME + timedelta(minutes=7)),
        )
        assert review_result["ok"] is True
        blocked_result = await run_v2_tool(
            "wallet.profile_history",
            {},
            database=database,
            clock=FixedClock(BASE_TIME + timedelta(minutes=8)),
        )
        assert blocked_result["ok"] is False
        assert blocked_result["blocked_reason"] == "wallet is required"
        after = await guarded_counts(database)
        assert after == before

    run(scenario())


async def migrated_database(tmp_path: Path, clock: FixedClock | None = None) -> Stage2Database:
    settings = load_stage2_settings(environment="test", database_path=tmp_path / "stage2.sqlite3")
    database = Stage2Database(settings, clock=clock)
    await database.migrate()
    return database


async def guarded_counts(database: Stage2Database) -> dict[str, int]:
    return await database.table_counts(["signals", "risk_checks", "paper_orders", "paper_fills", "trade_outcomes"])


async def seed_market_snapshot(database: Stage2Database, raw_id: str, observed_at: datetime) -> None:
    await seed_raw_event(database, raw_id, observed_at)
    await database.execute(
        """
        INSERT INTO market_snapshots(
          market_snapshot_id, token_mint, pool_address, chain, observed_at, source_name,
          raw_source_event_id, price_usd, liquidity_usd, volume_5m, volume_1h,
          volume_6h, volume_24h, market_cap, fdv, txns_5m, txns_1h, holder_count,
          confidence, quality_flags_json, eligible_for_high_confidence_evaluation, created_at
        )
        VALUES (?, ?, ?, 'solana', ?, 'fixture-market', ?, 1.0, 50000, 1000, 5000,
                10000, 25000, 250000, 300000, 5, 21, 100, 'medium', '[]', 1, ?)
        """,
        (f"market-{raw_id}", TOKEN, POOL, observed_at.isoformat(), raw_id, observed_at.isoformat()),
    )


async def seed_trade(
    database: Stage2Database,
    raw_id: str,
    wallet: str,
    side: str,
    token_amount: float,
    quote_amount: float,
    price_usd: float,
    observed_at: datetime,
) -> None:
    await seed_raw_event(database, raw_id, observed_at)
    await database.execute(
        """
        INSERT INTO wallet_trades(
          wallet_trade_id, wallet, token_mint, pool_address, side, token_amount,
          quote_amount, price_usd, observed_at, source_name, raw_source_event_id,
          market_snapshot_id, fees_estimate, confidence, quality_flags_json,
          reconstruction_method, eligible_for_high_confidence_evaluation, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'fixture-trades', ?, NULL, 0, 'medium', '[]',
                'fixture_direct_wallet_trade', 1, ?)
        """,
        (
            f"wallet-{raw_id}",
            wallet,
            TOKEN,
            POOL,
            side,
            token_amount,
            quote_amount,
            price_usd,
            observed_at.isoformat(),
            raw_id,
            observed_at.isoformat(),
        ),
    )


async def seed_raw_event(database: Stage2Database, raw_id: str, observed_at: datetime) -> None:
    await database.execute(
        """
        INSERT INTO raw_source_events(
          raw_source_event_id, source_name, source_type, external_id, payload_json,
          observed_at, ingested_at, confidence, quality_metadata_json
        )
        VALUES (?, 'fixture-source', 'fixture_trade', ?, '{}', ?, ?, 'medium', '{}')
        """,
        (raw_id, raw_id, observed_at.isoformat(), observed_at.isoformat()),
    )
