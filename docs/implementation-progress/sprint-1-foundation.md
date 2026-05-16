# Sprint 1 - Foundation, Environment, Source Of Truth

## Status

Foundation implemented and validated; legacy restore blocker resolved by operator.

The Sprint 1 source-of-truth foundation was implemented under `walletscarper.stage2` and targeted tests were added. During the implementation session, the pre-existing legacy `WalletScarper` directory was accidentally removed from this non-git workspace. The operator restored the legacy Final Free v1 project afterward and reported successful validation of both the restored legacy workflow and the Sprint 1 tests. This file now records that restoration, while still treating legacy WalletScarper as a separate pre-existing system that must be audited before Sprint 2 integration.

## Implemented

- Added the Stage 2 foundation into the restored `WalletScarper/` Python project.
- Added `walletscarper.stage2` as an isolated final-system foundation package.
- Added Stage 2 config loading with environment, database path/URL, app version, build info, feature flags, Hermes smoke-test enablement, lease defaults, append-only enforcement mode, and test overrides.
- Added SQLite migration foundation with `stage2_schema_migrations`.
- Added source-of-truth tables for raw source events, audit events, config snapshots, domain contracts, jobs, worker leases, monitoring sessions, and conflict reviews.
- Added database-level append-only triggers for raw source events, audit events, config snapshots, core decision records, paper order/fill skeletons, exit decisions, and trade outcomes.
- Added Pydantic contract models for `StrategyVersion`, `TradeThesis`, `Signal`, `RiskCheck`, `PaperOrder`, `PaperFill`, `PaperPosition`, `ExitDecision`, `TradeOutcome`, `PostTradeReview`, and `MemoryEntry`.
- Added config snapshot entities for `ConfigSnapshot`, `RiskLimitSnapshot`, `StrategyConfigSnapshot`, `PromotionCriteriaSnapshot`, and `AcceptanceRun`.
- Added repository helpers for appending raw source events and audit events.
- Added repository helpers for creating config snapshots and core contract skeleton rows.
- Added durable job queue primitives with lease acquisition, double-lease prevention, lease expiry, and max-attempt handling.
- Added monitoring session and conflict review skeleton repositories.
- Added deterministic service boundary stubs for Risk Service, Paper Trading Service, and Evaluation Service.
- Added Sprint 1 guard behavior so `PaperOrder` creation rejects missing, failed, non-authoritative, wrong-scope, or wrong-signal risk checks.
- Added read-only `project.health_check` Hermes/project tool boundary.
- Added CLI commands for `stage2-migrate` and `project-health-check`.
- Added targeted Sprint 1 tests.

## Legacy Restoration Recorded After Sprint 1 Implementation

The operator restored the pre-existing `WalletScarper` Final Free v1 project after the accidental deletion. Reported restored components:

- main `walletscarper` package;
- `.env` with known keys, without exposing secrets in this documentation;
- SQLite schema and database state;
- discovery through DexScreener and GeckoTerminal;
- trade collection through DexPaprika plus Gecko fallback;
- Bitquery CoreCast live stream;
- Helius/public RPC fallback;
- FIFO PnL;
- `bot_score`, `human_score`, and `copyability_score`;
- `tracked_wallets`, leaderboard, Telegram UX, web dashboard;
- batch launch files, Dockerfile, docker-compose;
- legacy `WalletScarper/docs`.

Reported operator validation after restore:

- `compileall` OK;
- `smoke-test` OK;
- `pytest`: 10 passed;
- Helius RPC health OK;
- Bitquery CoreCast gRPC working; a short test wrote 1335 trades;
- `run-once` OK; found 12 tokens, collected 1200 trades, rescored 120 wallets;
- web API OK.

These restored legacy capabilities are not Stage 2 Sprint 1 behavior. They remain existing collector/research workflow capabilities and must be audited/adapted before Sprint 2 uses them as source inputs.

## Files Created Or Modified

- `WalletScarper/pyproject.toml`
- `WalletScarper/requirements.txt`
- `WalletScarper/.env.example`
- `WalletScarper/walletscarper/__init__.py`
- `WalletScarper/walletscarper/__main__.py`
- `WalletScarper/walletscarper/stage2/**`
- `WalletScarper/tests/test_stage2_foundation.py`
- `docs/implementation-progress/README.md`
- `docs/implementation-progress/sprint-1-foundation.md`

## Tables Created

- `stage2_schema_migrations`
- `raw_source_events`
- `audit_events`
- `config_snapshots`
- `risk_limit_snapshots`
- `strategy_config_snapshots`
- `promotion_criteria_snapshots`
- `acceptance_runs`
- `strategy_versions`
- `signals`
- `trade_theses`
- `risk_checks`
- `paper_orders`
- `paper_fills`
- `paper_positions`
- `exit_decisions`
- `trade_outcomes`
- `post_trade_reviews`
- `memory_entries`
- `jobs`
- `worker_leases`
- `monitoring_sessions`
- `conflict_reviews`

## How The Pieces Work

The Stage 2 foundation is isolated under `walletscarper.stage2`. `Stage2Database.migrate()` applies versioned migrations and records applied migration versions. Immutable tables are protected by SQLite triggers that reject updates and deletes.

