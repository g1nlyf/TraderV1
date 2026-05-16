from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

import typer
import uvicorn
from rich.console import Console

from walletscarper.config import settings
from walletscarper.db import db
from walletscarper.logging_utils import setup_logging
from walletscarper.scheduler import WalletScarperScheduler
from walletscarper.services.backfill import BackfillService
from walletscarper.services.pipeline import Pipeline
from walletscarper.services.scoring import ScoringService
from walletscarper.services.telegram import TelegramService
from walletscarper.sources.bitquery_corecast import BitqueryCoreCastSource

try:
    from walletscarper.stage2.config import load_stage2_settings
    from walletscarper.stage2.db import Stage2Database
    from walletscarper.stage2.evaluation import DeterministicEvaluationService
    from walletscarper.stage2.hermes_integration import project_health_check, run_v2_tool
    from walletscarper.stage2.orchestrator.smoke import run_orchestrator_smoke
    from walletscarper.stage2.reports import Sprint4ReportService
    from walletscarper.stage2.acceptance import AcceptanceRunService, render_acceptance_report
    from walletscarper.stage2.shadow_readiness import (
        FillQuoteComparisonService,
        LiveDataAcceptanceWindowService,
        QuoteObservationService,
        RouteQualityService,
    )
    from walletscarper.stage2.sources import SourceHealthService
except Exception:  # pragma: no cover
    load_stage2_settings = None
    Stage2Database = None
    DeterministicEvaluationService = None
    project_health_check = None
    run_v2_tool = None
    run_orchestrator_smoke = None
    Sprint4ReportService = None
    AcceptanceRunService = None
    render_acceptance_report = None
    FillQuoteComparisonService = None
    LiveDataAcceptanceWindowService = None
    QuoteObservationService = None
    RouteQualityService = None
    SourceHealthService = None

app = typer.Typer(no_args_is_help=True, rich_markup_mode=None, pretty_exceptions_show_locals=False)
console = Console()


@app.command("smoke-test")
def smoke_test() -> None:
    setup_logging(settings.log_level)

    async def _run() -> None:
        settings.ensure_dirs()
        await db.init()
        console.print("[bold green]WalletScarper smoke test OK[/bold green]")
        console.print(f"Config version: {settings.config_version}")
        console.print(f"Database: {settings.database_path}")
        console.print(f"Telegram configured: {settings.telegram_configured}")
        console.print(f"OpenRouter configured: {settings.openrouter_configured}")
        console.print(f"Bitquery configured: {settings.bitquery_configured}")
        console.print(f"RPC URL: {'configured' if settings.rpc_url else 'missing'}")

    asyncio.run(_run())


@app.command("run-once")
def run_once(notify: bool = typer.Option(False, help="Send Telegram digest if chat is registered.")) -> None:
    setup_logging(settings.log_level)

    async def _run() -> None:
        settings.ensure_dirs()
        await db.init()
        summary = await Pipeline().run_once(notify=notify)
        console.print(summary)

    asyncio.run(_run())


@app.command("score")
def score() -> None:
    setup_logging(settings.log_level)

    async def _run() -> None:
        settings.ensure_dirs()
        await db.init()
        scores = await ScoringService().score_recent_swaps()
        console.print({"wallets_scored": len(scores), "top_score": round(scores[0].copyability_score, 2) if scores else 0})

    asyncio.run(_run())


@app.command("telegram-poll")
def telegram_poll() -> None:
    setup_logging(settings.log_level)

    async def _run() -> None:
        settings.ensure_dirs()
        await db.init()
        await TelegramService().poll_commands()
        console.print("Polling Telegram once OK")

    asyncio.run(_run())


@app.command("backfill")
def backfill(limit: int = typer.Option(20, help="Max pools to backfill in this batch.")) -> None:
    setup_logging(settings.log_level)

    async def _run() -> None:
        settings.ensure_dirs()
        await db.init()
        count = await BackfillService().run_backfill_batch(limit=limit)
        console.print({"trades_collected": count})

    asyncio.run(_run())


@app.command("bitquery-check")
def bitquery_check() -> None:
    setup_logging(settings.log_level)

    async def _run() -> None:
        settings.ensure_dirs()
        await db.init()
        ok, message = await BitqueryCoreCastSource().check_graphql_access()
        console.print({"ok": ok, "message": message})

    asyncio.run(_run())


