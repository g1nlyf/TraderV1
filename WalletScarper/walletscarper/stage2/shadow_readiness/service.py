from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from walletscarper.stage2.clock import Clock, SystemClock, isoformat_utc
from walletscarper.stage2.db import Stage2Database
from walletscarper.stage2.db.json import dumps_json
from walletscarper.stage2.events import RawSourceEventLog
from walletscarper.stage2.evidence import EvidenceNormalizer
from walletscarper.stage2.ids import new_id
from walletscarper.stage2.sources import SourceHealthService


class QuoteObservationService:
    """Observation-only quote evidence capture for shadow-readiness.

    This service writes RawSourceEvent, MarketSnapshot/evidence, latency samples,
    and quote-observation rows. It never creates Signal, RiskCheck, PaperOrder,
    PaperFill, TradeOutcome, credential, or transaction records.
    """

    def __init__(self, database: Stage2Database, *, clock: Clock | None = None):
        self.database = database
        self.clock = clock or SystemClock()

    async def record_quote_observation(
        self,
        *,
        source_name: str,
        token_mint: str | None,
        pool_address: str | None,
        price_usd: float | None,
        liquidity_usd: float | None = None,
        observed_at: datetime | None = None,
        response_latency_ms: float | None = None,
        confidence: str = "unknown",
        chain: str = "solana",
        provenance: dict[str, Any] | None = None,
        quality_flags: list[str] | None = None,
        max_quote_age_seconds: int = 300,
    ) -> str:
        now = self.clock.now()
        flags = _unique_list(quality_flags or [])
        if observed_at is None:
            flags.append("missing_observed_at")
        else:
            observed_at = _ensure_utc(observed_at)
            age_seconds = (now - observed_at).total_seconds()
            if age_seconds < 0:
                flags.append("future_quote_timestamp")
            if age_seconds > max_quote_age_seconds:
                flags.append("stale_source_data")
        if not token_mint:
            flags.append("missing_token_mint")
        if not pool_address:
            flags.append("missing_pool_address")
        if price_usd is None:
            flags.append("missing_price_usd")

        adjusted_confidence = _degraded_confidence(confidence, flags)
        payload = {
            "chain": chain,
            "chainId": chain,
            "token_mint": token_mint,
            "pool_address": pool_address,
            "pairAddress": pool_address,
            "baseToken": {"address": token_mint},
            "price_usd": price_usd,
            "priceUsd": str(price_usd) if price_usd is not None else None,
            "liquidity_usd": liquidity_usd,
            "liquidity": {"usd": liquidity_usd} if liquidity_usd is not None else {},
            "observed_at": isoformat_utc(observed_at) if observed_at else None,
        }
        quality_metadata = {
            "quality_flags": flags,
            "raw_adapter_name": "Stage2QuoteObservationAdapter",
            "provenance": {
                "adapter_boundary": "stage2_owned_observation_only",
                "source_endpoint_type": "quote_snapshot",
                **(provenance or {}),
            },
        }
        raw_id = await RawSourceEventLog(self.database, clock=self.clock).append(
            source_name=source_name,
            source_type="quote_snapshot",
            payload=payload,
            observed_at=observed_at,
            external_id=pool_address or token_mint,
            confidence=adjusted_confidence,
            quality_metadata=quality_metadata,
        )
        normalized = await EvidenceNormalizer(self.database, clock=self.clock).normalize_raw_source_event(raw_id)
        if not normalized.market_snapshot_ids:
            raise RuntimeError("quote observation did not produce a market snapshot")
        market_snapshot_id = normalized.market_snapshot_ids[0]
        market = await self.database.fetchone(
            "SELECT * FROM market_snapshots WHERE market_snapshot_id = ?",
            (market_snapshot_id,),
        )
        if not market:
            raise RuntimeError("normalized market snapshot disappeared")
        raw = await self.database.fetchone("SELECT * FROM raw_source_events WHERE raw_source_event_id = ?", (raw_id,))
        raw_observed = _parse_time((raw or {}).get("observed_at")) or now
        raw_ingested = _parse_time((raw or {}).get("ingested_at")) or now
        event_lag_ms = max(0.0, (raw_ingested - raw_observed).total_seconds() * 1000)
        response_latency = _float(response_latency_ms)
        total_latency_ms = event_lag_ms + (response_latency or 0.0)
        quote_age_seconds = max(0.0, (now - raw_observed).total_seconds())
        eligible = (
            int(market.get("eligible_for_high_confidence_evaluation") or 0) == 1
            and "stale_source_data" not in normalized.quality_flags
            and "missing_observed_at" not in normalized.quality_flags
        )

        await SourceHealthService(self.database, clock=self.clock).record_success(
            source_name=source_name,
            source_type="quote_snapshot",
            adapter_name="Stage2QuoteObservationAdapter",
            latency_ms=response_latency,
            event_time=raw_observed if observed_at else None,
            metadata={"quote_observation": True, "raw_source_event_id": raw_id},
        )
        quote_id = new_id("quote_observation")
        await self.database.execute(
            """
            INSERT INTO quote_observations(
              quote_observation_id, raw_source_event_id, market_snapshot_id, source_name,
              source_type, token_mint, pool_address, chain, observed_at, ingested_at,
              latency_ms, response_latency_ms, quote_age_seconds, price_usd, liquidity_usd,
              confidence, quality_flags_json, provenance_json, eligible_for_shadow_comparison,
              created_at
            )
            VALUES (?, ?, ?, ?, 'quote_snapshot', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                quote_id,
                raw_id,
                market_snapshot_id,
                source_name,
                market.get("token_mint"),
                market.get("pool_address"),
                market.get("chain"),
                raw["observed_at"],
                raw["ingested_at"],
                total_latency_ms,
                response_latency,
                quote_age_seconds,
                market.get("price_usd"),
                market.get("liquidity_usd"),
                adjusted_confidence,
                dumps_json(_unique_list(normalized.quality_flags + flags)),
                dumps_json(quality_metadata["provenance"]),
                1 if eligible else 0,
                isoformat_utc(now),
            ),
        )
        await self._record_latency_sample(
            quote_observation_id=quote_id,
            raw_source_event_id=raw_id,
            source_name=source_name,
            observed_at=raw["observed_at"],
            ingested_at=raw["ingested_at"],
            response_latency_ms=response_latency,
            event_lag_ms=event_lag_ms,
            total_latency_ms=total_latency_ms,
            confidence_impact="none" if eligible else "lower_confidence",
            quality_flags=_unique_list(normalized.quality_flags + flags),
        )
        return quote_id

    async def _record_latency_sample(
        self,
        *,
        quote_observation_id: str,
        raw_source_event_id: str,
        source_name: str,
        observed_at: str,
        ingested_at: str,
        response_latency_ms: float | None,
        event_lag_ms: float,
        total_latency_ms: float,
        confidence_impact: str,
        quality_flags: list[str],
    ) -> str:
        sample_id = new_id("source_latency_sample")
        await self.database.execute(
            """
            INSERT INTO source_latency_samples(
              source_latency_sample_id, quote_observation_id, raw_source_event_id,
              source_name, observed_at, ingested_at, response_latency_ms, event_lag_ms,
              total_latency_ms, confidence_impact, quality_flags_json, created_at,
              metadata_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                sample_id,
                quote_observation_id,
                raw_source_event_id,
                source_name,
                observed_at,
                ingested_at,
                response_latency_ms,
                event_lag_ms,
                total_latency_ms,
                confidence_impact,
                dumps_json(quality_flags),
                isoformat_utc(self.clock.now()),
                dumps_json({"sample_source": "quote_observation"}),
            ),
        )
        return sample_id


