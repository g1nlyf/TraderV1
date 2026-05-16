# 11. Paper Trading Framework

## Purpose

Paper trading is the central proof stage. The system is not validated by backfilled stories, screenshots, wallet labels or high win rate. It is validated by timestamped decisions in real market conditions with realistic execution assumptions.

Paper mode and future live mode must share the same decision workflow, risk workflow, signal schema, monitoring logic and audit trail. The execution adapter is the only intended difference:

```text
same signal -> same risk check -> same order intent -> different execution adapter

paper adapter: simulated fill
live adapter: real transaction, only in future stages after gates
```

This prevents the system from learning a paper-only behavior that cannot be transferred to live conditions.

## Mandatory lifecycle

1. Token discovered.
2. Token triage started.
3. Wallet / market / liquidity / social context collected.
4. Trade thesis created.
5. Signal generated.
6. Risk check performed.
7. Paper order created.
8. Simulated fill calculated.
9. Paper position opened.
10. Monitoring loop started.
11. Exit trigger or exit thesis created.
12. Risk / exit check performed.
13. Simulated exit fill calculated.
14. P&L calculated deterministically.
15. Post-trade review performed.
16. Hypothesis updated.
17. Strategy version scored.
18. Memory updated.

## Parallel real-market paper trading

The system must support multiple tokens and paper positions at the same time.

Required controls:

- max monitored tokens;
- max open paper positions;
- max token sessions per strategy;
- max wallet-cluster sessions;
- position monitoring priority over new discovery;
- exit checks before new entries;
- stale token stop criteria;
- session state machine;
- attention allocation through priority queue.

Paper position monitoring must not be blocked by token discovery or social research. If resources are constrained, reduce new investigations before reducing open-position monitoring.

## Required fields per paper trade

Before entry:

- timestamp;
- token candidate;
- signal id;
- strategy version;
- source signal;
- pre-entry reasoning;
- confidence;
- risk estimate;
- expected holding time;
- invalidation condition;
- expected exit logic;
- risk check result;
- market snapshot;
- liquidity snapshot.

At simulated entry:

- paper order;
- simulated fill;
- fill timestamp;
- fill price;
- fees;
- slippage;
- latency model;
- liquidity constraints;
- failed-fill handling.

During monitoring:

- monitoring events;
- updated market snapshots;
- thesis status;
- risk status.

Before exit:

- exit decision timestamp;
- exit reason;
- exit trigger;
- expected exit behavior;
- risk/exit check.

After exit:

- simulated exit fill;
- gross P&L;
- fees;
- slippage;
- net P&L;
- drawdown;
- holding time;
- post-trade review;
- hypothesis update.

## Prohibited behavior

Forbidden:

- hindsight entry;
- hindsight exit;
- ideal entry/exit prices;
- future data;
- post-outcome signal creation;
- paper success without costs;
- LLM editing trade history;
- LLM calculating final metrics;
- ignoring failed fills;
- ignoring liquidity constraints.

## Fill simulation

The first final-system fill model may be simple, but it must be conservative, explicit and acceptance-tested.

Required components:

- data timestamp;
- entry latency;
- exit latency;
- fee model;
- slippage model;
- liquidity cap;
- failed-fill rules;
- stale price rejection;
- route quality estimate if available.

If simulation quality is weak, the trade can still be logged but evidence quality must be lower.

## Rejected and missed trades

The system must log:

- rejected trades;
- risk-vetoed trades;
- missed opportunities;
- signals without fills;
- failed fills;
- no-trade decisions.

Rejected trades are needed to measure whether risk filters and no-trade logic improve expectancy.

## Ledger policy

Paper ledger must be append-only for critical events. Corrections require new correction records, not silent edits.

Immutable:

- signal;
- thesis;
- risk check;
- order;
- fill;
- exit decision;
- outcome.

## Positive expectancy connection

Paper trading is the proof layer. Without realistic paper execution, the system cannot distinguish real edge from hindsight and optimistic fills.