@app.command("bitquery-stream")
def bitquery_stream(seconds: int = typer.Option(60, help="How long to try the CoreCast stream.")) -> None:
    setup_logging(settings.log_level)

    async def _run() -> None:
        settings.ensure_dirs()
        await db.init()
        count = await BitqueryCoreCastSource().stream_dex_trades(seconds=seconds)
        console.print({"trades_ingested": count})

    asyncio.run(_run())


@app.command("run")
def run() -> None:
    setup_logging(settings.log_level)
    settings.ensure_dirs()
    asyncio.run(WalletScarperScheduler().start())


@app.command("stage2-legacy-sync")
def stage2_legacy_sync(
    limit: int = typer.Option(100, help="Max legacy tokens to sync into Stage 2."),
) -> None:
    """Sync legacy DB tokens into Stage 2 raw_source_events.

    Enables wallet extraction for transactions collected before the Stage 2 bridge
    was wired. Run once or on a schedule to keep Stage 2 up to date.
    """
    from walletscarper.services.stage2_scanner import Stage2ScannerService

    setup_logging(settings.log_level)
    settings.ensure_dirs()

    async def _run() -> None:
        await db.init()
        scanner = Stage2ScannerService()
        result = await scanner.run_legacy_token_sync(limit=limit)
        console.print(json.dumps(result, indent=2, sort_keys=True, default=str))

    asyncio.run(_run())


@app.command("stage2-wallet-backfill")
def stage2_wallet_backfill(
    max_tokens: int = typer.Option(50, help="Max token profiles to process."),
) -> None:
    """Extract wallets for all unprocessed Stage 2 token profiles (no age limit).

    Complements the periodic wallet extraction job by processing older profiles
    that were skipped due to the lookback_hours filter.
    """
    from walletscarper.services.stage2_scanner import Stage2ScannerService

    setup_logging(settings.log_level)
    settings.ensure_dirs()

    async def _run() -> None:
        await db.init()
        scanner = Stage2ScannerService()
        result = await scanner.run_wallet_extraction_backfill(max_tokens=max_tokens)
        console.print(json.dumps(result, indent=2, sort_keys=True, default=str))

    asyncio.run(_run())


@app.command("stage2-hermes-review")
def stage2_hermes_review(
    max_signals: int = typer.Option(10, help="Max wallet signal events to review per run."),
) -> None:
    """Run Hermes autonomous wallet signal review via configured LLM.

    Requires HERMES_ENABLED=true and HERMES_API_KEY in .env.
    Reviews pending real-source wallet signal events and records AgentTradingDecision.
    If decision_type is 'signal', also runs risk check and creates a paper order.
    """
    from walletscarper.services.stage2_scanner import Stage2ScannerService

    setup_logging(settings.log_level)
    settings.ensure_dirs()

    async def _run() -> None:
        await db.init()
        scanner = Stage2ScannerService()
        result = await scanner.run_hermes_signal_review(max_signals=max_signals)
        console.print(json.dumps(result, indent=2, sort_keys=True, default=str))

    asyncio.run(_run())


@app.command("stage2-run-daemon")
def stage2_run_daemon() -> None:
    """Start the Stage 2 continuous intelligence daemon.

    Runs token.scan_universe every 60 min, wallet extraction every 2 hours,
    and session heartbeats every 5 min. Blocks until Ctrl+C.
    """
    from walletscarper.services.stage2_daemon import Stage2Daemon

    setup_logging(settings.log_level)
    settings.ensure_dirs()
    asyncio.run(Stage2Daemon().start())


@app.command("web")
def web() -> None:
    setup_logging(settings.log_level)
    settings.ensure_dirs()
    uvicorn.run("walletscarper.web.app:app", host=settings.web_host, port=settings.web_port, reload=False)


@app.command("stage2-migrate")
def stage2_migrate() -> None:
    if not load_stage2_settings or not Stage2Database:
        raise typer.BadParameter("stage2 package is unavailable")

    async def _run() -> None:
        stage2_settings = load_stage2_settings()
        database = Stage2Database(stage2_settings)
        await database.migrate()
        console.print("[bold green]Stage 2 migrations applied[/bold green]")
        console.print(f"Database: {stage2_settings.database_path}")

    asyncio.run(_run())


@app.command("project-health-check")
def project_health() -> None:
    if not load_stage2_settings or not Stage2Database or not project_health_check:
        raise typer.BadParameter("stage2 package is unavailable")

    async def _run() -> None:
        stage2_settings = load_stage2_settings()
        result = await project_health_check(settings=stage2_settings, database=Stage2Database(stage2_settings))
        console.print(json.dumps(result, indent=2, sort_keys=True, default=str))

    asyncio.run(_run())


