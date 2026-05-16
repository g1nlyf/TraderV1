from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from walletscarper.stage2.clock import Clock, SystemClock, isoformat_utc
from walletscarper.stage2.db import Stage2Database
from walletscarper.stage2.db.json import dumps_json
from walletscarper.stage2.evidence.models import NormalizationResult
from walletscarper.stage2.ids import new_id
from walletscarper.stage2.sources import SourceHealthService, SourceRegistryRepository

DISQUALIFYING_EVALUATION_FLAGS = {
    "missing_observed_at",
    "invalid_observed_at",
    "missing_token_mint",
    "missing_price_usd",
    "missing_pool_address",
    "legacy_bitquery_block_time_may_be_ingested_at",
    "weak_timestamp_provenance",
    "source_degraded",
    "source_unavailable",
    "stale_source_data",
}


class EvidenceNormalizer:
    def __init__(self, database: Stage2Database, clock: Clock | None = None):
        self.database = database
        self.clock = clock or SystemClock()
        self.sources = SourceRegistryRepository(database, clock=self.clock)

    async def normalize_raw_source_event(self, raw_source_event_id: str) -> NormalizationResult:
        row = await self.database.fetchone(
            "SELECT * FROM raw_source_events WHERE raw_source_event_id = ?",
            (raw_source_event_id,),
        )
        if not row:
            raise ValueError(f"raw source event not found: {raw_source_event_id}")

        payload = _loads_dict(row["payload_json"])
        metadata = _loads_dict(row["quality_metadata_json"])
        raw_flags = _unique_list(metadata.get("quality_flags") or [])
        adapter_name = str(metadata.get("raw_adapter_name") or metadata.get("provenance", {}).get("legacy_adapter") or "unknown")
        data_source = await self.sources.get_or_register_default(
            source_name=str(row["source_name"]),
            source_type=str(row["source_type"]),
            adapter_name=adapter_name,
        )
        health_flags = await SourceHealthService(self.database, clock=self.clock).quality_flags_for_source(str(row["source_name"]))
        event = _RawEvent(
            raw_source_event_id=raw_source_event_id,
            source_name=str(row["source_name"]),
            source_type=str(row["source_type"]),
            observed_at=str(row["observed_at"]),
            confidence=str(row["confidence"] or "unknown"),
            payload=payload,
            quality_flags=_unique_list(raw_flags + health_flags),
            data_source=data_source,
        )

        if event.source_name == "dexscreener":
            return await self._normalize_dexscreener(event)
        if event.source_name == "geckoterminal":
            return await self._normalize_geckoterminal(event)
        if event.source_name == "dexpaprika":
            return await self._normalize_dexpaprika(event)
        if event.source_name == "bitquery_corecast":
            return await self._normalize_bitquery(event)
        if event.source_name == "solana_rpc":
            return await self._normalize_solana_rpc(event)
        if event.source_type == "quote_snapshot":
            return await self._normalize_quote_snapshot(event)
        return await self._reference_raw_only(event, ["unsupported_source_for_normalization"])

    async def _normalize_dexscreener(self, event: "_RawEvent") -> NormalizationResult:
        payload = event.payload
        base = payload.get("baseToken") if isinstance(payload.get("baseToken"), dict) else {}
        txns = payload.get("txns") if isinstance(payload.get("txns"), dict) else {}
        volume = payload.get("volume") if isinstance(payload.get("volume"), dict) else {}
        liquidity = payload.get("liquidity") if isinstance(payload.get("liquidity"), dict) else {}
        token_mint = _text(base.get("address") or payload.get("tokenAddress"))
        pool_address = _text(payload.get("pairAddress"))
        flags = self._base_flags(event, token_mint=token_mint, pool_address=pool_address, price=_float(payload.get("priceUsd")))
        chain = _text(payload.get("chainId"))
        if not chain:
            flags.append("missing_chain")
        candidate_id = await self._create_token_candidate(
            event=event,
            token_mint=token_mint,
            chain=chain,
            ecosystem=chain,
            symbol=_text(base.get("symbol")),
            name=_text(base.get("name")),
            quality_flags=flags,
        )
        snapshot_id = await self._create_market_snapshot(
            event=event,
            token_candidate_id=candidate_id,
            token_mint=token_mint,
            pool_address=pool_address,
            chain=chain,
            price_usd=_float(payload.get("priceUsd")),
            liquidity_usd=_float(liquidity.get("usd")),
            volume_5m=_float(volume.get("m5")),
            volume_1h=_float(volume.get("h1")),
            volume_6h=_float(volume.get("h6")),
            volume_24h=_float(volume.get("h24")),
            market_cap=_float(payload.get("marketCap")),
            fdv=_float(payload.get("fdv")),
            txns_5m=_txn_count(txns.get("m5")),
            txns_1h=_txn_count(txns.get("h1")),
            quality_flags=flags,
        )
        refs = [
            await self._create_ref(event, "token_candidate", candidate_id, {"source": event.source_name}),
            await self._create_ref(event, "market_snapshot", snapshot_id, {"source": event.source_name}),
        ]
        return NormalizationResult(
            raw_source_event_id=event.raw_source_event_id,
            token_candidate_ids=[candidate_id],
            market_snapshot_ids=[snapshot_id],
            evidence_ref_ids=refs,
            quality_flags=_unique_list(flags),
        )

    async def _normalize_geckoterminal(self, event: "_RawEvent") -> NormalizationResult:
        payload = event.payload
        attrs = payload.get("attributes") if isinstance(payload.get("attributes"), dict) else payload
        relationships = payload.get("relationships") if isinstance(payload.get("relationships"), dict) else {}
        base_ref = ((relationships.get("base_token") or {}).get("data") or {}).get("id") if isinstance(relationships.get("base_token"), dict) else None
        token_mint = _last_segment(_text(attrs.get("token_mint") or attrs.get("base_token_address") or base_ref))
        pool_address = _text(attrs.get("pool_address") or attrs.get("address")) or _last_segment(_text(payload.get("id")))
        chain = _first_segment(_text(payload.get("id"))) or _text(attrs.get("chain") or attrs.get("network"))
        volume = attrs.get("volume_usd") if isinstance(attrs.get("volume_usd"), dict) else {}
        txns = attrs.get("transactions") if isinstance(attrs.get("transactions"), dict) else {}
        price = _float(attrs.get("price_usd") or attrs.get("base_token_price_usd") or attrs.get("token_price_usd"))
        liquidity = _float(attrs.get("liquidity_usd") or attrs.get("reserve_in_usd"))
        flags = self._base_flags(event, token_mint=token_mint, pool_address=pool_address, price=price)
        if not chain:
            flags.append("missing_chain")
        candidate_id = await self._create_token_candidate(
            event=event,
            token_mint=token_mint,
            chain=chain,
            ecosystem=chain,
            symbol=_text(attrs.get("symbol") or attrs.get("name")),
            name=_text(attrs.get("name")),
            quality_flags=flags,
        )
        snapshot_id = await self._create_market_snapshot(
            event=event,
            token_candidate_id=candidate_id,
            token_mint=token_mint,
            pool_address=pool_address,
            chain=chain,
            price_usd=price,
            liquidity_usd=liquidity,
            volume_5m=_float(volume.get("m5")),
            volume_1h=_float(volume.get("h1")),
            volume_6h=_float(volume.get("h6")),
            volume_24h=_float(volume.get("h24")),
            market_cap=_float(attrs.get("market_cap_usd")),
            fdv=_float(attrs.get("fdv_usd")),
            txns_5m=_txn_count(txns.get("m5")),
            txns_1h=_txn_count(txns.get("h1")),
            quality_flags=flags,
        )
        refs = [
            await self._create_ref(event, "token_candidate", candidate_id, {"source": event.source_name}),
            await self._create_ref(event, "market_snapshot", snapshot_id, {"source": event.source_name}),
        ]
        return NormalizationResult(
            raw_source_event_id=event.raw_source_event_id,
            token_candidate_ids=[candidate_id],
            market_snapshot_ids=[snapshot_id],
            evidence_ref_ids=refs,
            quality_flags=_unique_list(flags),
        )

    async def _normalize_dexpaprika(self, event: "_RawEvent") -> NormalizationResult:
        payload = event.payload
        attrs = payload.get("attributes") if isinstance(payload.get("attributes"), dict) else payload
        token_mint = _text(attrs.get("token_mint") or attrs.get("token_0") or attrs.get("base_token"))
        pool_address = _text(attrs.get("pool_address") or attrs.get("pool") or attrs.get("pair_address"))
        price = _float(attrs.get("price_usd") or attrs.get("price_0_usd") or attrs.get("price"))
        liquidity = _float(attrs.get("liquidity_usd") or attrs.get("reserve_usd"))
        raw_liquidity = attrs.get("liquidity") if isinstance(attrs.get("liquidity"), dict) else {}
        if liquidity is None:
            liquidity = _float(raw_liquidity.get("usd"))
        flags = self._base_flags(event, token_mint=token_mint, pool_address=pool_address, price=price)
        snapshot_id = await self._create_market_snapshot(
            event=event,
            token_candidate_id=None,
            token_mint=token_mint,
            pool_address=pool_address,
            chain=_text(attrs.get("chain") or attrs.get("network")),
            price_usd=price,
            liquidity_usd=liquidity,
            volume_5m=None,
            volume_1h=None,
            volume_6h=None,
            volume_24h=_float(attrs.get("volume_usd") or attrs.get("amount_usd") or attrs.get("volume_in_usd")),
            market_cap=None,
            fdv=None,
            txns_5m=None,
            txns_1h=None,
            quality_flags=flags,
        )
        ref = await self._create_ref(event, "market_snapshot", snapshot_id, {"source": event.source_name, "evidence_kind": "pool_transaction"})
        return NormalizationResult(
            raw_source_event_id=event.raw_source_event_id,
            market_snapshot_ids=[snapshot_id],
            evidence_ref_ids=[ref],
            quality_flags=_unique_list(flags),
        )

    async def _normalize_bitquery(self, event: "_RawEvent") -> NormalizationResult:
        payload = event.payload
        token_mint = _text(payload.get("token_mint"))
        pool_address = _text(payload.get("pool_address"))
        flags = self._base_flags(event, token_mint=token_mint, pool_address=pool_address, price=_float(payload.get("price_usd")))
        flags.append("weak_timestamp_provenance")
        snapshot_id = await self._create_market_snapshot(
            event=event,
            token_candidate_id=None,
            token_mint=token_mint,
            pool_address=pool_address,
            chain=_text(payload.get("chain")),
            price_usd=_float(payload.get("price_usd")),
            liquidity_usd=None,
            volume_5m=None,
            volume_1h=None,
            volume_6h=None,
            volume_24h=None,
            market_cap=None,
            fdv=None,
            txns_5m=None,
            txns_1h=None,
            quality_flags=flags,
        )
        await self.sources.record_health_snapshot(
            source_name=event.source_name,
            data_source_id=event.data_source_id,
            status="degraded",
            observed_at=_parse_iso(event.observed_at) or self.clock.now(),
            degradation_reason="legacy Bitquery RawTrade timestamp may be local ingestion time",
            confidence_impact="prevents_high_confidence_evaluation",
        )
        ref = await self._create_ref(event, "market_snapshot", snapshot_id, {"source": event.source_name, "evidence_kind": "corecast_trade"})
        return NormalizationResult(
            raw_source_event_id=event.raw_source_event_id,
            market_snapshot_ids=[snapshot_id],
            evidence_ref_ids=[ref],
            quality_flags=_unique_list(flags),
        )

    async def _normalize_solana_rpc(self, event: "_RawEvent") -> NormalizationResult:
        metadata = {
            "source": event.source_name,
            "evidence_kind": "rpc_transaction",
            "slot": event.payload.get("slot"),
            "transaction_signature": event.payload.get("signature"),
        }
        ref = await self._create_ref(event, "transaction_evidence", event.raw_source_event_id, metadata)
        return NormalizationResult(
            raw_source_event_id=event.raw_source_event_id,
            evidence_ref_ids=[ref],
            quality_flags=_unique_list(event.quality_flags),
        )

    async def _normalize_quote_snapshot(self, event: "_RawEvent") -> NormalizationResult:
        payload = event.payload
        base = payload.get("baseToken") if isinstance(payload.get("baseToken"), dict) else {}
        liquidity = payload.get("liquidity") if isinstance(payload.get("liquidity"), dict) else {}
        token_mint = _text(payload.get("token_mint") or base.get("address") or payload.get("tokenAddress"))
        pool_address = _text(payload.get("pool_address") or payload.get("pairAddress"))
        chain = _text(payload.get("chain") or payload.get("chainId"))
        price = _float(payload.get("price_usd") or payload.get("priceUsd"))
        flags = self._base_flags(event, token_mint=token_mint, pool_address=pool_address, price=price)
        if not chain:
            flags.append("missing_chain")
        candidate_id = await self._create_token_candidate(
            event=event,
            token_mint=token_mint,
            chain=chain,
            ecosystem=chain,
            symbol=_text(base.get("symbol") or payload.get("symbol")),
            name=_text(base.get("name") or payload.get("name")),
            quality_flags=flags,
        )
        snapshot_id = await self._create_market_snapshot(
            event=event,
            token_candidate_id=candidate_id,
            token_mint=token_mint,
            pool_address=pool_address,
            chain=chain,
            price_usd=price,
            liquidity_usd=_float(payload.get("liquidity_usd") or liquidity.get("usd")),
            volume_5m=_float(payload.get("volume_5m")),
            volume_1h=_float(payload.get("volume_1h")),
            volume_6h=_float(payload.get("volume_6h")),
            volume_24h=_float(payload.get("volume_24h")),
            market_cap=_float(payload.get("market_cap") or payload.get("marketCap")),
            fdv=_float(payload.get("fdv")),
            txns_5m=_int(payload.get("txns_5m")),
            txns_1h=_int(payload.get("txns_1h")),
            quality_flags=flags,
        )
        refs = [
            await self._create_ref(event, "token_candidate", candidate_id, {"source": event.source_name, "evidence_kind": "quote_snapshot"}),
            await self._create_ref(event, "market_snapshot", snapshot_id, {"source": event.source_name, "evidence_kind": "quote_snapshot"}),
        ]
        return NormalizationResult(
            raw_source_event_id=event.raw_source_event_id,
            token_candidate_ids=[candidate_id],
            market_snapshot_ids=[snapshot_id],
            evidence_ref_ids=refs,
            quality_flags=_unique_list(flags),
        )

    async def _reference_raw_only(self, event: "_RawEvent", flags: list[str]) -> NormalizationResult:
        all_flags = _unique_list(event.quality_flags + flags)
        ref = await self._create_ref(event, "raw_only", event.raw_source_event_id, {"source": event.source_name, "quality_flags": all_flags})
        return NormalizationResult(
            raw_source_event_id=event.raw_source_event_id,
            evidence_ref_ids=[ref],
            quality_flags=all_flags,
        )

    def _base_flags(self, event: "_RawEvent", *, token_mint: str | None, pool_address: str | None, price: float | None) -> list[str]:
        flags = list(event.quality_flags)
        if not token_mint:
            flags.append("missing_token_mint")
        if not pool_address:
            flags.append("missing_pool_address")
        if price is None:
            flags.append("missing_price_usd")
        if event.confidence not in {"high", "medium"}:
            flags.append("low_source_confidence")
        return _unique_list(flags)

    async def _create_token_candidate(
        self,
        *,
        event: "_RawEvent",
        token_mint: str | None,
        chain: str | None,
        ecosystem: str | None,
        symbol: str | None,
        name: str | None,
        quality_flags: list[str],
    ) -> str:
        candidate_id = new_id("token_candidate")
        now = isoformat_utc(self.clock.now())
        eligible = self._eligible_for_high_confidence(event, quality_flags)
        await self.database.execute(
            """
            INSERT INTO token_candidates(
              token_candidate_id, token_mint, chain, ecosystem, symbol, name, discovered_at,
              data_source_id, source_names_json, raw_event_refs_json, confidence, quality_flags_json,
              candidate_status, eligible_for_high_confidence_evaluation, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'discovered', ?, ?)
            """,
            (
                candidate_id,
                token_mint,
                chain,
                ecosystem,
                symbol,
                name,
                event.observed_at,
                event.data_source_id,
                dumps_json([event.source_name]),
                dumps_json([event.raw_source_event_id]),
                event.confidence,
                dumps_json(_unique_list(quality_flags)),
                1 if eligible else 0,
                now,
            ),
        )
        return candidate_id

    async def _create_market_snapshot(
        self,
        *,
        event: "_RawEvent",
        token_candidate_id: str | None,
        token_mint: str | None,
        pool_address: str | None,
        chain: str | None,
        price_usd: float | None,
        liquidity_usd: float | None,
        volume_5m: float | None,
        volume_1h: float | None,
        volume_6h: float | None,
        volume_24h: float | None,
        market_cap: float | None,
        fdv: float | None,
        txns_5m: int | None,
        txns_1h: int | None,
        quality_flags: list[str],
    ) -> str:
        snapshot_id = new_id("market_snapshot")
        eligible = self._eligible_for_high_confidence(event, quality_flags)
        await self.database.execute(
            """
            INSERT INTO market_snapshots(
              market_snapshot_id, token_candidate_id, token_mint, pool_address, chain, observed_at,
              data_source_id, source_name, raw_source_event_id, price_usd, liquidity_usd, volume_5m,
              volume_1h, volume_6h, volume_24h, market_cap, fdv, txns_5m, txns_1h,
              confidence, quality_flags_json, eligible_for_high_confidence_evaluation, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                snapshot_id,
                token_candidate_id,
                token_mint,
                pool_address,
                chain,
                event.observed_at,
                event.data_source_id,
                event.source_name,
                event.raw_source_event_id,
                price_usd,
                liquidity_usd,
                volume_5m,
                volume_1h,
                volume_6h,
                volume_24h,
                market_cap,
                fdv,
                txns_5m,
                txns_1h,
                event.confidence,
                dumps_json(_unique_list(quality_flags)),
                1 if eligible else 0,
                isoformat_utc(self.clock.now()),
            ),
        )
        return snapshot_id

    async def _create_ref(self, event: "_RawEvent", normalized_type: str, normalized_id: str, metadata: dict[str, Any]) -> str:
        ref_id = new_id("evidence_ref")
        await self.database.execute(
            """
            INSERT INTO normalized_evidence_refs(
              normalized_evidence_ref_id, raw_source_event_id, normalized_type,
              normalized_id, created_at, metadata_json
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                ref_id,
                event.raw_source_event_id,
                normalized_type,
                normalized_id,
                isoformat_utc(self.clock.now()),
                dumps_json(metadata),
            ),
        )
        return ref_id

    def _eligible_for_high_confidence(self, event: "_RawEvent", quality_flags: list[str]) -> bool:
        source_allowed = bool(event.data_source.get("allowed_for_high_confidence_evaluation"))
        interface_kind = str(event.data_source.get("interface_kind") or "")
        return (
            source_allowed
            and interface_kind != "browser"
            and event.confidence in {"high", "medium"}
            and not (set(quality_flags) & DISQUALIFYING_EVALUATION_FLAGS)
        )


