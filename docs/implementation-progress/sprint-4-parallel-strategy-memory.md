# Sprint 4 - Parallel Monitoring, Strategy Search And Memory

## Status

Implemented and validated as deterministic Stage 2 services, database schema, tests, and read-only reporting.

Sprint 4 remains paper-only. It does not start Sprint 5, does not implement final continuous acceptance, and does not add shadow/live execution, private-key handling, signing, swap adapters, DEX transaction construction, or a new agent framework.

## Documentation Inspected

- `docs/implementation-almanac/sprints/sprint-4-parallel-strategy-memory.md`
- `docs/implementation-almanac/00-master-build-map.md`
- `docs/implementation-almanac/01-system-invariants.md`
- `docs/implementation-almanac/02-architecture-decisions.md`
- `docs/implementation-almanac/contracts/domain-contracts.md`
- `docs/implementation-almanac/contracts/service-api-contracts.md`
- `docs/implementation-almanac/contracts/config-snapshots.md`
- `docs/implementation-almanac/decisions/ADR-0002-risk-before-paper-order.md`
- `docs/implementation-almanac/decisions/ADR-0003-no-live-execution.md`
- `docs/implementation-almanac/decisions/ADR-0004-job-queue-over-freeform-a2a.md`
- `docs/research/10-strategy-search-and-self-improvement.md`
- `docs/architecture/05-agent-architecture.md`
- `docs/trading/12-evaluation-metrics.md`
- `docs/delivery/16-acceptance-criteria.md`
- `docs/implementation-progress/README.md`
- `docs/implementation-progress/sprint-1-foundation.md`
- `docs/implementation-progress/sprint-2-data-wallet-intelligence.md`
- `docs/implementation-progress/sprint-3-signal-risk-paper.md`

## What Was Implemented

### Monitoring Session State Machine

Implemented `walletscarper.stage2.monitoring.service.MonitoringService`.

The service supports deterministic monitoring session creation and transitions across `created`, `queued`, `active`, `waiting`, `blocked`, `completed`, `failed`, `expired`, and `archived`. Each transition writes a row to `monitoring_session_transitions` with previous state, new state, reason, actor, timestamp, optional job id, optional audit event id, and metadata.

The service blocks invalid transitions, prevents terminal sessions from being reactivated except archival, prevents closed paper positions from being reactivated for monitoring, creates conflict reviews for duplicate active monitoring jobs, and can complete monitoring sessions for positions that already have deterministic `TradeOutcome` rows.

### Worker Pool, Leases, Heartbeats, And Artifacts

Implemented `walletscarper.stage2.workers.service.WorkerPoolService`.

The service adds worker registration, worker heartbeat, bounded lease acquisition by worker type, lease heartbeat/extension, stale lease expiry, job completion/failure/block wrappers, worker artifact recording, and queue metrics. Worker output is stored as a non-authoritative artifact. The durable `jobs` and `worker_leases` tables remain the workflow bus; no free-form agent chat bus was added.

Supported worker types are:

- `token_monitor`
- `position_monitor`
- `wallet_cluster_monitor`
- `strategy_experiment`
- `post_trade_review`
- `memory_curator`

### Parallelism And Priority Rules

Implemented immutable `parallelism_configs` and shared defaults in `walletscarper.stage2.parallelism`.

Configurable limits include:

- max active token monitoring sessions;
- max active wallet cluster sessions;
- max active strategy experiments;
- max active browser/research jobs;
- max concurrent worker leases;
- priority values for position, strategy, wallet-cluster, and token monitoring work.

Open paper position monitoring receives higher queue priority than token discovery-style monitoring. Capacity exhaustion delays new research work by scheduling it later and marking the session as `waiting`; it does not silently drop work.

### Conflict Review Flow

Implemented conflict review creation/resolution through `MonitoringService` and `walletscarper.stage2.conflicts.service.ConflictReviewService`.

The existing `conflict_reviews` table was extended with resolver, involved refs, and resolution metadata. Resolution records the deterministic basis such as risk veto, ledger state, deterministic metrics, source quality, or narrative review. Conflict resolution does not rewrite historical signals, risk checks, fills, outcomes, or metrics.

### Strategy Mutation Proposals

Implemented `strategy_mutation_proposals` and `StrategyResearchService.create_mutation_proposal`.

Allowed mutation categories:

- wallet scoring weights;
- signal combination;
- no-trade filter;
- confidence calibration;
- token bucket policy;
- expected holding-time hypothesis;
- wallet ranking hypothesis;
- exit logic variant;
- risk-filter candidate for deterministic review.

Forbidden mutation attempts are rejected, including attempts to change canonical P&L calculation, rewrite ledger/outcomes, disable fees/slippage/latency/failed fills, disable the risk engine, change live execution constraints, or request credential-material access.

### Strategy Versioning And Experiment Registry

Implemented `strategy_experiments` and strategy-version creation from mutation proposals. Material strategy mutations create child `StrategyVersion` records linked to the parent version and mutation proposal. Experiments require explicit budget, strategy config snapshot, promotion criteria snapshot, target/baseline refs where available, status, and audit refs.

Active strategy config snapshots remain immutable and cannot be silently edited.

### Leaderboard V1

Implemented deterministic leaderboard v1 in `StrategyResearchService.leaderboard_v1` and delegated `DeterministicEvaluationService.produce_leaderboard` to it.

Leaderboard rows are stored as append-only `strategy_metric_snapshots` derived only from deterministic Sprint 3 tables, especially `trade_outcomes`, `paper_positions`, `paper_fills`, `no_trade_signals`, and `rejected_trade_logs`.

Metrics include:

- closed paper trade count;
- open paper position count;
- rejected/no-trade counts;
- failed fill count;
- gross and net P&L from `trade_outcomes`;
- expectancy;
- win rate;
- profit factor where enough data exists;
- average win/loss where enough data exists;
- simple drawdown from deterministic outcome sequence;
- degraded outcome count;
- low sample-size warning;
- token concentration warning.

Legacy `paper_trades`, legacy FIFO PnL, and legacy wallet scores are not queried or used.

### Promotion, Demotion, Kill, Keep-Testing, And Insufficient-Data Decisions

Implemented `strategy_decisions` and `StrategyResearchService.decide_strategy`.

Every decision requires a `PromotionCriteriaSnapshot` and a deterministic metrics snapshot. Decisions fail closed to `insufficient_data` when closed trade sample size or outcome quality is inadequate. Promotion requires configured criteria to pass; narrative review alone cannot promote a strategy.

### Post-Trade Review

Implemented `post_trade_review_details` and `PostTradeReviewService`.

Reviews require an existing deterministic `TradeOutcome`, link the position, strategy version, signal, thesis, and outcome, summarize thesis expectations, actual result, fees/slippage impact, risk checks, fill quality, source quality issues, whether exit matched plan, bias/hindsight flags, lessons, and proposed mutation/memory refs.

Reviews are append-only artifacts and do not replace or rewrite `TradeOutcome`.

### Memory Proposal And Curation

Implemented `memory_proposals`, `memory_curation_events`, and `MemoryService`.

Memory proposals must be typed as fact, hypothesis, lesson, warning, or obsolete conclusion and must link to evidence, reviews, or strategy refs. Curation supports accept, reject, archive, and supersede. Accepted proposals create existing `memory_entries` records with provenance metadata. Memory cannot rewrite ledger, risk, fills, outcomes, or strategy history.

### Queue, Session, And Strategy Metrics

Implemented `Sprint4ReportService` and CLI command:

```powershell
python -m walletscarper stage2-sprint4-report
```

The report is read-only and shows queue/job status, worker status, active/expired leases, session status, monitored open positions, strategy experiments, latest leaderboard rows, strategy decisions, post-trade review count, memory proposal/curation counts, conflict review counts, and warnings for failed jobs, low sample size, degraded outcomes, and concentration.

## Files Created Or Modified

Created:

- `WalletScarper/walletscarper/stage2/parallelism.py`
- `WalletScarper/walletscarper/stage2/workers/__init__.py`
- `WalletScarper/walletscarper/stage2/workers/service.py`
- `WalletScarper/walletscarper/stage2/strategy/__init__.py`
- `WalletScarper/walletscarper/stage2/strategy/service.py`
- `WalletScarper/walletscarper/stage2/reviews/__init__.py`
- `WalletScarper/walletscarper/stage2/reviews/service.py`
- `WalletScarper/walletscarper/stage2/memory/__init__.py`
- `WalletScarper/walletscarper/stage2/memory/service.py`
- `WalletScarper/walletscarper/stage2/conflicts/__init__.py`
- `WalletScarper/walletscarper/stage2/conflicts/service.py`
- `WalletScarper/walletscarper/stage2/reports/__init__.py`
- `WalletScarper/walletscarper/stage2/reports/service.py`
- `WalletScarper/tests/test_stage2_sprint4_parallel_strategy_memory.py`
- `docs/implementation-progress/sprint-4-parallel-strategy-memory.md`