@app.command("stage2-v2-tool")
def stage2_v2_tool(
    tool_name: str = typer.Argument(..., help="V2 token/wallet Hermes tool name."),
    payload_json: str = typer.Option("{}", "--payload-json", help="JSON payload for the typed V2 tool."),
) -> None:
    if not load_stage2_settings or not Stage2Database or not run_v2_tool:
        raise typer.BadParameter("stage2 V2 Hermes tool package is unavailable")
    try:
        payload = json.loads(payload_json or "{}")
    except json.JSONDecodeError as exc:
        console.print(
            json.dumps(
                {
                    "ok": False,
                    "tool": tool_name,
                    "blocked_reason": f"payload-json must be valid JSON: {exc}",
                    "quality_flags": ["invalid_payload_json"],
                },
                indent=2,
                sort_keys=True,
            )
        )
        raise typer.Exit(code=2) from exc
    if not isinstance(payload, dict):
        console.print(
            json.dumps(
                {
                    "ok": False,
                    "tool": tool_name,
                    "blocked_reason": "payload-json must decode to a JSON object",
                    "quality_flags": ["invalid_payload_json"],
                },
                indent=2,
                sort_keys=True,
            )
        )
        raise typer.Exit(code=2)

    async def _run() -> None:
        stage2_settings = load_stage2_settings()
        result = await run_v2_tool(tool_name, payload, settings=stage2_settings, database=Stage2Database(stage2_settings))
        console.print(json.dumps(result, indent=2, sort_keys=True, default=str))

    asyncio.run(_run())


@app.command("stage2-v2-orchestrator-smoke")
def stage2_v2_orchestrator_smoke(
    mode: str = typer.Option("fixture", help="fixture or smoke. No real source/profitability claim is made."),
) -> None:
    if not load_stage2_settings or not Stage2Database or not run_orchestrator_smoke:
        raise typer.BadParameter("stage2 V2 orchestrator smoke package is unavailable")

    async def _run() -> None:
        stage2_settings = load_stage2_settings()
        database = Stage2Database(stage2_settings)
        result = await run_orchestrator_smoke(settings=stage2_settings, database=database, mode=mode)
        console.print(json.dumps(result, indent=2, sort_keys=True, default=str))

    asyncio.run(_run())


@app.command("stage2-dashboard")
def stage2_dashboard() -> None:
    if not load_stage2_settings or not Stage2Database or not DeterministicEvaluationService:
        raise typer.BadParameter("stage2 package is unavailable")

    async def _run() -> None:
        stage2_settings = load_stage2_settings()
        database = Stage2Database(stage2_settings)
        snapshot = await DeterministicEvaluationService(database).baseline_dashboard_snapshot()
        console.print(json.dumps(snapshot, indent=2, sort_keys=True, default=str))

    asyncio.run(_run())


@app.command("stage2-sprint4-report")
def stage2_sprint4_report() -> None:
    if not load_stage2_settings or not Stage2Database or not Sprint4ReportService:
        raise typer.BadParameter("stage2 package is unavailable")

    async def _run() -> None:
        stage2_settings = load_stage2_settings()
        database = Stage2Database(stage2_settings)
        snapshot = await Sprint4ReportService(database).snapshot()
        console.print(json.dumps(snapshot, indent=2, sort_keys=True, default=str))

    asyncio.run(_run())


@app.command("stage2-final-acceptance")
def stage2_final_acceptance(
    run_mode: str = typer.Option("fixture_replay", help="fixture_replay, paper_live_data, or shadow_gap_assessment."),
) -> None:
    if not load_stage2_settings or not Stage2Database or not AcceptanceRunService or not render_acceptance_report:
        raise typer.BadParameter("stage2 package is unavailable")

    async def _run() -> None:
        stage2_settings = load_stage2_settings()
        database = Stage2Database(stage2_settings)
        await database.migrate()
        result = await AcceptanceRunService(database, settings=stage2_settings).run_acceptance(run_mode=run_mode)
        console.print(render_acceptance_report(result))

    asyncio.run(_run())


