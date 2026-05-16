from __future__ import annotations

from typing import Any

from walletscarper.stage2.clock import Clock, SystemClock, isoformat_utc
from walletscarper.stage2.db import Stage2Database
from walletscarper.stage2.db.json import dumps_json
from walletscarper.stage2.domain import DomainRepository
from walletscarper.stage2.ids import new_id
from walletscarper.stage2.parallelism import parse_json_object


ALLOWED_MUTATION_TYPES = {
    "wallet_scoring_weights",
    "signal_combination",
    "no_trade_filter",
    "confidence_calibration",
    "token_bucket_policy",
    "expected_holding_time_hypothesis",
    "wallet_ranking_hypothesis",
    "exit_logic_variant",
    "risk_filter_candidate",
}

FORBIDDEN_MUTATION_KEYWORDS = {
    "pnl_calculation",
    "ledger_rewrite",
    "disable_fees",
    "disable_slippage",
    "disable_latency",
    "disable_failed_fills",
    "disable_risk_engine",
    "rewrite_outcomes",
    "live_execution",
    "credential_material_access",
}


class StrategyResearchService:
    """Strategy mutation, experiment, leaderboard, and decision service.

    Metrics are derived only from Sprint 3 deterministic `trade_outcomes` and
    ledger records. Legacy paper trades and FIFO PnL are never queried here.
    """

    def __init__(self, database: Stage2Database, *, domain: DomainRepository | None = None, clock: Clock | None = None):
        self.database = database
        self.clock = clock or SystemClock()
        self.domain = domain or DomainRepository(database, clock=self.clock)

    async def create_mutation_proposal(
        self,
        *,
        parent_strategy_version_id: str,
        mutation_type: str,
        hypothesis: str,
        changed_assumptions: dict[str, Any],
        expected_effect: str,
        target_buckets: dict[str, Any],
        proposed_budget: dict[str, Any],
        promotion_criteria_snapshot_id: str,
        created_by: str,
        kill_criteria_ref: str | None = None,
        source_refs: list[str] | None = None,
        review_refs: list[str] | None = None,
    ) -> str:
        if mutation_type not in ALLOWED_MUTATION_TYPES:
            raise ValueError(f"Forbidden or unsupported strategy mutation type: {mutation_type}")
        serialized = dumps_json({"mutation_type": mutation_type, "changed_assumptions": changed_assumptions})
        if any(keyword in serialized for keyword in FORBIDDEN_MUTATION_KEYWORDS):
            raise ValueError("Strategy mutation attempts to change forbidden ledger/risk/execution assumptions.")
        await self._require_row("strategy_versions", "strategy_version_id", parent_strategy_version_id)
        await self._require_row("promotion_criteria_snapshots", "promotion_criteria_snapshot_id", promotion_criteria_snapshot_id)
        proposal_id = new_id("strategy_mutation_proposal")
        await self.database.execute(
            """
            INSERT INTO strategy_mutation_proposals(
              strategy_mutation_proposal_id, parent_strategy_version_id, mutation_type,
              hypothesis, changed_assumptions_json, expected_effect, target_buckets_json,
              proposed_budget_json, kill_criteria_ref, promotion_criteria_snapshot_id,
              source_refs_json, review_refs_json, created_by, created_at, status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'proposed')
            """,
            (
                proposal_id,
                parent_strategy_version_id,
                mutation_type,
                hypothesis,
                dumps_json(changed_assumptions),
                expected_effect,
                dumps_json(target_buckets),
                dumps_json(proposed_budget),
                kill_criteria_ref,
                promotion_criteria_snapshot_id,
                dumps_json(source_refs or []),
                dumps_json(review_refs or []),
                created_by,
                isoformat_utc(self.clock.now()),
            ),
        )
        return proposal_id

    async def create_strategy_version_from_proposal(
        self,
        proposal_id: str,
        *,
        strategy_config_snapshot_id: str,
        rules: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        agents: list[str] | None = None,
    ) -> str:
        proposal = await self.database.fetchone(
            "SELECT * FROM strategy_mutation_proposals WHERE strategy_mutation_proposal_id = ?",
            (proposal_id,),
        )
        if not proposal:
            raise ValueError(f"StrategyMutationProposal not found: {proposal_id}")
        strategy_version_id = await self.domain.create_strategy_version(
            strategy_config_snapshot_id=strategy_config_snapshot_id,
            parent_strategy_version_id=str(proposal["parent_strategy_version_id"]),
            mutation_proposal_id=proposal_id,
            rules=rules or {"mutation_type": proposal["mutation_type"]},
            params=params or parse_json_object(proposal["changed_assumptions_json"]),
            agents=agents or [],
            status="experimental",
        )
        await self.database.execute(
            """
            UPDATE strategy_mutation_proposals
            SET proposed_strategy_version_id = ?, status = 'versioned'
            WHERE strategy_mutation_proposal_id = ?
            """,
            (strategy_version_id, proposal_id),
        )
        return strategy_version_id

    async def create_strategy_experiment(
        self,
        *,
        strategy_version_id: str,
        strategy_config_snapshot_id: str,
        promotion_criteria_snapshot_id: str,
        budget: dict[str, Any],
        stop_conditions: dict[str, Any] | None = None,
        target_buckets: dict[str, Any] | None = None,
        mutation_proposal_id: str | None = None,
        baseline_refs: list[str] | None = None,
        no_trade_baseline_refs: list[str] | None = None,
        status: str = "planned",
    ) -> str:
        if not budget:
            raise ValueError("StrategyExperiment requires an explicit budget.")
        strategy = await self._require_row("strategy_versions", "strategy_version_id", strategy_version_id)
        await self._require_row("strategy_config_snapshots", "strategy_config_snapshot_id", strategy_config_snapshot_id)
        await self._require_row("promotion_criteria_snapshots", "promotion_criteria_snapshot_id", promotion_criteria_snapshot_id)
        experiment_id = new_id("strategy_experiment")
        await self.database.execute(
            """
            INSERT INTO strategy_experiments(
              strategy_experiment_id, strategy_version_id, parent_strategy_version_id,
              mutation_proposal_id, strategy_config_snapshot_id, promotion_criteria_snapshot_id,
              budget_json, stop_conditions_json, target_buckets_json, baseline_refs_json,
              no_trade_baseline_refs_json, status, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                experiment_id,
                strategy_version_id,
                strategy.get("parent_strategy_version_id"),
                mutation_proposal_id,
                strategy_config_snapshot_id,
                promotion_criteria_snapshot_id,
                dumps_json(budget),
                dumps_json(stop_conditions or {}),
                dumps_json(target_buckets or {}),
                dumps_json(baseline_refs or []),
                dumps_json(no_trade_baseline_refs or []),
                status,
                isoformat_utc(self.clock.now()),
            ),
        )
        return experiment_id

    async def create_metric_snapshot(
        self,
        strategy_version_id: str,
        *,
        promotion_criteria_snapshot_id: str | None = None,
    ) -> str:
        await self._require_row("strategy_versions", "strategy_version_id", strategy_version_id)
        criteria = await self._criteria(promotion_criteria_snapshot_id)
        metrics = await self._calculate_metrics(strategy_version_id, criteria)
        snapshot_id = new_id("strategy_metric_snapshot")
        await self.database.execute(
            """
            INSERT INTO strategy_metric_snapshots(
              strategy_metric_snapshot_id, strategy_version_id, promotion_criteria_snapshot_id,
              calculated_at, closed_trade_count, open_position_count, rejected_count,
              no_trade_count, failed_fill_count, gross_pnl, net_pnl, expectancy,
              win_rate, profit_factor, average_win, average_loss, max_drawdown,
              degraded_outcome_count, sample_size_warning, concentration_warning,
              quality_flags_json, metrics_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                snapshot_id,
                strategy_version_id,
                promotion_criteria_snapshot_id,
                isoformat_utc(self.clock.now()),
                metrics["closed_trade_count"],
                metrics["open_position_count"],
                metrics["rejected_count"],
                metrics["no_trade_count"],
                metrics["failed_fill_count"],
                metrics["gross_pnl"],
                metrics["net_pnl"],
                metrics["expectancy"],
                metrics["win_rate"],
                metrics["profit_factor"],
                metrics["average_win"],
                metrics["average_loss"],
                metrics["max_drawdown"],
                metrics["degraded_outcome_count"],
                metrics["sample_size_warning"],
                metrics["concentration_warning"],
                dumps_json(metrics["quality_flags"]),
                dumps_json(metrics),
            ),
        )
        return snapshot_id

    async def leaderboard_v1(self, *, promotion_criteria_snapshot_id: str | None = None) -> list[dict[str, Any]]:
        strategies = await self.database.fetchall(
            "SELECT strategy_version_id FROM strategy_versions ORDER BY created_at ASC"
        )
        rows: list[dict[str, Any]] = []
        for strategy in strategies:
            snapshot_id = await self.create_metric_snapshot(
                str(strategy["strategy_version_id"]),
                promotion_criteria_snapshot_id=promotion_criteria_snapshot_id,
            )
            row = await self.database.fetchone(
                "SELECT * FROM strategy_metric_snapshots WHERE strategy_metric_snapshot_id = ?",
                (snapshot_id,),
            )
            if row:
                rows.append(dict(row))
        rows.sort(key=lambda item: (float(item["net_pnl"]), int(item["closed_trade_count"])), reverse=True)
        return rows

    async def decide_strategy(
        self,
        *,
        strategy_version_id: str,
        promotion_criteria_snapshot_id: str,
        metrics_snapshot_id: str | None = None,
        created_by_service: str = "strategy_research_service",
    ) -> str:
        await self._require_row("promotion_criteria_snapshots", "promotion_criteria_snapshot_id", promotion_criteria_snapshot_id)
        if metrics_snapshot_id is None:
            metrics_snapshot_id = await self.create_metric_snapshot(
                strategy_version_id,
                promotion_criteria_snapshot_id=promotion_criteria_snapshot_id,
            )
        metrics = await self._require_row("strategy_metric_snapshots", "strategy_metric_snapshot_id", metrics_snapshot_id)
        criteria = await self._criteria(promotion_criteria_snapshot_id)
        decision_type, reason, passed, failed = self._evaluate_decision(metrics, criteria)
        decision_id = new_id("strategy_decision")
        await self.database.execute(
            """
            INSERT INTO strategy_decisions(
              strategy_decision_id, strategy_version_id, decision_type,
              promotion_criteria_snapshot_id, metrics_snapshot_id, reason,
              failed_criteria_json, passed_criteria_json, created_by_service,
              created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                decision_id,
                strategy_version_id,
                decision_type,
                promotion_criteria_snapshot_id,
                metrics_snapshot_id,
                reason,
                dumps_json(failed),
                dumps_json(passed),
                created_by_service,
                isoformat_utc(self.clock.now()),
            ),
        )
        return decision_id

    async def _calculate_metrics(self, strategy_version_id: str, criteria: dict[str, Any]) -> dict[str, Any]:
        outcome_rows = await self.database.fetchall(
            """
            SELECT tout.*, pp.token_id
            FROM trade_outcomes tout
            JOIN paper_positions pp ON pp.position_id = tout.position_id
            WHERE pp.strategy_version_id = ?
            ORDER BY tout.calculated_at ASC
            """,
            (strategy_version_id,),
        )
        net_values = [float(row["net_pnl"]) for row in outcome_rows]
        gross_values = [float(row["gross_pnl"]) for row in outcome_rows]
        wins = [value for value in net_values if value > 0]
        losses = [value for value in net_values if value < 0]
        closed = len(outcome_rows)
        gross_pnl = sum(gross_values)
        net_pnl = sum(net_values)
        expectancy = net_pnl / closed if closed else None
        win_rate = len(wins) / closed if closed else None
        profit_factor = (sum(wins) / abs(sum(losses))) if losses and wins else (None if closed == 0 else 0)
        average_win = sum(wins) / len(wins) if wins else None
        average_loss = sum(losses) / len(losses) if losses else None
        max_drawdown = self._max_drawdown(net_values)
        open_count = await self._count(
            "paper_positions",
            "strategy_version_id = ? AND position_id NOT IN (SELECT position_id FROM trade_outcomes)",
            (strategy_version_id,),
        )
        no_trade_count = await self._count(
            "no_trade_signals",
            "strategy_version_id = ?",
            (strategy_version_id,),
        )
        rejected_count = await self._count(
            "rejected_trade_logs",
            "metadata_json LIKE ? OR subject_id IN (SELECT signal_id FROM signals WHERE strategy_version_id = ?)",
            (f"%{strategy_version_id}%", strategy_version_id),
        )
        failed_fill_count = await self._failed_fill_count(strategy_version_id)
        degraded_count = await self._degraded_outcome_count([str(row["position_id"]) for row in outcome_rows])
        tokens = {str(row["token_id"]) for row in outcome_rows}
        min_sample = int(criteria.get("min_closed_trades") or criteria.get("min_forward_paper_trades") or 5)
        quality_flags: list[str] = []
        sample_warning = None
        if closed < min_sample:
            sample_warning = f"closed_trade_count {closed} below required sample {min_sample}"
            quality_flags.append("low_sample_size")
        concentration_warning = None
        if closed >= 2 and len(tokens) <= 1:
            concentration_warning = "closed outcomes are concentrated in one token"
            quality_flags.append("token_concentration")
        if degraded_count:
            quality_flags.append("degraded_outcomes_present")
        return {
            "strategy_version_id": strategy_version_id,
            "closed_trade_count": closed,
            "open_position_count": open_count,
            "rejected_count": rejected_count,
            "no_trade_count": no_trade_count,
            "failed_fill_count": failed_fill_count,
            "gross_pnl": gross_pnl,
            "net_pnl": net_pnl,
            "expectancy": expectancy,
            "win_rate": win_rate,
            "profit_factor": profit_factor,
            "average_win": average_win,
            "average_loss": average_loss,
            "max_drawdown": max_drawdown,
            "degraded_outcome_count": degraded_count,
            "sample_size_warning": sample_warning,
            "concentration_warning": concentration_warning,
            "quality_flags": quality_flags,
            "canonical_source": "trade_outcomes",
            "legacy_sources_excluded": ["paper_trades", "FIFO PnL", "wallet_scores"],
        }

    def _evaluate_decision(
        self, metrics: dict[str, Any], criteria: dict[str, Any]
    ) -> tuple[str, str, list[str], list[str]]:
        passed: list[str] = []
        failed: list[str] = []
        closed = int(metrics["closed_trade_count"])
        min_sample = int(criteria.get("min_closed_trades") or criteria.get("min_forward_paper_trades") or 5)
        if closed < min_sample:
            failed.append("min_closed_trades")
            return "insufficient_data", "Insufficient deterministic closed paper trades.", passed, failed
        if int(metrics["degraded_outcome_count"]) > int(criteria.get("max_degraded_outcomes", 0)):
            failed.append("max_degraded_outcomes")
            return "insufficient_data", "Outcome quality is too degraded for a promotion decision.", passed, failed
        min_expectancy = criteria.get("min_net_expectancy")
        if min_expectancy is not None:
            if metrics["expectancy"] is not None and float(metrics["expectancy"]) >= float(min_expectancy):
                passed.append("min_net_expectancy")
            else:
                failed.append("min_net_expectancy")
        min_pnl = criteria.get("min_cumulative_net_pnl")
        if min_pnl is not None:
            if float(metrics["net_pnl"]) >= float(min_pnl):
                passed.append("min_cumulative_net_pnl")
            else:
                failed.append("min_cumulative_net_pnl")
        max_drawdown = criteria.get("max_drawdown")
        if max_drawdown is not None:
            if abs(float(metrics["max_drawdown"] or 0)) <= abs(float(max_drawdown)):
                passed.append("max_drawdown")
            else:
                failed.append("max_drawdown")
        kill_below = criteria.get("kill_net_pnl_below")
        if kill_below is not None and float(metrics["net_pnl"]) <= float(kill_below):
            failed.append("kill_net_pnl_below")
            return "kill", "Deterministic metrics breached kill criteria.", passed, failed
        if failed:
            return "keep_testing", "Deterministic metrics do not satisfy promotion criteria.", passed, failed
        return "promote", "Deterministic metrics satisfy configured promotion criteria.", passed, failed

    async def _criteria(self, promotion_criteria_snapshot_id: str | None) -> dict[str, Any]:
        if not promotion_criteria_snapshot_id:
            return {}
        row = await self.database.fetchone(
            "SELECT criteria_json FROM promotion_criteria_snapshots WHERE promotion_criteria_snapshot_id = ?",
            (promotion_criteria_snapshot_id,),
        )
        return parse_json_object(row["criteria_json"]) if row else {}

    async def _require_row(self, table: str, key: str, value: str) -> dict[str, Any]:
        row = await self.database.fetchone(f"SELECT * FROM {table} WHERE {key} = ?", (value,))
        if not row:
            raise ValueError(f"{table}.{key} not found: {value}")
        return row

    async def _count(self, table: str, where: str, params: tuple[Any, ...]) -> int:
        row = await self.database.fetchone(f"SELECT COUNT(*) AS count FROM {table} WHERE {where}", params)
        return int(row["count"]) if row else 0

    async def _failed_fill_count(self, strategy_version_id: str) -> int:
        row = await self.database.fetchone(
            """
            SELECT COUNT(*) AS count
            FROM paper_fills pf
            JOIN paper_orders po ON po.paper_order_id = pf.paper_order_id
            WHERE po.strategy_version_id = ?
              AND pf.failed_fill_reason IS NOT NULL
            """,
            (strategy_version_id,),
        )
        return int(row["count"]) if row else 0

    async def _degraded_outcome_count(self, position_ids: list[str]) -> int:
        if not position_ids:
            return 0
        placeholders = ",".join("?" for _ in position_ids)
        rows = await self.database.fetchall(
            f"""
            SELECT COUNT(DISTINCT pp.position_id) AS count
            FROM paper_position_events ppe
            JOIN paper_positions pp ON pp.position_id = ppe.position_id
            WHERE pp.position_id IN ({placeholders})
              AND ppe.payload_json LIKE '%degraded%'
            """,
            tuple(position_ids),
        )
        return int(rows[0]["count"]) if rows else 0

    def _max_drawdown(self, values: list[float]) -> float:
        peak = 0.0
        cumulative = 0.0
        max_drawdown = 0.0
        for value in values:
            cumulative += value
            peak = max(peak, cumulative)
            max_drawdown = min(max_drawdown, cumulative - peak)
        return max_drawdown
