# Sprint 3 - Integrated Signal, Deterministic Risk, And Paper Trading Workflow

## Status

Sprint 3 is implemented and validated as a paper-only research workflow.

The implemented lifecycle is:

`Signal -> TradeThesis -> entry RiskCheck -> PaperOrder -> entry PaperFill -> PaperPosition -> monitoring job/session -> ExitDecision -> exit RiskCheck -> exit PaperFill -> TradeOutcome`

No Sprint 4 strategy search, strategy promotion/demotion/kill logic, memory curator workflow, Hermes autonomous trading workflow, live execution, private-key handling, signing, swap adapter, or DEX transaction path was implemented.

## Documentation Inspected

- `docs/implementation-almanac/sprints/sprint-3-signal-risk-paper.md`
- `docs/implementation-almanac/contracts/domain-contracts.md`
- `docs/implementation-almanac/contracts/service-api-contracts.md`
- `docs/implementation-almanac/contracts/config-snapshots.md`
- `docs/implementation-almanac/01-system-invariants.md`
- `docs/implementation-almanac/02-architecture-decisions.md`
- `docs/implementation-almanac/decisions/ADR-0002-risk-before-paper-order.md`
- `docs/implementation-almanac/decisions/ADR-0003-no-live-execution.md`
- `docs/trading/11-paper-trading-framework.md`
- `docs/trading/12-evaluation-metrics.md`
- `docs/trading/13-risk-management-and-live-readiness.md`
- `docs/research/09-signal-generation.md`
- `docs/research/10-strategy-search-and-self-improvement.md`
- `docs/delivery/16-acceptance-criteria.md`
- `docs/implementation-progress/README.md`
- `docs/implementation-progress/sprint-1-foundation.md`
- `docs/implementation-progress/sprint-2-data-wallet-intelligence.md`

## Implemented

- `SignalService.create_signal(payload)` creates canonical Stage 2 `signals` from Sprint 2 evidence references only.
- `SignalService.create_no_trade_signal(payload)` creates first-class `no_trade_signals` and logs rejected/missed opportunity evidence where requested.
- `SignalService.create_trade_thesis(signal_id, payload)` creates a pre-entry thesis and detailed thesis record before entry risk begins.
- `DeterministicRiskService` creates authoritative entry, exit, and position-monitoring `risk_checks`.
- `Sprint3PaperTradingService.create_paper_order()` rejects missing, failed, mismatched, non-authoritative, or incompatible risk checks and requires a prior thesis.
- `Sprint3PaperTradingService.simulate_entry_fill()` creates conservative paper entry fills with timestamp checks, fees, slippage, latency assumption, liquidity constraint, failed-fill reasons, and filled size.
- `Sprint3PaperTradingService.open_position_from_fill()` opens positions only from successful entry fills and creates monitoring sessions and jobs.
- `Sprint3PaperTradingService.create_exit_decision()` creates timestamped exit decisions before any exit fill.
- `Sprint3PaperTradingService.execute_paper_exit()` requires a passed matching exit risk check and creates conservative paper-only exit fills.
- `DeterministicEvaluationService.calculate_trade_outcome()` calculates canonical paper `TradeOutcome` from successful entry and exit fills, fees, slippage, size, and timestamps.
- `DeterministicEvaluationService.baseline_dashboard_snapshot()` and CLI command `stage2-dashboard` provide baseline workflow counts and realized outcome summaries.
- Rejected/no-trade/missed/failed-fill paths are logged through append-only evidence logs.
- Sprint 2 wallet metric ordering was tightened to sort same-timestamp reconstructed trades by `created_at` before ID, making historical wallet estimates deterministic.

## Files Created Or Modified

