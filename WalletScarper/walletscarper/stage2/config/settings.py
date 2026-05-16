from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


AppendOnlyMode = Literal["strict", "application"]


class Stage2Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="STAGE2_",
        extra="ignore",
    )

    environment: str = "local"
    database_path: Path = Path("data/stage2_foundation.sqlite3")
    app_version: str = "stage2-sprint1"
    build_info: dict[str, Any] = Field(default_factory=dict)
    feature_flags: dict[str, bool] = Field(
        default_factory=lambda: {
            "hermes_project_health_check": True,
            "trading_workflows_enabled": False,
            "live_execution_enabled": False,
        }
    )
    hermes_smoke_test_enabled: bool = True
    job_lease_seconds: int = 60
    append_only_enforcement_mode: AppendOnlyMode = "strict"

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.database_path}"

    @property
    def is_test(self) -> bool:
        return self.environment.lower() == "test"

    def ensure_dirs(self) -> None:
        if self.database_path != Path(":memory:"):
            self.database_path.parent.mkdir(parents=True, exist_ok=True)


def load_stage2_settings(
    *,
    environment: str | None = None,
    database_path: str | Path | None = None,
    app_version: str | None = None,
    feature_flags: dict[str, bool] | None = None,
    hermes_smoke_test_enabled: bool | None = None,
    job_lease_seconds: int | None = None,
    append_only_enforcement_mode: AppendOnlyMode | None = None,
) -> Stage2Settings:
    overrides: dict[str, Any] = {}
    if environment is not None:
        overrides["environment"] = environment
    if database_path is not None:
        overrides["database_path"] = Path(database_path)
    if app_version is not None:
        overrides["app_version"] = app_version
    if feature_flags is not None:
        overrides["feature_flags"] = feature_flags
    if hermes_smoke_test_enabled is not None:
        overrides["hermes_smoke_test_enabled"] = hermes_smoke_test_enabled
    if job_lease_seconds is not None:
        overrides["job_lease_seconds"] = job_lease_seconds
    if append_only_enforcement_mode is not None:
        overrides["append_only_enforcement_mode"] = append_only_enforcement_mode
    return Stage2Settings(**overrides)
