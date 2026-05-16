from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from walletscarper.stage2.clock import Clock, SystemClock, isoformat_utc
from walletscarper.stage2.db import Stage2Database
from walletscarper.stage2.db.json import dumps_json
from walletscarper.stage2.domain.repository import DomainRepository
from walletscarper.stage2.ids import new_id
from walletscarper.stage2.jobs import JobQueueService
from walletscarper.stage2.monitoring import MonitoringRepository
from walletscarper.stage2.signals import SignalService


class PaperOrderRejected(ValueError):
    pass


class Sprint3PaperTradingService:
    """Deterministic paper-trading service for Sprint 3.

    This service simulates paper-only orders/fills/positions/exits. It does not
    call wallet-control paths, network mutation methods, or legacy paper trades.
    """

    def __init__(
        self,
        database: Stage2Database,
        domain: DomainRepository,
        clock: Clock | None = None,
        *,
        monitoring: MonitoringRepository | None = None,
        jobs: JobQueueService | None = None,
    ):
        self.database = database
        self.domain = domain
        self.clock = clock or SystemClock()
        self.monitoring = monitoring or MonitoringRepository(database, clock=self.clock)
        self.jobs = jobs or JobQueueService(database, clock=self.clock)

    async def create_paper_order(
        self,
        *,
        signal_id: str,
        risk_check_id: str,
        side: str = "buy",
        intended_size: float | None = None,
        intended_price_ref: str | None = None,
    ) -> str:
        signal = await self.domain.get_signal(signal_id)
        if signal is None:
            raise PaperOrderRejected(f"Signal does not exist: {signal_id}")
        thesis = await self.domain.get_trade_thesis_for_signal(signal_id)
        if thesis is None:
            raise PaperOrderRejected("TradeThesis must exist before PaperOrder.")
        risk_check = await self.domain.get_risk_check(risk_check_id)
        self._validate_risk_check_for_entry(risk_check, signal_id)
        await self._validate_config_compatibility(signal, risk_check)
        existing = await self.database.fetchone(
            """
            SELECT paper_order_id FROM paper_orders
            WHERE signal_id = ? AND side = 'buy'
            LIMIT 1
            """,
            (signal_id,),
        )
        if existing:
            raise PaperOrderRejected("Signal already has an entry PaperOrder.")
        if side != "buy":
            raise PaperOrderRejected("Entry PaperOrder side must be 'buy'.")
        size = intended_size if intended_size is not None else _float(_loads_dict(signal.get("estimated_risk_json")).get("intended_size"))
        if size is None:
            size = 1.0
        if size <= 0:
            raise PaperOrderRejected("PaperOrder intended_size must be positive.")

        return await self._insert_paper_order(
            signal_id=signal_id,
            risk_check_id=risk_check_id,
            strategy_version_id=signal["strategy_version_id"],
            side="buy",
            intended_size=size,
            intended_price_ref=intended_price_ref or (f"market_snapshot:{risk_check.get('market_snapshot_id')}" if risk_check else None),
            status="created",
        )

    async def simulate_entry_fill(self, *, paper_order_id: str, market_snapshot_id: str) -> str:
        order = await self._order(paper_order_id)
        if str(order["side"]) != "buy":
            raise PaperOrderRejected("Entry fill simulation requires a buy PaperOrder.")
        return await self._simulate_fill_for_order(order, market_snapshot_id, fill_kind="entry")

    async def open_position_from_fill(self, *, paper_fill_id: str) -> str:
        fill = await self._fill(paper_fill_id)
        if fill.get("failed_fill_reason"):
            raise PaperOrderRejected("Failed fill cannot open PaperPosition.")
        if fill.get("fill_price") is None:
            raise PaperOrderRejected("Fill without price cannot open PaperPosition.")
        order = await self._order(str(fill["paper_order_id"]))
        if str(order["side"]) != "buy":
            raise PaperOrderRejected("Only entry buy fills can open PaperPosition.")
        signal = await self.domain.get_signal(str(order["signal_id"]))
        if not signal:
            raise PaperOrderRejected("Entry order signal is missing.")
        existing = await self.database.fetchone(
            "SELECT position_id FROM paper_positions WHERE entry_fill_id = ?",
            (paper_fill_id,),
        )
        if existing:
            return str(existing["position_id"])
        position_id = new_id("paper_position")
        size = float(fill.get("filled_size") or order["intended_size"])
        cost_basis = size * float(fill["fill_price"]) + float(fill["fees"] or 0)
        await self.database.execute(
            """
            INSERT INTO paper_positions(
              position_id, token_id, strategy_version_id, entry_order_id, entry_fill_id,
              size, cost_basis, opened_at, status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'open')
            """,
            (
                position_id,
                signal["token_id"],
                signal["strategy_version_id"],
                order["paper_order_id"],
                paper_fill_id,
                size,
                cost_basis,
                fill["fill_time"],
            ),
        )
        await self._record_position_event(
            position_id=position_id,
            event_type="opened",
            market_snapshot_id=fill.get("market_snapshot_id"),
            payload={"entry_fill_id": paper_fill_id, "cost_basis": cost_basis},
        )
        await self.monitoring.create_session(
            session_type="paper_position_monitoring",
            subject_type="paper_position",
            subject_id=position_id,
            priority=10,
            status="active",
            strategy_version_id=signal["strategy_version_id"],
            metadata={"entry_order_id": order["paper_order_id"], "entry_fill_id": paper_fill_id},
        )
        await self.jobs.create_job(
            job_type="paper_position_monitor",
            worker_type="position_monitor",
            target_ref=position_id,
            priority=10,
            payload={"position_id": position_id, "token_id": signal["token_id"]},
        )
        return position_id

    async def create_exit_decision(self, *, position_id: str, payload: dict[str, Any]) -> str:
        position = await self.database.fetchone("SELECT * FROM paper_positions WHERE position_id = ?", (position_id,))
        if not position:
            raise PaperOrderRejected(f"PaperPosition not found: {position_id}")
        if await self._position_has_outcome(position_id):
            raise PaperOrderRejected("PaperPosition already has a TradeOutcome.")
        market_snapshot_id = _text(payload.get("market_snapshot_id"))
        snapshot = await self.database.fetchone(
            "SELECT * FROM market_snapshots WHERE market_snapshot_id = ?",
            (market_snapshot_id,),
        ) if market_snapshot_id else None
        now = self.clock.now()
        exit_id = new_id("exit_decision")
        await self.database.execute(
            """
            INSERT INTO exit_decisions(
              exit_decision_id, position_id, created_at, data_as_of, market_snapshot_id,
              exit_reason, exit_trigger, expected_exit_logic, created_by
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                exit_id,
                position_id,
                isoformat_utc(now),
                isoformat_utc(_parse_time(payload.get("data_as_of")) or _parse_time((snapshot or {}).get("observed_at")) or now),
                market_snapshot_id,
                _required_text(payload, "exit_reason"),
                _required_text(payload, "exit_trigger"),
                _required_text(payload, "expected_exit_logic"),
                str(payload.get("created_by") or "paper_trading_service"),
            ),
        )
        await self._record_position_event(
            position_id=position_id,
            event_type="exit_decision_created",
            market_snapshot_id=market_snapshot_id,
            payload={"exit_decision_id": exit_id, "exit_reason": payload["exit_reason"]},
        )
        return exit_id

    async def execute_paper_exit(self, *, exit_decision_id: str, risk_check_id: str) -> str:
        exit_decision = await self.database.fetchone(
            "SELECT * FROM exit_decisions WHERE exit_decision_id = ?",
            (exit_decision_id,),
        )
        if not exit_decision:
            raise PaperOrderRejected("ExitDecision must exist before exit fill.")
        risk_check = await self.domain.get_risk_check(risk_check_id)
        self._validate_risk_check_for_exit(risk_check, exit_decision_id)
        position = await self.database.fetchone(
            "SELECT * FROM paper_positions WHERE position_id = ?",
            (exit_decision["position_id"],),
        )
        if not position:
            raise PaperOrderRejected("ExitDecision position is missing.")
        entry_order = await self._order(str(position["entry_order_id"]))
        sell_order_id = await self._insert_paper_order(
            signal_id=entry_order["signal_id"],
            risk_check_id=risk_check_id,
            strategy_version_id=position["strategy_version_id"],
            side="sell",
            intended_size=float(position["size"]),
            intended_price_ref=f"market_snapshot:{risk_check.get('market_snapshot_id')}",
            status="exit_created",
        )
        sell_order = await self._order(sell_order_id)
        fill_id = await self._simulate_fill_for_order(
            sell_order,
            str(risk_check.get("market_snapshot_id") or exit_decision.get("market_snapshot_id")),
            fill_kind="exit",
        )
        fill = await self._fill(fill_id)
        if not fill.get("failed_fill_reason"):
            await self._record_position_event(
                position_id=str(position["position_id"]),
                event_type="exit_fill_created",
                market_snapshot_id=fill.get("market_snapshot_id"),
                risk_check_id=risk_check_id,
                payload={"exit_decision_id": exit_decision_id, "exit_fill_id": fill_id},
            )
        return fill_id

    async def create_fill_later(self, *, paper_order_id: str, market_snapshot_id: str) -> str:
        return await self.simulate_entry_fill(paper_order_id=paper_order_id, market_snapshot_id=market_snapshot_id)

    async def _insert_paper_order(
        self,
        *,
        signal_id: str,
        risk_check_id: str,
        strategy_version_id: str,
        side: str,
        intended_size: float,
        intended_price_ref: str | None,
        status: str,
    ) -> str:
        order_id = new_id("paper_order")
        await self.database.execute(
            """
            INSERT INTO paper_orders(
              paper_order_id, signal_id, risk_check_id, strategy_version_id,
              side, intended_size, intended_price_ref, created_at, status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                order_id,
                signal_id,
                risk_check_id,
                strategy_version_id,
                side,
                intended_size,
                intended_price_ref,
                isoformat_utc(self.clock.now()),
                status,
            ),
        )
        return order_id

    async def _simulate_fill_for_order(self, order: dict[str, Any], market_snapshot_id: str, *, fill_kind: str) -> str:
        snapshot = await self.database.fetchone(
            "SELECT * FROM market_snapshots WHERE market_snapshot_id = ?",
            (market_snapshot_id,),
        )
        risk = await self.domain.get_risk_check(str(order["risk_check_id"]))
        limits = await self._limits_for_risk(risk)
        now = self.clock.now()
        failed_reason: str | None = None
        base_price = _float((snapshot or {}).get("price_usd"))
        observed_at = _parse_time((snapshot or {}).get("observed_at"))
        liquidity = _float((snapshot or {}).get("liquidity_usd"))
        if not snapshot:
            failed_reason = "missing_market_snapshot"
        elif observed_at is None:
            failed_reason = "missing_market_snapshot_timestamp"
        elif observed_at > now:
            failed_reason = "market_snapshot_from_future"
        elif (now - observed_at).total_seconds() > _float(limits.get("max_fill_stale_seconds"), default=300.0):
            failed_reason = "stale_market_snapshot"
        elif base_price is None:
            failed_reason = "missing_fill_price"
        elif liquidity is None:
            failed_reason = "missing_liquidity_for_conservative_fill"

        slippage_bps = _float(limits.get("fill_slippage_bps"), default=50.0)
        fee_bps = _float(limits.get("paper_fee_bps"), default=25.0)
        latency_ms = int(_float(limits.get("fill_latency_ms"), default=1500.0) or 1500)
        filled_size = float(order["intended_size"])
        fill_price: float | None = None
        fees = 0.0
        slippage_cost = 0.0
        if failed_reason is None and base_price is not None:
            liquidity_cap_notional = float(liquidity or 0) * float(limits.get("max_liquidity_fraction", 0.01))
            intended_notional = float(order["intended_size"]) * base_price
            if liquidity_cap_notional > 0 and intended_notional > liquidity_cap_notional:
                capped_size = liquidity_cap_notional / base_price
                if order["side"] == "sell":
                    failed_reason = "liquidity_cap_exceeded_for_full_exit"
                elif capped_size > 0:
                    filled_size = capped_size
                else:
                    failed_reason = "liquidity_cap_exceeded"
        if failed_reason is None and base_price is not None:
            slip_per_token = base_price * slippage_bps / 10_000
            if order["side"] == "buy":
                fill_price = base_price + slip_per_token
            else:
                fill_price = max(0.0, base_price - slip_per_token)
            notional = filled_size * fill_price
            fees = notional * fee_bps / 10_000
            slippage_cost = abs(slip_per_token) * filled_size

        fill_id = new_id("paper_fill")
        await self.database.execute(
            """
            INSERT INTO paper_fills(
              paper_fill_id, paper_order_id, fill_time, fill_price, filled_size, fees, slippage,
              latency_assumption, liquidity_constraint, failed_fill_reason, market_snapshot_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                fill_id,
                order["paper_order_id"],
                isoformat_utc(now),
                fill_price,
                filled_size if failed_reason is None else None,
                fees,
                slippage_cost,
                f"conservative_fixed_latency_ms:{latency_ms}",
                "max_liquidity_fraction:" + str(limits.get("max_liquidity_fraction", 0.01))
                + f"; intended_size:{order['intended_size']}; filled_size:{filled_size if failed_reason is None else 0}",
                failed_reason,
                market_snapshot_id,
            ),
        )
        if failed_reason:
            await SignalService(self.database, self.domain, clock=self.clock).log_rejected_trade(
                subject_type="paper_order",
                subject_id=str(order["paper_order_id"]),
                stage=f"{fill_kind}_fill",
                reason=failed_reason,
                metadata={"market_snapshot_id": market_snapshot_id, "paper_fill_id": fill_id},
            )
        return fill_id

    async def _record_position_event(
        self,
        *,
        position_id: str,
        event_type: str,
        market_snapshot_id: str | None = None,
        risk_check_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> str:
        event_id = new_id("paper_position_event")
        await self.database.execute(
            """
            INSERT INTO paper_position_events(
              paper_position_event_id, position_id, event_type, created_at,
              market_snapshot_id, risk_check_id, payload_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                position_id,
                event_type,
                isoformat_utc(self.clock.now()),
                market_snapshot_id,
                risk_check_id,
                dumps_json(payload or {}),
            ),
        )
        return event_id

    async def _limits_for_risk(self, risk_check: dict[str, Any] | None) -> dict[str, Any]:
        if not risk_check:
            return {}
        row = await self.database.fetchone(
            "SELECT limits_json FROM risk_limit_snapshots WHERE risk_limit_snapshot_id = ?",
            (risk_check["risk_limit_snapshot_id"],),
        )
        return _loads_dict((row or {}).get("limits_json"))

    def _validate_risk_check_for_entry(self, risk_check: dict[str, Any] | None, signal_id: str) -> None:
        if risk_check is None:
            raise PaperOrderRejected("PaperOrder requires an existing RiskCheck.")
        if risk_check["created_by_service"] != "risk_service":
            raise PaperOrderRejected("RiskCheck is not authoritative from Risk Service.")
        if risk_check["check_scope"] != "entry":
            raise PaperOrderRejected("PaperOrder requires an entry RiskCheck.")
        if risk_check["subject_type"] != "signal" or risk_check["subject_id"] != signal_id:
            raise PaperOrderRejected("RiskCheck does not belong to this signal.")
        if int(risk_check["passed"]) != 1:
            raise PaperOrderRejected("PaperOrder requires a passed RiskCheck.")

    def _validate_risk_check_for_exit(self, risk_check: dict[str, Any] | None, exit_decision_id: str) -> None:
        if risk_check is None:
            raise PaperOrderRejected("Paper exit requires an existing RiskCheck.")
        if risk_check["created_by_service"] != "risk_service":
            raise PaperOrderRejected("Exit RiskCheck is not authoritative from Risk Service.")
        if risk_check["check_scope"] != "exit":
            raise PaperOrderRejected("Paper exit requires an exit RiskCheck.")
        if risk_check["subject_type"] != "exit_decision" or risk_check["subject_id"] != exit_decision_id:
            raise PaperOrderRejected("Exit RiskCheck does not belong to this ExitDecision.")
        if int(risk_check["passed"]) != 1:
            raise PaperOrderRejected("Paper exit requires a passed exit RiskCheck.")

    async def _validate_config_compatibility(self, signal: dict[str, Any], risk_check: dict[str, Any] | None) -> None:
        if not risk_check:
            return
        strategy_config = await self.database.fetchone(
            "SELECT config_snapshot_id FROM strategy_config_snapshots WHERE strategy_config_snapshot_id = ?",
            (signal["strategy_config_snapshot_id"],),
        )
        linked_config = (strategy_config or {}).get("config_snapshot_id")
        if linked_config and linked_config != risk_check["config_snapshot_id"]:
            raise PaperOrderRejected("Signal strategy config and RiskCheck config snapshot are incompatible.")

    async def _order(self, paper_order_id: str) -> dict[str, Any]:
        order = await self.database.fetchone("SELECT * FROM paper_orders WHERE paper_order_id = ?", (paper_order_id,))
        if not order:
            raise PaperOrderRejected(f"PaperOrder not found: {paper_order_id}")
        return order

    async def _fill(self, paper_fill_id: str) -> dict[str, Any]:
        fill = await self.database.fetchone("SELECT * FROM paper_fills WHERE paper_fill_id = ?", (paper_fill_id,))
        if not fill:
            raise PaperOrderRejected(f"PaperFill not found: {paper_fill_id}")
        return fill

    async def _position_has_outcome(self, position_id: str) -> bool:
        row = await self.database.fetchone("SELECT outcome_id FROM trade_outcomes WHERE position_id = ? LIMIT 1", (position_id,))
        return bool(row)


Sprint1PaperTradingService = Sprint3PaperTradingService


def _required_text(payload: dict[str, Any], key: str) -> str:
    value = _text(payload.get(key))
    if not value:
        raise PaperOrderRejected(f"{key} is required")
    return value


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None


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