@app.command("stage2-calibration-smoke")
def stage2_calibration_smoke(
    database_path: Path = typer.Option(Path("tmp/calibration_smoke.sqlite3"), help="Temp Stage 2 database for fixture smoke evidence."),
) -> None:
    """Safe fixture-only smoke for the observation evidence path."""

    required = (load_stage2_settings, Stage2Database, QuoteObservationService, RouteQualityService, LiveDataAcceptanceWindowService)
    if not all(required):
        raise typer.BadParameter("stage2 shadow-readiness package is unavailable")

    async def _run() -> None:
        stage2_settings = load_stage2_settings(database_path=database_path)
        database = Stage2Database(stage2_settings)
        await database.migrate()
        quote_id = await QuoteObservationService(database).record_quote_observation(
            source_name="stage2_quote_observer",
            token_mint="calibration-smoke-token",
            pool_address="calibration-smoke-pool",
            price_usd=1.0,
            liquidity_usd=50_000,
            observed_at=datetime.now(timezone.utc),
            response_latency_ms=75,
            confidence="high",
            provenance={"calibration_mode": "fixture_smoke", "live_market_evidence": False},
        )
        route_id = await RouteQualityService(database).record_route_quality(
            quote_observation_id=quote_id,
            route_depth_usd=5_000,
            spread_bps=30,
            independent_quote_count=2,
            evidence={"calibration_mode": "fixture_smoke", "live_market_evidence": False},
        )
        window_id = await LiveDataAcceptanceWindowService(database).run_observation_window(
            source_names=["stage2_quote_observer"],
            token_mints=["calibration-smoke-token"],
            duration_seconds=300,
            min_fresh_quotes=1,
            require_route_quality=True,
            require_fill_comparisons=True,
        )
        window = await database.fetchone(
            "SELECT * FROM live_data_acceptance_windows WHERE live_data_acceptance_window_id = ?",
            (window_id,),
        )
        console.print(
            json.dumps(
                {
                    "mode": "fixture_smoke",
                    "database": str(stage2_settings.database_path),
                    "quote_observation_id": quote_id,
                    "route_quality_evidence_id": route_id,
                    "live_data_acceptance_window_id": window_id,
                    "window_status": (window or {}).get("status"),
                    "gaps": json.loads((window or {}).get("gaps_json") or "[]"),
                    "truth_boundary": "fixture smoke only; not real live calibration evidence",
                },
                indent=2,
                sort_keys=True,
            )
        )

    asyncio.run(_run())


@app.command("stage2-calibration-window")
def stage2_calibration_window(
    token_mint: str = typer.Argument("", help="Solana token mint to observe through a free source."),
    pool_address: str = typer.Argument("", help="Optional pool address filter."),
    source: str = typer.Option("dexscreener", help="dexscreener, geckoterminal, dexpaprika, or all_free."),
    duration_seconds: int = typer.Option(300, help="Observation window size recorded in the acceptance window row."),
    interval_seconds: int = typer.Option(30, help="Delay between quote fetch attempts."),
    max_samples: int = typer.Option(3, help="Maximum public API quote fetch attempts."),
    database_path: Path | None = typer.Option(None, help="Optional Stage 2 database path override."),
) -> None:
    """Observation-only live quote calibration wrapper for free public sources."""

    required = (load_stage2_settings, Stage2Database, QuoteObservationService, RouteQualityService, LiveDataAcceptanceWindowService)
    if not all(required):
        raise typer.BadParameter("stage2 shadow-readiness package is unavailable")
    if not token_mint:
        console.print(
            json.dumps(
                {
                    "status": "blocked_missing_token_mint",
                    "message": "Provide a token mint. This command does not auto-select live market targets.",
                    "example": "python -m walletscarper stage2-calibration-window TOKEN_MINT",
                },
                indent=2,
                sort_keys=True,
            )
        )
        raise typer.Exit(code=2)
    try:
        selected_sources = _sources_for_calibration(source)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc

    async def _run() -> None:
        result = await _run_calibration_window(
            token_mint=token_mint,
            pool_address=pool_address or None,
            source=source,
            selected_sources=selected_sources,
            duration_seconds=duration_seconds,
            interval_seconds=interval_seconds,
            max_samples=max_samples,
            database_path=database_path,
        )
        console.print(json.dumps(result, indent=2, sort_keys=True, default=str))

    asyncio.run(_run())


FREE_CALIBRATION_SOURCES = ("dexscreener", "geckoterminal", "dexpaprika")


class CalibrationSourceError(Exception):
    def __init__(
        self,
        message: str,
        *,
        source_name: str,
        status_code: int | None = None,
        latency_ms: float | None = None,
        rate_limited: bool = False,
    ) -> None:
        super().__init__(message)
        self.source_name = source_name
        self.status_code = status_code
        self.latency_ms = latency_ms
        self.rate_limited = rate_limited


