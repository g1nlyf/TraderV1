from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response

from walletscarper.db import db

try:
    from walletscarper.stage2.config import load_stage2_settings
    from walletscarper.stage2.db import MIGRATIONS, Stage2Database
    from walletscarper.stage2.hermes_integration import project_health_check
except Exception:  # pragma: no cover - dashboard degrades if Stage 2 import fails
    load_stage2_settings = None
    Stage2Database = None
    MIGRATIONS = []
    project_health_check = None


app = FastAPI(title="TraderV1 Operator Dashboard")

APP_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = Path(__file__).resolve().parents[3]
REPORTS_ROOT = REPO_ROOT / "docs" / "implementation-progress" / "reports"
KNOWN_REPORTS = {
    "validation-summary.md",
    "final-acceptance-report.md",
    "final-acceptance-report.json",
    "shadow-mode-gap-report.md",
    "shadow-mode-gap-report.json",
    "shadow-readiness-gap-closure-report.md",
    "shadow-readiness-gap-closure-report.json",
    "dust-sol-calibration-note.md",
}


_START_TIME = __import__("time").time()


@app.on_event("startup")
async def startup() -> None:
    await db.init()


@app.get("/health")
async def health() -> JSONResponse:
    """Liveness / readiness probe. Returns 200 if DB is reachable."""
    import time

    try:
        row = await db.fetchone("SELECT COUNT(*) AS n FROM raw_trades")
        db_ok = row is not None
    except Exception:
        db_ok = False
    uptime = int(time.time() - _START_TIME)
    status_code = 200 if db_ok else 503
    return JSONResponse(
        {"status": "ok" if db_ok else "degraded", "db": db_ok, "uptime_seconds": uptime},
        status_code=status_code,
    )


@app.get("/metrics", response_class=Response)
async def metrics() -> Response:
    """Prometheus text-format metrics endpoint.

    Exposes key trading system counters without requiring prometheus_client.
    Scrape with Prometheus or Grafana agent.
    """
    try:
        trades = await db.fetchone("SELECT COUNT(*) AS n FROM raw_trades") or {}
        wallets = await db.fetchone("SELECT COUNT(*) AS n FROM tracked_wallets WHERE status='active'") or {}
        tokens = await db.fetchone("SELECT COUNT(*) AS n FROM tokens") or {}
        signals = await db.fetchone("SELECT COUNT(*) AS n FROM signal_log") or {}
        paper = await db.fetchone("SELECT COUNT(*) AS n FROM paper_trades WHERE status='open'") or {}
    except Exception:
        trades = wallets = tokens = signals = paper = {}

    lines = [
        "# HELP traderv1_raw_trades_total Total raw trades collected",
        "# TYPE traderv1_raw_trades_total counter",
        f"traderv1_raw_trades_total {int(trades.get('n') or 0)}",
        "# HELP traderv1_active_wallets Active tracked wallets",
        "# TYPE traderv1_active_wallets gauge",
        f"traderv1_active_wallets {int(wallets.get('n') or 0)}",
        "# HELP traderv1_tokens_total Tokens ever discovered",
        "# TYPE traderv1_tokens_total counter",
        f"traderv1_tokens_total {int(tokens.get('n') or 0)}",
        "# HELP traderv1_signals_total Total wallet signals detected",
        "# TYPE traderv1_signals_total counter",
        f"traderv1_signals_total {int(signals.get('n') or 0)}",
        "# HELP traderv1_open_paper_trades Open paper trade positions",
        "# TYPE traderv1_open_paper_trades gauge",
        f"traderv1_open_paper_trades {int(paper.get('n') or 0)}",
        "",
    ]
    return Response("\n".join(lines), media_type="text/plain; version=0.0.4; charset=utf-8")


@app.get("/api/status")
async def api_status() -> JSONResponse:
    stats = await db.fetchone("SELECT COUNT(*) AS trades, COUNT(DISTINCT wallet) AS walletsSeen, COUNT(DISTINCT token_mint) AS tokensSeen FROM raw_trades")
    tracked = await db.fetchall("SELECT status, COUNT(*) AS count FROM tracked_wallets GROUP BY status")
    sources = await db.fetchall("SELECT source, status, confidence, last_success_at, last_error_message FROM source_health ORDER BY source")
    top = await db.fetchall(
        """
        SELECT wl.rank, wl.wallet, wl.copyability_score, wl.status, ws.realized_pnl_usd, ws.winrate,
          ws.median_holding_minutes, ws.median_buy_usd, ws.human_score, ws.bot_score, ws.unique_tokens, ws.total_trades
        FROM wallet_leaderboard wl LEFT JOIN wallet_scores ws ON ws.wallet=wl.wallet
        ORDER BY wl.rank LIMIT 25
        """
    )
    return JSONResponse({"stats": stats or {}, "tracked": tracked, "sources": sources, "leaderboard": top})


