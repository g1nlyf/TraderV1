# Sprint 5 - Hardening, Shadow Mode And Final Acceptance

## Status

Implemented and validated as a deterministic Stage 2 hardening/acceptance layer.

Final acceptance decision from the validated fixture replay harness: `accepted_with_gaps`.

This means the Stage 2 paper-trading research system has a passing fixture acceptance run with zero critical invariant violations, deterministic paper workflow evidence, operational health reporting, final report persistence, and explicit shadow-mode gap reporting. It does not mean Stage 3 shadow execution is complete or validated.

Sprint 5 remains paper-only. It does not add live trading, private-key handling, signing, swap adapters, DEX transaction construction, real-money order placement, or any new agent framework.

## Documentation Inspected

- `docs/implementation-almanac/sprints/sprint-5-hardening-acceptance.md`
- `docs/implementation-almanac/checklists/final-acceptance-checklist.md`
- `docs/implementation-almanac/runbooks/continuous-run-runbook.md`
- `docs/implementation-almanac/00-master-build-map.md`
- `docs/implementation-almanac/01-system-invariants.md`
- `docs/implementation-almanac/02-architecture-decisions.md`
- `docs/implementation-almanac/contracts/domain-contracts.md`
- `docs/implementation-almanac/contracts/service-api-contracts.md`
- `docs/implementation-almanac/contracts/config-snapshots.md`
- `docs/implementation-almanac/decisions/ADR-0001-release-target.md`
- `docs/implementation-almanac/decisions/ADR-0002-risk-before-paper-order.md`
- `docs/implementation-almanac/decisions/ADR-0003-no-live-execution.md`
- `docs/implementation-almanac/decisions/ADR-0004-job-queue-over-freeform-a2a.md`
- `docs/implementation-almanac/decisions/ADR-0005-browser-data-policy.md`
- `docs/delivery/14-final-system-delivery.md`
- `docs/delivery/15-implementation-guide.md`
- `docs/delivery/16-acceptance-criteria.md`
- `docs/delivery/17-unknowns.md`
- `docs/trading/11-paper-trading-framework.md`
- `docs/trading/12-evaluation-metrics.md`
- `docs/trading/13-risk-management-and-live-readiness.md`
- `docs/architecture/03-system-architecture.md`
- `docs/architecture/04-hermes-system-design.md`
- `docs/architecture/05-agent-architecture.md`
- `docs/architecture/06-data-model.md`
- `docs/research/07-wallet-intelligence.md`
- `docs/research/08-token-discovery-and-market-context.md`
- `docs/research/09-signal-generation.md`
- `docs/research/10-strategy-search-and-self-improvement.md`
- `docs/implementation-progress/README.md`
- `docs/implementation-progress/sprint-1-foundation.md`
- `docs/implementation-progress/sprint-2-data-wallet-intelligence.md`
- `docs/implementation-progress/sprint-3-signal-risk-paper.md`
- `docs/implementation-progress/sprint-4-parallel-strategy-memory.md`

## What Was Implemented

### Final Invariant Suite

Implemented `walletscarper.stage2.acceptance.service.InvariantChecker`.

The checker records append-only `invariant_violations` and covers the core release invariants:

- runtime source scan for prohibited execution or credential-material terminology;
- Hermes integration remains read-only and does not directly mutate the database;
- authoritative `RiskCheck` rows must be created by deterministic Risk Service;
- canonical `TradeOutcome` rows must be calculated by deterministic Evaluation Service;
- `Signal` exists before entry risk;
- `TradeThesis` exists before `PaperOrder`;
- passed authoritative entry risk exists before buy `PaperOrder`;
- successful fills include fees, slippage, latency assumptions, and liquidity constraints;
- failed fills are visible;
- `ExitDecision` and passed exit risk precede sell fill;
- normalized evidence links back to `RawSourceEvent`;
- browser extraction records cannot be high-confidence evaluation evidence;
- wallet metric snapshots remain candidate evidence only;
- `StrategyVersion` records reference immutable config snapshots;
- strategy decisions require deterministic metrics and promotion criteria snapshots;
- worker lease expiry is visible;
- duplicate active monitoring sessions are flagged;
- open paper positions without monitoring are critical;
- conflict reviews must not resolve by rewriting history;
- critical workflow tables retain append-only trigger coverage.

The checker does not repair state or overwrite history.

### End-To-End Paper Trading Acceptance Fixture

Implemented fixture replay inside `AcceptanceRunService.run_acceptance(run_mode="fixture_replay")`.

The fixture creates a controlled deterministic flow:

