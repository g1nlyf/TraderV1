# H-067 — Stop-cluster reversion at round-number price levels

**Status:** proposed
**Zone:** FORCED-FLOW PREMIA
**Created:** 2026-06-05 (Session 5)

## Statement
Round-number price levels (10%, 20%, 30% declines from the prior 30d high, or psychologically
salient round dollar values) cluster stop-loss orders from retail traders and leveraged positions.
When price breaches a round level, a cascade of stops fires, creating a price overshoot below the
round number. The name reverts above the round level within 1–2 8h periods as the stop-cluster
is exhausted. Enter long (market-neutral) immediately after the breach, exit at reversion to or
above the round level.

## Quality filter
- **Who is FORCED & cannot stop:** stop-loss orders at round levels are pre-placed and execute
  automatically on breach — price-insensitive, mechanical, involuntary at the moment of trigger.
  The trader cannot intervene faster than the order executes.
- **Falsifier:** breaches of round-number % drawdowns from 30d high do not predict forward excess
  return vs names that dropped equally but did not breach a round level. The key comparison is
  round-level breach vs same-magnitude drop without round-level proximity.
- **Why funds can't capture:** requires per-name high-water tracking and round-level classification
  in real time; events are sparse at the name level; entering into a stop-cascade is operationally
  risky; the reversion window is short.
- **data_status:** HAVE — 8h perp price 730d 49 names. Compute rolling 30d high per name;
  define round levels as −10%, −20%, −30% from that high; flag periods where close crosses a
  round level from above for the first time.

## Test method
Extend `scripts/h042_deep.py`: compute 30d rolling high per name; flag round-level breach events
(−10%, −20%, −30% from high, first-touch only). Stratify by which round level. Measure forward
1–2 period excess return with full H-042 hardened protocol (market-demean, per-name beta-adjust,
period-cluster eff-n, cost). Cross-check: compare vs non-round-level drops of same magnitude.

## data_status
HAVE — existing 8h perp cache. Expected n: 100–400 round-level breach events across 49 names.

## Score
6.75 / 10
(edge_plausibility 6 × 2 + data_feasibility 7 + novelty 8) / 4

## Status
proposed