Modified:

- `WalletScarper/walletscarper/stage2/db/migrations.py`
- `WalletScarper/walletscarper/stage2/domain/repository.py`
- `WalletScarper/walletscarper/stage2/evaluation/service.py`
- `WalletScarper/walletscarper/stage2/monitoring/__init__.py`
- `WalletScarper/walletscarper/__main__.py`
- `docs/implementation-progress/README.md`

## Database And Migration Changes

Added migration `6 - stage2_parallel_strategy_memory_schema`.

New tables:

- `worker_registry`
- `monitoring_session_transitions`
- `worker_artifacts`
- `parallelism_configs`
- `strategy_mutation_proposals`
- `strategy_experiments`
- `strategy_metric_snapshots`
- `strategy_decisions`
- `post_trade_review_details`
- `memory_proposals`
- `memory_curation_events`

Extended table:

- `conflict_reviews`: added resolver, involved refs, and resolution metadata.

Append-only protections were added for worker artifacts, parallelism configs, strategy metric snapshots, strategy decisions, post-trade review details, and memory curation events. Mutation proposals, experiments, worker registry rows, memory proposals, sessions, jobs, leases, and conflict reviews remain mutable where status/heartbeat/resolution workflows require updates.

## Tests Added

Added `WalletScarper/tests/test_stage2_sprint4_parallel_strategy_memory.py`.

Coverage includes:

- monitoring session transitions and transition audit rows;
- worker registration, lease acquisition, heartbeat extension, stale lease expiry;
- per-worker and global lease capacity;
- max active token-session limit and delayed scheduling;
- open paper position monitoring priority;
- duplicate monitoring job conflict review;
- conflict resolution without rewriting ledger/risk/fill/outcome rows;
- strategy mutation proposal creation and forbidden mutation rejection;
- child `StrategyVersion` creation from mutation proposals;
- strategy experiment budget requirement;
- deterministic leaderboard/metrics snapshots from `trade_outcomes`;
- insufficient-data decision fail-closed behavior;
- promotion when configured criteria and deterministic metrics pass;
- post-trade review linkage to signal/thesis/outcome and append-only protection;
- memory proposal and curation workflow;
- read-only Sprint 4 report snapshot.

Existing Sprint 1, Sprint 2, and Sprint 3 tests still pass.

## Acceptance Criteria Satisfied

- Monitoring session state machine exists.
- Bounded worker pools and leases work.
- Heartbeats, expiry, and failure/block/complete paths exist.
- Max parallel investigation limits are enforced.
- Open paper positions receive priority through queue priorities.
- Conflict review flow exists and records resolution metadata.
- `StrategyMutationProposal` exists.
- `StrategyExperiment` / experiment registry exists.
- `StrategyVersion` parent/child mutation links exist.
- Strategy leaderboard v1 exists and uses deterministic outcomes only.
- Promotion/demotion/kill/keep-testing/insufficient-data decisions require `PromotionCriteriaSnapshot`.
- Insufficient data fails closed.
- `PostTradeReview` workflow exists and requires `TradeOutcome`.
- Memory proposal and curation workflow exists.
- Queue/session/strategy metrics exist through a read-only CLI/report service.
- Tests validate controlled parallelism, memory curation, review artifacts, strategy decision gates, and conflict behavior.
- All prior Sprint 1/2/3 tests pass.
- No Sprint 5 final acceptance run was started.
- No live execution/private-key/signer/swap/DEX path was added.

## Acceptance Criteria Not Fully Expanded

- Worker pools are implemented as deterministic service primitives and tested through direct service calls. No long-running daemon process was added.
- Monitoring workers record leases, state transitions, and artifacts. Source polling/business-specific worker bodies remain future work and must stay behind the existing source/evidence boundaries.
- Leaderboard v1 includes a simple deterministic drawdown placeholder from closed outcome sequence; a richer equity curve remains future work.
- Partial exits remain unsupported because Sprint 3 did not model partial exits.
- A polished dashboard UI was not implemented; Sprint 4 uses a read-only CLI/report.

## Intentionally Excluded