@app.get("/api/operations/status")
async def api_operations_status() -> JSONResponse:
    return JSONResponse(await _stage2_payload())


@app.get("/reports/{report_name}")
async def report_file(report_name: str) -> FileResponse:
    if report_name not in KNOWN_REPORTS:
        raise HTTPException(status_code=404, detail="Unknown report")
    path = REPORTS_ROOT / report_name
    if not path.exists():
        raise HTTPException(status_code=404, detail="Report not found")
    media_type = "application/json" if path.suffix == ".json" else "text/markdown"
    return FileResponse(path, media_type=media_type, filename=report_name)


@app.get("/", response_class=HTMLResponse)
async def index() -> str:
    return _dashboard_html()


@app.get("/favicon.ico", include_in_schema=False)
async def favicon() -> Response:
    return Response(status_code=204)


async def _stage2_payload() -> dict[str, Any]:
    if not load_stage2_settings or not Stage2Database:
        return {
            "status": "blocked",
            "generated_at": None,
            "blocker": "Stage 2 package import failed.",
            "next_actions": ["Fix Stage 2 imports before using the dashboard."],
        }

    settings = load_stage2_settings()
    database = Stage2Database(settings)
    db_exists = database.path.exists()
    tables = await _existing_tables(database) if db_exists else set()
    expected_migrations = [m.version for m in MIGRATIONS]
    applied = await database.applied_migrations() if db_exists else []
    applied_versions = [int(row["version"]) for row in applied]

    health = {}
    if project_health_check:
        try:
            health = await project_health_check(settings=settings, database=database)
        except Exception as exc:  # pragma: no cover - dashboard must remain inspectable
            health = {"database_connectivity": f"error: {exc}", "migration_status": "unknown"}

    final_report = await _latest(database, tables, "final_acceptance_reports", "generated_at")
    shadow_report = await _latest(database, tables, "shadow_mode_gap_reports", "assessed_at")
    operational_health = await _latest(database, tables, "operational_health_snapshots", "observed_at")
    invariant_summary = await _invariant_summary(database, tables, (final_report or {}).get("acceptance_run_id"))
    paper_summary = await _paper_summary(database, tables)
    shadow_summary = await _shadow_summary(database, tables)
    source_health = await _source_health(database, tables)
    latency = await _latency_summary(database, tables)
    route_quality = await _route_quality(database, tables)
    fill_quote = await _fill_quote(database, tables)
    quotes = await _recent_quotes(database, tables)
    leaderboard = await _strategy_leaderboard(database, tables)
    workers = await _worker_status(database, tables)

    release_decision = (final_report or {}).get("decision")
    shadow_status = (shadow_report or {}).get("status")
    critical = invariant_summary.get("critical_count", 0)
    status = _overall_status(db_exists, applied_versions, expected_migrations, release_decision, shadow_status, critical)

    return {
        "status": status,
        "database": {
            "path": str(settings.database_path),
            "exists": db_exists,
            "migration_status": health.get("migration_status", "missing" if not db_exists else "unknown"),
            "applied_migrations": applied_versions,
            "expected_migrations": expected_migrations,
            "connectivity": health.get("database_connectivity", "missing" if not db_exists else "unknown"),
            "feature_flags": health.get("feature_flags", {}),
        },
        "stage2_release_decision": {
            "decision": release_decision or "missing",
            "acceptance_run_result": (final_report or {}).get("acceptance_run_result"),
            "run_mode": (final_report or {}).get("run_mode"),
            "generated_at": (final_report or {}).get("generated_at"),
            "known_limitations": _loads((final_report or {}).get("known_limitations_json"), []),
        },
        "shadow_gap_status": {
            "status": shadow_status or "missing",
            "assessed_at": (shadow_report or {}).get("assessed_at"),
            "blocks_stage2_release": bool((shadow_report or {}).get("blocks_stage2_release", False)),
            "blocks_stage3_progression": bool((shadow_report or {}).get("blocks_stage3_progression", True)),
            "missing_capabilities": _loads((shadow_report or {}).get("missing_capabilities_json"), []),
        },
        "source_health": source_health,
        "quote_observations": quotes,
        "latency_summary": latency,
        "route_quality_evidence": route_quality,
        "fill_vs_quote_comparisons": fill_quote,
        "paper_trading_summary": paper_summary,
        "strategy_leaderboard": leaderboard,
        "worker_queue_status": workers,
        "invariant_violations": invariant_summary,
        "operational_health": _row_to_dict(operational_health),
        "reports": _reports(),
        "next_actions": _next_actions(status, release_decision, shadow_status, shadow_summary, db_exists),
        "boundary_confirmation": "Read-only dashboard. No live execution, credential custody, signing, route execution, or order-placement control is exposed.",
    }