class _RawEvent:
    def __init__(
        self,
        *,
        raw_source_event_id: str,
        source_name: str,
        source_type: str,
        observed_at: str,
        confidence: str,
        payload: dict[str, Any],
        quality_flags: list[str],
        data_source: dict[str, Any],
    ):
        self.raw_source_event_id = raw_source_event_id
        self.source_name = source_name
        self.source_type = source_type
        self.observed_at = observed_at
        self.confidence = confidence
        self.payload = payload
        self.quality_flags = quality_flags
        self.data_source = data_source
        self.data_source_id = str(data_source["data_source_id"])


def _loads_dict(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    parsed = json.loads(raw)
    return parsed if isinstance(parsed, dict) else {}


def _unique_list(values: list[Any]) -> list[str]:
    result: list[str] = []
    for value in values:
        text = str(value)
        if text and text not in result:
            result.append(text)
    return result


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None


def _float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, dict):
        value = value.get("usd") or value.get("value")
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _txn_count(value: Any) -> int | None:
    if isinstance(value, dict):
        buys = _int(value.get("buys")) or 0
        sells = _int(value.get("sells")) or 0
        return buys + sells
    return _int(value)


def _last_segment(value: str | None) -> str | None:
    if not value:
        return None
    return value.split("_")[-1]


def _first_segment(value: str | None) -> str | None:
    if not value or "_" not in value:
        return None
    return value.split("_")[0] or None


def _parse_iso(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