`RawSourceEvent` -> normalized token/market evidence -> `TokenProfile` / triage evidence -> wallet trade evidence -> wallet metrics/profile -> `Signal` and `NoTradeSignal` -> `TradeThesis` -> entry `RiskCheck` -> `PaperOrder` -> conservative entry `PaperFill` -> `PaperPosition` and monitoring job/session -> failed-fill branch -> `ExitDecision` -> exit `RiskCheck` -> conservative exit `PaperFill` -> deterministic `TradeOutcome` -> `PostTradeReview` -> memory proposal/curation -> strategy metric snapshot -> `insufficient_data` strategy decision.

The fixture is explicitly test/replay evidence. It is not live market proof and is not a profitability claim.

### Continuous Acceptance Harness

Implemented `walletscarper.stage2.acceptance.service.AcceptanceRunService`.

Supported run modes:

- `fixture_replay`: deterministic local replay used for Stage 2 acceptance validation.
- `shadow_gap_assessment`: records a shadow-readiness assessment without pretending execution readiness.
- `paper_live_data`: currently produces a gap-required acceptance path because Stage 2-owned live data reliability is not fully validated in this repository state.

The harness creates immutable `AcceptanceRun` records through existing config snapshot infrastructure and mutable execution state in `acceptance_run_executions`.

### AcceptanceRun Tracking And Reports

Added persistent acceptance execution/reporting records:

- `acceptance_run_executions`
- `acceptance_run_events`
- `invariant_violations`
- `operational_health_snapshots`
- `shadow_mode_gap_reports`
- `final_acceptance_reports`

The final report includes invariant results, operational health, fixture paper workflow results, strategy leaderboard snapshot, source degradation summary, memory/review counts, shadow/gap status, known limitations, and final decision.

### Operational Health

Implemented `OperationalHealthService`.

Health snapshots capture:

- source health/degradation/staleness counts;
- queue depth;
- active and expired leases;
- failed jobs;
- active and blocked sessions;
- open paper positions;
- unmonitored open positions;
- missed exit/risk checks;
- failed fills;
- risk vetoes;
- net P&L, expectancy, and drawdown from deterministic `TradeOutcome` rows;
- leaderboard summary;
- memory/review counts;
- critical invariant violation count;
- warnings.

### Shadow Mode Assessment

Implemented `ShadowModeAssessmentService`.

The assessment produces a `shadow_mode_gap_reports` row when required evidence is missing. In the current validated fixture run, the report is required because Stage 3-quality shadow readiness is not proven.

The 2026-05-15 fixture replay exported to `docs/implementation-progress/reports/shadow-mode-gap-report.md` reports these current missing capabilities:

- `route_quality_model`;
- `fill_vs_quote_comparison`.

The final acceptance report still treats quote freshness, latency, route quality, and fill comparison as Stage 3 evidence requirements. In the current fixture database, fresh quote and source latency evidence exist only as deterministic fixture evidence; they are not a claim of Stage 3 shadow readiness.

The gap report marks these as blocking Stage 3 progression, not blocking the Stage 2 fixture-validated paper release.

### CLI Reporting

Added CLI command:

```powershell
python -m walletscarper stage2-final-acceptance --run-mode fixture_replay
```

The command runs migrations, executes the selected acceptance mode, persists acceptance artifacts, and prints a compact report showing status, decision, invariant findings, failed fills, risk vetoes, source degradation, net P&L, expectancy, drawdown, and shadow gap status.

## Files Created Or Modified

Created:

- `WalletScarper/walletscarper/stage2/acceptance/__init__.py`
- `WalletScarper/walletscarper/stage2/acceptance/service.py`
- `WalletScarper/tests/test_stage2_sprint5_hardening_acceptance.py`
- `docs/implementation-progress/sprint-5-hardening-acceptance.md`
- `docs/implementation-progress/reports/final-acceptance-report.md`
- `docs/implementation-progress/reports/final-acceptance-report.json`
- `docs/implementation-progress/reports/shadow-mode-gap-report.md`
- `docs/implementation-progress/reports/shadow-mode-gap-report.json`
- `docs/implementation-progress/reports/validation-summary.md`
- `docs/implementation-progress/reports/validation-summary.json`

Modified:

- `WalletScarper/walletscarper/stage2/db/migrations.py`
- `WalletScarper/walletscarper/__main__.py`
- `docs/implementation-progress/README.md`

## Database And Migration Changes

Added migration `7 - stage2_hardening_shadow_acceptance_schema`.

New tables:

- `acceptance_run_executions`
- `acceptance_run_events`
- `invariant_violations`
- `operational_health_snapshots`
- `shadow_mode_gap_reports`
- `final_acceptance_reports`

Append-only protections were added for:

- `acceptance_run_events`
- `invariant_violations`
- `operational_health_snapshots`
- `shadow_mode_gap_reports`
- `final_acceptance_reports`

`acceptance_runs` remains the immutable Sprint 1 config-linked run record. `acceptance_run_executions` is the mutable execution-status companion because acceptance status/counts need to be updated during a run.