async def _existing_tables(database: Any) -> set[str]:
    rows = await database.fetchall("SELECT name FROM sqlite_master WHERE type='table'")
    return {str(row["name"]) for row in rows}


async def _latest(database: Any, tables: set[str], table: str, order_column: str) -> dict[str, Any] | None:
    if table not in tables:
        return None
    return await database.fetchone(f"SELECT * FROM {table} ORDER BY {order_column} DESC, rowid DESC LIMIT 1")


async def _count(database: Any, tables: set[str], table: str, where: str = "", params: tuple[Any, ...] = ()) -> int:
    if table not in tables:
        return 0
    sql = f"SELECT COUNT(*) AS count FROM {table}"
    if where:
        sql += f" WHERE {where}"
    row = await database.fetchone(sql, params)
    return int((row or {}).get("count") or 0)


async def _source_health(database: Any, tables: set[str]) -> list[dict[str, Any]]:
    if "source_health_snapshots" not in tables:
        return []
    return await database.fetchall(
        """
        SELECT sh.*
        FROM source_health_snapshots sh
        JOIN (
          SELECT source_name, MAX(observed_at) AS observed_at
          FROM source_health_snapshots
          GROUP BY source_name
        ) latest ON latest.source_name = sh.source_name AND latest.observed_at = sh.observed_at
        ORDER BY sh.source_name
        """
    )


async def _latency_summary(database: Any, tables: set[str]) -> dict[str, Any]:
    if "source_latency_samples" not in tables:
        return {"sources": [], "sample_count": 0}
    rows = await database.fetchall(
        """
        SELECT source_name,
               COUNT(*) AS sample_count,
               AVG(total_latency_ms) AS avg_total_latency_ms,
               MAX(total_latency_ms) AS max_total_latency_ms,
               AVG(response_latency_ms) AS avg_response_latency_ms
        FROM source_latency_samples
        GROUP BY source_name
        ORDER BY source_name
        """
    )
    return {"sources": rows, "sample_count": sum(int(row["sample_count"] or 0) for row in rows)}


async def _route_quality(database: Any, tables: set[str]) -> dict[str, Any]:
    total = await _count(database, tables, "route_quality_evidence")
    sufficient = await _count(database, tables, "route_quality_evidence", "sufficient_for_shadow_comparison = 1")
    recent = []
    if "route_quality_evidence" in tables:
        recent = await database.fetchall(
            """
            SELECT route_quality_evidence_id, token_mint, pool_address, observed_at,
                   liquidity_usd, route_depth_usd, spread_bps, independent_quote_count,
                   route_quality_score, sufficient_for_shadow_comparison, insufficiency_reason
            FROM route_quality_evidence
            ORDER BY observed_at DESC, route_quality_evidence_id DESC
            LIMIT 10
            """
        )
    return {"total": total, "sufficient": sufficient, "recent": recent}


async def _fill_quote(database: Any, tables: set[str]) -> dict[str, Any]:
    if "fill_quote_comparisons" not in tables:
        return {"total": 0, "by_status": [], "recent": []}
    by_status = await database.fetchall(
        """
        SELECT status, COUNT(*) AS count
        FROM fill_quote_comparisons
        GROUP BY status
        ORDER BY status
        """
    )
    recent = await database.fetchall(
        """
        SELECT fill_quote_comparison_id, paper_fill_id, compared_at, fill_time,
               quote_observed_at, fill_price, quote_price, difference_bps,
               quote_age_seconds, status
        FROM fill_quote_comparisons
        ORDER BY compared_at DESC, fill_quote_comparison_id DESC
        LIMIT 10
        """
    )
    return {"total": sum(int(row["count"] or 0) for row in by_status), "by_status": by_status, "recent": recent}