- `WalletScarper/walletscarper/stage2/db/migrations.py`
- `WalletScarper/walletscarper/stage2/domain/models.py`
- `WalletScarper/walletscarper/stage2/domain/__init__.py`
- `WalletScarper/walletscarper/stage2/signals/__init__.py`
- `WalletScarper/walletscarper/stage2/signals/service.py`
- `WalletScarper/walletscarper/stage2/risk/service.py`
- `WalletScarper/walletscarper/stage2/risk/interfaces.py`
- `WalletScarper/walletscarper/stage2/risk/__init__.py`
- `WalletScarper/walletscarper/stage2/paper_trading/service.py`
- `WalletScarper/walletscarper/stage2/paper_trading/interfaces.py`
- `WalletScarper/walletscarper/stage2/paper_trading/__init__.py`
- `WalletScarper/walletscarper/stage2/evaluation/service.py`
- `WalletScarper/walletscarper/stage2/evaluation/interfaces.py`
- `WalletScarper/walletscarper/stage2/evaluation/__init__.py`
- `WalletScarper/walletscarper/stage2/wallet_intelligence/service.py`
- `WalletScarper/walletscarper/__main__.py`
- `WalletScarper/tests/test_stage2_sprint3_signal_risk_paper.py`
- `docs/implementation-progress/README.md`
- `docs/implementation-progress/sprint-2-data-wallet-intelligence.md`
- `docs/implementation-progress/sprint-3-signal-risk-paper.md`

## Schema Changes

Migration `4`, `stage2_signal_risk_paper_workflow_schema`, adds:

- `no_trade_signals`
- `trade_thesis_details`
- `paper_position_events`
- `rejected_trade_logs`
- `missed_opportunity_logs`

Migration `4` also adds append-only protections for those tables and for `paper_positions`, and adds a guard preventing `trade_outcomes` from being inserted with `calculated_by_service` other than `evaluation_service`.

Migration `5`, `stage2_paper_fill_size_schema`, adds:

- `paper_fills.filled_size`

This lets conservative entry fills record actual filled size when liquidity caps reduce the simulated entry below intended size. Exit fills fail closed if liquidity cannot cover the full open paper position.

Existing Sprint 1 tables remain the canonical tables for `signals`, `trade_theses`, `risk_checks`, `paper_orders`, `paper_fills`, `paper_positions`, `exit_decisions`, and `trade_outcomes`.

## How The Workflow Works

`SignalService` resolves Sprint 2 evidence from token profiles, token candidates, market snapshots, wallet profiles, wallet clusters, wallet trades, wallet metric snapshots, normalized evidence refs, and browser extraction context when provided. A signal requires source refs and a strategy version/config snapshot pair. A no-trade signal is a separate append-only record; it is not a failed trade.

`TradeThesis` creation writes the existing `trade_theses` contract row plus `trade_thesis_details`, which records why the token, why now, evidence refs, planned exit logic, invalidation condition, what would prove the thesis wrong, and uncopyable-risk notes. The service rejects thesis creation after an entry risk check has started.

`DeterministicRiskService` creates authoritative `risk_checks` with `created_by_service='risk_service'`. It checks stale or missing market snapshots, source/evidence confidence, degraded/unavailable source flags, minimum liquidity, estimated slippage, max open positions, max notional, and open-position conflict where data exists. Failed checks log rejected trade evidence.

`Sprint3PaperTradingService` enforces risk-before-order. Entry paper orders require a passed authoritative entry risk check for the same signal, compatible config snapshots, and a prior thesis. Fills use current configured assumptions from the risk limit snapshot for stale-data, fees, slippage, latency, and liquidity fraction. Failed fills are explicit rows. Successful entry fills open positions and create monitoring session/job records.

Exit flow requires `ExitDecision` first, then a deterministic exit risk check, then a conservative paper exit fill. There is no free-text `close_position(position_id, reason)` API. Position closure is inferred from the presence of a deterministic `TradeOutcome` rather than mutating `paper_positions.status`; this preserves append-only position records while still allowing dashboard open/closed counts.

`DeterministicEvaluationService` calculates canonical paper outcome only from successful entry/exit fills and costs. It computes gross P&L, net P&L after fees, total slippage cost, duration, and a basic max drawdown placeholder based on realized net outcome. It does not calculate strategy promotion metrics.

