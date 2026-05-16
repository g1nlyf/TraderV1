from __future__ import annotations

from typing import Any

from walletscarper.stage2.clock import Clock, SystemClock, isoformat_utc
from walletscarper.stage2.config import Stage2Settings, load_stage2_settings
from walletscarper.stage2.db import MIGRATIONS, Stage2Database


async def project_health_check(
    *,
    settings: Stage2Settings | None = None,
    database: Stage2Database | None = None,
    clock: Clock | None = None,
) -> dict[str, Any]:
    """Read-only project.health_check tool boundary for Hermes smoke testing."""

    resolved_settings = settings or load_stage2_settings()
    resolved_database = database or Stage2Database(resolved_settings)
    resolved_clock = clock or SystemClock()
    applied = await resolved_database.applied_migrations()
    applied_versions = {int(row["version"]) for row in applied}
    expected_versions = {migration.version for migration in MIGRATIONS}
    if not resolved_database.path.exists():
        connectivity = "missing"
    else:
        try:
            await resolved_database.fetchone("SELECT 1 AS ok")
            connectivity = "ok"
        except Exception as exc:
            connectivity = f"error: {exc}"
    return {
        "tool": "project.health_check",
        "app_version": resolved_settings.app_version,
        "environment": resolved_settings.environment,
        "database_path": str(resolved_settings.database_path),
        "database_connectivity": connectivity,
        "migration_status": "current" if applied_versions == expected_versions else "pending",
        "applied_migrations": applied,
        "current_time": isoformat_utc(resolved_clock.now()),
        "feature_flags": resolved_settings.feature_flags,
        "hermes_smoke_test_enabled": resolved_settings.hermes_smoke_test_enabled,
    }
