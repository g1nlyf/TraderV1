# Operational Launch, Hermes Runtime And Design Sprint

Date: 2026-05-15

## Status

Operational launch layer complete; overall system readiness remains partially complete because Stage 3 shadow readiness is still blocked by real evidence gaps.

Implemented:

- Operational reality audit in `docs/operations/current-system-reality-audit.md`.
- Hermes runtime/setup doc in `docs/operations/hermes-runtime.md`.
- Free/no-key source policy in `docs/operations/free-data-sources.md`.
- Operator runbook in `docs/operations/operator-runbook.md`.
- Hermes persona in `docs/operations/hermes-agent-persona.md`.
- Hermes prompt copy in `config/hermes/system-prompt.md`.
- Hermes project plugin in `.hermes/plugins/traderv1_operator`.
- Windows launch scripts in `scripts/`.
- Local read-only FastAPI operator dashboard at `http://127.0.0.1:8787`.
- Calibration smoke and DexScreener observation-window CLI wrappers.

## Hermes Status

Hermes was not installed on `PATH`. The upstream repo was cloned to:

```text
external/hermes-agent
```

Installed version:

```text
Hermes Agent v0.13.0
```

Configured provider/model:

```text
provider: openrouter
model: openai/gpt-oss-20b:free
base_url: https://openrouter.ai/api/v1
```

Direct OpenRouter API smoke succeeded with this model. Hermes one-shot also succeeded when `OPENROUTER_API_KEY`, `HERMES_INFERENCE_PROVIDER`, and `HERMES_INFERENCE_MODEL` were loaded into the process environment. `scripts/run-hermes.bat` does this without printing the key.

Ollama is installed and available but not selected because the operator requested OpenRouter free models.

Hermes project tool integration is wired through the project plugin toolset:

```text
.hermes/plugins/traderv1_operator
```

Validated tools:

- `traderv1_project_health`
- `traderv1_latest_reports`
- `traderv1_shadow_gap_summary`

Validation: `scripts/run-hermes.bat -z "Use the traderv1_shadow_gap_summary tool and answer only with the shadow_status value."` returned `gap_report_required`.

## Dashboard Status

The existing FastAPI app now serves a Stage 2 operator dashboard at:

```text
http://127.0.0.1:8787
```

Screens/sections wired:

- System Status
- Stage 2 Release Decision
- Shadow Gap Status
- Source Health
- Quote Observations
- Latency Summary
- Route Quality Evidence
- Fill-vs-Quote Comparisons
- Paper Trading Summary
- Strategy Leaderboard
- Worker/Queue Status
- Invariant Violations
- Reports / Downloads
- Next Operator Actions

The dashboard is read-only and exposes no destructive controls. Playwright rendered the dashboard on desktop and mobile. The 15-second refresh path was checked after fixing a header status refresh bug. Mobile layout had no horizontal overflow in the checked viewport.

## Launch Scripts

Created:

- `scripts/setup-env.bat`
- `scripts/run-health.bat`
- `scripts/run-migrations.bat`
- `scripts/run-final-acceptance.bat`
- `scripts/run-shadow-gap-assessment.bat`
- `scripts/run-calibration-smoke.bat`
- `scripts/run-calibration-window.bat`
- `scripts/run-dashboard.bat`
- `scripts/run-hermes.bat`
- `scripts/run-all-local.bat`

Scripts use `WalletScarper\.venv` where present and do not print secrets.

## Free/No-Key Sources

Supported in code:

- DexScreener public REST endpoints.
- GeckoTerminal public API.
- DexPaprika public endpoints.
- Public Solana RPC fallback.
- Browser extraction schema as degraded fallback, not a default live adapter.

Current calibration wrapper support:

- DexScreener.
- GeckoTerminal.
- DexPaprika.
- `all_free`, which attempts all three and records per-source failures as degraded health.

Dust/SOL one-sample `all_free` smoke on 2026-05-15 wrote 3 quote observations and 3 route-quality records with no source failures. The window stayed `gap_report_required` with `route_quality_model` and `fill_vs_quote_comparison` gaps because cross-source spread was too wide and no contemporaneous paper fill comparison existed.

Blocked or optional:

- Bitquery CoreCast requires `BITQUERY_API_TOKEN`.
- Helius requires optional RPC/API key if public RPC is insufficient.
- OpenRouter requires a key but is configured for free model usage only.

## Calibration Workflow

Documented and wired:

1. Start dashboard.
2. Run calibration smoke.
3. Inspect source health.
4. Run calibration window with a selected token mint.
5. Rerun shadow gap assessment.
6. Read updated shadow gap report/dashboard.
7. Decide whether to continue calibration, provide optional keys, close a specific gap, or stop as not ready.

Current limitation: no passed real observation-only live data window is recorded.

## Validation Results

- `python -m pytest -q`: 59 passed.
- `python -m compileall walletscarper`: passed.
- `scripts\run-migrations.bat`: passed, migrations current.
- `scripts\run-health.bat`: passed, database connectivity `ok`, live execution flags false.
- `scripts\run-final-acceptance.bat`: passed, decision `accepted_with_gaps`, invariant findings 0, critical violations 0.
- `scripts\run-shadow-gap-assessment.bat`: passed, shadow status `gap_report_required`, invariant findings 0, critical violations 0.
- `scripts\run-calibration-smoke.bat`: passed as fixture smoke; remaining expected gap is fill-vs-quote comparison.
- `scripts\run-calibration-window.bat` without a token: blocked safely with a clear message.
- Dust/SOL `all_free` one-sample smoke: passed as evidence capture; wrote 3 quotes and 3 route records, failures none, status `gap_report_required`.
- `scripts\run-hermes.bat -z "Reply with exactly OK."`: passed.
- Hermes project plugin smoke: passed, returned `gap_report_required`.
- Dashboard smoke/API/render: passed at `http://127.0.0.1:8787`.
- Dangerous-term scan over runtime Python, scripts, and the project Hermes plugin: no matches.

## Remaining Gaps

- Stage 3 shadow readiness remains not accepted.
- Fresh quote evidence is still insufficient for readiness; a one-sample DexPaprika timestamp was captured, but no accepted live window has passed.
- Source latency distribution now records for no-key calibration attempts, but a longer real observation window has not passed.
- Route-quality model evidence is still insufficient when spread/depth gates fail.
- Fill-vs-quote comparison evidence from real paper fills is missing.
- Hermes integration is local/project-plugin based, not a packaged MCP server.
- No hosted dashboard exists; local dashboard only.

## Boundary Confirmation

No live trading, private-key handling, signer, swap adapter, DEX transaction construction, or real order placement path was added.

## Next Operator Action

Run:

```bat
scripts\run-all-local.bat
```

Then open:

```text
http://127.0.0.1:8787
```

If the dashboard is healthy, run:

```bat
scripts\run-calibration-smoke.bat
```