## Acceptance Criteria Satisfied

- Signal creation exists.
- NoTradeSignal creation exists.
- TradeThesis exists and is required before order.
- Entry RiskCheck is deterministic and authoritative.
- PaperOrder can only be created from approved Signal plus passed entry RiskCheck.
- Conservative entry fill simulation exists.
- PaperPosition opens only from successful fill.
- Open position creates monitoring job/session.
- Position monitoring risk check exists.
- ExitDecision exists before exit fill.
- Exit RiskCheck exists and is deterministic.
- Paper exit simulation exists.
- TradeOutcome is calculated deterministically from fills/costs.
- Fees, slippage, latency, and liquidity constraints are included.
- Failed fills are represented.
- Rejected/no-trade/missed opportunities are logged.
- Signal/thesis/order/fill/exit/outcome records are append-only or protected.
- Baseline dashboard/metrics view exists through `stage2-dashboard` and the evaluation service.
- Tests validate no-hindsight and risk-before-order invariants.
- Prior Sprint 1 and Sprint 2 tests pass.
- No Sprint 4 strategy search or memory workflow was added.
- No live execution/private-key/signer/swap/DEX path was added.

## Acceptance Criteria Not Satisfied

No Sprint 3 acceptance criteria remain knowingly open in the implemented paper-only workflow.

Important limitation: `paper_positions.status` is not mutated to `closed` because `paper_positions` is now append-only. Closed status is derived from `trade_outcomes` and position events. This is an intentional implementation choice to preserve critical-record immutability.

## Intentionally Deferred

- Sprint 4 strategy self-search.
- Strategy promotion/demotion/kill decisions.
- Hermes autonomous trading workflows.
- Memory curator.
- Full dashboard UI.
- Real-time position monitoring worker implementation beyond durable job/session creation.
- Advanced drawdown path calculation from intra-trade market path.
- Strategy performance metrics beyond read-only baseline counts and realized closed outcome summary.
- Live/shadow execution behavior.
- Private key handling, signing, swap adapters, DEX transaction construction, or real order placement.
- Legacy `paper_trades` migration.
- Legacy FIFO PnL as Stage 2 evaluation truth.
- Legacy wallet scores as strategy proof.

## Incomplete Or Risky Items

- Fill simulation is conservative but intentionally simple. It uses configured bps/fraction assumptions and does not yet model order book depth or multi-hop routing.
- Exit fills fail closed when liquidity cannot cover the full open paper position; partial exits are not modeled yet.
- Max drawdown is a deterministic placeholder based on closed outcome because Sprint 3 does not yet maintain an intra-position price path.
- Source quality is consumed from Sprint 2 evidence flags and source health snapshots, but no real Stage 2 network ingestion workers are implemented here.

## Tests Added

`WalletScarper/tests/test_stage2_sprint3_signal_risk_paper.py` covers:

- Signal creation from Sprint 2 evidence.
- NoTradeSignal logging without paper records.
- TradeThesis requirement and immutability after entry risk starts.
- Deterministic entry risk pass and stale-data veto.
- Rejection of missing, failed, mismatched, duplicate, and non-authoritative risk checks for orders.
- Conservative entry fill fees/slippage/latency.
- Stale fill failure and failed-fill no-position behavior.
- Liquidity cap through `paper_fills.filled_size`.
- Position creation and monitoring job/session creation.
- Position monitoring risk check.
- ExitDecision requirement before exit fill.
- Exit risk matching.
- Conservative exit fill fees/slippage/latency.
- Deterministic TradeOutcome with fees and slippage.
- Prevention of non-evaluation-service outcome insertion.
- Rejected/no-trade/missed opportunity logs.
- Baseline dashboard snapshot.
- No free-text close-position API.

Existing Sprint 1 and Sprint 2 tests also remain in the full suite.

## Validation

Validation run on 2026-05-14:

