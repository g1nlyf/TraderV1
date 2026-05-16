# 14. Final System Delivery Plan

## Delivery philosophy

This project is not delivered as a reduced prototype. A half-connected subset of modules is not meaningful for this system because the hard problem is integration: data, agents, risk, paper trading, evaluation, memory and strategy search must work together.

The delivery model is therefore:

> Build the final Stage 2 system brick by brick, with Stage 3-compatible shadow execution design, dependency order and integration gates, but do not define a stripped-down product as the goal.

This does not mean building everything chaotically at once. It means every sprint builds a load-bearing part of the same final house. A sprint can be incomplete internally, but it is not considered a product release until the full final workflow is integrated, tested and accepted.

## Final system scope for this release

The final implemented system for this release is a **Hermes-based autonomous trading research and real-market paper trading system** for Solana memecoins, designed with Stage 3-compatible shadow execution boundaries.

Release target: **Stage 2 system with Stage 3-compatible shadow execution design**. Stage 3 shadow mode may be partially implemented where feasible, but full Stage 3 completion is not required for this release unless data quality supports it.

It includes:

- Hermes orchestration and research workflows;
- deterministic data ingestion and normalization;
- Solana / GMGN / DEX / browser research adapters where available;
- token discovery and triage;
- wallet intelligence and wallet cluster analysis;
- signal and no-trade generation;
- deterministic risk checks;
- immutable paper trading ledger;
- realistic paper/shadow fills;
- multi-token monitoring sessions;
- job queue and worker leases;
- strategy proposal and mutation policy;
- experiment registry and strategy comparison / leaderboard v1;
- deterministic P&L, expectancy and drawdown metrics;
- post-trade review;
- curated memory;
- dashboard and operational monitoring;
- hardening, tests and acceptance gates.

It does not include real-money autonomous execution. Future live execution remains a gated extension after evidence from the final paper/shadow system.

## Final workflow that must work end-to-end

The final system is accepted only when this loop runs continuously:

```text
discover tokens
  -> triage candidates
  -> create token monitoring sessions
  -> profile wallets and clusters
  -> generate signal or no-trade decision
  -> run risk check
  -> create paper order
  -> simulate fill
  -> monitor open paper position
  -> create exit decision
  -> simulate exit fill
  -> calculate net P&L deterministically
  -> run post-trade review
  -> update experiment registry
  -> update strategy leaderboard
  -> curate memory
  -> reprioritize queue
```

No document, sprint or implementation task should redefine success as a disconnected module demo.

## Five-sprint delivery plan

There are no more than five delivery sprints. Each sprint has an integration gate. The final sprint delivers the tested final system.

### Sprint 1 - Foundation, Environment And Source Of Truth

Goal: create the system foundation that later modules cannot bypass.

Build:

- repository structure for final system;
- runtime environment and configuration;
- Hermes connectivity smoke test and tool/MCP boundary;
- database schema;
- raw event log;
- source metadata model;
- immutable audit event model;
- core domain contracts and audit/event boundaries;
- job queue tables;
- monitoring session model;
- paper ledger/event skeleton;
- risk/P&L/evaluation service interfaces;
- test harness and smoke checks.

Integration gate:

- Hermes can call a harmless project tool.
- Hermes-driven trading/research workflows are not started yet.
- DB can store raw events, jobs, sessions and ledger records.
- Core contracts exist for Signal, TradeThesis, RiskCheck, PaperOrder, PaperFill, ExitDecision and TradeOutcome, even if behavior is implemented later.
- Append-only audit records work.
- Job lease/timeout mechanics work.
- P&L/risk services exist as deterministic boundaries, even if only with baseline rules.

Do not build signal intelligence before this foundation exists.
Hermes setup in Sprint 1 is only connectivity and boundary validation. Hermes-driven trading/research workflows start only after deterministic contracts exist.

### Sprint 2 - Data, Token Discovery And Wallet Intelligence

Goal: turn raw sources into normalized token and wallet intelligence that can feed trading decisions.

Build:

- Solana / DEX / GMGN / available market adapters;
- browser research adapter with confidence/degradation policy;
- source health and rate-limit handling;
- TokenCandidate and TokenProfile pipeline;
- token triage with priors as configurable buckets;
- wallet trade reconstruction;
- WalletProfile and WalletCluster;
- historical reconstructed wallet metrics: P&L, win rate, expectancy, holding time, payoff ratio, drawdown;
- farm/noise/copy-trader/cluster flags;
- evidence quality model.