def _sources_for_calibration(source: str) -> list[str]:
    source = source.strip().lower()
    if source == "all_free":
        return list(FREE_CALIBRATION_SOURCES)
    if source in FREE_CALIBRATION_SOURCES:
        return [source]
    raise ValueError("source must be one of: dexscreener, geckoterminal, dexpaprika, all_free")


async def _run_calibration_window(
    *,
    token_mint: str,
    pool_address: str | None,
    source: str,
    selected_sources: list[str] | None = None,
    duration_seconds: int = 300,
    interval_seconds: int = 30,
    max_samples: int = 3,
    database_path: Path | None = None,
) -> dict[str, object]:
    stage2_settings = load_stage2_settings(database_path=database_path) if database_path else load_stage2_settings()
    database = Stage2Database(stage2_settings)
    await database.migrate()
    selected_sources = selected_sources or _sources_for_calibration(source)
    quotes_written: list[str] = []
    routes_written: list[str] = []
    comparisons_written: list[str] = []
    failures: list[dict[str, object]] = []
    source_attempts: dict[str, dict[str, int]] = {
        source_name: {"attempted": 0, "quotes_written": 0, "failures": 0} for source_name in selected_sources
    }

    for attempt in range(max(1, max_samples)):
        attempt_quotes: list[dict[str, object]] = []
        for source_name in selected_sources:
            source_attempts[source_name]["attempted"] += 1
            try:
                quote = await _fetch_source_quote(source_name=source_name, token_mint=token_mint, pool_address=pool_address)
            except CalibrationSourceError as exc:
                source_attempts[source_name]["failures"] += 1
                failures.append(
                    {
                        "attempt": attempt + 1,
                        "source": source_name,
                        "reason": str(exc),
                        "status_code": exc.status_code,
                        "rate_limited": exc.rate_limited,
                    }
                )
                await _record_source_failure(
                    database,
                    source_name=source_name,
                    reason=str(exc),
                    latency_ms=exc.latency_ms,
                    status_code=exc.status_code,
                    rate_limited=exc.rate_limited,
                )
                continue
            if not quote:
                source_attempts[source_name]["failures"] += 1
                failures.append({"attempt": attempt + 1, "source": source_name, "reason": "no_quote"})
                await _record_source_failure(database, source_name=source_name, reason="No quote returned for requested token/pool.")
                continue
            attempt_quotes.append(quote)

        grouped_sources = _independent_sources_by_pool(attempt_quotes)
        for quote in attempt_quotes:
            pool_key = _pool_key(str(quote.get("token_mint") or ""), str(quote.get("pool_address") or ""))
            spread_bps = _spread_bps_for_pool(attempt_quotes, pool_key)
            independent_sources = sorted(grouped_sources.get(pool_key, set()) - {str(quote.get("source_name"))})
            quality_flags = list(quote.get("quality_flags") or [])
            if spread_bps is None:
                quality_flags.append("missing_spread")
            if not independent_sources:
                quality_flags.append("no_independent_quote")
            quote_id = await QuoteObservationService(database).record_quote_observation(
                source_name=str(quote["source_name"]),
                token_mint=str(quote.get("token_mint") or token_mint),
                pool_address=str(quote.get("pool_address") or pool_address or ""),
                price_usd=_maybe_float(quote.get("price_usd")),
                liquidity_usd=_maybe_float(quote.get("liquidity_usd")),
                observed_at=_parse_optional_datetime(quote.get("observed_at")),
                response_latency_ms=_maybe_float(quote.get("response_latency_ms")),
                confidence=str(quote.get("confidence") or "medium"),
                provenance={
                    "calibration_mode": "observation_only_live_window",
                    "endpoint": quote.get("endpoint"),
                    "source_timestamp_note": quote.get("source_timestamp_note"),
                    "independent_sources_seen": independent_sources,
                    "selected_sources": selected_sources,
                },
                quality_flags=quality_flags,
            )
            quotes_written.append(quote_id)
            source_attempts[str(quote["source_name"])]["quotes_written"] += 1
            route_id = await RouteQualityService(database).record_route_quality(
                quote_observation_id=quote_id,
                route_depth_usd=_maybe_float(quote.get("route_depth_usd")),
                spread_bps=spread_bps,
                independent_quote_count=len(independent_sources),
                evidence={
                    "calibration_mode": "observation_only_live_window",
                    "source": quote.get("source_name"),
                    "spread_bps": spread_bps,
                    "independent_sources_seen": independent_sources,
                    "all_sources_in_attempt": sorted({str(item.get("source_name")) for item in attempt_quotes}),
                },
            )
            routes_written.append(route_id)
            if FillQuoteComparisonService:
                comparison_ids = await FillQuoteComparisonService(database).compare_recent_fills_for_quote(
                    quote_observation_id=quote_id,
                    route_quality_evidence_id=route_id,
                )
                comparisons_written.extend(comparison_ids)

        if attempt < max_samples - 1:
            await asyncio.sleep(max(1, interval_seconds))

    window_id = await LiveDataAcceptanceWindowService(database).run_observation_window(
        source_names=selected_sources,
        token_mints=[token_mint],
        duration_seconds=duration_seconds,
        min_fresh_quotes=1,
        require_route_quality=True,
        require_fill_comparisons=True,
    )
    window = await database.fetchone(
        "SELECT * FROM live_data_acceptance_windows WHERE live_data_acceptance_window_id = ?",
        (window_id,),
    )
    return {
        "status": (window or {}).get("status"),
        "database": str(stage2_settings.database_path),
        "source": source,
        "selected_sources": selected_sources,
        "token_mint": token_mint,
        "pool_address": pool_address,
        "quotes_written": quotes_written,
        "routes_written": routes_written,
        "comparisons_written": comparisons_written,
        "source_attempts": source_attempts,
        "failures": failures,
        "live_data_acceptance_window_id": window_id,
        "gaps": json.loads((window or {}).get("gaps_json") or "[]"),
        "truth_boundary": "observation-only; no trading, fills, route execution, or P&L mutation",
    }


async def _fetch_source_quote(*, source_name: str, token_mint: str, pool_address: str | None) -> dict[str, object] | None:
    if source_name == "dexscreener":
        return await _fetch_dexscreener_quote(token_mint=token_mint, pool_address=pool_address)
    if source_name == "geckoterminal":
        return await _fetch_geckoterminal_quote(token_mint=token_mint, pool_address=pool_address)
    if source_name == "dexpaprika":
        return await _fetch_dexpaprika_quote(token_mint=token_mint, pool_address=pool_address)
    raise CalibrationSourceError(f"unsupported source {source_name}", source_name=source_name)


async def _fetch_dexscreener_quote(*, token_mint: str, pool_address: str | None) -> dict[str, object] | None:
    import time

    import httpx

    endpoint = f"https://api.dexscreener.com/latest/dex/tokens/{token_mint}"
    started = time.perf_counter()
    elapsed_ms = (time.perf_counter() - started) * 1000
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(endpoint)
        elapsed_ms = (time.perf_counter() - started) * 1000
    except httpx.HTTPError as exc:
        elapsed_ms = (time.perf_counter() - started) * 1000
        raise CalibrationSourceError(str(exc), source_name="dexscreener", latency_ms=elapsed_ms) from exc
    if response.status_code == 429:
        raise CalibrationSourceError("rate_limited", source_name="dexscreener", status_code=429, latency_ms=elapsed_ms, rate_limited=True)
    if response.status_code >= 400:
        raise CalibrationSourceError(
            f"http_status_{response.status_code}",
            source_name="dexscreener",
            status_code=response.status_code,
            latency_ms=elapsed_ms,
        )
    payload = response.json()
    pairs = [pair for pair in (payload or {}).get("pairs", []) or [] if str(pair.get("chainId", "")).lower() == "solana"]
    if pool_address:
        pairs = [pair for pair in pairs if str(pair.get("pairAddress") or "").lower() == pool_address.lower()]
    if not pairs:
        return None
    pairs.sort(key=lambda pair: _float(((pair.get("liquidity") or {}).get("usd"))), reverse=True)
    chosen = pairs[0]
    base = chosen.get("baseToken") or {}
    liquidity = _maybe_float((chosen.get("liquidity") or {}).get("usd"))
    return {
        "source_name": "dexscreener",
        "adapter_name": "DexScreenerPublicQuoteAdapter",
        "endpoint": endpoint,
        "token_mint": str(base.get("address") or token_mint),
        "pool_address": str(chosen.get("pairAddress") or pool_address or ""),
        "price_usd": _maybe_float(chosen.get("priceUsd")),
        "liquidity_usd": liquidity,
        "route_depth_usd": min(liquidity * 0.01, 5_000.0) if liquidity else None,
        "response_latency_ms": round(elapsed_ms, 3),
        "observed_at": None,
        "confidence": "medium",
        "quality_flags": ["source_timestamp_not_provided"],
        "source_timestamp_note": "DexScreener token-pairs response has no quote timestamp in this adapter.",
    }