- `.\.venv\Scripts\python.exe -m pytest tests\test_stage2_sprint3_signal_risk_paper.py -q`: passed, 5 tests.
- `.\.venv\Scripts\python.exe -m pytest -q`: passed, 37 tests.
- `.\.venv\Scripts\python.exe -m compileall walletscarper`: passed.
- `.\.venv\Scripts\python.exe -m walletscarper stage2-migrate`: passed; migrations 1-5 applied to `data\stage2_foundation.sqlite3`.
- `.\.venv\Scripts\python.exe -m walletscarper project-health-check`: passed; `database_connectivity: ok`, `migration_status: current`, applied migrations 1-5.
- `.\.venv\Scripts\python.exe -m walletscarper stage2-dashboard`: passed; returned read-only baseline metrics snapshot.
- Dangerous-term `rg` scan: completed. Matches are documentation prohibitions, read-only market-data naming, read-only parsed RPC metadata, or historical legacy naming. No dangerous live execution path was found.

The system `python` command in this Windows environment is a stub and returns only `Python`; validation used the repository virtual environment at `WalletScarper\.venv\Scripts\python.exe`.

## Dangerous-Term Scan Classification

Command run:

```powershell
rg -n -i "private_key|secret_key|seed phrase|signer|signTransaction|sendTransaction|VersionedTransaction|\bswap\b|\bswaps\b|jupiter|raydium|dex transaction|live trade|execute trade|order placement" WalletScarper\walletscarper docs\implementation-progress docs\implementation-almanac docs\research docs\architecture -g "*.py" -g "*.md"
```

| Finding Area | Classification | Notes |
|---|---|---|
| `docs/implementation-almanac/**`, `docs/architecture/**`, `docs/implementation-progress/**` | Harmless config/doc reference | Architecture prohibitions, acceptance criteria, and execution-record statements. |
| `WalletScarper/walletscarper/sources/dexpaprika.py` | Read-only market-data terminology | Uses a provider endpoint/key named `swaps`; no execution path. |
| `WalletScarper/walletscarper/services/transactions.py` | Read-only market-data terminology / read-only RPC parsed metadata | Normalizes observed trade rows; parsed account metadata uses a `signer` field returned by read-only transaction parsing. |
| `WalletScarper/walletscarper/sources/solana_rpc.py` | Read-only RPC parsed metadata | Reads account-key `signer` metadata from `getTransaction`; does not sign. |
| `WalletScarper/walletscarper/services/backfill.py` and `services/scoring.py` | Historical/legacy naming only | Variable names for observed legacy trade rows and FIFO candidate evidence. |
| New Sprint 3 Stage 2 modules | No dangerous code matches | No private-key, transaction signing, live order, or DEX execution path was added. |

No secrets or environment values were printed or copied.

## Assumptions

- Sprint 2 evidence records are the only valid source input for Sprint 3 signal/no-trade records.
- Non-authoritative risk-check rows may exist for test/manual proposal evidence, but the paper workflow accepts only `created_by_service='risk_service'`.
- Configurable fill assumptions in risk limit snapshots are sufficient for Sprint 3 conservative simulation.
- Position closure can be represented append-only by `TradeOutcome` and `paper_position_events` instead of mutating `paper_positions`.
- A CLI/read-only service snapshot satisfies the Sprint 3 baseline visibility requirement; a full dashboard UI belongs later.

## Blockers

No blockers remain for Sprint 3 scope.

## Carry Forward To Sprint 4

- Build real monitoring workers around existing position monitoring jobs/sessions.
- Add strategy self-search and promotion/demotion/kill only after Sprint 3 outcomes accumulate.
- Expand evaluation metrics beyond baseline closed-outcome summary.
- Improve drawdown calculation using observed intra-position market snapshots.
- Decide whether partial exits require a dedicated exit order/fill/position event model.
- Keep live execution, private-key handling, signing, swap adapters, and DEX transaction construction excluded unless a later approved Stage 3 design explicitly introduces shadow/live boundaries.