## Tests Added

Added `WalletScarper/tests/test_stage2_sprint5_hardening_acceptance.py`.

Coverage includes:

- migration creates Sprint 5 acceptance tables;
- invariant checker records authority violations without repairing state;
- fixture acceptance run creates end-to-end paper workflow artifacts;
- fixture acceptance run records failed fill evidence;
- fixture acceptance run records shadow gap and final acceptance report;
- strategy decision fails closed to `insufficient_data`;
- synthetic critical invariant produces rejected final report decision;
- shadow assessment does not claim Stage 3 readiness when evidence is insufficient;
- acceptance artifact append-only protections.

All Sprint 1-4 regression tests still pass.

## Acceptance Criteria Satisfied

- Final invariant suite exists and passes on the fixture acceptance run.
- End-to-end deterministic paper trading acceptance fixture exists and passes.
- Continuous acceptance run harness exists.
- `AcceptanceRun` can be configured and executed with execution tracking.
- Invariant violations are tracked.
- Critical invariant violations fail final acceptance reporting.
- Operational health reporting exists.
- Reports surface failed fills, risk vetoes, source degradation, queue/worker/session state, and critical invariant counts.
- Final metrics include deterministic net P&L, expectancy, drawdown, and strategy comparison where fixture data exists.
- Source degradation and missing shadow evidence fail safely into warnings/gap reports.
- Shadow mode is honestly gap-reported.
- Final acceptance report is generated and persisted.
- All previous Sprint 1/2/3/4 tests pass.
- No live execution/private-key/signer/swap/DEX path was added.
- Implementation progress docs reflect final status.

## Acceptance Criteria Not Fully Satisfied

- Stage 3-quality shadow readiness is not complete. It is gap-reported because quote freshness, latency distribution, route-quality evidence, and fill-vs-quote comparison are insufficient.
- `paper_live_data` acceptance mode is not honestly validated as a full continuous live-data run in this repository state. The harness supports the mode but returns gap-required status rather than pretending completion.
- No long-running production worker daemon was added. Sprint 4 worker primitives remain service-level DB-backed primitives.
- Partial exits remain unsupported.
- Drawdown is deterministic from closed outcome sequence, but still simple relative to a richer future equity curve.
- No polished UI dashboard was added; reporting is CLI/read-only.

## Intentionally Excluded

- Real-money execution.
- Live order placement.
- Private-key handling.
- Signing.
- Swap adapters.
- DEX transaction construction.
- Real DEX execution APIs.
- Fake Stage 3 shadow completion.
- Strategy profitability claims.
- New agent frameworks.
- Legacy `paper_trades` as Stage 2 ledger.
- Legacy FIFO PnL as Stage 2 evaluation.
- Legacy wallet scores as strategy proof.
- Browser-only prices as canonical high-confidence P&L or promotion input.

## Final Acceptance Decision

Decision: `accepted_with_gaps`.

Reason:

- Fixture replay completed with zero critical invariant violations.
- Deterministic paper workflow, failed-fill path, no-trade path, review/memory artifacts, strategy metrics, and insufficient-data strategy decision were persisted.
- Final report and operational health snapshots were generated.
- Shadow readiness is not complete and is explicitly documented as a gap.

The system is accepted for the Stage 2 paper-mode construction target represented by deterministic fixture acceptance, with Stage 3 shadow-readiness gaps carried forward. This is not a claim that the strategy is profitable or that live/shadow execution is ready.

## Shadow Mode Gap Report

The fixture acceptance run produced a `shadow_mode_gap_reports` row and the row was exported to filesystem artifacts:

- Markdown: `docs/implementation-progress/reports/shadow-mode-gap-report.md`
- JSON: `docs/implementation-progress/reports/shadow-mode-gap-report.json`
- SQLite row: `WalletScarper/tmp/final_release_validation.sqlite3`, table `shadow_mode_gap_reports`, id `shadow_gap_3e858fab1e104e6f99a73cdd6d5fa906`

The persisted report status is `gap_report_required`. It does not block Stage 2 fixture-validated paper acceptance. It blocks Stage 3 progression until the missing route-quality and fill-vs-independent-quote evidence exists.

## Assumptions

- Fixture replay is an acceptable deterministic local acceptance mode for the Stage 2 construction release because it validates ordering, invariants, persistence, and reporting without relying on unstable external APIs.
- `paper_live_data` mode should not be marked passed until Stage 2-owned source reliability and run-window evidence are available.
- Stage 3 shadow readiness requires stronger quote/latency/route/fill comparison evidence than current conservative paper fills provide.
- Acceptance execution status may be updated in `acceptance_run_executions`; immutable acceptance evidence is stored in append-only event, violation, health, gap, and report tables.

## Remaining Risks And Carry-Forward Items