- Sprint 5 continuous acceptance run.
- Shadow/live execution.
- Live trading.
- Private-key handling.
- Signing.
- Swap adapters.
- DEX transaction construction.
- New agent frameworks.
- Free-form agent chat as state transport.
- Hermes direct mutation of source-of-truth tables.
- LLM-created authoritative risk checks.
- LLM-calculated canonical P&L.
- Narrative-only strategy promotion.
- Legacy `paper_trades`, FIFO PnL, or wallet scores as Stage 2 truth.
- Rewriting historical signals, theses, risk checks, fills, outcomes, or metrics.

## Assumptions

- Sprint 4 worker implementation can be service-level primitives rather than a continuously running daemon because the almanac requires durable worker pools, leases, heartbeats, artifacts, and metrics, not a production scheduler process.
- Promotion criteria snapshot JSON may use practical keys such as `min_closed_trades`, `min_forward_paper_trades`, `min_net_expectancy`, `min_cumulative_net_pnl`, `max_drawdown`, `max_degraded_outcomes`, and `kill_net_pnl_below`.
- Strategy comparison uses only deterministic Sprint 3 paper outcomes; open/rejected/no-trade/failed-fill counts are supporting context, not promotion proof by themselves.
- Memory entries are curated interpretation/evidence and may update their own status, but cannot mutate ledger/risk/fill/outcome/history tables.

## Remaining Risks And Carry-Forward Items

- Add a supervised worker runner/daemon only after Sprint 5 hardening requirements are defined and only if it uses the same DB-backed job/lease primitives.
- Expand drawdown from placeholder to deterministic equity curve once more complete position history is available.
- Add richer concentration warnings once source-linked token/wallet attribution is stronger.
- Define a typed Hermes tool layer for safe Sprint 4 operations if Hermes integration needs external invocation.
- Consider append-only event tables for mutable experiment/proposal status if later audit requirements become stricter.

## Validation

Commands run from `C:\Users\hacke\CascadeProjects\Finals1\TraderV1\WalletScarper` unless noted:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_stage2_sprint4_parallel_strategy_memory.py -q
```

Result: `5 passed`.

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Result: `42 passed`.

```powershell
.\.venv\Scripts\python.exe -m compileall walletscarper
```

Result: compile completed successfully.

```powershell
.\.venv\Scripts\python.exe -m walletscarper stage2-migrate
```

Result: Stage 2 migrations applied; migration 6 present in local Stage 2 database.

```powershell
.\.venv\Scripts\python.exe -m walletscarper project-health-check
```

Result: database connectivity `ok`; migration status `current`; migrations 1 through 6 applied; live execution feature flag remains false.

```powershell
.\.venv\Scripts\python.exe -m walletscarper stage2-sprint4-report
```

Result: read-only report returned queue/session/strategy/memory/conflict metrics without mutation.

Dangerous-term scan from repository root:

```powershell
rg -n -i "private_key|secret_key|seed phrase|signer|signTransaction|sendTransaction|VersionedTransaction|\bswap\b|\bswaps\b|jupiter|raydium|dex transaction|live trade|execute trade|order placement" WalletScarper\walletscarper docs\implementation-progress docs\implementation-almanac docs\research docs\architecture -g "*.py" -g "*.md"
```

Scan classification:

| Area | Terms | Classification | Notes |
|---|---|---|---|
| `WalletScarper/walletscarper/services/backfill.py` | `swaps` | Historical/legacy naming only | Refers to observed transaction rows from legacy collector. |
| `WalletScarper/walletscarper/services/scoring.py` | `swaps` | Historical/legacy naming only | Used for legacy FIFO-style scoring evidence; not Stage 2 evaluation. |
| `WalletScarper/walletscarper/services/transactions.py` | `swap`, `swaps`, `store_swap`, `signer` | Read-only market-data terminology / read-only RPC parsed metadata | Normalizes observed source transactions; `signer` is parsed account metadata from read-only RPC output. |
| `WalletScarper/walletscarper/sources/solana_rpc.py` | `signer` | Read-only RPC parsed metadata | Reads `getTransaction` account-key metadata; no signing operation. |
| `WalletScarper/walletscarper/sources/dexpaprika.py` | `swaps` | Read-only market-data terminology | Provider endpoint/key naming only. |
| `docs/**` | private-key, signer, swap, DEX transaction, order placement references | Harmless config/doc reference | Architecture prohibitions, ADRs, and progress documentation. |

No dangerous live execution path was found in scanned Python code. No new live execution/private-key/signer/swap/DEX path was added by Sprint 4.

