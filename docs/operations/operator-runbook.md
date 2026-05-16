# Operator Runbook

## Fresh Install

From `C:\Users\hacke\CascadeProjects\Finals1\TraderV1`:

```bat
scripts\setup-env.bat
```

This creates/uses `WalletScarper\.venv` and installs Python dependencies. It does not enable live trading.

## Environment Setup

Local config lives in:

- Project env: `WalletScarper\.env`
- Example env: `WalletScarper\.env.example`
- Hermes env: `C:\Users\hacke\.hermes\.env`
- Hermes config: `C:\Users\hacke\.hermes\config.yaml`

Keep real keys in `.env` only. Do not put keys in docs, scripts, or `.env.example`.

## Choosing Hermes Model

Current selected free OpenRouter model:

```text
openai/gpt-oss-20b:free
```

Run Hermes through the script so the key is loaded into the process:

```bat
scripts\run-hermes.bat -z "Reply with exactly OK."
```

The launcher enables the project `traderv1_operator` toolset. Hermes can use read-only tools for project health and deterministic reports:

- `traderv1_project_health`
- `traderv1_latest_reports`
- `traderv1_shadow_gap_summary`

To change model interactively:

```bat
external\hermes-agent\.venv\Scripts\hermes.exe model
```

Only choose `:free` models or `openrouter/free` unless you intentionally change the cost policy.

## Migrations

```bat
scripts\run-migrations.bat
```

Expected result: Stage 2 migrations applied and migration status current.

## Health Check

```bat
scripts\run-health.bat
```

Check:

- database connectivity is `ok`;
- migration status is `current`;
- `live_execution_enabled` is false;
- `trading_workflows_enabled` is false.

## Open Dashboard

```bat
scripts\run-dashboard.bat
```

URL:

```text
http://127.0.0.1:8787
```

Dashboard is read-only. It has no live trading controls.

## Fixture Acceptance

```bat
scripts\run-final-acceptance.bat
```

Expected current decision: `accepted_with_gaps`.

This validates deterministic fixture paper-mode behavior only. It is not live/shadow readiness and not a profitability claim.

## Shadow Gap Assessment

```bat
scripts\run-shadow-gap-assessment.bat
```

Expected current status: `gap_report_required`.

Stage 3 remains blocked until real observation evidence closes quote freshness, latency distribution, route-quality, fill-vs-quote, and live-window gaps.

## Calibration Smoke

```bat
scripts\run-calibration-smoke.bat
```

This uses `WalletScarper\tmp\calibration_smoke.sqlite3`. It is fixture-only and proves the quote/latency/route/window writing path works. It does not count as real live calibration.

## Calibration Window

Pick a real token mint first. Optional pool address narrows the pool selection. The launcher defaults to `all_free`, which attempts DexScreener, GeckoTerminal, and DexPaprika.

```bat
scripts\run-calibration-window.bat TOKEN_MINT [POOL_ADDRESS] [SOURCE]
```

Allowed `SOURCE` values:

- `dexscreener`
- `geckoterminal`
- `dexpaprika`
- `all_free`

Dust/SOL all-free one-sample smoke:

```bat
cd WalletScarper
.venv\Scripts\python.exe -m walletscarper stage2-calibration-window 6veQU7HDdXV5DC2Eqhnri5q71gkMzG73qKkSSudnpump cxlnktczbdgtdh94luwginkdb6esa6ry2vqrdi1dvfhm --source all_free --max-samples 1 --interval-seconds 1 --duration-seconds 300
```

Then rerun:

```bat
scripts\run-shadow-gap-assessment.bat
```

Read dashboard sections:

- Source Health
- Quote Observations
- Latency Summary
- Route Quality Evidence
- Fill-vs-Quote Comparisons
- Shadow Gap Status

## Reading Reports

Dashboard links reports from:

```text
docs\implementation-progress\reports
```

Important reports:

- `validation-summary.md`
- `final-acceptance-report.md`
- `shadow-mode-gap-report.md`
- `shadow-readiness-gap-closure-report.md`

## What System Ready Means

For this sprint, ready means:

- local install works;
- migrations run;
- health check runs;
- dashboard opens locally;
- fixture acceptance runs;
- shadow gaps are visible;
- Hermes is installed and can use a free OpenRouter model;
- calibration smoke/window workflow is wired.

It does not mean Stage 3 shadow readiness.

## What accepted_with_gaps Means

`accepted_with_gaps` means the Stage 2 deterministic fixture/paper-mode acceptance target passed without critical invariant violations, while shadow/live observation evidence remains insufficient.

## What Not To Do

- Do not add private keys.
- Do not add a signer.
- Do not add swap adapters.
- Do not construct DEX transactions.
- Do not place real orders.
- Do not claim profitability.
- Do not treat fixture P&L as live evidence.

## Later Optional Keys

Place optional keys in `WalletScarper\.env` only:

- `OPENROUTER_API_KEY` for Hermes/OpenRouter free models.
- `BITQUERY_API_TOKEN` only if enabling Bitquery.
- `HELIUS_RPC_URL` or `HELIUS_API_KEY` only if public RPC limits block read-only inspection.

Never put real keys in `.env.example` or docs.
