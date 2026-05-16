from __future__ import annotations

import json
from typing import Any


DEFAULT_PARALLELISM_LIMITS: dict[str, int] = {
    "max_active_token_monitoring_sessions": 5,
    "max_active_wallet_cluster_sessions": 3,
    "max_active_strategy_experiments": 2,
    "max_active_browser_research_jobs": 2,
    "max_concurrent_worker_leases": 4,
    "position_monitoring_priority": 10,
    "strategy_experiment_priority": 40,
    "wallet_cluster_monitoring_priority": 70,
    "token_monitoring_priority": 100,
}


def parse_json_object(value: Any, default: dict[str, Any] | None = None) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not value:
        return dict(default or {})
    try:
        parsed = json.loads(str(value))
    except json.JSONDecodeError:
        return dict(default or {})
    return parsed if isinstance(parsed, dict) else dict(default or {})


def parse_json_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if not value:
        return []
    try:
        parsed = json.loads(str(value))
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []

