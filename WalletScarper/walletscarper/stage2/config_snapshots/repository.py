from __future__ import annotations

import hashlib
from typing import Any

from walletscarper.stage2.clock import Clock, SystemClock, isoformat_utc
from walletscarper.stage2.config import Stage2Settings
from walletscarper.stage2.db import Stage2Database
from walletscarper.stage2.db.json import dumps_json
from walletscarper.stage2.ids import new_id


def content_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(dumps_json(payload).encode("utf-8")).hexdigest()


class ConfigSnapshotRepository:
    def __init__(self, database: Stage2Database, clock: Clock | None = None):
        self.database = database
        self.clock = clock or SystemClock()

    async def create_config_snapshot(
        self,
        *,
        source: str,
        settings: Stage2Settings | dict[str, Any],
        environment: str | None = None,
        app_version: str | None = None,
        build_info: dict[str, Any] | None = None,
    ) -> str:
        if isinstance(settings, Stage2Settings):
            settings_payload = settings.model_dump(mode="json")
            environment = environment or settings.environment
            app_version = app_version or settings.app_version
            build_info = build_info or settings.build_info
        else:
            settings_payload = settings
        payload = {
            "source": source,
            "environment": environment or "unknown",
            "app_version": app_version or "unknown",
            "settings": settings_payload,
            "build_info": build_info or {},
        }
        snapshot_id = new_id("config_snapshot")
        await self.database.execute(
            """
            INSERT INTO config_snapshots(
              config_snapshot_id, created_at, source, content_hash, environment,
              app_version, settings_json, build_info_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                snapshot_id,
                isoformat_utc(self.clock.now()),
                source,
                content_hash(payload),
                payload["environment"],
                payload["app_version"],
                dumps_json(settings_payload),
                dumps_json(build_info or {}),
            ),
        )
        return snapshot_id

    async def create_risk_limit_snapshot(
        self,
        *,
        limits: dict[str, Any],
        source: str = "stage2_sprint1_seed",
        config_snapshot_id: str | None = None,
    ) -> str:
        snapshot_id = new_id("risk_limit_snapshot")
        payload = {"config_snapshot_id": config_snapshot_id, "source": source, "limits": limits}
        await self.database.execute(
            """
            INSERT INTO risk_limit_snapshots(
              risk_limit_snapshot_id, config_snapshot_id, created_at, source, content_hash, limits_json
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                snapshot_id,
                config_snapshot_id,
                isoformat_utc(self.clock.now()),
                source,
                content_hash(payload),
                dumps_json(limits),
            ),
        )
        return snapshot_id

    async def create_strategy_config_snapshot(
        self,
        *,
        strategy_name: str,
        strategy_version_label: str,
        config_snapshot_id: str | None = None,
        weights: dict[str, Any] | None = None,
        thresholds: dict[str, Any] | None = None,
        signal_rules: dict[str, Any] | None = None,
        exit_rules: dict[str, Any] | None = None,
        no_trade_rules: dict[str, Any] | None = None,
    ) -> str:
        snapshot_id = new_id("strategy_config_snapshot")
        payload = {
            "config_snapshot_id": config_snapshot_id,
            "strategy_name": strategy_name,
            "strategy_version_label": strategy_version_label,
            "weights": weights or {},
            "thresholds": thresholds or {},
            "signal_rules": signal_rules or {},
            "exit_rules": exit_rules or {},
            "no_trade_rules": no_trade_rules or {},
        }
        await self.database.execute(
            """
            INSERT INTO strategy_config_snapshots(
              strategy_config_snapshot_id, config_snapshot_id, strategy_name,
              strategy_version_label, created_at, content_hash, weights_json,
              thresholds_json, signal_rules_json, exit_rules_json, no_trade_rules_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                snapshot_id,
                config_snapshot_id,
                strategy_name,
                strategy_version_label,
                isoformat_utc(self.clock.now()),
                content_hash(payload),
                dumps_json(weights or {}),
                dumps_json(thresholds or {}),
                dumps_json(signal_rules or {}),
                dumps_json(exit_rules or {}),
                dumps_json(no_trade_rules or {}),
            ),
        )
        return snapshot_id

    async def create_promotion_criteria_snapshot(
        self,
        *,
        criteria: dict[str, Any],
        source: str = "stage2_sprint1_seed",
        config_snapshot_id: str | None = None,
    ) -> str:
        snapshot_id = new_id("promotion_criteria_snapshot")
        payload = {"config_snapshot_id": config_snapshot_id, "source": source, "criteria": criteria}
        await self.database.execute(
            """
            INSERT INTO promotion_criteria_snapshots(
              promotion_criteria_snapshot_id, config_snapshot_id, created_at,
              source, content_hash, criteria_json
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                snapshot_id,
                config_snapshot_id,
                isoformat_utc(self.clock.now()),
                source,
                content_hash(payload),
                dumps_json(criteria),
            ),
        )
        return snapshot_id

    async def create_acceptance_run(
        self,
        *,
        config_snapshot_id: str,
        risk_limit_snapshot_id: str | None = None,
        promotion_criteria_snapshot_id: str | None = None,
        result: str = "pending",
    ) -> str:
        run_id = new_id("acceptance_run")
        await self.database.execute(
            """
            INSERT INTO acceptance_runs(
              acceptance_run_id, config_snapshot_id, risk_limit_snapshot_id,
              promotion_criteria_snapshot_id, created_at, result
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                config_snapshot_id,
                risk_limit_snapshot_id,
                promotion_criteria_snapshot_id,
                isoformat_utc(self.clock.now()),
                result,
            ),
        )
        return run_id
