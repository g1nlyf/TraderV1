from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from typing import Any

from walletscarper.stage2.legacy_ingestion.models import RawSourceEventDraft

TimestampPath = tuple[str, ...]


def map_dexscreener_payload(payload: Any, *, adapter_name: str = "DexScreenerSource") -> RawSourceEventDraft:
    raw = _raw_payload(payload)
    observed_at, flags = _observed_at(raw, (("pairCreatedAt",), ("pair_created_at",), ("created_at",)))
    external_id = _first_value(raw, (("pairAddress",), ("url",), ("baseToken", "address"), ("tokenAddress",)))
    return _draft(
        source_name="dexscreener",
        source_type="market_profile",
        external_id=external_id,
        observed_at=observed_at,
        payload=raw,
        provenance={
            "legacy_adapter": adapter_name,
            "source_endpoint_type": "http_market_profile",
            "timestamp_fields_checked": ["pairCreatedAt", "pair_created_at", "created_at"],
        },
        confidence=_confidence(payload, raw, default="medium"),
        extraction_method="legacy_payload_mapping",
        quality_flags=flags,
        raw_adapter_name=adapter_name,
    )


def map_geckoterminal_payload(payload: Any, *, adapter_name: str = "GeckoTerminalSource") -> RawSourceEventDraft:
    raw = _raw_payload(payload)
    observed_at, flags = _observed_at(
        raw,
        (
            ("attributes", "pool_created_at"),
            ("attributes", "block_timestamp"),
            ("attributes", "timestamp"),
            ("attributes", "created_at"),
            ("pool_created_at",),
            ("block_time",),
            ("timestamp",),
            ("created_at",),
        ),
    )
    external_id = _first_value(raw, (("id",), ("attributes", "address"), ("attributes", "tx_hash"), ("attributes", "txHash")))
    return _draft(
        source_name="geckoterminal",
        source_type="market_pool",
        external_id=external_id,
        observed_at=observed_at,
        payload=raw,
        provenance={
            "legacy_adapter": adapter_name,
            "source_endpoint_type": "http_pool_or_trade",
            "timestamp_fields_checked": ["attributes.pool_created_at", "attributes.block_timestamp", "timestamp", "created_at"],
        },
        confidence=_confidence(payload, raw, default="medium"),
        extraction_method="legacy_payload_mapping",
        quality_flags=flags,
        raw_adapter_name=adapter_name,
    )


def map_dexpaprika_payload(payload: Any, *, adapter_name: str = "DexPaprikaSource") -> RawSourceEventDraft:
    raw = _raw_payload(payload)
    attrs = raw.get("attributes") if isinstance(raw.get("attributes"), dict) else raw
    observed_at, flags = _observed_at(
        raw,
        (
            ("attributes", "block_time"),
            ("attributes", "timestamp"),
            ("attributes", "created_at"),
            ("block_time",),
            ("timestamp",),
            ("created_at",),
        ),
    )
    external_id = _first_value(
        attrs,
        (("tx_hash",), ("txHash",), ("transaction_hash",), ("signature",), ("hash",), ("id",)),
    ) or _first_value(raw, (("id",),))
    return _draft(
        source_name="dexpaprika",
        source_type="pool_transaction",
        external_id=external_id,
        observed_at=observed_at,
        payload=raw,
        provenance={
            "legacy_adapter": adapter_name,
            "source_endpoint_type": "http_pool_transaction",
            "timestamp_fields_checked": ["block_time", "timestamp", "created_at"],
        },
        confidence=_confidence(payload, raw, default="medium"),
        extraction_method="legacy_payload_mapping",
        quality_flags=flags,
        raw_adapter_name=adapter_name,
    )


def map_bitquery_raw_trade(raw_trade: Any, *, adapter_name: str = "BitqueryCoreCastSource") -> RawSourceEventDraft:
    raw = _raw_payload(raw_trade)
    observed_at, flags = _observed_at(raw, (("block_time",), ("timestamp",), ("created_at",)))
    if observed_at is None and getattr(raw_trade, "block_time", None):
        observed_at = _parse_timestamp(getattr(raw_trade, "block_time"))
        flags = [flag for flag in flags if flag != "missing_observed_at"]
        if observed_at is None:
            flags.append("invalid_observed_at")
    external_id = _string_or_none(getattr(raw_trade, "signature", None)) or _first_value(raw, (("signature",),))
    confidence = _string_or_none(getattr(raw_trade, "confidence", None)) or _confidence(raw_trade, raw, default="medium")
    bitquery_flags = list(dict.fromkeys(flags + ["legacy_bitquery_block_time_may_be_ingested_at"]))
    return _draft(
        source_name="bitquery_corecast",
        source_type="corecast_trade",
        external_id=external_id,
        observed_at=observed_at,
        payload=raw,
        provenance={
            "legacy_adapter": adapter_name,
            "source_endpoint_type": "grpc_corecast_trade_stream",
            "ingestion_run_id": _string_or_none(getattr(raw_trade, "ingestion_run_id", None)),
            "slot": getattr(raw_trade, "slot", None) or raw.get("slot"),
            "timestamp_fields_checked": ["block_time", "timestamp", "created_at"],
        },
        confidence=confidence,
        extraction_method="legacy_raw_trade_mapping",
        quality_flags=bitquery_flags,
        raw_adapter_name=adapter_name,
    )