async def _recent_quotes(database: Any, tables: set[str]) -> dict[str, Any]:
    if "quote_observations" not in tables:
        return {"total": 0, "recent": []}
    total = await _count(database, tables, "quote_observations")
    recent = await database.fetchall(
        """
        SELECT quote_observation_id, source_name, token_mint, pool_address, observed_at,
               ingested_at, quote_age_seconds, latency_ms, response_latency_ms,
               price_usd, liquidity_usd, confidence, eligible_for_shadow_comparison,
               quality_flags_json
        FROM quote_observations
        ORDER BY observed_at DESC, quote_observation_id DESC
        LIMIT 15
        """
    )
    return {"total": total, "recent": recent}


async def _paper_summary(database: Any, tables: set[str]) -> dict[str, Any]:
    outcomes = []
    if "trade_outcomes" in tables:
        outcomes = await database.fetchall("SELECT net_pnl, max_drawdown FROM trade_outcomes")
    net_pnl = sum(float(row["net_pnl"] or 0) for row in outcomes)
    return {
        "signals": await _count(database, tables, "signals"),
        "no_trade_signals": await _count(database, tables, "no_trade_signals"),
        "risk_checks": await _count(database, tables, "risk_checks"),
        "risk_vetoes": await _count(database, tables, "risk_checks", "passed = 0"),
        "paper_orders": await _count(database, tables, "paper_orders"),
        "paper_fills": await _count(database, tables, "paper_fills"),
        "failed_fills": await _count(database, tables, "paper_fills", "failed_fill_reason IS NOT NULL"),
        "open_positions": await _count(database, tables, "paper_positions", "status = 'open'"),
        "closed_outcomes": len(outcomes),
        "net_pnl": net_pnl,
        "expectancy": net_pnl / len(outcomes) if outcomes else None,
        "drawdown": min((float(row["max_drawdown"] or 0) for row in outcomes), default=0.0),
    }


async def _strategy_leaderboard(database: Any, tables: set[str]) -> list[dict[str, Any]]:
    if "strategy_metric_snapshots" not in tables:
        return []
    return await database.fetchall(
        """
        SELECT strategy_metric_snapshot_id, strategy_version_id, calculated_at,
               closed_trade_count, open_position_count, failed_fill_count,
               net_pnl, expectancy, win_rate, max_drawdown, sample_size_warning,
               degraded_outcome_count
        FROM strategy_metric_snapshots
        ORDER BY calculated_at DESC, net_pnl DESC
        LIMIT 10
        """
    )


async def _worker_status(database: Any, tables: set[str]) -> dict[str, Any]:
    jobs = []
    workers = []
    if "jobs" in tables:
        jobs = await database.fetchall(
            """
            SELECT COALESCE(worker_type, 'unassigned') AS worker_type, status, COUNT(*) AS count
            FROM jobs
            GROUP BY COALESCE(worker_type, 'unassigned'), status
            ORDER BY worker_type, status
            """
        )
    if "worker_registry" in tables:
        workers = await database.fetchall(
            """
            SELECT worker_type, status, COUNT(*) AS count
            FROM worker_registry
            GROUP BY worker_type, status
            ORDER BY worker_type, status
            """
        )
    return {"jobs_by_worker_type_and_status": jobs, "workers_by_type_and_status": workers}


