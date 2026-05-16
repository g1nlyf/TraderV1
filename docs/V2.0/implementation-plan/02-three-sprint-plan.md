# Three Sprint Implementation Plan

## Sprint 1: Agentic Token And Wallet Intelligence Foundation

### Goal

Build the V2 evidence and decision foundation so Token Selection Agent and Wallet Intelligence Agent can operate over real structured artifacts rather than legacy script scores.

### Final Result

At the end of Sprint 1, the system can select a token for deeper research, parse the best available token trade corpus, extract candidate wallets, calculate wallet metrics including P&L and win rate estimates, and store an AI wallet review that clearly says include/probation/watch/reject with reasons and data sufficiency.

No paper orders are created in Sprint 1.

### Deliverables

1. Add V2 schema extensions:
   - `token_agent_decisions`;
   - `token_trade_corpora`;
   - `wallet_token_outcomes`;
   - `agent_wallet_reviews`;
   - `wallet_forward_contributions`;
   - `active_token_sessions`;
   - `agent_trading_decisions`.

2. Normalize legacy outputs into Stage 2/V2 evidence:
   - map legacy `tokens`, `pools`, `token_snapshots`, `pool_transactions`, `wallet_scores`, `tracked_wallets` into append-only V2-compatible artifacts;
   - preserve legacy tables as adapter state, not source of truth.

3. Implement token intelligence upgrade:
   - holder count and concentration fields where data source supports it;
   - market cap/FDV/liquidity/volume growth windows;
   - tradeability and source-quality summaries;
   - `TokenAgentDecision` service.

4. Implement token trade corpus:
   - fetch recent available trades for selected token/pool;
   - store corpus metadata and coverage;
   - derive wallet list from corpus;
   - mark coverage gaps honestly.

5. Implement wallet funnel prefilter:
   - calculate token-specific wallet ROI/P&L;
   - bucket ROI from 20% upward;
   - require notional/sample/timestamp quality;
   - produce `WalletTokenOutcome`.

6. Implement broader wallet profiler:
   - recent multi-token history where sources support it;
   - total P&L estimate;
   - win rate estimate;
   - average win/loss, payoff ratio, holding time, position size, concentration;
   - bot-like and copyability flags;
   - source-quality output;
   - data sufficiency status: `sufficient`, `partial`, `insufficient`.

7. Implement Wallet Intelligence Agent review storage:
   - `AgentWalletReview` service;
   - elite/probation/watch/reject decisions;
   - reasons, observed behavior, inferred behavior, unknowns and demotion triggers;
   - explicit "interesting wallet, insufficient data" outcome.

8. Add Hermes tools for Token and Wallet agents:
   - `token.scan_universe`;
   - `token.get_profile`;
   - `token.request_deep_parse`;
   - `token.record_agent_decision`;
   - `wallet.extract_from_token`;
   - `wallet.profile_history`;
   - `wallet.get_metrics`;
   - `wallet.record_agent_review`;
   - `wallet.list_elite`.

### Acceptance Gates

- A selected token can produce a trade corpus, wallet candidates and token-specific wallet outcomes.
- A candidate wallet can be profiled across recent history with P&L and win rate estimates where data exists.
- If wallet history is shallow, the review records insufficient data instead of inventing a wallet personality.
- Wallet Intelligence Agent can store include/reject/probation/watch decisions with reasons.
- Hermes can call token/wallet tools without raw SQL and without mutating paper ledger.
- Existing Stage 2 tests still pass.

## Sprint 2: Hermes Orchestrator And Safe Paper/Shadow Decision Path

### Goal

Turn Hermes from read-only operator into the active Trading Orchestrator that can combine token-agent decisions, wallet-agent ratings, wallet signals and market evidence into auditable paper/shadow decisions.

### Final Result

At the end of Sprint 2, Hermes can receive a tracked wallet signal, inspect the token and wallet context, write a pre-action `AgentTradingDecision`, create `Signal` or `NoTradeSignal`, request deterministic risk, and create a paper/shadow order only if risk passes. Hermes still does not run the full continuous high-frequency market daemon; Sprint 2 proves the safe orchestrated decision path.

### Deliverables

1. Update Hermes persona and toolset:
   - replace read-only operator framing with Trading Research Director framing;
   - preserve forbidden live/private-key boundaries;
   - add write-safe tools from `almanac-v2/02-hermes-tool-contracts.md`.

2. Implement tracked wallet signal intake:
   - monitor elite/probation wallets for buys and sells using available sources;
   - dedupe transactions;
   - measure source/event latency;
   - collapse correlated cluster signals;
   - emit signal events to jobs/sessions.

