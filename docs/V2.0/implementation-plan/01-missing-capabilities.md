# Missing Capabilities For V2.0

## Critical Gaps

### 1. Hermes Is Not Yet Running As A Sustained Trading Orchestrator

Hermes now has a Trading Research Director plugin and write-safe tools that can create token/wallet decisions, signals, no-trades, risk check requests, paper/shadow orders, exit decisions, reviews and memory proposals. The remaining gap is runtime autonomy: Hermes is not yet continuously choosing tokens, rating wallets and reacting to live signals without manual prompting.

Needed:

- run a sustained Hermes review/orchestration loop;
- keep deterministic services as authority for risk/accounting;
- preserve full audit trail;
- add operator controls for when Hermes should pause, resume or degrade.

### 2. Token Selection Agent Is Not Continuous

Current token triage and Stage 2 tools work over real discovery events, but token choice is still not a sustained AI loop.

Needed:

- richer token profile inputs: holders, concentration, market cap/FDV, growth windows, liquidity/route quality, source freshness;
- token active/passive watchlists;
- autonomous Hermes policy for choosing which candidate becomes active watch.

### 3. Wallet Funnel Needs More High-Confidence Depth

Current code can build token corpora, extract wallets, calculate token-specific wallet outcomes and profile wallet history with legacy fallback. It still does not guarantee normalized Stage 2 wallet trades or broad multi-source history for every candidate.

Needed:

- normalized Stage 2 wallet-trade ingestion, not only legacy fallback;
- fuller recent wallet history profiler across multiple sources;
- data-source strategy for wallets beyond a single pool;
- stronger sample-size, concentration and copyability checks.
- explicit data sufficiency status so the agent can say "interesting wallet, insufficient data" when history depth is weak.

### 4. Wallet Intelligence Agent Reviews Are Not Populated At Scale

Agent review storage exists, but the database is not yet populated from the new real wallet outcomes by a sustained AI wallet-review loop.

Needed:

- elite/probation/watch/reject database;
- "why yes", "why no", demotion triggers;
- wallet personality model;
- strict separation between observed behavior, inferred behavior and unknowns;
- forward contribution calculations by wallet.

### 5. Tracked Wallet Signals Are Connected But Not Complete Enough

Legacy `LiveMonitor` now emits Stage 2 `tracked_wallet_signal_events` with `input_mode=real_source`, but it still checks the latest known row in `pool_transactions`. It does not independently stream every tracked wallet transaction.

Needed:

- tracked-wallet monitor against Solana/indexer/Bitquery/Helius-compatible sources;
- transaction event bus;
- dedupe and latency measurement;
- buy and sell signal handling;
- wallet-cluster signal collapsing.

### 6. Adaptive Market Loop Is Missing

Current calibration wrappers can record quote observations, but Hermes does not control an adaptive active market loop. A fixed one-second cadence for every token is too heavy for free public sources and would create false confidence when sources rate-limit or lag.

Needed:

- active token sessions;
- cadence policy by priority: normal watched tokens slower, active tokens faster, open positions highest priority;
- one-second snapshots/candles only for high-priority active/open-position sessions where sources support it;
- honest cadence degradation when sources cannot sustain requested polling;
- recent-window query tool;
- 2-10 second Hermes review loop;
- exit-priority queueing;
- stale-data blocks.

### 7. Forward Learning Is Not Connected To Agent Choices

Stage 2 can calculate paper outcomes and strategy metrics, but it does not yet attribute performance to token agent choices, wallet reviews and Hermes trading decisions.

Needed:

- `AgentTradingDecision` records linked to `Signal`/`NoTradeSignal`;
- wallet forward contribution reports;
- token selection outcome reports;
- strategy comparison by agent decision class;
- memory proposals from post-trade reviews.

### 8. Shadow Readiness Remains Gap-Blocked

The current reports explicitly say Stage 3 shadow readiness is `gap_report_required`.

Needed:

- real observation-window evidence;
- source quote freshness;
- latency distribution;
- route-quality model;
- fill-vs-quote comparison with contemporaneous quotes.

## Important Non-Gaps

The project does not need real live execution for V2.0. It also does not need a new general multi-agent framework before the tool surface, wallet funnel and active market loop exist.

## Win Rate Decision

Win rate should be included and usually positive for wallet admission, but it must not be the main target.

Use it as:

- repeatability check;
- sample-quality check;
- lucky-wallet filter;
- payoff-ratio context;
- demotion signal when it collapses in forward testing.

Do not use it as:

- direct buy/sell rule;
- replacement for net P&L;
- proof of edge without sample size and costs.