async def _invariant_summary(database: Any, tables: set[str], acceptance_run_id: str | None = None) -> dict[str, Any]:
    if "invariant_violations" not in tables:
        return {
            "acceptance_run_id": acceptance_run_id,
            "scope": "latest_acceptance_run" if acceptance_run_id else "all_records",
            "total": 0,
            "critical_count": 0,
            "historical_total": 0,
            "historical_critical_count": 0,
            "by_severity": [],
            "recent": [],
        }
    params: tuple[Any, ...] = (acceptance_run_id,) if acceptance_run_id else ()
    where = "WHERE acceptance_run_id = ?" if acceptance_run_id else ""
    by_severity = await database.fetchall(
        f"""
        SELECT severity, COUNT(*) AS count
        FROM invariant_violations
        {where}
        GROUP BY severity
        ORDER BY severity
        """,
        params,
    )
    recent = await database.fetchall(
        f"""
        SELECT invariant_violation_id, invariant_name, severity, detected_at,
               description, remediation_hint, status
        FROM invariant_violations
        {where}
        ORDER BY detected_at DESC, invariant_violation_id DESC
        LIMIT 10
        """,
        params,
    )
    critical = sum(int(row["count"] or 0) for row in by_severity if row["severity"] == "critical")
    total = sum(int(row["count"] or 0) for row in by_severity)
    historical_by_severity = await database.fetchall(
        "SELECT severity, COUNT(*) AS count FROM invariant_violations GROUP BY severity ORDER BY severity"
    )
    historical_critical = sum(int(row["count"] or 0) for row in historical_by_severity if row["severity"] == "critical")
    historical_total = sum(int(row["count"] or 0) for row in historical_by_severity)
    return {
        "acceptance_run_id": acceptance_run_id,
        "scope": "latest_acceptance_run" if acceptance_run_id else "all_records",
        "total": total,
        "critical_count": critical,
        "historical_total": historical_total,
        "historical_critical_count": historical_critical,
        "by_severity": by_severity,
        "recent": recent,
    }


async def _shadow_summary(database: Any, tables: set[str]) -> dict[str, int]:
    return {
        "quote_observations": await _count(database, tables, "quote_observations"),
        "source_latency_samples": await _count(database, tables, "source_latency_samples"),
        "route_quality_evidence": await _count(database, tables, "route_quality_evidence"),
        "sufficient_route_quality_evidence": await _count(database, tables, "route_quality_evidence", "sufficient_for_shadow_comparison = 1"),
        "fill_quote_comparisons": await _count(database, tables, "fill_quote_comparisons"),
        "passed_fill_quote_comparisons": await _count(database, tables, "fill_quote_comparisons", "status = 'passed'"),
        "live_data_acceptance_windows": await _count(database, tables, "live_data_acceptance_windows"),
        "passed_live_data_acceptance_windows": await _count(database, tables, "live_data_acceptance_windows", "status = 'passed'"),
    }


def _overall_status(
    db_exists: bool,
    applied_versions: list[int],
    expected_versions: list[int],
    release_decision: str | None,
    shadow_status: str | None,
    critical_count: int,
) -> str:
    if not db_exists or set(applied_versions) != set(expected_versions):
        return "blocked"
    if critical_count:
        return "blocked"
    if shadow_status == "gap_report_required":
        return "accepted_with_gaps" if release_decision == "accepted_with_gaps" else "gap_required"
    if release_decision == "accepted_stage2_release":
        return "healthy"
    if release_decision == "accepted_with_gaps":
        return "accepted_with_gaps"
    return "degraded"


def _next_actions(
    status: str,
    release_decision: str | None,
    shadow_status: str | None,
    shadow_summary: dict[str, int],
    db_exists: bool,
) -> list[str]:
    actions: list[str] = []
    if not db_exists:
        actions.append("Run scripts\\run-migrations.bat.")
    if not release_decision:
        actions.append("Run scripts\\run-final-acceptance.bat to create a current fixture acceptance report.")
    if shadow_summary.get("quote_observations", 0) == 0:
        actions.append("Run scripts\\run-calibration-smoke.bat to verify the observation-only quote path in a temp database.")
    if shadow_status == "gap_report_required":
        actions.append("Run scripts\\run-calibration-window.bat TOKEN_MINT [POOL_ADDRESS] when a real no-key token/pool observation target is selected.")
        actions.append("Rerun scripts\\run-shadow-gap-assessment.bat after collecting observation evidence.")
    if status == "blocked":
        actions.append("Read invariant violations and stop before claiming readiness.")
    actions.append("Do not enable live execution, credential custody, signing, route execution, or real order placement.")
    return actions


def _reports() -> list[dict[str, str]]:
    reports = []
    for name in sorted(KNOWN_REPORTS):
        path = REPORTS_ROOT / name
        reports.append({"name": name, "href": f"/reports/{name}", "status": "available" if path.exists() else "missing"})
    return reports