Raw source events and audit events are append-only logs. Config snapshot repositories create hashed immutable snapshot rows. The domain repository creates only skeleton contract rows needed for Sprint 1 validation. The paper trading service implements only the risk-before-order guard and does not simulate fills, positions, exits, or P&L.

The job queue stores durable jobs in SQLite. Leasing inserts immutable lease rows, marks jobs running, prevents a second worker from leasing the same running job, returns expired jobs to pending if attempts remain, and marks jobs failed when attempts are exhausted.

`project.health_check` reads config, database connectivity, migration state, current time, and feature flags. It does not create jobs, mutate source-of-truth tables, create risk checks, create orders, create fills, calculate P&L, touch keys, or call external trading APIs.

## Acceptance Criteria Satisfied

- Config foundation exists and loads test environment overrides.
- Migration/database setup exists and is tested.
- Raw source event log exists and is append-only.
- Audit event log exists and is append-only.
- Config snapshot entities exist and are protected.
- Core domain contract skeletons exist.
- `Signal` references `strategy_version_id` and `strategy_config_snapshot_id`.
- `RiskCheck` includes required scope, subject, snapshot, and timestamp fields.
- `PaperOrder` requires `signal_id` and `risk_check_id`.
- `PaperOrder` creation rejects missing, failed, or incompatible risk checks.
- Durable job rows and worker leases exist.
- Lease acquisition, double-lease prevention, expiry, and max attempts are tested.
- Monitoring session and conflict review skeletons exist.
- Risk, paper trading, and evaluation service boundaries exist.
- Harmless `project.health_check` exists and is tested as read-only.
- No new live execution/private-key/signer/swap/DEX path was added in the recreated `walletscarper` package.

## Acceptance Criteria Not Satisfied Or Carried Forward

- Legacy WalletScarper was restored after the Stage 2 foundation work, but it has not yet been re-audited end-to-end against the Sprint 2 source-quality requirements.
- Existing legacy paper-trade behavior remains pre-existing Final Free v1 behavior, not the Stage 2 `Signal -> RiskCheck -> PaperOrder` workflow. It must not be treated as Stage 2 paper ledger behavior.
- Legacy source adapters use DEX/swap terminology for observed market data. That is not live execution, but Sprint 2 must explicitly separate data ingestion vocabulary from forbidden execution/swap modules.
- Hermes MCP packaging remains a local tool-boundary stub; no installed Hermes MCP server registration was added in Sprint 1.

## Intentionally Not Implemented

- Token discovery.
- GMGN integration.
- Solana RPC/indexer integration.
- Wallet intelligence behavior.
- WalletScarper refactor.
- Signal generation intelligence.
- Strategy search.
- Paper fill simulation.
- P&L calculation.
- Metrics engine behavior.
- Dashboard.
- Browser automation.
- Multi-agent workflows.
- Live/shadow execution behavior.
- Private key management.
- DEX/swap execution.

## Assumptions

- SQLite with `aiosqlite` is acceptable for Sprint 1 because the restored project uses Python and SQLite, and the almanac leaves database choice open.
- Stage 2 code should remain isolated from legacy WalletScarper until that code is audited and adapted through explicit source-event boundaries.
- Risk checks used in Sprint 1 tests are explicit deterministic fixtures inserted with `created_by_service='risk_service'`; actual risk calculation remains out of scope.
- `project.health_check` is a local tool boundary/stub until Hermes MCP/tool packaging is configured.

## Deviations

- The legacy project had to be restored by the operator after an implementation-session filesystem mistake. This is not an architectural decision.
- Stage 2 foundation code was added as an isolated package instead of refactoring legacy WalletScarper modules. This matches the Sprint 1 non-goal of not refactoring WalletScarper.

## Validation

Validation run on 2026-05-14:

- Created a temporary local `.venv` because the available `python` launcher was a Windows placeholder and the bundled Python did not include project dependencies.
- Installed `requirements.txt` plus `pytest` into that temporary environment.
- `.\.venv\Scripts\python.exe -m pytest`: passed, 10 tests.
- `.\.venv\Scripts\python.exe -m walletscarper stage2-migrate`: passed and applied `stage2_foundation_schema`.
- `.\.venv\Scripts\python.exe -m walletscarper project-health-check`: passed and returned `database_connectivity: ok`, `migration_status: current`, and disabled trading/live-execution feature flags.
- `python -m compileall walletscarper`: passed.
- `rg -n -i "private_key|secret_key|seed phrase|signTransaction|sendTransaction|VersionedTransaction|swap adapter|dex transaction|jupiter|raydium" WalletScarper\walletscarper -g "*.py"`: no matches. `rg` returned exit code 1 because no matches is represented as non-zero.

Generated validation artifacts (`.venv`, `.pytest_cache`, bytecode, and the smoke-test SQLite file) were removed after validation.

Additional operator validation after legacy restoration is recorded above. This documentation did not expose restored environment secrets.

## Carry Forward

- Re-run the legacy module audit from the restored filesystem before Sprint 2 integration work.
- Adapt legacy source outputs into `RawSourceEvent` with source confidence, observed/ingested timestamps, payload provenance, and quality metadata.
- Keep legacy paper-trade tables separate from Stage 2 paper ledger records until Sprint 3 implements the risk-gated workflow.
- Review legacy signer/DEX/swap terminology and document which paths are data parsing only versus forbidden execution behavior.
