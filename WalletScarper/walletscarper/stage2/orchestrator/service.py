from __future__ import annotations

import json
from typing import Any

from walletscarper.stage2.clock import Clock, SystemClock, isoformat_utc
from walletscarper.stage2.db import Stage2Database
from walletscarper.stage2.db.json import dumps_json
from walletscarper.stage2.ids import new_id


AGENT_TRADING_DECISIONS = {"signal", "no_trade", "wait", "exit", "downgrade_wallet", "downgrade_token"}
TRACKED_WALLET_SIDES = {"buy", "sell"}
SIGNAL_INPUT_MODES = {"real_source", "fixture", "smoke"}


class HermesOrchestratorService:
    """Append-only V2 orchestration audit layer.

    This service records Hermes synthesis and attribution artifacts. It does
    not calculate canonical P&L, create risk checks, or mutate paper ledger
    tables directly.
    """

    def __init__(self, database: Stage2Database, clock: Clock | None = None):
        self.database = database
        self.clock = clock or SystemClock()

    async def record_tracked_wallet_signal_event(
        self,
        *,
        wallet: str,
        token_mint: str,
        side: str,
        observed_at: str | None = None,
        pool_address: str | None = None,
        source_name: str = "unknown",
        source_refs: list[str] | None = None,
        latency_metadata: dict[str, Any] | None = None,
        cluster_refs: list[str] | None = None,
        correlation_refs: list[str] | None = None,
        input_mode: str = "fixture",
        data_sufficiency: str | None = None,
        quality_flags: list[str] | None = None,
    ) -> str:
        if side not in TRACKED_WALLET_SIDES:
            raise ValueError(f"unsupported tracked wallet signal side: {side}")
        if input_mode not in SIGNAL_INPUT_MODES:
            raise ValueError(f"unsupported tracked wallet signal input_mode: {input_mode}")
        if not wallet:
            raise ValueError("wallet is required")
        if not token_mint:
            raise ValueError("token_mint is required")
        refs = _unique(source_refs or [])
        clusters = _unique(cluster_refs or [])
        correlations = _unique(correlation_refs or [])
        flags = list(quality_flags or [])
        if not refs:
            flags.append("missing_source_refs")
        if input_mode in {"fixture", "smoke"}:
            flags.append(f"{input_mode}_tracked_wallet_signal")
        if clusters or correlations:
            flags.append("cluster_correlated_not_independent_confirmation")
        sufficiency = data_sufficiency or ("partial" if refs else "insufficient")
        if sufficiency not in {"sufficient", "partial", "insufficient"}:
            raise ValueError(f"unsupported data sufficiency: {sufficiency}")
        event_id = new_id("tracked_wallet_signal_event")
        now = isoformat_utc(self.clock.now())
        await self.database.execute(
            """
            INSERT INTO tracked_wallet_signal_events(
              tracked_wallet_signal_event_id, wallet, token_mint, pool_address, side,
              observed_at, source_name, source_refs_json, latency_metadata_json,
              cluster_refs_json, correlation_refs_json, input_mode, data_sufficiency,
              quality_flags_json, created_by_service, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                wallet,
                token_mint,
                pool_address,
                side,
                observed_at or now,
                source_name,
                dumps_json(refs),
                dumps_json(latency_metadata or {}),
                dumps_json(clusters),
                dumps_json(correlations),
                input_mode,
                sufficiency,
                dumps_json(_unique(flags)),
                "tracked_wallet_signal_intake_service",
                now,
            ),
        )
        return event_id

    async def record_agent_trading_decision(
        self,
        *,
        decision_type: str,
        pre_action_reasoning: str,
        created_by_agent: str,
        active_token_session_id: str | None = None,
        token_refs: list[str] | None = None,
        wallet_refs: list[str] | None = None,
        market_snapshot_refs: list[str] | None = None,
        source_quality_summary: dict[str, Any] | None = None,
        uncertainties: list[str] | None = None,
        evidence_refs: list[str] | None = None,
        data_as_of: str | None = None,
        linked_signal_id: str | None = None,
        linked_no_trade_signal_id: str | None = None,
        linked_exit_decision_id: str | None = None,
        linked_outcome_id: str | None = None,
        linked_tracked_wallet_signal_event_id: str | None = None,
        quality_flags: list[str] | None = None,
    ) -> str:
        if decision_type not in AGENT_TRADING_DECISIONS:
            raise ValueError(f"unsupported agent trading decision type: {decision_type}")
        if not pre_action_reasoning:
            raise ValueError("pre_action_reasoning is required")
        refs = _unique(evidence_refs or [])
        decision_uncertainties = list(uncertainties or [])
        flags = list(quality_flags or [])
        if linked_tracked_wallet_signal_event_id:
            await self._require_row(
                "tracked_wallet_signal_events",
                "tracked_wallet_signal_event_id",
                linked_tracked_wallet_signal_event_id,
            )
            refs.append(f"tracked_wallet_signal_event:{linked_tracked_wallet_signal_event_id}")
        if not refs:
            decision_uncertainties.append("missing_evidence_refs")
        decision_id = new_id("agent_trading_decision")
        now = isoformat_utc(self.clock.now())
        await self.database.execute(
            """
            INSERT INTO agent_trading_decisions(
              agent_trading_decision_id, active_token_session_id, decision_type,
              pre_action_reasoning, evidence_refs_json, wallet_refs_json,
              token_refs_json, market_snapshot_refs_json, source_quality_summary_json,
              uncertainties_json, data_as_of, linked_signal_id, linked_no_trade_signal_id,
              linked_exit_decision_id, linked_outcome_id, linked_tracked_wallet_signal_event_id,
              quality_flags_json, created_by_agent, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                decision_id,
                active_token_session_id,
                decision_type,
                pre_action_reasoning,
                dumps_json(_unique(refs)),
                dumps_json(_unique(wallet_refs or [])),
                dumps_json(_unique(token_refs or [])),
                dumps_json(_unique(market_snapshot_refs or [])),
                dumps_json(source_quality_summary or {}),
                dumps_json(_unique(decision_uncertainties)),
                data_as_of or now,
                linked_signal_id,
                linked_no_trade_signal_id,
                linked_exit_decision_id,
                linked_outcome_id,
                linked_tracked_wallet_signal_event_id,
                dumps_json(_unique(flags)),
                created_by_agent,
                now,
            ),
        )
        if linked_tracked_wallet_signal_event_id:
            await self.link_decision_artifact(
                agent_trading_decision_id=decision_id,
                artifact_type="tracked_wallet_signal_event",
                artifact_id=linked_tracked_wallet_signal_event_id,
                relationship="decision_used_wallet_signal",
                evidence_refs=[f"tracked_wallet_signal_event:{linked_tracked_wallet_signal_event_id}"],
            )
        return decision_id

    async def link_decision_artifact(
        self,
        *,
        agent_trading_decision_id: str,
        artifact_type: str,
        artifact_id: str,
        relationship: str,
        evidence_refs: list[str] | None = None,
    ) -> str:
        await self._require_row("agent_trading_decisions", "agent_trading_decision_id", agent_trading_decision_id)
        link_id = new_id("agent_decision_link")
        await self.database.execute(
            """
            INSERT INTO agent_trading_decision_artifact_links(
              agent_trading_decision_artifact_link_id, agent_trading_decision_id,
              artifact_type, artifact_id, relationship, evidence_refs_json, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                link_id,
                agent_trading_decision_id,
                artifact_type,
                artifact_id,
                relationship,
                dumps_json(_unique(evidence_refs or [])),
                isoformat_utc(self.clock.now()),
            ),
        )
        return link_id

    async def create_wallet_contribution_report(
        self,
        *,
        wallet: str,
        strategy_version_id: str | None = None,
        window_start: str | None = None,
        window_end: str | None = None,
        created_by_service: str = "v2_wallet_contribution_report_service",
    ) -> dict[str, Any]:
        if not wallet:
            raise ValueError("wallet is required")
        signal_events = await self.database.fetchall(
            """
            SELECT *
            FROM tracked_wallet_signal_events
            WHERE wallet = ?
              AND (? IS NULL OR observed_at >= ?)
              AND (? IS NULL OR observed_at <= ?)
            ORDER BY observed_at ASC
            """,
            (wallet, window_start, window_start, window_end, window_end),
        )
        decisions = await self.database.fetchall(
            """
            SELECT *
            FROM agent_trading_decisions
            WHERE wallet_refs_json LIKE ?
            ORDER BY created_at ASC
            """,
            (f"%{wallet}%",),
        )
        decision_ids = [str(row["agent_trading_decision_id"]) for row in decisions]
        outcome_ids: list[str] = []
        if decision_ids:
            placeholders = ",".join("?" for _ in decision_ids)
            links = await self.database.fetchall(
                f"""
                SELECT artifact_id
                FROM agent_trading_decision_artifact_links
                WHERE agent_trading_decision_id IN ({placeholders})
                  AND artifact_type = 'trade_outcome'
                """,
                tuple(decision_ids),
            )
            outcome_ids = _unique([row["artifact_id"] for row in links])
        outcomes = []
        for outcome_id in outcome_ids:
            row = await self.database.fetchone("SELECT * FROM trade_outcomes WHERE outcome_id = ?", (outcome_id,))
            if row:
                if strategy_version_id:
                    position = await self.database.fetchone(
                        "SELECT strategy_version_id FROM paper_positions WHERE position_id = ?",
                        (row["position_id"],),
                    )
                    if not position or position["strategy_version_id"] != strategy_version_id:
                        continue
                outcomes.append(row)
        net_values = [float(row["net_pnl"]) for row in outcomes]
        wins = [value for value in net_values if value > 0]
        linked_count = len(net_values)
        signal_count = len(signal_events)
        net_pnl = sum(net_values) if net_values else None
        expectancy = (net_pnl / linked_count) if net_pnl is not None and linked_count else None
        win_rate = (len(wins) / linked_count) if linked_count else None
        max_drawdown = _max_drawdown(net_values) if net_values else None
        quality_flags: list[str] = []
        if not linked_count:
            quality_flags.append("insufficient_forward_outcomes")
        if any(row.get("input_mode") in {"fixture", "smoke"} for row in signal_events):
            quality_flags.append("fixture_or_smoke_signal_evidence")
        data_sufficiency = "sufficient" if linked_count >= 5 else ("partial" if linked_count else "insufficient")
        refs = _unique(
            [f"tracked_wallet_signal_event:{row['tracked_wallet_signal_event_id']}" for row in signal_events]
            + [f"agent_trading_decision:{decision_id}" for decision_id in decision_ids]
            + [f"trade_outcome:{outcome_id}" for outcome_id in outcome_ids]
        )
        report = {
            "wallet": wallet,
            "strategy_version_id": strategy_version_id,
            "source_signal_count": signal_count,
            "linked_outcome_count": linked_count,
            "net_pnl": net_pnl,
            "expectancy": expectancy,
            "win_rate": win_rate,
            "max_drawdown": max_drawdown,
            "data_sufficiency": data_sufficiency,
            "quality_flags": _unique(quality_flags),
            "truth_boundary": "wallet forward contribution draft; not proof of future edge",
        }
        report_id = new_id("wallet_contribution_report")
        await self.database.execute(
            """
            INSERT INTO wallet_contribution_reports(
              wallet_contribution_report_id, wallet, strategy_version_id, window_start,
              window_end, source_signal_count, linked_outcome_count, net_pnl,
              expectancy, win_rate, max_drawdown, data_sufficiency,
              quality_flags_json, evidence_refs_json, report_json,
              created_by_service, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                report_id,
                wallet,
                strategy_version_id,
                window_start,
                window_end,
                signal_count,
                linked_count,
                net_pnl,
                expectancy,
                win_rate,
                max_drawdown,
                data_sufficiency,
                dumps_json(_unique(quality_flags)),
                dumps_json(refs),
                dumps_json(report),
                created_by_service,
                isoformat_utc(self.clock.now()),
            ),
        )
        contribution_id = new_id("wallet_forward_contribution")
        await self.database.execute(
            """
            INSERT INTO wallet_forward_contributions(
              wallet_forward_contribution_id, wallet, strategy_version_id, window_start,
              window_end, signal_count, paper_trade_count, net_pnl, expectancy,
              win_rate, max_drawdown, quality_flags_json, calculated_by_service,
              calculated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                contribution_id,
                wallet,
                strategy_version_id,
                window_start,
                window_end,
                signal_count,
                linked_count,
                net_pnl,
                expectancy,
                win_rate,
                max_drawdown,
                dumps_json(_unique(quality_flags + ["draft_report"])),
                created_by_service,
                isoformat_utc(self.clock.now()),
            ),
        )
        report["wallet_contribution_report_id"] = report_id
        report["wallet_forward_contribution_id"] = contribution_id
        report["evidence_refs"] = refs
        return report

    async def _require_row(self, table: str, key: str, value: str) -> dict[str, Any]:
        row = await self.database.fetchone(f"SELECT * FROM {table} WHERE {key} = ?", (value,))
        if not row:
            raise ValueError(f"{table}.{key} not found: {value}")
        return row


def _loads_list(raw: Any) -> list[Any]:
    if not raw:
        return []
    parsed = json.loads(raw) if isinstance(raw, str) else raw
    return parsed if isinstance(parsed, list) else []


def _unique(values: list[Any]) -> list[str]:
    result: list[str] = []
    for value in values:
        text = str(value)
        if text and text not in result:
            result.append(text)
    return result


def _max_drawdown(values: list[float]) -> float:
    peak = 0.0
    cumulative = 0.0
    drawdown = 0.0
    for value in values:
        cumulative += value
        peak = max(peak, cumulative)
        drawdown = min(drawdown, cumulative - peak)
    return drawdown