async def _fetch_geckoterminal_quote(*, token_mint: str, pool_address: str | None) -> dict[str, object] | None:
    import time

    import httpx

    endpoint = f"https://api.geckoterminal.com/api/v2/networks/solana/tokens/{token_mint}/pools"
    started = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(endpoint)
        elapsed_ms = (time.perf_counter() - started) * 1000
    except httpx.HTTPError as exc:
        elapsed_ms = (time.perf_counter() - started) * 1000
        raise CalibrationSourceError(str(exc), source_name="geckoterminal", latency_ms=elapsed_ms) from exc
    if response.status_code == 429:
        raise CalibrationSourceError("rate_limited", source_name="geckoterminal", status_code=429, latency_ms=elapsed_ms, rate_limited=True)
    if response.status_code >= 400:
        raise CalibrationSourceError(
            f"http_status_{response.status_code}",
            source_name="geckoterminal",
            status_code=response.status_code,
            latency_ms=elapsed_ms,
        )
    payload = response.json()
    pools = list((payload or {}).get("data", []) or [])
    if pool_address:
        pools = [
            pool
            for pool in pools
            if str((pool.get("attributes") or {}).get("address") or "").lower() == pool_address.lower()
            or str(pool.get("id") or "").split("_")[-1].lower() == pool_address.lower()
        ]
    if not pools:
        return None
    pools.sort(key=lambda pool: _float(((pool.get("attributes") or {}).get("reserve_in_usd"))), reverse=True)
    chosen = pools[0]
    attrs = chosen.get("attributes") or {}
    liquidity = _maybe_float(attrs.get("reserve_in_usd"))
    chosen_pool = str(attrs.get("address") or str(chosen.get("id") or "").split("_")[-1] or pool_address or "")
    return {
        "source_name": "geckoterminal",
        "adapter_name": "GeckoTerminalPublicPoolAdapter",
        "endpoint": endpoint,
        "token_mint": token_mint,
        "pool_address": chosen_pool,
        "price_usd": _maybe_float(attrs.get("base_token_price_usd") or attrs.get("token_price_usd")),
        "liquidity_usd": liquidity,
        "route_depth_usd": min(liquidity * 0.01, 5_000.0) if liquidity else None,
        "response_latency_ms": round(elapsed_ms, 3),
        "observed_at": None,
        "confidence": "medium",
        "quality_flags": ["source_timestamp_not_provided"],
        "source_timestamp_note": "GeckoTerminal pool response has no quote timestamp in this adapter.",
    }


async def _fetch_dexpaprika_quote(*, token_mint: str, pool_address: str | None) -> dict[str, object] | None:
    import time

    import httpx

    pools_endpoint = f"https://api.dexpaprika.com/networks/solana/tokens/{token_mint}/pools"
    started = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            pools_response = await client.get(pools_endpoint)
            elapsed_ms = (time.perf_counter() - started) * 1000
            if pools_response.status_code == 429:
                raise CalibrationSourceError(
                    "rate_limited",
                    source_name="dexpaprika",
                    status_code=429,
                    latency_ms=elapsed_ms,
                    rate_limited=True,
                )
            if pools_response.status_code >= 400:
                raise CalibrationSourceError(
                    f"http_status_{pools_response.status_code}",
                    source_name="dexpaprika",
                    status_code=pools_response.status_code,
                    latency_ms=elapsed_ms,
                )
            pools_payload = pools_response.json()
            pools = list((pools_payload or {}).get("pools", []) or [])
            if pool_address:
                pools = [pool for pool in pools if str(pool.get("id") or "").lower() == pool_address.lower()]
            if not pools:
                return None
            pools.sort(key=lambda pool: _float(pool.get("volume_usd")), reverse=True)
            chosen_pool_id = str(pools[0].get("id") or pool_address or "")
            detail_endpoint = f"https://api.dexpaprika.com/networks/solana/pools/{chosen_pool_id}"
            detail_response = await client.get(detail_endpoint)
            elapsed_ms = (time.perf_counter() - started) * 1000
        if detail_response.status_code == 429:
            raise CalibrationSourceError(
                "rate_limited",
                source_name="dexpaprika",
                status_code=429,
                latency_ms=elapsed_ms,
                rate_limited=True,
            )
        if detail_response.status_code >= 400:
            raise CalibrationSourceError(
                f"http_status_{detail_response.status_code}",
                source_name="dexpaprika",
                status_code=detail_response.status_code,
                latency_ms=elapsed_ms,
            )
    except CalibrationSourceError:
        raise
    except httpx.HTTPError as exc:
        elapsed_ms = (time.perf_counter() - started) * 1000
        raise CalibrationSourceError(str(exc), source_name="dexpaprika", latency_ms=elapsed_ms) from exc

    detail = detail_response.json()
    liquidity = _dexpaprika_liquidity(detail)
    observed_at = _parse_optional_datetime(detail.get("price_time"))
    quality_flags: list[str] = []
    if observed_at is None:
        quality_flags.append("source_timestamp_not_provided")
    return {
        "source_name": "dexpaprika",
        "adapter_name": "DexPaprikaPublicPoolAdapter",
        "endpoint": detail_endpoint,
        "token_mint": token_mint,
        "pool_address": str(detail.get("id") or chosen_pool_id),
        "price_usd": _maybe_float(detail.get("last_price_usd") or detail.get("price_usd")),
        "liquidity_usd": liquidity,
        "route_depth_usd": min(liquidity * 0.01, 5_000.0) if liquidity else None,
        "response_latency_ms": round(elapsed_ms, 3),
        "observed_at": observed_at,
        "confidence": "high" if observed_at else "medium",
        "quality_flags": quality_flags,
        "source_timestamp_note": "DexPaprika pool detail price_time used as source quote timestamp." if observed_at else "DexPaprika response did not include price_time.",
    }