def _loads(raw: Any, default: Any) -> Any:
    if not raw:
        return default
    if isinstance(raw, (list, dict)):
        return raw
    try:
        return json.loads(str(raw))
    except json.JSONDecodeError:
        return default


def _row_to_dict(row: dict[str, Any] | None) -> dict[str, Any] | None:
    return dict(row) if row else None


def _dashboard_html() -> str:
    return """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>TraderV1 Operator Dashboard</title>
  <style>
    :root {
      color-scheme: dark light;
      --bg: #111312;
      --panel: #181b1a;
      --panel-2: #202422;
      --line: #303632;
      --text: #edf1ee;
      --muted: #9da8a1;
      --good: #7bc99a;
      --warn: #e5b567;
      --bad: #e06c75;
      --info: #74b3ce;
      --ink: #0d0f0e;
      font-family: "Aptos", "Segoe UI", sans-serif;
    }
    @media (prefers-color-scheme: light) {
      :root {
        --bg: #f4f5f2;
        --panel: #ffffff;
        --panel-2: #e9ece7;
        --line: #d2d8d0;
        --text: #171b18;
        --muted: #5f6b63;
        --ink: #ffffff;
      }
    }
    * { box-sizing: border-box; }
    body { margin: 0; background: var(--bg); color: var(--text); font-size: 14px; letter-spacing: 0; }
    header { position: sticky; top: 0; z-index: 3; display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 14px 20px; background: color-mix(in srgb, var(--bg) 92%, transparent); border-bottom: 1px solid var(--line); backdrop-filter: blur(8px); }
    h1 { margin: 0; font-size: 18px; font-weight: 700; }
    main { max-width: 1440px; margin: 0 auto; padding: 18px 20px 32px; }
    h2 { margin: 0 0 10px; font-size: 14px; text-transform: uppercase; color: var(--muted); font-weight: 700; }
    .top { display: grid; grid-template-columns: 1.2fr .8fr; gap: 14px; margin-bottom: 14px; }
    .grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; }
    .wide { grid-column: span 2; }
    section, .tile { background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 14px; min-width: 0; }
    .tile { min-height: 104px; }
    .metric { font-size: 28px; font-weight: 760; margin-top: 6px; }
    .sub { color: var(--muted); font-size: 12px; margin-top: 4px; }
    .pill { display: inline-flex; align-items: center; min-height: 24px; padding: 3px 9px; border-radius: 999px; border: 1px solid var(--line); background: var(--panel-2); color: var(--muted); font-size: 12px; font-weight: 700; white-space: nowrap; }
    .healthy, .passed, .shadow_ready { color: var(--good); border-color: color-mix(in srgb, var(--good) 45%, var(--line)); }
    .degraded, .accepted_with_gaps, .gap_required, .gap_report_required, .warning { color: var(--warn); border-color: color-mix(in srgb, var(--warn) 45%, var(--line)); }
    .blocked, .failed, .rejected_blocked, .unavailable, .critical { color: var(--bad); border-color: color-mix(in srgb, var(--bad) 45%, var(--line)); }
    .missing, .unknown { color: var(--info); border-color: color-mix(in srgb, var(--info) 45%, var(--line)); }
    .warnline { border-left: 4px solid var(--warn); background: var(--panel-2); padding: 10px 12px; margin: 8px 0; border-radius: 6px; }
    table { width: 100%; border-collapse: collapse; table-layout: fixed; }
    th, td { padding: 8px 6px; border-bottom: 1px solid var(--line); text-align: left; vertical-align: top; font-size: 12px; overflow-wrap: anywhere; }
    th { color: var(--muted); font-weight: 700; }
    a { color: var(--info); text-decoration: none; }
    a:hover { text-decoration: underline; }
    ul { margin: 8px 0 0; padding-left: 18px; }
    li { margin: 5px 0; }
    .mono { font-family: "Cascadia Mono", Consolas, monospace; font-size: 12px; }
    .empty { color: var(--muted); background: var(--panel-2); border: 1px dashed var(--line); border-radius: 7px; padding: 10px; }
    @media (max-width: 980px) {
      header { align-items: flex-start; flex-direction: column; }
      .top, .grid { grid-template-columns: 1fr; }
      .wide { grid-column: auto; }
      main { padding: 12px; }
      table { table-layout: auto; }
    }
  </style>
</head>
<body>
  <header>
    <h1>TraderV1 Operator Dashboard</h1>
    <div id="headerStatus" class="pill unknown">loading</div>
  </header>
  <main>
    <div class="top">
      <section>
        <h2>System Status</h2>
        <div id="warnings"></div>
        <div class="grid" style="margin-top:12px">
          <div class="tile"><div>Stage 2 decision</div><div class="metric" id="decision">-</div><div class="sub" id="decisionSub"></div></div>
          <div class="tile"><div>Shadow status</div><div class="metric" id="shadow">-</div><div class="sub" id="shadowSub"></div></div>
          <div class="tile"><div>Database</div><div class="metric" id="dbStatus">-</div><div class="sub mono" id="dbPath"></div></div>
        </div>
      </section>
      <section>
        <h2>Next Operator Actions</h2>
        <ul id="actions"></ul>
      </section>
    </div>
    <div class="grid">
      <section><h2>Source Health</h2><div id="sources"></div></section>
      <section><h2>Quote Observations</h2><div id="quotes"></div></section>
      <section><h2>Latency Summary</h2><div id="latency"></div></section>
      <section><h2>Route Quality Evidence</h2><div id="routes"></div></section>
      <section><h2>Fill-vs-Quote Comparisons</h2><div id="comparisons"></div></section>
      <section><h2>Paper Trading Summary</h2><div id="paper"></div></section>
      <section class="wide"><h2>Strategy Leaderboard</h2><div id="leaderboard"></div></section>
      <section><h2>Worker / Queue Status</h2><div id="workers"></div></section>
      <section class="wide"><h2>Invariant Violations</h2><div id="invariants"></div></section>
      <section><h2>Reports / Downloads</h2><div id="reports"></div></section>
    </div>
  </main>
  <script>
    const fmt = (v) => v === null || v === undefined || v === "" ? "-" : String(v);
    const pill = (v) => `<span class="pill ${String(v || 'unknown')}">${fmt(v)}</span>`;
    const setPill = (id, value) => {
      const element = document.getElementById(id);
      element.className = `pill ${String(value || 'unknown')}`;
      element.textContent = fmt(value);
    };
    const num = (v, digits = 2) => v === null || v === undefined ? "-" : Number(v).toFixed(digits);
    const empty = (text) => `<div class="empty">${text}</div>`;
    const table = (headers, rows) => {
      if (!rows || !rows.length) return empty("No data recorded. Run the relevant operator script listed above.");
      return `<table><thead><tr>${headers.map(h => `<th>${h}</th>`).join("")}</tr></thead><tbody>${rows.join("")}</tbody></table>`;
    };

    async function load() {
      const data = await fetch("/api/operations/status").then(r => r.json());
      setPill("headerStatus", data.status);
      document.getElementById("decision").innerHTML = pill(data.stage2_release_decision.decision);
      document.getElementById("decisionSub").textContent = `${fmt(data.stage2_release_decision.run_mode)} / ${fmt(data.stage2_release_decision.generated_at)}`;
      document.getElementById("shadow").innerHTML = pill(data.shadow_gap_status.status);
      document.getElementById("shadowSub").textContent = data.shadow_gap_status.blocks_stage3_progression ? "Blocks Stage 3 progression" : "No Stage 3 block recorded";
      document.getElementById("dbStatus").innerHTML = pill(data.database.migration_status);
      document.getElementById("dbPath").textContent = data.database.path;
      document.getElementById("warnings").innerHTML = [
        "Read-only dashboard. No live trading controls exist here.",
        data.shadow_gap_status.blocks_stage3_progression ? "Stage 3 shadow readiness is not accepted." : "",
        data.invariant_violations.critical_count ? "Latest acceptance run has critical invariant violations. Stop and inspect reports." : "",
        !data.invariant_violations.critical_count && data.invariant_violations.historical_critical_count ? "Historical invariant findings exist from older runs; latest acceptance is clean." : ""
      ].filter(Boolean).map(x => `<div class="warnline">${x}</div>`).join("");
      document.getElementById("actions").innerHTML = data.next_actions.map(a => `<li>${a}</li>`).join("");

      document.getElementById("sources").innerHTML = table(["source","status","latency","reason"], data.source_health.map(s => `<tr><td>${fmt(s.source_name)}</td><td>${pill(s.status)}</td><td>${num(s.latency_ms,0)} ms</td><td>${fmt(s.degradation_reason)}</td></tr>`));
      document.getElementById("quotes").innerHTML = `<div class="metric">${data.quote_observations.total}</div><div class="sub">total quote observations</div>` +
        table(["source","token","age","price","eligible"], data.quote_observations.recent.map(q => `<tr><td>${fmt(q.source_name)}</td><td class="mono">${fmt(q.token_mint)}</td><td>${num(q.quote_age_seconds,1)}s</td><td>${num(q.price_usd,8)}</td><td>${pill(q.eligible_for_shadow_comparison ? "healthy" : "gap_required")}</td></tr>`));
      document.getElementById("latency").innerHTML = `<div class="metric">${data.latency_summary.sample_count}</div><div class="sub">latency samples</div>` +
        table(["source","samples","avg total","max total"], data.latency_summary.sources.map(l => `<tr><td>${fmt(l.source_name)}</td><td>${fmt(l.sample_count)}</td><td>${num(l.avg_total_latency_ms,0)} ms</td><td>${num(l.max_total_latency_ms,0)} ms</td></tr>`));
      document.getElementById("routes").innerHTML = `<div class="metric">${data.route_quality_evidence.sufficient} / ${data.route_quality_evidence.total}</div><div class="sub">sufficient / total</div>` +
        table(["token","depth","spread","quotes","status"], data.route_quality_evidence.recent.map(r => `<tr><td class="mono">${fmt(r.token_mint)}</td><td>${num(r.route_depth_usd,0)}</td><td>${num(r.spread_bps,1)} bps</td><td>${fmt(r.independent_quote_count)}</td><td>${pill(r.sufficient_for_shadow_comparison ? "healthy" : "gap_required")}</td></tr>`));
      document.getElementById("comparisons").innerHTML = table(["status","count"], data.fill_vs_quote_comparisons.by_status.map(c => `<tr><td>${pill(c.status)}</td><td>${fmt(c.count)}</td></tr>`));
      const p = data.paper_trading_summary;
      document.getElementById("paper").innerHTML = `<table><tbody>
        <tr><th>Signals</th><td>${p.signals}</td></tr><tr><th>Orders</th><td>${p.paper_orders}</td></tr>
        <tr><th>Fills / failed</th><td>${p.paper_fills} / ${p.failed_fills}</td></tr><tr><th>Closed outcomes</th><td>${p.closed_outcomes}</td></tr>
        <tr><th>Net P&L</th><td>${num(p.net_pnl,4)} fixture/paper only</td></tr><tr><th>Risk vetoes</th><td>${p.risk_vetoes}</td></tr>
      </tbody></table>`;
      document.getElementById("leaderboard").innerHTML = table(["strategy","closed","net","expectancy","warning"], data.strategy_leaderboard.map(s => `<tr><td class="mono">${fmt(s.strategy_version_id)}</td><td>${s.closed_trade_count}</td><td>${num(s.net_pnl,4)}</td><td>${num(s.expectancy,4)}</td><td>${fmt(s.sample_size_warning)}</td></tr>`));
      document.getElementById("workers").innerHTML = table(["worker","status","count"], data.worker_queue_status.jobs_by_worker_type_and_status.map(w => `<tr><td>${fmt(w.worker_type)}</td><td>${pill(w.status)}</td><td>${w.count}</td></tr>`));
      const historicalNote = data.invariant_violations.historical_total > data.invariant_violations.total
        ? `<div class="sub">${data.invariant_violations.historical_critical_count} historical critical across older runs</div>`
        : "";
      document.getElementById("invariants").innerHTML = `<div class="metric">${data.invariant_violations.critical_count} current critical</div>${historicalNote}` +
        table(["severity","name","status","hint"], data.invariant_violations.recent.map(i => `<tr><td>${pill(i.severity)}</td><td>${fmt(i.invariant_name)}</td><td>${fmt(i.status)}</td><td>${fmt(i.remediation_hint)}</td></tr>`));
      document.getElementById("reports").innerHTML = data.reports.map(r => `<div>${pill(r.status)} <a href="${r.href}" target="_blank">${r.name}</a></div>`).join("");
    }
    load().catch(err => {
      document.getElementById("warnings").innerHTML = `<div class="warnline">Dashboard load failed: ${err}</div>`;
    });
    setInterval(load, 15000);
  </script>
</body>
</html>
"""