Integration gate:

- The system can discover and triage real token candidates.
- Wallet intelligence can profile wallets from observed data.
- Browser-derived data is marked as non-canonical.
- Data quality and confidence are visible to downstream modules.
- Historical reconstructed wallet metrics are candidate evidence, not system strategy performance.

Do not create paper trades until data provenance and wallet evidence quality are stored.
Do not promote a strategy because a wallet was historically profitable. Strategy success is proven only through forward paper trades.

### Sprint 3 - Integrated Signal, Risk And Paper Trading Workflow

Goal: make the core trading research loop work end-to-end under no-hindsight rules.

Build:

- Signal and NoTradeSignal generation;
- TradeThesis schema;
- full behavior for Signal, TradeThesis, RiskCheck, PaperOrder, PaperFill, ExitDecision and TradeOutcome contracts;
- StrategyVersion attachment to every signal;
- deterministic risk checks;
- paper order creation;
- simulated entry/exit fills;
- fees/slippage/latency/failed-fill model;
- paper position monitoring;
- exit decision workflow;
- deterministic TradeOutcome calculation;
- rejected/missed trade logging;
- baseline dashboard.

Integration gate:

- A real token candidate can flow from discovery to signal/no-trade.
- Passing signals create paper orders through risk engine.
- Paper positions open, monitor, exit and calculate net P&L.
- Every decision is timestamped before outcome.
- Paper mode uses the same signal/risk/monitoring workflow intended for future live mode.

Do not add strategy self-search before this loop is reliable.

### Sprint 4 - Parallel Monitoring, Strategy Search And Memory

Goal: scale from one linear workflow to bounded autonomous research across many tokens, wallet clusters and strategy hypotheses.

Build:

- per-token monitoring sessions;
- per-paper-position monitoring sessions;
- per-wallet-cluster sessions;
- bounded worker pools;
- max parallel investigation limits;
- conflict review state;
- Strategy Proposal & Mutation Policy enforcement;
- experiment registry;
- strategy comparison / leaderboard v1;
- promotion/demotion/kill criteria;
- post-trade review agent;
- memory curator;
- failed assumption log;
- strategy leaderboard.

Integration gate:

- Multiple token sessions can run in parallel without corrupting state.
- Open paper positions receive priority over new research.
- Strategy mutations create new StrategyVersions.
- Agents cannot mutate ledger, P&L, costs or risk controls.
- Reviews update curated memory without rewriting history.

Do not increase agent count unless queue metrics and conflict rates remain healthy.

### Sprint 5 - Hardening, Shadow Mode And Final Acceptance

Goal: make the final system reliable enough to run continuously and decide whether it is ready for any future live-readiness work.

Build:

- full test suite;
- no-hindsight workflow tests;
- deterministic P&L tests;
- risk veto tests;
- ledger immutability tests;
- job queue failure/retry tests;
- source degradation tests;
- browser adapter failure tests;
- dashboard and alerting;
- operational metrics;
- shadow trading with live quotes where feasible under the Shadow Mode Gap rule;
- Shadow Mode Gap Report if high-quality live quote/shadow execution data is not available;
- final acceptance report.

Integration gate:

- System runs continuously.
- Multiple tokens and paper positions are monitored.
- Metrics show expectancy, P&L, drawdown, strategy comparison and operational health.
- Failures degrade safely.
- If high-quality live quote/shadow execution data is unavailable, Sprint 5 still completes the Stage 2 autonomous paper trading system and produces a Shadow Mode Gap Report instead of pretending Stage 3 is complete.
- Final acceptance criteria pass.
- Live execution remains disabled unless a separate future readiness decision is made.

## Non-release construction states

During development, the system may temporarily run partial flows for testing. These are not product states and must not be described as "working trading system".

Allowed temporary construction states:

- schema smoke tests;
- adapter smoke tests;
- isolated wallet reconstruction test;
- paper ledger unit test;
- one-token dry run;
- single strategy workflow test.

These are construction checks, not product releases.

## Final definition of done

The final system is done when it can run the full real-market paper trading research loop continuously, across multiple token sessions, with deterministic accounting, risk vetoes, strategy versioning, bounded parallel agents, curated memory and a dashboard that exposes whether strategies demonstrate positive net expectancy after realistic costs. If Stage 3-quality shadow execution cannot be completed due to data limitations, the system must explicitly document the gap rather than mark shadow mode complete.