- Implement and validate Stage 2-owned live data collection for acceptance windows before using `paper_live_data` as a passing mode.
- Add quote freshness and latency distributions per source.
- Add route-quality and fill-vs-quote comparison artifacts for Stage 3 shadow readiness.
- Add a supervised long-running worker runner if operational use requires it.
- Expand drawdown to a richer equity-curve calculation when enough closed outcome history exists.
- Keep partial exits out until the paper ledger explicitly supports them.
- Consider a read-only UI once CLI/report semantics stabilize.

## Validation

Commands rerun from `C:\Users\hacke\CascadeProjects\Finals1\TraderV1\WalletScarper` on 2026-05-15 unless noted. The CLI smoke commands used `STAGE2_DATABASE_PATH=tmp/final_release_validation.sqlite3`.

Full regression suite:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Result: `48 passed`.

Compile check:

```powershell
.\.venv\Scripts\python.exe -m compileall walletscarper
```

Result: compile completed successfully.

Migration smoke:

```powershell
$env:STAGE2_DATABASE_PATH='tmp/final_release_validation.sqlite3'
.\.venv\Scripts\python.exe -m walletscarper stage2-migrate
```

Result: Stage 2 migrations applied to `tmp/final_release_validation.sqlite3`; migrations 1 through 7 are present.

Project health check:

```powershell
$env:STAGE2_DATABASE_PATH='tmp/final_release_validation.sqlite3'
.\.venv\Scripts\python.exe -m walletscarper project-health-check
```

Result: database connectivity `ok`; migration status `current`; migrations 1 through 7 applied; `live_execution_enabled=false`; `trading_workflows_enabled=false`.

Sprint 4 report CLI smoke:

```powershell
$env:STAGE2_DATABASE_PATH='tmp/final_release_validation.sqlite3'
.\.venv\Scripts\python.exe -m walletscarper stage2-sprint4-report
```

Result: read-only report returned successfully. Before fixture replay the report was an empty-state report. After fixture replay it included one low-sample-size leaderboard warning and one `insufficient_data` strategy decision.

Sprint 5 acceptance/report CLI smoke:

```powershell
$env:STAGE2_DATABASE_PATH='tmp/final_release_validation.sqlite3'
.\.venv\Scripts\python.exe -m walletscarper stage2-final-acceptance --run-mode fixture_replay
```

Result:

- status: `gap_report_required`
- decision: `accepted_with_gaps`
- invariant findings: `0`
- critical violations: `0`
- failed fills: `1`
- risk vetoes: `0`
- degraded sources: `0`
- net P&L: `4.8125625`
- expectancy: `4.8125625`
- drawdown: `0.0`
- shadow status: `gap_report_required`
- shadow gap report id: `shadow_gap_3e858fab1e104e6f99a73cdd6d5fa906`
- final acceptance report id: `final_acceptance_report_54ebabb37daf4a798870fe204dc7f68d`

Persisted final report exports:

- `docs/implementation-progress/reports/final-acceptance-report.md`
- `docs/implementation-progress/reports/final-acceptance-report.json`
- `docs/implementation-progress/reports/validation-summary.md`
- `docs/implementation-progress/reports/validation-summary.json`

Dangerous-term scan from repository root:

```powershell
rg -n -i "private_key|secret_key|seed phrase|signer|signTransaction|sendTransaction|VersionedTransaction|\bswap\b|\bswaps\b|jupiter|raydium|dex transaction|live trade|execute trade|order placement" WalletScarper\walletscarper docs\implementation-progress docs\implementation-almanac docs\research docs\architecture -g "*.py" -g "*.md"
```

Scan classification:

| Area | Terms | Classification | Notes |
|---|---|---|---|
| `WalletScarper/walletscarper/sources/dexpaprika.py` | `swaps` | Read-only market-data terminology | Provider endpoint/key naming only. |
| `WalletScarper/walletscarper/sources/solana_rpc.py` | `signer` | Read-only RPC parsed metadata | Reads account-key metadata from `getTransaction`; no signing operation. |
| `WalletScarper/walletscarper/services/transactions.py` | `swap`, `swaps`, `store_swap`, `signer` | Read-only market-data terminology / read-only RPC parsed metadata | Normalizes observed source transactions. |
| `WalletScarper/walletscarper/services/backfill.py` | `swaps` | Historical/legacy naming only | Refers to observed transaction rows from legacy collector. |
| `WalletScarper/walletscarper/services/scoring.py` | `swaps` | Historical/legacy naming only | Used for legacy FIFO-style scoring evidence, not Stage 2 evaluation. |
| `docs/**` | private-key, signer, swap, DEX transaction, order-placement references | Harmless config/doc reference | Architecture prohibitions, ADRs, and progress documentation. |

No dangerous live execution path was found in scanned Python code. No new live execution/private-key/signer/swap/DEX path was added by Sprint 5.
