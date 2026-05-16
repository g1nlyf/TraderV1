from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from walletscarper.stage2.clock import Clock, SystemClock, isoformat_utc
from walletscarper.stage2.db import Stage2Database
from walletscarper.stage2.db.json import dumps_json
from walletscarper.stage2.domain import DomainRepository
from walletscarper.stage2.ids import new_id


class SignalService:
    """Deterministic Stage 2 signal/no-trade/thesis boundary.

    This service records canonical Sprint 3 research workflow records from
    existing Sprint 2 evidence. It does not create orders, risk checks, fills,
    positions, outcomes, or strategy metrics.
    """

    def __init__(self, database: Stage2Database, domain: DomainRepository | None = None, clock: Clock | None = None):
        self.database = database
        self.clock = clock or SystemClock()
        self.domain = domain or DomainRepository(database, clock=self.clock)

    async def create_signal(self, payload: dict[str, Any]) -> str:
        strategy_version_id = _required_text(payload, "strategy_version_id")
        strategy_config_snapshot_id = _required_text(payload, "strategy_config_snapshot_id")
        await self._validate_strategy_config(strategy_version_id, strategy_config_snapshot_id)

        evidence = await self._resolve_evidence(payload)
        token_id = _text(payload.get("token_id") or evidence.get("token_id"))
        if not token_id:
            raise ValueError("Signal requires a token_id or Sprint 2 evidence that resolves to a token.")
        source_refs = _unique(_loads_list(payload.get("source_refs")) + evidence["source_refs"])
        if not source_refs:
            raise ValueError("Signal requires Sprint 2 evidence source refs.")
        data_as_of = _parse_time(payload.get("data_as_of")) or evidence.get("data_as_of") or self.clock.now()

        return await self.domain.create_signal(
            token_id=token_id,
            strategy_version_id=strategy_version_id,
            strategy_config_snapshot_id=strategy_config_snapshot_id,
            data_as_of=data_as_of,
            promotion_criteria_snapshot_id=_text(payload.get("promotion_criteria_snapshot_id")),
            source_refs=source_refs,
            confidence=str(payload.get("confidence") or evidence.get("confidence") or "unknown"),
            invalidation_condition=str(payload.get("invalidation_condition") or "not specified"),
            expected_holding_time=str(payload.get("expected_holding_time") or "not specified"),
            estimated_risk=_loads_dict(payload.get("estimated_risk")),
            estimated_slippage=_float(payload.get("estimated_slippage")),
            status=str(payload.get("status") or "candidate"),
        )

    async def create_no_trade_signal(self, payload: dict[str, Any]) -> str:
        strategy_version_id = _required_text(payload, "strategy_version_id")
        strategy_config_snapshot_id = _required_text(payload, "strategy_config_snapshot_id")
        reason = _required_text(payload, "reason")
        await self._validate_strategy_config(strategy_version_id, strategy_config_snapshot_id)

        evidence = await self._resolve_evidence(payload)
        source_refs = _unique(_loads_list(payload.get("source_refs")) + evidence["source_refs"])
        if not source_refs:
            raise ValueError("NoTradeSignal requires Sprint 2 evidence source refs.")
        now = self.clock.now()
        signal_id = new_id("no_trade_signal")
        await self.database.execute(
            """
            INSERT INTO no_trade_signals(
              no_trade_signal_id, created_at, data_as_of, token_id, token_profile_id,
              strategy_version_id, strategy_config_snapshot_id, promotion_criteria_snapshot_id,
              reason, source_refs_json, confidence, quality_flags_json, observe_later, status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                signal_id,
                isoformat_utc(now),
                isoformat_utc(_parse_time(payload.get("data_as_of")) or evidence.get("data_as_of") or now),
                _text(payload.get("token_id") or evidence.get("token_id")),
                _text(payload.get("token_profile_id")),
                strategy_version_id,
                strategy_config_snapshot_id,
                _text(payload.get("promotion_criteria_snapshot_id")),
                reason,
                dumps_json(source_refs),
                str(payload.get("confidence") or evidence.get("confidence") or "unknown"),
                dumps_json(_unique(_loads_list(payload.get("quality_flags")) + evidence["quality_flags"])),
                1 if bool(payload.get("observe_later")) else 0,
                str(payload.get("status") or "logged"),
            ),
        )
        await self.log_rejected_trade(
            subject_type="no_trade_signal",
            subject_id=signal_id,
            stage="no_trade_decision",
            reason=reason,
            source_refs=source_refs,
            metadata={"observe_later": bool(payload.get("observe_later"))},
        )
        if bool(payload.get("observe_later")):
            await self.log_missed_opportunity(
                token_id=_text(payload.get("token_id") or evidence.get("token_id")),
                token_profile_id=_text(payload.get("token_profile_id")),
                reason=reason,
                source_refs=source_refs,
                observed_at=_parse_time(payload.get("data_as_of")) or evidence.get("data_as_of") or now,
            )
        return signal_id

    async def create_trade_thesis(self, signal_id: str, payload: dict[str, Any]) -> str:
        signal = await self.domain.get_signal(signal_id)
        if not signal:
            raise ValueError(f"Signal not found: {signal_id}")
        started = await self.database.fetchone(
            "SELECT risk_check_id FROM risk_checks WHERE subject_type = 'signal' AND subject_id = ? AND check_scope = 'entry' LIMIT 1",
            (signal_id,),
        )
        if started:
            raise ValueError("TradeThesis cannot be created after entry risk check starts.")
        existing = await self.domain.get_trade_thesis_for_signal(signal_id)
        if existing:
            raise ValueError("TradeThesis already exists for signal.")

        why_token = _required_text(payload, "why_token")
        why_now = _required_text(payload, "why_now")
        planned_exit_logic = _required_text(payload, "planned_exit_logic")
        invalidation_condition = _required_text(payload, "invalidation_condition")
        wrong_condition = _required_text(payload, "wrong_condition")
        uncopyable_risk = _required_text(payload, "uncopyable_risk")
        expected_holding_time = str(payload.get("expected_holding_time") or signal["expected_holding_time"])
        evidence_refs = _unique(_loads_list(payload.get("evidence_refs")) + _loads_list(signal.get("source_refs_json")))

        thesis_id = await self.domain.create_trade_thesis(
            signal_id=signal_id,
            entry_reason=f"{why_token}\n{why_now}",
            exit_plan=planned_exit_logic,
            expected_holding_time=expected_holding_time,
            proof_wrong=wrong_condition,
            context_snapshot_id=_text(payload.get("context_snapshot_id")),
        )
        detail_id = new_id("trade_thesis_detail")
        await self.database.execute(
            """
            INSERT INTO trade_thesis_details(
              trade_thesis_detail_id, thesis_id, signal_id, why_token, why_now,
              evidence_refs_json, planned_exit_logic, invalidation_condition,
              wrong_condition, uncopyable_risk, strategy_version_id, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                detail_id,
                thesis_id,
                signal_id,
                why_token,
                why_now,
                dumps_json(evidence_refs),
                planned_exit_logic,
                invalidation_condition,
                wrong_condition,
                uncopyable_risk,
                signal["strategy_version_id"],
                isoformat_utc(self.clock.now()),
            ),
        )
        return thesis_id

    async def log_rejected_trade(
        self,
        *,
        subject_type: str,
        subject_id: str | None,
        stage: str,
        reason: str,
        source_refs: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        log_id = new_id("rejected_trade_log")
        await self.database.execute(
            """
            INSERT INTO rejected_trade_logs(
              rejected_trade_log_id, subject_type, subject_id, stage, reason,
              source_refs_json, metadata_json, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                log_id,
                subject_type,
                subject_id,
                stage,
                reason,
                dumps_json(source_refs or []),
                dumps_json(metadata or {}),
                isoformat_utc(self.clock.now()),
            ),
        )
        return log_id

    async def log_missed_opportunity(
        self,
        *,
        token_id: str | None,
        reason: str,
        source_refs: list[str] | None = None,
        token_profile_id: str | None = None,
        observed_at: datetime | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        log_id = new_id("missed_opportunity")
        await self.database.execute(
            """
            INSERT INTO missed_opportunity_logs(
              missed_opportunity_log_id, token_id, token_profile_id, reason,
              source_refs_json, observed_at, created_at, metadata_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                log_id,
                token_id,
                token_profile_id,
                reason,
                dumps_json(source_refs or []),
                isoformat_utc(observed_at or self.clock.now()),
                isoformat_utc(self.clock.now()),
                dumps_json(metadata or {}),
            ),
        )
        return log_id

    async def _resolve_evidence(self, payload: dict[str, Any]) -> dict[str, Any]:
        refs: list[str] = []
        flags: list[str] = []
        token_id = _text(payload.get("token_id"))
        data_as_of: datetime | None = None
        confidence = _text(payload.get("confidence"))

        token_profile_id = _text(payload.get("token_profile_id"))
        if token_profile_id:
            profile = await self.database.fetchone("SELECT * FROM token_profiles WHERE token_profile_id = ?", (token_profile_id,))
            if not profile:
                raise ValueError(f"TokenProfile not found: {token_profile_id}")
            refs.extend(_loads_list(profile.get("source_refs_json")))
            refs.append(token_profile_id)
            token_id = token_id or _text(profile.get("token_mint") or profile.get("token_profile_id"))
            data_as_of = data_as_of or _parse_time(profile.get("latest_observed_at"))
            confidence = confidence or _text(profile.get("confidence"))
            flags.extend(_loads_list(profile.get("quality_flags_json")))

        token_candidate_id = _text(payload.get("token_candidate_id"))
        if token_candidate_id:
            candidate = await self.database.fetchone(
                "SELECT * FROM token_candidates WHERE token_candidate_id = ?",
                (token_candidate_id,),
            )
            if not candidate:
                raise ValueError(f"TokenCandidate not found: {token_candidate_id}")
            refs.extend(_loads_list(candidate.get("raw_event_refs_json")))
            refs.append(token_candidate_id)
            token_id = token_id or _text(candidate.get("token_mint") or candidate.get("token_candidate_id"))
            data_as_of = data_as_of or _parse_time(candidate.get("discovered_at"))
            confidence = confidence or _text(candidate.get("confidence"))
            flags.extend(_loads_list(candidate.get("quality_flags_json")))

        market_snapshot_id = _text(payload.get("market_snapshot_id"))
        if market_snapshot_id:
            snapshot = await self.database.fetchone(
                "SELECT * FROM market_snapshots WHERE market_snapshot_id = ?",
                (market_snapshot_id,),
            )
            if not snapshot:
                raise ValueError(f"MarketSnapshot not found: {market_snapshot_id}")
            refs.append(market_snapshot_id)
            if snapshot.get("raw_source_event_id"):
                refs.append(str(snapshot["raw_source_event_id"]))
            token_id = token_id or _text(snapshot.get("token_mint") or snapshot.get("token_candidate_id"))
            data_as_of = data_as_of or _parse_time(snapshot.get("observed_at"))
            confidence = confidence or _text(snapshot.get("confidence"))
            flags.extend(_loads_list(snapshot.get("quality_flags_json")))

        for key, table, column in (
            ("wallet_profile_id", "wallet_profiles", "wallet_profile_id"),
            ("wallet_cluster_id", "wallet_clusters", "wallet_cluster_id"),
            ("wallet_trade_id", "wallet_trades", "wallet_trade_id"),
            ("wallet_metric_snapshot_id", "wallet_metric_snapshots", "wallet_metric_snapshot_id"),
            ("normalized_evidence_ref_id", "normalized_evidence_refs", "normalized_evidence_ref_id"),
            ("browser_extraction_id", "browser_extractions", "browser_extraction_id"),
        ):
            value = _text(payload.get(key))
            if not value:
                continue
            row = await self.database.fetchone(f"SELECT * FROM {table} WHERE {column} = ?", (value,))
            if not row:
                raise ValueError(f"{key} not found: {value}")
            refs.append(value)
            flags.extend(_loads_list(row.get("quality_flags_json")))

        return {
            "token_id": token_id,
            "source_refs": _unique(refs),
            "quality_flags": _unique(flags),
            "data_as_of": data_as_of,
            "confidence": confidence,
        }

    async def _validate_strategy_config(self, strategy_version_id: str, strategy_config_snapshot_id: str) -> None:
        row = await self.database.fetchone(
            "SELECT strategy_config_snapshot_id FROM strategy_versions WHERE strategy_version_id = ?",
            (strategy_version_id,),
        )
        if not row:
            raise ValueError(f"StrategyVersion not found: {strategy_version_id}")
        if row["strategy_config_snapshot_id"] != strategy_config_snapshot_id:
            raise ValueError("StrategyVersion and strategy_config_snapshot_id are incompatible.")


def _required_text(payload: dict[str, Any], key: str) -> str:
    value = _text(payload.get(key))
    if not value:
        raise ValueError(f"{key} is required")
    return value


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None


def _loads_list(raw: Any) -> list[Any]:
    if not raw:
        return []
    if isinstance(raw, list):
        return raw
    parsed = json.loads(raw) if isinstance(raw, str) else raw
    return parsed if isinstance(parsed, list) else []


def _loads_dict(raw: Any) -> dict[str, Any]:
    if not raw:
        return {}
    if isinstance(raw, dict):
        return raw
    parsed = json.loads(raw) if isinstance(raw, str) else raw
    return parsed if isinstance(parsed, dict) else {}


def _parse_time(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _unique(values: list[Any]) -> list[str]:
    result: list[str] = []
    for value in values:
        text = str(value)
        if text and text not in result:
            result.append(text)
    return result