def map_solana_rpc_transaction(
    payload: dict[str, Any],
    *,
    signature: str,
    adapter_name: str = "SolanaRpcSource",
) -> RawSourceEventDraft:
    raw = _raw_payload(payload)
    observed_at, flags = _observed_at(raw, (("blockTime",), ("block_time",), ("timestamp",), ("created_at",)))
    return _draft(
        source_name="solana_rpc",
        source_type="rpc_transaction",
        external_id=signature,
        observed_at=observed_at,
        payload=raw,
        provenance={
            "legacy_adapter": adapter_name,
            "source_endpoint_type": "read_only_json_rpc_getTransaction",
            "rpc_method": "getTransaction",
            "timestamp_fields_checked": ["blockTime", "block_time", "timestamp", "created_at"],
        },
        confidence=_confidence(payload, raw, default="medium"),
        extraction_method="legacy_rpc_payload_mapping",
        quality_flags=flags,
        raw_adapter_name=adapter_name,
    )


def _draft(
    *,
    source_name: str,
    source_type: str,
    external_id: str | None,
    observed_at: datetime | None,
    payload: dict[str, Any],
    provenance: dict[str, Any],
    confidence: str,
    extraction_method: str,
    quality_flags: list[str],
    raw_adapter_name: str,
) -> RawSourceEventDraft:
    flags = list(dict.fromkeys(quality_flags))
    if external_id is None:
        flags.append("missing_external_id")
        confidence = "unknown" if confidence == "medium" else confidence
    return RawSourceEventDraft(
        source_name=source_name,
        source_type=source_type,
        external_id=external_id,
        observed_at=observed_at,
        payload=payload,
        provenance={key: value for key, value in provenance.items() if value is not None},
        confidence=confidence,
        extraction_method=extraction_method,
        quality_flags=list(dict.fromkeys(flags)),
        raw_adapter_name=raw_adapter_name,
    )


def _raw_payload(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    raw = getattr(value, "raw", None)
    if isinstance(raw, dict):
        return raw
    if is_dataclass(value):
        converted = asdict(value)
        return converted if isinstance(converted, dict) else {}
    raise TypeError("legacy ingestion payload must be a dict or object with dict raw payload")


def _confidence(value: Any, payload: dict[str, Any], *, default: str) -> str:
    return (
        _string_or_none(getattr(value, "confidence", None))
        or _string_or_none(payload.get("confidence"))
        or _string_or_none(payload.get("source_confidence"))
        or default
    )


def _observed_at(payload: dict[str, Any], paths: tuple[TimestampPath, ...]) -> tuple[datetime | None, list[str]]:
    flags: list[str] = []
    for path in paths:
        value = _path_value(payload, path)
        if value is None:
            continue
        parsed = _parse_timestamp(value, prefer_millis=path[-1] == "pairCreatedAt")
        if parsed:
            return parsed, flags
        flags.append("invalid_observed_at")
    if not flags:
        flags.append("missing_observed_at")
    return None, flags


def _parse_timestamp(value: Any, *, prefer_millis: bool = False) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, (int, float)):
        return _from_epoch(float(value), prefer_millis=prefer_millis)
    text = str(value).strip()
    if not text:
        return None
    try:
        number = float(text)
        return _from_epoch(number, prefer_millis=prefer_millis)
    except ValueError:
        pass
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _from_epoch(value: float, *, prefer_millis: bool) -> datetime | None:
    try:
        seconds = value / 1000 if prefer_millis or value > 10_000_000_000 else value
        return datetime.fromtimestamp(seconds, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None


def _first_value(payload: dict[str, Any], paths: tuple[TimestampPath, ...]) -> str | None:
    for path in paths:
        value = _path_value(payload, path)
        text = _string_or_none(value)
        if text:
            return text
    return None


def _path_value(payload: dict[str, Any], path: TimestampPath) -> Any:
    current: Any = payload
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None