class RouteQualityService:
    def __init__(self, database: Stage2Database, *, clock: Clock | None = None):
        self.database = database
        self.clock = clock or SystemClock()

    async def record_route_quality(
        self,
        *,
        quote_observation_id: str,
        route_depth_usd: float | None,
        spread_bps: float | None,
        independent_quote_count: int,
        min_route_depth_usd: float = 1000.0,
        max_spread_bps: float = 500.0,
        evidence: dict[str, Any] | None = None,
    ) -> str:
        quote = await self._quote(quote_observation_id)
        reasons: list[str] = []
        liquidity = _float(quote.get("liquidity_usd"))
        depth = _float(route_depth_usd)
        spread = _float(spread_bps)
        if int(quote.get("eligible_for_shadow_comparison") or 0) != 1:
            reasons.append("quote_not_shadow_eligible")
        if liquidity is None or liquidity <= 0:
            reasons.append("missing_liquidity")
        if depth is None or depth < min_route_depth_usd:
            reasons.append("insufficient_route_depth")
        if spread is None:
            reasons.append("missing_spread")
        elif spread > max_spread_bps:
            reasons.append("spread_too_wide")
        if independent_quote_count < 1:
            reasons.append("missing_independent_quote")
        sufficient = not reasons
        score = _route_score(liquidity=liquidity, depth=depth, spread=spread, sufficient=sufficient)
        route_id = new_id("route_quality")
        await self.database.execute(
            """
            INSERT INTO route_quality_evidence(
              route_quality_evidence_id, quote_observation_id, market_snapshot_id,
              token_mint, pool_address, observed_at, liquidity_usd, route_depth_usd,
              spread_bps, independent_quote_count, route_quality_score,
              sufficient_for_shadow_comparison, insufficiency_reason, evidence_json,
              created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                route_id,
                quote_observation_id,
                quote["market_snapshot_id"],
                quote.get("token_mint"),
                quote.get("pool_address"),
                quote["observed_at"],
                liquidity,
                depth,
                spread,
                independent_quote_count,
                score,
                1 if sufficient else 0,
                "; ".join(reasons) if reasons else None,
                dumps_json(evidence or {}),
                isoformat_utc(self.clock.now()),
            ),
        )
        return route_id

    async def latest_for_quote(self, quote_observation_id: str) -> dict[str, Any] | None:
        return await self.database.fetchone(
            """
            SELECT * FROM route_quality_evidence
            WHERE quote_observation_id = ?
            ORDER BY created_at DESC, route_quality_evidence_id DESC
            LIMIT 1
            """,
            (quote_observation_id,),
        )

    async def _quote(self, quote_observation_id: str) -> dict[str, Any]:
        quote = await self.database.fetchone(
            "SELECT * FROM quote_observations WHERE quote_observation_id = ?",
            (quote_observation_id,),
        )
        if not quote:
            raise ValueError(f"QuoteObservation not found: {quote_observation_id}")
        return quote


class FillQuoteComparisonService:
    def __init__(self, database: Stage2Database, *, clock: Clock | None = None):
        self.database = database
        self.clock = clock or SystemClock()

    async def compare_fill_to_quote(
        self,
        *,
        paper_fill_id: str,
        quote_observation_id: str | None = None,
        route_quality_evidence_id: str | None = None,
        max_quote_age_seconds: int = 300,
    ) -> str:
        fill = await self._fill(paper_fill_id)
        order = await self.database.fetchone("SELECT * FROM paper_orders WHERE paper_order_id = ?", (fill["paper_order_id"],))
        if not order:
            raise ValueError("PaperFill references a missing PaperOrder")
        quote = await self._resolve_quote(fill=fill, quote_observation_id=quote_observation_id, max_quote_age_seconds=max_quote_age_seconds)
        route = await self._resolve_route(quote, route_quality_evidence_id)
        status = "passed"
        flags: list[str] = []
        fill_price = _float(fill.get("fill_price"))
        if fill.get("failed_fill_reason"):
            status = "failed_fill"
            flags.append("failed_fill")
        elif fill_price is None:
            status = "missing_fill_price"
            flags.append("missing_fill_price")
        elif not quote:
            status = "missing_quote"
            flags.append("missing_quote")
        elif _quote_age_seconds(fill.get("fill_time"), quote.get("observed_at")) > max_quote_age_seconds:
            status = "stale_quote"
            flags.append("stale_quote")
        elif not route or int(route.get("sufficient_for_shadow_comparison") or 0) != 1:
            status = "weak_route_quality"
            flags.append("weak_route_quality")

        quote_price = _float((quote or {}).get("price_usd"))
        absolute_difference: float | None = None
        difference_bps: float | None = None
        if fill_price is not None and quote_price not in (None, 0):
            absolute_difference = fill_price - float(quote_price)
            difference_bps = absolute_difference / float(quote_price) * 10_000
        comparison_id = new_id("fill_quote_comparison")
        await self.database.execute(
            """
            INSERT INTO fill_quote_comparisons(
              fill_quote_comparison_id, paper_fill_id, paper_order_id,
              quote_observation_id, quote_market_snapshot_id, route_quality_evidence_id,
              compared_at, fill_time, quote_observed_at, fill_price, quote_price,
              absolute_difference, difference_bps, quote_age_seconds, status,
              quality_flags_json, evidence_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                comparison_id,
                paper_fill_id,
                fill["paper_order_id"],
                (quote or {}).get("quote_observation_id"),
                (quote or {}).get("market_snapshot_id"),
                (route or {}).get("route_quality_evidence_id"),
                isoformat_utc(self.clock.now()),
                fill.get("fill_time"),
                (quote or {}).get("observed_at"),
                fill_price,
                quote_price,
                absolute_difference,
                difference_bps,
                _quote_age_seconds(fill.get("fill_time"), (quote or {}).get("observed_at")) if quote else None,
                status,
                dumps_json(flags),
                dumps_json(
                    {
                        "comparison_scope": "shadow_readiness_evidence_only",
                        "does_not_replace_trade_outcome": True,
                        "max_quote_age_seconds": max_quote_age_seconds,
                    }
                ),
            ),
        )
        return comparison_id

    async def compare_recent_fills_for_quote(
        self,
        *,
        quote_observation_id: str,
        route_quality_evidence_id: str | None = None,
        max_quote_age_seconds: int = 300,
        limit: int = 10,
    ) -> list[str]:
        quote = await self.database.fetchone(
            "SELECT * FROM quote_observations WHERE quote_observation_id = ?",
            (quote_observation_id,),
        )
        if not quote or int(quote.get("eligible_for_shadow_comparison") or 0) != 1:
            return []
        route = await self._resolve_route(quote, route_quality_evidence_id)
        if not route or int(route.get("sufficient_for_shadow_comparison") or 0) != 1:
            return []
        observed = _parse_time(quote.get("observed_at"))
        if not observed:
            return []
        cutoff_start = isoformat_utc(observed - timedelta(seconds=max_quote_age_seconds))
        cutoff_end = isoformat_utc(observed + timedelta(seconds=max_quote_age_seconds))
        fills = await self.database.fetchall(
            """
            SELECT pf.paper_fill_id
            FROM paper_fills pf
            JOIN market_snapshots ms ON ms.market_snapshot_id = pf.market_snapshot_id
            WHERE ms.token_mint = ?
              AND ms.pool_address = ?
              AND pf.fill_time BETWEEN ? AND ?
              AND NOT EXISTS (
                SELECT 1
                FROM fill_quote_comparisons fqc
                WHERE fqc.paper_fill_id = pf.paper_fill_id
                  AND fqc.quote_observation_id = ?
              )
            ORDER BY ABS(strftime('%s', pf.fill_time) - strftime('%s', ?)) ASC,
                     pf.fill_time DESC
            LIMIT ?
            """,
            (
                quote.get("token_mint"),
                quote.get("pool_address"),
                cutoff_start,
                cutoff_end,
                quote_observation_id,
                isoformat_utc(observed),
                max(1, limit),
            ),
        )
        comparison_ids: list[str] = []
        for fill in fills:
            comparison_ids.append(
                await self.compare_fill_to_quote(
                    paper_fill_id=str(fill["paper_fill_id"]),
                    quote_observation_id=quote_observation_id,
                    route_quality_evidence_id=route.get("route_quality_evidence_id"),
                    max_quote_age_seconds=max_quote_age_seconds,
                )
            )
        return comparison_ids

    async def _fill(self, paper_fill_id: str) -> dict[str, Any]:
        fill = await self.database.fetchone("SELECT * FROM paper_fills WHERE paper_fill_id = ?", (paper_fill_id,))
        if not fill:
            raise ValueError(f"PaperFill not found: {paper_fill_id}")
        return fill

    async def _resolve_quote(
        self,
        *,
        fill: dict[str, Any],
        quote_observation_id: str | None,
        max_quote_age_seconds: int,
    ) -> dict[str, Any] | None:
        if quote_observation_id:
            return await self.database.fetchone(
                "SELECT * FROM quote_observations WHERE quote_observation_id = ?",
                (quote_observation_id,),
            )
        snapshot = await self.database.fetchone(
            "SELECT token_mint, pool_address FROM market_snapshots WHERE market_snapshot_id = ?",
            (fill.get("market_snapshot_id"),),
        )
        if not snapshot:
            return None
        fill_time = _parse_time(fill.get("fill_time"))
        if not fill_time:
            return None
        cutoff_start = isoformat_utc(fill_time - timedelta(seconds=max_quote_age_seconds))
        cutoff_end = isoformat_utc(fill_time + timedelta(seconds=max_quote_age_seconds))
        return await self.database.fetchone(
            """
            SELECT *
            FROM quote_observations
            WHERE token_mint = ?
              AND pool_address = ?
              AND observed_at BETWEEN ? AND ?
            ORDER BY ABS(strftime('%s', observed_at) - strftime('%s', ?)) ASC,
                     observed_at DESC
            LIMIT 1
            """,
            (snapshot["token_mint"], snapshot["pool_address"], cutoff_start, cutoff_end, isoformat_utc(fill_time)),
        )

    async def _resolve_route(
        self,
        quote: dict[str, Any] | None,
        route_quality_evidence_id: str | None,
    ) -> dict[str, Any] | None:
        if route_quality_evidence_id:
            return await self.database.fetchone(
                "SELECT * FROM route_quality_evidence WHERE route_quality_evidence_id = ?",
                (route_quality_evidence_id,),
            )
        if not quote:
            return None
        return await RouteQualityService(self.database, clock=self.clock).latest_for_quote(str(quote["quote_observation_id"]))


