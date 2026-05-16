from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from walletscarper.stage2.clock import Clock, SystemClock
from walletscarper.stage2.db import Stage2Database
from walletscarper.stage2.domain.repository import DomainRepository
from walletscarper.stage2.signals import SignalService


QUALITY_VETO_FLAGS = {
    "missing_observed_at",
    "invalid_observed_at",
    "source_unavailable",
    "stale_source_data",
}


class DeterministicRiskService:
    """Authoritative deterministic RiskCheck creator for Sprint 3."""

    def __init__(self, database: Stage2Database, domain: DomainRepository | None = None, clock: Clock | None = None):
        self.database = database
        self.clock = clock or SystemClock()
        self.domain = domain or DomainRepository(database, clock=self.clock)

    async def run_entry_risk_check(
        self,
        *,
        signal_id: str,
        market_snapshot_id: str | None,
        risk_limit_snapshot_id: str,
        config_snapshot_id: str,
    ) -> str:
        signal = await self.domain.get_signal(signal_id)
        if not signal:
            raise ValueError(f"Signal not found: {signal_id}")
        limits = await self._limits(risk_limit_snapshot_id, config_snapshot_id)
        snapshot = await self._market_snapshot(market_snapshot_id)
        warnings: list[str] = []
        vetoes: list[str] = []
        if await self.domain.get_trade_thesis_for_signal(signal_id) is None:
            vetoes.append("missing_trade_thesis")
        self._check_market_snapshot(snapshot, limits, warnings, vetoes, require_price=True)
        self._check_entry_signal(signal, limits, warnings, vetoes)
        await self._check_open_position_limits(signal, limits, warnings, vetoes)
        passed = not vetoes
        risk_id = await self.domain.create_risk_check(
            check_scope="entry",
            subject_type="signal",
            subject_id=signal_id,
            market_snapshot_id=market_snapshot_id,
            risk_limit_snapshot_id=risk_limit_snapshot_id,
            config_snapshot_id=config_snapshot_id,
            data_as_of=_parse_time((snapshot or {}).get("observed_at")) or self.clock.now(),
            passed=passed,
            veto_reason="; ".join(vetoes) if vetoes else None,
            warnings=warnings,
            created_by_service="risk_service",
        )
        if not passed:
            await SignalService(self.database, self.domain, clock=self.clock).log_rejected_trade(
                subject_type="signal",
                subject_id=signal_id,
                stage="entry_risk",
                reason="; ".join(vetoes),
                source_refs=_loads_list(signal.get("source_refs_json")),
                metadata={"market_snapshot_id": market_snapshot_id, "risk_check_id": risk_id},
            )
        return risk_id

    async def run_exit_risk_check(
        self,
        *,
        exit_decision_id: str,
        market_snapshot_id: str | None,
        risk_limit_snapshot_id: str,
        config_snapshot_id: str,
    ) -> str:
        exit_decision = await self.database.fetchone(
            "SELECT * FROM exit_decisions WHERE exit_decision_id = ?",
            (exit_decision_id,),
        )
        if not exit_decision:
            raise ValueError(f"ExitDecision not found: {exit_decision_id}")
        limits = await self._limits(risk_limit_snapshot_id, config_snapshot_id)
        snapshot = await self._market_snapshot(market_snapshot_id)
        warnings: list[str] = []
        vetoes: list[str] = []
        self._check_market_snapshot(snapshot, limits, warnings, vetoes, require_price=True)
        if snapshot and exit_decision.get("data_as_of") and _parse_time(snapshot["observed_at"]) is not None:
            if _parse_time(snapshot["observed_at"]) < _parse_time(exit_decision["data_as_of"]):
                warnings.append("exit_market_snapshot_older_than_decision_data_as_of")
        position = await self.database.fetchone(
            "SELECT * FROM paper_positions WHERE position_id = ?",
            (exit_decision["position_id"],),
        )
        if not position:
            vetoes.append("missing_position")
        passed = not vetoes
        risk_id = await self.domain.create_risk_check(
            check_scope="exit",
            subject_type="exit_decision",
            subject_id=exit_decision_id,
            market_snapshot_id=market_snapshot_id,
            risk_limit_snapshot_id=risk_limit_snapshot_id,
            config_snapshot_id=config_snapshot_id,
            data_as_of=_parse_time((snapshot or {}).get("observed_at")) or _parse_time(exit_decision["data_as_of"]) or self.clock.now(),
            passed=passed,
            veto_reason="; ".join(vetoes) if vetoes else None,
            warnings=warnings,
            created_by_service="risk_service",
        )
        if not passed:
            await SignalService(self.database, self.domain, clock=self.clock).log_rejected_trade(
                subject_type="exit_decision",
                subject_id=exit_decision_id,
                stage="exit_risk",
                reason="; ".join(vetoes),
                metadata={"market_snapshot_id": market_snapshot_id, "risk_check_id": risk_id},
            )
        return risk_id

    async def run_position_monitoring_risk_check(
        self,
        *,
        position_id: str,
        market_snapshot_id: str | None,
        risk_limit_snapshot_id: str,
        config_snapshot_id: str,
    ) -> str:
        position = await self.database.fetchone("SELECT * FROM paper_positions WHERE position_id = ?", (position_id,))
        if not position:
            raise ValueError(f"PaperPosition not found: {position_id}")
        limits = await self._limits(risk_limit_snapshot_id, config_snapshot_id)
        snapshot = await self._market_snapshot(market_snapshot_id)
        warnings: list[str] = []
        vetoes: list[str] = []
        self._check_market_snapshot(snapshot, limits, warnings, vetoes, require_price=True)
        passed = not vetoes
        return await self.domain.create_risk_check(
            check_scope="position_monitoring",
            subject_type="paper_position",
            subject_id=position_id,
            market_snapshot_id=market_snapshot_id,
            risk_limit_snapshot_id=risk_limit_snapshot_id,
            config_snapshot_id=config_snapshot_id,
            data_as_of=_parse_time((snapshot or {}).get("observed_at")) or self.clock.now(),
            passed=passed,
            veto_reason="; ".join(vetoes) if vetoes else None,
            warnings=warnings,
            created_by_service="risk_service",
        )

    async def request_entry_risk_check(
        self,
        *,
        signal_id: str,
        market_snapshot_id: str | None,
        risk_limit_snapshot_id: str,
        config_snapshot_id: str,
    ) -> str:
        return await self.run_entry_risk_check(
            signal_id=signal_id,
            market_snapshot_id=market_snapshot_id,
            risk_limit_snapshot_id=risk_limit_snapshot_id,
            config_snapshot_id=config_snapshot_id,
        )

    async def request_exit_risk_check(
        self,
        *,
        exit_decision_id: str,
        market_snapshot_id: str | None,
        risk_limit_snapshot_id: str,
        config_snapshot_id: str,
    ) -> str:
        return await self.run_exit_risk_check(
            exit_decision_id=exit_decision_id,
            market_snapshot_id=market_snapshot_id,
            risk_limit_snapshot_id=risk_limit_snapshot_id,
            config_snapshot_id=config_snapshot_id,
        )

    async def retrieve_risk_result(self, risk_check_id: str) -> dict[str, Any] | None:
        return await self.domain.get_risk_check(risk_check_id)

    async def _limits(self, risk_limit_snapshot_id: str, config_snapshot_id: str) -> dict[str, Any]:
        row = await self.database.fetchone(
            "SELECT * FROM risk_limit_snapshots WHERE risk_limit_snapshot_id = ?",
            (risk_limit_snapshot_id,),
        )
        if not row:
            raise ValueError(f"RiskLimitSnapshot not found: {risk_limit_snapshot_id}")
        if row.get("config_snapshot_id") and row["config_snapshot_id"] != config_snapshot_id:
            raise ValueError("RiskLimitSnapshot and ConfigSnapshot are incompatible.")
        config = await self.database.fetchone("SELECT * FROM config_snapshots WHERE config_snapshot_id = ?", (config_snapshot_id,))
        if not config:
            raise ValueError(f"ConfigSnapshot not found: {config_snapshot_id}")
        return _loads_dict(row["limits_json"])

    async def _market_snapshot(self, market_snapshot_id: str | None) -> dict[str, Any] | None:
        if not market_snapshot_id:
            return None
        return await self.database.fetchone(
            "SELECT * FROM market_snapshots WHERE market_snapshot_id = ?",
            (market_snapshot_id,),
        )

    def _check_market_snapshot(
        self,
        snapshot: dict[str, Any] | None,
        limits: dict[str, Any],
        warnings: list[str],
        vetoes: list[str],
        *,
        require_price: bool,
    ) -> None:
        if not snapshot:
            vetoes.append("missing_market_snapshot")
            return
        observed_at = _parse_time(snapshot.get("observed_at"))
        if not observed_at:
            vetoes.append("missing_market_snapshot_timestamp")
        else:
            age = (self.clock.now() - observed_at).total_seconds()
            if age < 0:
                vetoes.append("market_snapshot_from_future")
            max_stale = _float(limits.get("max_stale_seconds"), default=300.0)
            if age > max_stale:
                vetoes.append("stale_market_snapshot")
        flags = set(_loads_list(snapshot.get("quality_flags_json")))
        if flags & QUALITY_VETO_FLAGS:
            vetoes.append("market_snapshot_quality_veto:" + ",".join(sorted(flags & QUALITY_VETO_FLAGS)))
        if "source_degraded" in flags or "weak_timestamp_provenance" in flags:
            warnings.append("market_snapshot_degraded_source")
            if not bool(limits.get("allow_degraded_sources", False)):
                vetoes.append("degraded_source_not_allowed")
        if str(snapshot.get("confidence") or "unknown") not in {"high", "medium"}:
            warnings.append("low_market_snapshot_confidence")
            if not bool(limits.get("allow_low_confidence", False)):
                vetoes.append("low_market_snapshot_confidence")
        if require_price and snapshot.get("price_usd") is None:
            vetoes.append("missing_market_price")
        min_liquidity = limits.get("min_liquidity_usd")
        if min_liquidity is not None and snapshot.get("liquidity_usd") is not None:
            if float(snapshot["liquidity_usd"]) < float(min_liquidity):
                vetoes.append("insufficient_liquidity")

    def _check_entry_signal(self, signal: dict[str, Any], limits: dict[str, Any], warnings: list[str], vetoes: list[str]) -> None:
        slippage = signal.get("estimated_slippage")
        max_slippage = limits.get("max_estimated_slippage_bps")
        if slippage is not None and max_slippage is not None and float(slippage) > float(max_slippage):
            vetoes.append("excessive_estimated_slippage")
        estimated_risk = _loads_dict(signal.get("estimated_risk_json"))
        intended_size = estimated_risk.get("intended_size")
        max_notional = limits.get("max_position_notional_usd")
        if intended_size is not None and max_notional is not None and float(intended_size) > float(max_notional):
            vetoes.append("max_position_notional_exceeded")
        if signal.get("confidence") not in {"high", "medium"}:
            warnings.append("low_signal_confidence")
            if not bool(limits.get("allow_low_confidence", False)):
                vetoes.append("low_signal_confidence")

    async def _check_open_position_limits(
        self,
        signal: dict[str, Any],
        limits: dict[str, Any],
        warnings: list[str],
        vetoes: list[str],
    ) -> None:
        open_rows = await self.database.fetchall(
            """
            SELECT p.*
            FROM paper_positions p
            LEFT JOIN trade_outcomes o ON o.position_id = p.position_id
            WHERE o.outcome_id IS NULL
            """
        )
        max_open = limits.get("max_open_paper_positions")
        if max_open is not None and len(open_rows) >= int(max_open):
            vetoes.append("max_open_paper_positions_exceeded")
        token_id = signal.get("token_id")
        if token_id and any(row.get("token_id") == token_id for row in open_rows):
            vetoes.append("existing_open_position_conflict")
        if open_rows:
            warnings.append("existing_open_positions_present")


Sprint1RiskService = DeterministicRiskService


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


def _float(value: Any, default: float | None = None) -> float | None:
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
