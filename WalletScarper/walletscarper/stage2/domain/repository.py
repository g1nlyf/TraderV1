from __future__ import annotations

from datetime import datetime
from typing import Any

from walletscarper.stage2.clock import Clock, SystemClock, isoformat_utc
from walletscarper.stage2.db import Stage2Database
from walletscarper.stage2.db.json import dumps_json
from walletscarper.stage2.ids import new_id


class DomainRepository:
    def __init__(self, database: Stage2Database, clock: Clock | None = None):
        self.database = database
        self.clock = clock or SystemClock()

    async def create_strategy_version(
        self,
        *,
        strategy_config_snapshot_id: str,
        parent_strategy_version_id: str | None = None,
        rules: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        agents: list[str] | None = None,
        status: str = "experimental",
        mutation_proposal_id: str | None = None,
    ) -> str:
        strategy_version_id = new_id("strategy_version")
        await self.database.execute(
            """
            INSERT INTO strategy_versions(
              strategy_version_id, strategy_config_snapshot_id, parent_strategy_version_id,
              mutation_proposal_id, rules_json, params_json, agents_json, created_at, status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                strategy_version_id,
                strategy_config_snapshot_id,
                parent_strategy_version_id,
                mutation_proposal_id,
                dumps_json(rules or {}),
                dumps_json(params or {}),
                dumps_json(agents or []),
                isoformat_utc(self.clock.now()),
                status,
            ),
        )
        return strategy_version_id

    async def create_signal(
        self,
        *,
        token_id: str,
        strategy_version_id: str,
        strategy_config_snapshot_id: str,
        data_as_of: datetime | None = None,
        promotion_criteria_snapshot_id: str | None = None,
        source_refs: list[str] | None = None,
        confidence: str = "unknown",
        thesis_ref: str | None = None,
        invalidation_condition: str = "not specified",
        expected_holding_time: str = "not specified",
        estimated_risk: dict[str, Any] | None = None,
        estimated_slippage: float | None = None,
        status: str = "candidate",
    ) -> str:
        now = self.clock.now()
        signal_id = new_id("signal")
        await self.database.execute(
            """
            INSERT INTO signals(
              signal_id, created_at, data_as_of, token_id, strategy_version_id,
              strategy_config_snapshot_id, promotion_criteria_snapshot_id, source_refs_json,
              confidence, thesis_ref, invalidation_condition, expected_holding_time,
              estimated_risk_json, estimated_slippage, status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                signal_id,
                isoformat_utc(now),
                isoformat_utc(data_as_of or now),
                token_id,
                strategy_version_id,
                strategy_config_snapshot_id,
                promotion_criteria_snapshot_id,
                dumps_json(source_refs or []),
                confidence,
                thesis_ref,
                invalidation_condition,
                expected_holding_time,
                dumps_json(estimated_risk or {}),
                estimated_slippage,
                status,
            ),
        )
        return signal_id

    async def create_trade_thesis(
        self,
        *,
        signal_id: str,
        entry_reason: str,
        exit_plan: str,
        expected_holding_time: str,
        proof_wrong: str,
        context_snapshot_id: str | None = None,
    ) -> str:
        thesis_id = new_id("thesis")
        await self.database.execute(
            """
            INSERT INTO trade_theses(
              thesis_id, signal_id, entry_reason, exit_plan, expected_holding_time,
              proof_wrong, context_snapshot_id, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                thesis_id,
                signal_id,
                entry_reason,
                exit_plan,
                expected_holding_time,
                proof_wrong,
                context_snapshot_id,
                isoformat_utc(self.clock.now()),
            ),
        )
        return thesis_id

    async def create_risk_check(
        self,
        *,
        check_scope: str,
        subject_type: str,
        subject_id: str,
        risk_limit_snapshot_id: str,
        config_snapshot_id: str,
        passed: bool,
        data_as_of: datetime | None = None,
        market_snapshot_id: str | None = None,
        veto_reason: str | None = None,
        warnings: list[str] | None = None,
        created_by_service: str = "risk_service",
    ) -> str:
        now = self.clock.now()
        risk_check_id = new_id("risk_check")
        await self.database.execute(
            """
            INSERT INTO risk_checks(
              risk_check_id, check_scope, subject_type, subject_id, market_snapshot_id,
              risk_limit_snapshot_id, config_snapshot_id, data_as_of, passed, veto_reason,
              warnings_json, created_at, created_by_service
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                risk_check_id,
                check_scope,
                subject_type,
                subject_id,
                market_snapshot_id,
                risk_limit_snapshot_id,
                config_snapshot_id,
                isoformat_utc(data_as_of or now),
                1 if passed else 0,
                veto_reason,
                dumps_json(warnings or []),
                isoformat_utc(now),
                created_by_service,
            ),
        )
        return risk_check_id

    async def get_signal(self, signal_id: str) -> dict[str, Any] | None:
        return await self.database.fetchone("SELECT * FROM signals WHERE signal_id = ?", (signal_id,))

    async def get_trade_thesis_for_signal(self, signal_id: str) -> dict[str, Any] | None:
        return await self.database.fetchone("SELECT * FROM trade_theses WHERE signal_id = ?", (signal_id,))

    async def get_risk_check(self, risk_check_id: str) -> dict[str, Any] | None:
        return await self.database.fetchone("SELECT * FROM risk_checks WHERE risk_check_id = ?", (risk_check_id,))