async def _record_source_failure(
    database: object,
    *,
    source_name: str,
    reason: str,
    latency_ms: float | None = None,
    status_code: int | None = None,
    rate_limited: bool = False,
) -> None:
    if not SourceHealthService:
        return
    await SourceHealthService(database).record_failure(
        source_name=source_name,
        source_type="quote_snapshot",
        adapter_name=_adapter_name_for_source(source_name),
        degradation_reason=reason,
        unavailable=False,
        latency_ms=latency_ms,
        rate_limit_state={"status_code": status_code, "rate_limited": rate_limited} if status_code or rate_limited else None,
        metadata={"calibration_window": True},
    )


def _adapter_name_for_source(source_name: str) -> str:
    return {
        "dexscreener": "DexScreenerPublicQuoteAdapter",
        "geckoterminal": "GeckoTerminalPublicPoolAdapter",
        "dexpaprika": "DexPaprikaPublicPoolAdapter",
    }.get(source_name, "PublicQuoteAdapter")


def _independent_sources_by_pool(quotes: list[dict[str, object]]) -> dict[tuple[str, str], set[str]]:
    grouped: dict[tuple[str, str], set[str]] = {}
    for quote in quotes:
        key = _pool_key(str(quote.get("token_mint") or ""), str(quote.get("pool_address") or ""))
        if not key[0] or not key[1]:
            continue
        grouped.setdefault(key, set()).add(str(quote.get("source_name")))
    return grouped


def _pool_key(token_mint: str, pool_address: str) -> tuple[str, str]:
    return token_mint.lower(), pool_address.lower()


def _spread_bps(prices: list[float | None]) -> float | None:
    values = [price for price in prices if price is not None and price > 0]
    if len(values) < 2:
        return None
    high = max(values)
    low = min(values)
    midpoint = (high + low) / 2
    if midpoint <= 0:
        return None
    return round((high - low) / midpoint * 10_000, 6)


def _spread_bps_for_pool(quotes: list[dict[str, object]], pool_key: tuple[str, str]) -> float | None:
    prices = [
        _maybe_float(quote.get("price_usd"))
        for quote in quotes
        if _pool_key(str(quote.get("token_mint") or ""), str(quote.get("pool_address") or "")) == pool_key
    ]
    return _spread_bps(prices)


def _dexpaprika_liquidity(payload: dict[str, object]) -> float | None:
    reserves = payload.get("token_reserves")
    if not isinstance(reserves, list):
        return None
    total = 0.0
    for reserve in reserves:
        if isinstance(reserve, dict):
            total += _float(reserve.get("reserve_usd"))
    return total or None


def _parse_optional_datetime(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _maybe_float(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except Exception:
        return None


def _float(value: object) -> float:
    try:
        return float(value or 0)
    except Exception:
        return 0.0


if __name__ == "__main__":
    app()
