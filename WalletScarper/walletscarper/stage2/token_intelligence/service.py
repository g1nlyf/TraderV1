from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

from walletscarper.stage2.clock import Clock, SystemClock, isoformat_utc
from walletscarper.stage2.db import Stage2Database
from walletscarper.stage2.db.json import dumps_json
from walletscarper.stage2.evidence import EvidenceNormalizer
from walletscarper.stage2.ids import new_id

DEFAULT_TRIAGE_PRIORS: dict[str, Any] = {
    "version": "sprint2-default-v1",
    "notes": "Configurable evidence priors only; not strategy rules or trading truth.",
    "liquidity_usd": {"watching_min": 10_000, "rejected_below": 1_000},
    "market_cap": {"watching_min": 20_000, "giant_above": 50_000_000},
    "token_age_seconds": {"watching_min": 60, "archive_above": 30 * 24 * 3600},
    "volume_24h": {"watching_min": 5_000},
    "txns_1h": {"watching_min": 10},
    "holder_count": {"watching_min": None},
    "source_confidence": {"minimum_for_watching": "medium"},
    "data_completeness": {"required_for_watching": ["token_mint", "pool_address", "latest_observed_at"]},
}


class TokenIntelligenceService:
    def __init__(self, database: Stage2Database, clock: Clock | None = None):
        self.database = database
        self.clock = clock or SystemClock()

    async def scan_token_candidates_from_raw_events(self, *, limit: int = 100) -> dict[str, Any]:
        rows = await self.database.fetchall(
            """
            SELECT r.raw_source_event_id
            FROM raw_source_events r
            WHERE NOT EXISTS (
              SELECT 1
              FROM normalized_evidence_refs e
              WHERE e.raw_source_event_id = r.raw_source_event_id
                AND e.normalized_type != 'raw_only'
            )
            ORDER BY r.ingested_at, r.raw_source_event_id
            LIMIT ?
            """,
            (limit,),
        )
        normalizer = EvidenceNormalizer(self.database, clock=self.clock)
        raw_events_seen = len(rows)
        token_candidates_created = 0
        profiles_created = 0
        triage_decisions_created = 0
        quality_flags: list[str] = []
        config_id = await self.create_default_triage_config()
        for row in rows:
            result = await normalizer.normalize_raw_source_event(row["raw_source_event_id"])
            quality_flags.extend(result.quality_flags)
            for candidate_id in result.token_candidate_ids:
                token_candidates_created += 1
                profile_id = await self.create_profile_from_candidate(candidate_id)
                profiles_created += 1
                await self.triage_token_profile(profile_id, config_id)
                triage_decisions_created += 1
        return {
            "raw_events_seen": raw_events_seen,
            "token_candidates_created": token_candidates_created,
            "profiles_created": profiles_created,
            "triage_decisions_created": triage_decisions_created,
            "quality_flags": _unique(quality_flags),
            "trading_decisions_created": 0,
        }

    async def create_profile_from_candidate(self, token_candidate_id: str) -> str:
        candidate = await self.database.fetchone("SELECT * FROM token_candidates WHERE token_candidate_id = ?", (token_candidate_id,))
        if not candidate:
            raise ValueError(f"token candidate not found: {token_candidate_id}")
        snapshots = await self.database.fetchall(
            """
            SELECT * FROM market_snapshots
            WHERE token_candidate_id = ? OR token_mint = ?
            ORDER BY observed_at DESC, created_at DESC
            """,
            (token_candidate_id, candidate.get("token_mint")),
        )
        latest = snapshots[0] if snapshots else None
        source_refs = _unique(
            list(_loads_list(candidate.get("raw_event_refs_json")))
            + [row["raw_source_event_id"] for row in snapshots if row.get("raw_source_event_id")]
            + [row["market_snapshot_id"] for row in snapshots if row.get("market_snapshot_id")]
        )
        flags = _unique(list(_loads_list(candidate.get("quality_flags_json"))) + _collect_snapshot_flags(snapshots))
        latest_observed = latest.get("observed_at") if latest else candidate["discovered_at"]
        discovered_at = candidate.get("discovered_at")
        age_seconds = _age_seconds(discovered_at, latest_observed)
        token_mint = candidate.get("token_mint") or (latest.get("token_mint") if latest else None)
        pool_address = latest.get("pool_address") if latest else None
        if not token_mint:
            flags.append("missing_token_mint")
        if not pool_address:
            flags.append("missing_pool_address")
        if latest and latest.get("liquidity_usd") is None:
            flags.append("missing_liquidity_usd")
        if latest and latest.get("price_usd") is None:
            flags.append("missing_price_usd")
        evidence_quality = _evidence_quality(flags, confidence=str(candidate.get("confidence") or "unknown"))
        degradation_status = _degradation_status(flags)
        eligible = bool(candidate.get("eligible_for_high_confidence_evaluation")) and bool(
            latest and latest.get("eligible_for_high_confidence_evaluation")
        ) and evidence_quality in {"high", "medium"}
        profile_id = new_id("token_profile")
        await self.database.execute(
            """
            INSERT INTO token_profiles(
              token_profile_id, token_candidate_id, token_mint, pool_address, chain, ecosystem,
              symbol, name, discovered_at, latest_observed_at, age_seconds, market_cap, fdv,
              liquidity_usd, volume_24h, txns_1h, holder_count, top_holder_concentration,
              source_refs_json, evidence_quality, confidence, quality_flags_json,
              degradation_status, eligible_for_high_confidence_evaluation, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                profile_id,
                token_candidate_id,
                token_mint,
                pool_address,
                candidate.get("chain") or (latest.get("chain") if latest else None),
                candidate.get("ecosystem"),
                candidate.get("symbol"),
                candidate.get("name"),
                discovered_at,
                latest_observed,
                age_seconds,
                latest.get("market_cap") if latest else None,
                latest.get("fdv") if latest else None,
                latest.get("liquidity_usd") if latest else None,
                latest.get("volume_24h") if latest else None,
                latest.get("txns_1h") if latest else None,
                latest.get("holder_count") if latest else None,
                None,
                dumps_json(source_refs),
                evidence_quality,
                _combined_confidence(str(candidate.get("confidence") or "unknown"), flags),
                dumps_json(_unique(flags)),
                degradation_status,
                1 if eligible else 0,
                isoformat_utc(self.clock.now()),
            ),
        )
        return profile_id

    async def create_default_triage_config(self, *, version_label: str = "sprint2-default-v1") -> str:
        content = dict(DEFAULT_TRIAGE_PRIORS)
        content["version"] = version_label
        content_hash = hashlib.sha256(dumps_json(content).encode("utf-8")).hexdigest()
        existing = await self.database.fetchone("SELECT * FROM token_triage_configs WHERE content_hash = ?", (content_hash,))
        if existing:
            return str(existing["token_triage_config_id"])
        config_id = new_id("token_triage_config")
        await self.database.execute(
            """
            INSERT INTO token_triage_configs(token_triage_config_id, version_label, content_hash, bucket_priors_json, notes, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                config_id,
                version_label,
                content_hash,
                dumps_json(content),
                "Configurable Sprint 2 evidence priors; not a trading strategy.",
                isoformat_utc(self.clock.now()),
            ),
        )
        return config_id

    async def triage_token_profile(self, token_profile_id: str, token_triage_config_id: str | None = None) -> str:
        profile = await self.database.fetchone("SELECT * FROM token_profiles WHERE token_profile_id = ?", (token_profile_id,))
        if not profile:
            raise ValueError(f"token profile not found: {token_profile_id}")
        config_id = token_triage_config_id or await self.create_default_triage_config()
        config = await self.database.fetchone("SELECT * FROM token_triage_configs WHERE token_triage_config_id = ?", (config_id,))
        if not config:
            raise ValueError(f"token triage config not found: {config_id}")
        priors = _loads_dict(config["bucket_priors_json"])
        flags = list(_loads_list(profile["quality_flags_json"]))
        buckets = _bucket_assignments(profile, priors)
        reasons: list[str] = []
        no_trade_reason = None
        status = "triage_pending"
        if profile["evidence_quality"] in {"low", "unavailable"}:
            status = "rejected"
            no_trade_reason = "insufficient evidence quality"
            reasons.append(no_trade_reason)
        elif profile.get("liquidity_usd") is not None and float(profile["liquidity_usd"]) < float(priors["liquidity_usd"]["rejected_below"]):
            status = "rejected"
            no_trade_reason = "liquidity below configured evidence prior"
            reasons.append(no_trade_reason)
        elif bool(profile.get("eligible_for_high_confidence_evaluation")) and _meets_watch_priors(profile, priors):
            status = "watching"
            reasons.append("profile meets configured watching evidence priors")
        else:
            status = "triage_pending"
            reasons.append("profile needs more evidence before watching")
        decision_id = new_id("token_triage_decision")
        await self.database.execute(
            """
            INSERT INTO token_triage_decisions(
              token_triage_decision_id, token_profile_id, token_candidate_id, token_triage_config_id,
              decision_status, reasons_json, bucket_assignments_json, no_trade_reason, confidence,
              quality_flags_json, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                decision_id,
                token_profile_id,
                profile.get("token_candidate_id"),
                config_id,
                status,
                dumps_json(reasons),
                dumps_json(buckets),
                no_trade_reason,
                profile["confidence"],
                dumps_json(flags),
                isoformat_utc(self.clock.now()),
            ),
        )
        return decision_id

    async def record_token_agent_decision(
        self,
        *,
        decision_type: str,
        created_by_agent: str,
        token_profile_id: str | None = None,
        token_mint: str | None = None,
        pool_address: str | None = None,
        reasons: list[str] | None = None,
        uncertainties: list[str] | None = None,
        requested_tool_calls: list[Any] | None = None,
        evidence_refs: list[str] | None = None,
        confidence: str = "unknown",
        expires_at: str | None = None,
    ) -> str:
        if decision_type not in {"reject", "passive_watch", "deep_parse", "active_watch", "archive"}:
            raise ValueError(f"unsupported token agent decision type: {decision_type}")
        profile: dict[str, Any] | None = None
        if token_profile_id:
            profile = await self.database.fetchone("SELECT * FROM token_profiles WHERE token_profile_id = ?", (token_profile_id,))
            if not profile:
                raise ValueError(f"token profile not found: {token_profile_id}")
            token_mint = token_mint or profile.get("token_mint")
            pool_address = pool_address or profile.get("pool_address")
        decision_uncertainties = list(uncertainties or [])
        refs = _unique(list(evidence_refs or []))
        if not refs:
            decision_uncertainties.append("missing_evidence_refs")
        if not token_mint:
            decision_uncertainties.append("missing_token_mint")
        decision_id = new_id("token_agent_decision")
        await self.database.execute(
            """
            INSERT INTO token_agent_decisions(
              token_agent_decision_id, token_profile_id, token_mint, pool_address, decision_type,
              reasons_json, uncertainties_json, requested_tool_calls_json, evidence_refs_json,
              confidence, expires_at, created_by_agent, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                decision_id,
                token_profile_id,
                token_mint,
                pool_address,
                decision_type,
                dumps_json(reasons or []),
                dumps_json(_unique(decision_uncertainties)),
                dumps_json(requested_tool_calls or []),
                dumps_json(refs),
                confidence if confidence in {"high", "medium", "low", "unknown"} else "unknown",
                expires_at,
                created_by_agent,
                isoformat_utc(self.clock.now()),
            ),
        )
        return decision_id

    async def build_token_trade_corpus(
        self,
        *,
        token_mint: str,
        pool_address: str | None = None,
        window_start: str | None = None,
        window_end: str | None = None,
        created_by_service: str = "token_trade_corpus_service",
    ) -> dict[str, Any]:
        if not token_mint:
            raise ValueError("token_mint is required")
        stage2_trades = await _fetch_stage2_corpus_trades(
            self.database,
            token_mint=token_mint,
            pool_address=pool_address,
            window_start=window_start,
            window_end=window_end,
        )
        market_rows = await _fetch_corpus_market_snapshots(
            self.database,
            token_mint=token_mint,
            pool_address=pool_address,
            window_start=window_start,
            window_end=window_end,
        )
        legacy_trades = []
        if not stage2_trades:
            legacy_trades = await _fetch_legacy_pool_transactions(
                token_mint=token_mint,
                pool_address=pool_address,
                window_start=window_start,
                window_end=window_end,
            )
        trade_rows = stage2_trades or legacy_trades
        source_names = _unique(
            [row.get("source_name") for row in stage2_trades]
            + [row.get("source_name") for row in market_rows]
            + [row.get("source") for row in legacy_trades]
        )
        wallets = _unique([row.get("wallet") for row in trade_rows if row.get("wallet")])
        raw_refs = _unique(
            [f"wallet_trade:{row.get('wallet_trade_id')}" for row in stage2_trades if row.get("wallet_trade_id")]
            + [str(row.get("raw_source_event_id")) for row in stage2_trades if row.get("raw_source_event_id")]
            + [f"market_snapshot:{row.get('market_snapshot_id')}" for row in market_rows if row.get("market_snapshot_id")]
            + [str(row.get("raw_source_event_id")) for row in market_rows if row.get("raw_source_event_id")]
            + [f"legacy_pool_transaction:{row.get('signature')}" for row in legacy_trades if row.get("signature")]
        )
        flags: list[str] = []
        flags.extend(flag for row in stage2_trades for flag in _loads_list(row.get("quality_flags_json")))
        flags.extend(flag for row in market_rows for flag in _loads_list(row.get("quality_flags_json")))
        if legacy_trades:
            flags.append("legacy_adapter_source")
        if not pool_address:
            flags.append("missing_pool_address")
        if market_rows and not trade_rows:
            flags.append("market_snapshot_only")
        if not trade_rows:
            flags.append("no_trade_events_available")
        if len(wallets) < 3:
            flags.append("limited_wallet_sample")
        if legacy_trades or not stage2_trades or not market_rows:
            flags.append("partial_coverage")
        observed_times = [
            str(value)
            for value in (
                [row.get("observed_at") for row in stage2_trades]
                + [row.get("observed_at") for row in market_rows]
                + [row.get("block_time") for row in legacy_trades]
            )
            if value
        ]
        resolved_start = window_start or (min(observed_times) if observed_times else None)
        resolved_end = window_end or (max(observed_times) if observed_times else None)
        trade_count = len(trade_rows)
        wallet_count = len(wallets)
        coverage = _coverage_estimate(
            stage2_trade_count=len(stage2_trades),
            market_snapshot_count=len(market_rows),
            legacy_trade_count=len(legacy_trades),
        )
        data_sufficiency = _corpus_data_sufficiency(trade_count=trade_count, wallet_count=wallet_count, market_count=len(market_rows))
        if data_sufficiency != "sufficient":
            flags.append("partial_coverage")
        corpus_id = new_id("token_trade_corpus")
        await self.database.execute(
            """
            INSERT INTO token_trade_corpora(
              token_trade_corpus_id, token_mint, pool_address, window_start, window_end,
              source_names_json, trade_count, wallet_count, coverage_estimate, data_sufficiency,
              quality_flags_json, raw_event_refs_json, created_by_service, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                corpus_id,
                token_mint,
                pool_address,
                resolved_start,
                resolved_end,
                dumps_json(source_names),
                trade_count,
                wallet_count,
                coverage,
                data_sufficiency,
                dumps_json(_unique(flags)),
                dumps_json(raw_refs),
                created_by_service,
                isoformat_utc(self.clock.now()),
            ),
        )
        return {
            "token_trade_corpus_id": corpus_id,
            "token_mint": token_mint,
            "pool_address": pool_address,
            "trade_count": trade_count,
            "wallet_count": wallet_count,
            "coverage_estimate": coverage,
            "data_sufficiency": data_sufficiency,
            "source_names": source_names,
            "quality_flags": _unique(flags),
            "raw_event_refs": raw_refs,
            "window_start": resolved_start,
            "window_end": resolved_end,
        }

    async def extract_wallet_candidates_from_corpus(self, token_trade_corpus_id: str) -> dict[str, Any]:
        corpus = await self.database.fetchone(
            "SELECT * FROM token_trade_corpora WHERE token_trade_corpus_id = ?",
            (token_trade_corpus_id,),
        )
        if not corpus:
            raise ValueError(f"token trade corpus not found: {token_trade_corpus_id}")
        stage2_trades = await _fetch_stage2_corpus_trades(
            self.database,
            token_mint=str(corpus["token_mint"]),
            pool_address=corpus.get("pool_address"),
            window_start=corpus.get("window_start"),
            window_end=corpus.get("window_end"),
        )
        legacy_trades = []
        if not stage2_trades:
            legacy_trades = await _fetch_legacy_pool_transactions(
                token_mint=str(corpus["token_mint"]),
                pool_address=corpus.get("pool_address"),
                window_start=corpus.get("window_start"),
                window_end=corpus.get("window_end"),
            )
        grouped: dict[str, dict[str, Any]] = {}
        for row in stage2_trades:
            wallet = row.get("wallet")
            if not wallet:
                continue
            item = grouped.setdefault(
                str(wallet),
                {"wallet": str(wallet), "trade_count": 0, "buy_count": 0, "sell_count": 0, "source_refs": [], "quality_flags": []},
            )
            item["trade_count"] += 1
            if row.get("side") == "buy":
                item["buy_count"] += 1
            elif row.get("side") == "sell":
                item["sell_count"] += 1
            item["source_refs"].extend([row.get("wallet_trade_id"), row.get("raw_source_event_id")])
            item["quality_flags"].extend(_loads_list(row.get("quality_flags_json")))
        for row in legacy_trades:
            wallet = row.get("wallet")
            if not wallet:
                continue
            item = grouped.setdefault(
                str(wallet),
                {"wallet": str(wallet), "trade_count": 0, "buy_count": 0, "sell_count": 0, "source_refs": [], "quality_flags": []},
            )
            item["trade_count"] += 1
            if row.get("side") == "buy":
                item["buy_count"] += 1
            elif row.get("side") == "sell":
                item["sell_count"] += 1
            item["source_refs"].append(f"legacy_pool_transaction:{row.get('signature')}")
            item["quality_flags"].append("legacy_adapter_source")
        candidates = []
        for wallet, item in sorted(grouped.items()):
            quality_flags = _unique(item["quality_flags"])
            if not item["buy_count"] or not item["sell_count"]:
                quality_flags.append("incomplete_buy_sell_path")
            candidates.append(
                {
                    "wallet": wallet,
                    "trade_count": item["trade_count"],
                    "buy_count": item["buy_count"],
                    "sell_count": item["sell_count"],
                    "source_refs": _unique(item["source_refs"]),
                    "quality_flags": _unique(quality_flags),
                    "data_sufficiency": "partial" if item["buy_count"] and item["sell_count"] else "insufficient",
                    "eligible_for_outcome_calculation": bool(item["buy_count"] or item["sell_count"]),
                }
            )
        quality_flags = _unique(list(_loads_list(corpus.get("quality_flags_json"))) + (["no_wallet_candidates"] if not candidates else []))
        return {
            "token_trade_corpus_id": token_trade_corpus_id,
            "token_mint": corpus["token_mint"],
            "pool_address": corpus.get("pool_address"),
            "wallet_candidates": candidates,
            "wallet_count": len(candidates),
            "source_refs": _loads_list(corpus.get("raw_event_refs_json")),
            "quality_flags": quality_flags,
            "data_sufficiency": corpus.get("data_sufficiency") or "insufficient",
        }


def _loads_list(raw: Any) -> list[Any]:
    if not raw:
        return []
    parsed = json.loads(raw) if isinstance(raw, str) else raw
    return parsed if isinstance(parsed, list) else []


def _loads_dict(raw: Any) -> dict[str, Any]:
    if not raw:
        return {}
    parsed = json.loads(raw) if isinstance(raw, str) else raw
    return parsed if isinstance(parsed, dict) else {}


def _unique(values: list[Any]) -> list[str]:
    result: list[str] = []
    for value in values:
        text = str(value)
        if text and text not in result:
            result.append(text)
    return result


def _collect_snapshot_flags(snapshots: list[dict[str, Any]]) -> list[str]:
    flags: list[str] = []
    for snapshot in snapshots:
        flags.extend(str(flag) for flag in _loads_list(snapshot.get("quality_flags_json")))
    return _unique(flags)


def _age_seconds(start: str | None, end: str | None) -> float | None:
    if not start or not end:
        return None
    try:
        start_dt = datetime.fromisoformat(str(start).replace("Z", "+00:00"))
        end_dt = datetime.fromisoformat(str(end).replace("Z", "+00:00"))
    except ValueError:
        return None
    return max(0, (end_dt - start_dt).total_seconds())


def _evidence_quality(flags: list[str], *, confidence: str) -> str:
    disqualifying = {"missing_observed_at", "missing_token_mint", "missing_pool_address", "source_unavailable"}
    degraded = {"missing_price_usd", "missing_liquidity_usd", "source_degraded", "stale_source_data", "weak_timestamp_provenance"}
    if disqualifying & set(flags) or confidence == "unknown":
        return "low"
    if degraded & set(flags) or confidence == "low":
        return "medium"
    return "high" if confidence == "high" else "medium"


def _degradation_status(flags: list[str]) -> str:
    if "source_unavailable" in flags:
        return "unavailable"
    if set(flags) & {"source_degraded", "stale_source_data", "weak_timestamp_provenance"}:
        return "degraded"
    if set(flags) & {"missing_price_usd", "missing_liquidity_usd", "missing_pool_address", "missing_token_mint"}:
        return "partial"
    return "normal"


def _combined_confidence(confidence: str, flags: list[str]) -> str:
    if _evidence_quality(flags, confidence=confidence) == "low":
        return "low"
    return confidence if confidence in {"high", "medium"} else "unknown"


def _bucket_assignments(profile: dict[str, Any], priors: dict[str, Any]) -> dict[str, str]:
    return {
        "liquidity": _bucket_number(profile.get("liquidity_usd"), priors["liquidity_usd"]["watching_min"]),
        "market_cap": _bucket_number(profile.get("market_cap"), priors["market_cap"]["watching_min"]),
        "token_age": _bucket_number(profile.get("age_seconds"), priors["token_age_seconds"]["watching_min"]),
        "volume": _bucket_number(profile.get("volume_24h"), priors["volume_24h"]["watching_min"]),
        "tx_velocity": _bucket_number(profile.get("txns_1h"), priors["txns_1h"]["watching_min"]),
        "source_confidence": str(profile.get("confidence") or "unknown"),
        "data_completeness": str(profile.get("evidence_quality") or "unknown"),
    }


def _bucket_number(value: Any, threshold: Any) -> str:
    if value is None or threshold is None:
        return "unknown"
    try:
        return "meets_prior" if float(value) >= float(threshold) else "below_prior"
    except (TypeError, ValueError):
        return "unknown"


def _meets_watch_priors(profile: dict[str, Any], priors: dict[str, Any]) -> bool:
    checks = [
        _meets(profile.get("liquidity_usd"), priors["liquidity_usd"]["watching_min"]),
        _meets(profile.get("volume_24h"), priors["volume_24h"]["watching_min"]),
        _meets(profile.get("txns_1h"), priors["txns_1h"]["watching_min"]),
        str(profile.get("confidence")) in {"high", "medium"},
    ]
    return all(checks)


def _meets(value: Any, threshold: Any) -> bool:
    if value is None or threshold is None:
        return False
    try:
        return float(value) >= float(threshold)
    except (TypeError, ValueError):
        return False


async def _fetch_stage2_corpus_trades(
    database: Stage2Database,
    *,
    token_mint: str,
    pool_address: str | None,
    window_start: str | None,
    window_end: str | None,
) -> list[dict[str, Any]]:
    return await database.fetchall(
        """
        SELECT *
        FROM wallet_trades
        WHERE token_mint = ?
          AND (? IS NULL OR pool_address = ?)
          AND (? IS NULL OR observed_at >= ?)
          AND (? IS NULL OR observed_at <= ?)
        ORDER BY observed_at, created_at, wallet_trade_id
        """,
        (token_mint, pool_address, pool_address, window_start, window_start, window_end, window_end),
    )


async def _fetch_corpus_market_snapshots(
    database: Stage2Database,
    *,
    token_mint: str,
    pool_address: str | None,
    window_start: str | None,
    window_end: str | None,
) -> list[dict[str, Any]]:
    return await database.fetchall(
        """
        SELECT *
        FROM market_snapshots
        WHERE token_mint = ?
          AND (? IS NULL OR pool_address = ?)
          AND (? IS NULL OR observed_at >= ?)
          AND (? IS NULL OR observed_at <= ?)
        ORDER BY observed_at, created_at, market_snapshot_id
        """,
        (token_mint, pool_address, pool_address, window_start, window_start, window_end, window_end),
    )


async def _fetch_legacy_pool_transactions(
    *,
    token_mint: str,
    pool_address: str | None,
    window_start: str | None,
    window_end: str | None,
) -> list[dict[str, Any]]:
    try:
        from walletscarper.db import db as legacy_db

        return await legacy_db.fetchall(
            """
            SELECT signature, pool_address, token_mint, wallet, side, token_amount, quote_amount,
                   price_usd, block_time, source, source_confidence, completeness, raw_json
            FROM pool_transactions
            WHERE token_mint = ?
              AND (? IS NULL OR pool_address = ?)
              AND (? IS NULL OR block_time >= ?)
              AND (? IS NULL OR block_time <= ?)
            ORDER BY block_time, signature
            """,
            (token_mint, pool_address, pool_address, window_start, window_start, window_end, window_end),
        )
    except Exception:
        return []


def _coverage_estimate(*, stage2_trade_count: int, market_snapshot_count: int, legacy_trade_count: int) -> float:
    if stage2_trade_count:
        base = 0.65
        if market_snapshot_count:
            base += 0.1
        return min(base, 0.8)
    if legacy_trade_count:
        base = 0.35
        if market_snapshot_count:
            base += 0.1
        return min(base, 0.5)
    if market_snapshot_count:
        return 0.1
    return 0.0


def _corpus_data_sufficiency(*, trade_count: int, wallet_count: int, market_count: int) -> str:
    if trade_count >= 10 and wallet_count >= 3:
        return "sufficient"
    if trade_count > 0 or market_count > 0:
        return "partial"
    return "insufficient"