3. Implement Hermes trading decision workflow:
   - create `AgentTradingDecision`;
   - link decision to token, wallets, market snapshots, browser/API evidence and memory;
   - create `Signal` or `NoTradeSignal`;
   - request deterministic entry risk;
   - request paper/shadow order only after passed risk;
   - record wait/skip/downgrade decisions.

4. Implement basic exit orchestration:
   - observe tracked wallet sells;
   - combine exit signals with market state and wallet profile;
   - create `ExitDecision`;
   - request exit risk check;
   - simulate exit fill;
   - calculate deterministic outcome.

5. Implement first forward attribution:
   - link paper outcomes to Hermes decisions;
   - link decisions to source wallets and token-agent decisions;
   - create post-trade review and memory proposals;
   - produce wallet contribution draft report.

### Acceptance Gates

- A tracked wallet buy can trigger Hermes analysis.
- Hermes can choose signal/no-trade/wait from combined evidence.
- Risk engine can veto Hermes decisions.
- A complete paper/shadow entry and exit can be produced from Hermes decisions.
- Wallet exits can influence exit decisions without being hardcoded as automatic exits.
- Agent decisions, paper outcomes and wallet contribution draft reports are linked.
- No private keys, signer, DEX transaction builder or real live execution path exists.

## Sprint 3: Adaptive Market Loop, Continuous Runtime And V2 Acceptance

### Goal

Build the continuous runtime around Hermes and the agents: adaptive market sessions, priority-aware polling, honest source degradation, forward wallet competition, dashboards and final V2 acceptance.

### Final Result

At the end of Sprint 3, the system runs as the requested agentic trading research loop: AI selects tokens, AI rates wallets, Hermes orchestrates paper/shadow decisions, active sessions collect market evidence at adaptive cadence, open positions receive highest priority, weak sources reduce cadence honestly, and the V2 acceptance report shows what is proven, what is gap-limited and whether forward paper/shadow P&L is improving.

### Deliverables

1. Implement active token session engine:
   - `ActiveTokenSession` lifecycle;
   - priority states: passive watch, active watch, open position, degraded, archived;
   - recent-window query;
   - source health and stale-data gating;
   - exit checks prioritized over new research.

2. Implement adaptive cadence policy:
   - normal watched tokens use lower-frequency polling;
   - active tokens use higher-frequency polling only when source health supports it;
   - open paper/shadow positions get highest-priority polling;
   - one-second snapshots/candles are allowed only for high-priority active/open-position sessions where sources can sustain it;
   - source rate limits, lag or errors lower cadence and write degradation flags.

3. Implement continuous worker daemon:
   - Stage 2/V2 worker process;
   - durable leases and recovery;
   - priority queue for open positions, exits, wallet signals and token research;
   - bounded parallelism.

4. Implement forward learning:
   - calculate wallet forward contribution;
   - calculate token selection outcome;
   - attribute paper outcomes to Hermes decision classes;
   - promote/demote wallets based on forward evidence;
   - update strategy and memory artifacts.

5. Add dashboard and reports:
   - active sessions and cadence state;
   - source degradation and cadence reductions;
   - elite/probation wallet leaderboard;
   - wallet data sufficiency warnings;
   - Hermes decisions, no-trades, paper positions and outcomes.

6. Add final V2 acceptance:
   - fixture and live-observation modes;
   - no-hindsight invariant checks;
   - risk/accounting invariant checks;
   - source cadence degradation report;
   - wallet data sufficiency report;
   - paper/shadow P&L, expectancy, win rate and drawdown summary.

### Acceptance Gates

- Active sessions run with adaptive cadence, not fixed one-second polling for every token.
- Open paper/shadow positions outrank new token research.
- If sources cannot sustain high cadence, the system lowers cadence and records the degradation.
- Hermes can still make wait/no-trade/degrade decisions when source freshness is insufficient.
- Wallet profiles with weak history remain marked as insufficient or probationary.
- Wallet forward contribution can promote or demote tracked wallets.
- V2 acceptance report clearly separates proven paper results, shadow gaps, cadence/source limitations and wallet-data insufficiency.
- Existing Stage 2 safety boundaries remain intact.

## Completion Definition

After Sprint 3, the system should match the requested concept:

- AI agent selects tokens.
- AI agent selects and rates wallets.
- Hermes orchestrates market decisions from combined evidence.
- Scripts are data/tools, not the trader.
- Best wallets compete in a maintained database.
- Market polling is adaptive and source-aware.
- The system learns through forward paper/shadow P&L, not retrospective stories.