class LiveDataAcceptanceWindowService:
    def __init__(self, database: Stage2Database, *, clock: Clock | None = None):
        self.database = database
        self.clock = clock or SystemClock()

    async def run_observation_window(
        self,
        *,
        source_names: list[str],
        token_mints: list[str],
        duration_seconds: int = 300,
        min_fresh_quotes: int = 1,
        require_route_quality: bool = True,
        require_fill_comparisons: bool = True,
    ) -> str:
        ended_at = self.clock.now()
        started_at = ended_at - timedelta(seconds=duration_seconds)
        source_names = _unique_list(source_names)
        token_mints = _unique_list(token_mints)
        quotes = await self._quotes(source_names=source_names, token_mints=token_mints, started_at=started_at, ended_at=ended_at)
        fresh = [quote for quote in quotes if int(quote.get("eligible_for_shadow_comparison") or 0) == 1]
        stale = [quote for quote in quotes if "stale_source_data" in _loads_list(quote.get("quality_flags_json"))]
        latency_count = await self._count_latency(source_names=source_names, started_at=started_at, ended_at=ended_at)
        route_count = await self._count_routes(started_at=started_at, ended_at=ended_at)
        comparison_count = await self._count_comparisons(started_at=started_at, ended_at=ended_at)
        independent_quote_group_count = _independent_quote_group_count(quotes)
        gaps: list[str] = []
        if len(fresh) < min_fresh_quotes:
            gaps.append("fresh_high_confidence_quote_stream")
        if latency_count < len(fresh):
            gaps.append("source_latency_distribution")
        if require_route_quality and route_count < len(fresh):
            gaps.append("route_quality_model")
        if require_fill_comparisons and comparison_count < 1:
            gaps.append("fill_vs_quote_comparison")
        status = "passed" if not gaps else "gap_report_required"
        window_id = new_id("live_data_window")
        metrics = {
            "duration_seconds": duration_seconds,
            "min_fresh_quotes": min_fresh_quotes,
            "require_route_quality": require_route_quality,
            "require_fill_comparisons": require_fill_comparisons,
            "independent_quote_group_count": independent_quote_group_count,
            "independent_quote_evidence_present": independent_quote_group_count > 0,
        }
        await self.database.execute(
            """
            INSERT INTO live_data_acceptance_windows(
              live_data_acceptance_window_id, configured_at, started_at, ended_at,
              status, source_names_json, token_mints_json, quotes_seen,
              fresh_quote_count, stale_quote_count, latency_sample_count,
              route_quality_sufficient_count, fill_comparison_count, gaps_json,
              metrics_json, created_by
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                window_id,
                isoformat_utc(self.clock.now()),
                isoformat_utc(started_at),
                isoformat_utc(ended_at),
                status,
                dumps_json(source_names),
                dumps_json(token_mints),
                len(quotes),
                len(fresh),
                len(stale),
                latency_count,
                route_count,
                comparison_count,
                dumps_json(gaps),
                dumps_json(metrics),
                "live_data_acceptance_window_service",
            ),
        )
        return window_id

    async def latest_summary(self) -> dict[str, Any] | None:
        return await self.database.fetchone(
            "SELECT * FROM live_data_acceptance_windows ORDER BY ended_at DESC, live_data_acceptance_window_id DESC LIMIT 1"
        )

    async def _quotes(
        self,
        *,
        source_names: list[str],
        token_mints: list[str],
        started_at: datetime,
        ended_at: datetime,
    ) -> list[dict[str, Any]]:
        source_clause, source_params = _in_clause("source_name", source_names)
        token_clause, token_params = _in_clause("token_mint", token_mints)
        return await self.database.fetchall(
            f"""
            SELECT *
            FROM quote_observations
            WHERE observed_at BETWEEN ? AND ?
              {source_clause}
              {token_clause}
            ORDER BY observed_at
            """,
            (isoformat_utc(started_at), isoformat_utc(ended_at), *source_params, *token_params),
        )

    async def _count_latency(self, *, source_names: list[str], started_at: datetime, ended_at: datetime) -> int:
        source_clause, source_params = _in_clause("source_name", source_names)
        row = await self.database.fetchone(
            f"""
            SELECT COUNT(*) AS count
            FROM source_latency_samples
            WHERE ingested_at BETWEEN ? AND ?
              {source_clause}
            """,
            (isoformat_utc(started_at), isoformat_utc(ended_at), *source_params),
        )
        return int((row or {}).get("count") or 0)

    async def _count_routes(self, *, started_at: datetime, ended_at: datetime) -> int:
        row = await self.database.fetchone(
            """
            SELECT COUNT(*) AS count
            FROM route_quality_evidence
            WHERE observed_at BETWEEN ? AND ?
              AND sufficient_for_shadow_comparison = 1
            """,
            (isoformat_utc(started_at), isoformat_utc(ended_at)),
        )
        return int((row or {}).get("count") or 0)

    async def _count_comparisons(self, *, started_at: datetime, ended_at: datetime) -> int:
        row = await self.database.fetchone(
            """
            SELECT COUNT(*) AS count
            FROM fill_quote_comparisons
            WHERE compared_at BETWEEN ? AND ?
              AND status = 'passed'
            """,
            (isoformat_utc(started_at), isoformat_utc(ended_at)),
        )
        return int((row or {}).get("count") or 0)


def _degraded_confidence(confidence: str, flags: list[str]) -> str:
    if set(flags) & {"missing_observed_at", "invalid_observed_at", "stale_source_data", "missing_price_usd"}:
        return "low"
    return confidence or "unknown"


def _route_score(*, liquidity: float | None, depth: float | None, spread: float | None, sufficient: bool) -> float | None:
    if not sufficient:
        return None
    liquidity_component = min(1.0, float(liquidity or 0) / 50_000)
    depth_component = min(1.0, float(depth or 0) / 5_000)
    spread_component = max(0.0, 1.0 - float(spread or 0) / 500)
    return round((liquidity_component + depth_component + spread_component) / 3, 6)


def _quote_age_seconds(fill_time: Any, quote_observed_at: Any) -> float:
    fill_dt = _parse_time(fill_time)
    quote_dt = _parse_time(quote_observed_at)
    if not fill_dt or not quote_dt:
        return float("inf")
    return abs((fill_dt - quote_dt).total_seconds())


def _parse_time(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return _ensure_utc(value)
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return _ensure_utc(parsed)


def _ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _loads_list(raw: Any) -> list[str]:
    if not raw:
        return []
    if isinstance(raw, list):
        values = raw
    else:
        parsed = json.loads(raw) if isinstance(raw, str) else raw
        values = parsed if isinstance(parsed, list) else []
    return _unique_list(values)


def _unique_list(values: list[Any]) -> list[str]:
    result: list[str] = []
    for value in values:
        text = str(value)
        if text and text not in result:
            result.append(text)
    return result


def _in_clause(column: str, values: list[str]) -> tuple[str, list[str]]:
    if not values:
        return "", []
    placeholders = ", ".join("?" for _ in values)
    return f"AND {column} IN ({placeholders})", values


def _independent_quote_group_count(quotes: list[dict[str, Any]]) -> int:
    grouped: dict[tuple[str, str], set[str]] = {}
    for quote in quotes:
        token = str(quote.get("token_mint") or "").lower()
        pool = str(quote.get("pool_address") or "").lower()
        source = str(quote.get("source_name") or "")
        if not token or not pool or not source:
            continue
        grouped.setdefault((token, pool), set()).add(source)
    return sum(1 for sources in grouped.values() if len(sources) >= 2)
