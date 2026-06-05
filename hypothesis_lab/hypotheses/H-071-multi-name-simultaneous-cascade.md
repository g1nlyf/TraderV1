# H-071 — Multi-name simultaneous cascade basket (systemic event bounce)

**Status:** tested · 2026-06-05 · **FALSIFIED — no simultaneity premium (net −0.01%, 15 periods)**
**Zone:** FORCED-FLOW PREMIA
**Created:** 2026-06-05 (Session 5)

## Statement
When 3 or more names simultaneously cascade (>−8% in the same 8h period), the event is systemic —
a macro shock rather than idiosyncratic. The forced-selling pool is maximal (all correlated margin
books fire at once), and the post-event bounce across the entire basket should be larger and more
reliable than single-name H-042 events. Build an EW basket of all names that cascade in the same
period (≥3 names), long the basket market-neutral, hold 1–2 periods. The multi-name simultaneous
event is a more powerful signal of forced-flow exhaustion than any single-name event.

## Quality filter
- **Who is FORCED & cannot stop:** systemic margin calls across all leveraged books simultaneously.
  When a macro event hits, every correlated leveraged position fires margin at once; sellers cannot
  stagger exits or wait — the clock is simultaneous.
- **Falsifier:** the basket bounce in systemic events is NO LARGER than the EW average of
  individual H-042 events (i.e., no incremental signal from simultaneity). Or basket reduces n
  below inference threshold.
- **Why funds can't capture:** systemic events are precisely when liquidity is worst — entering
  a basket of crashing names requires executing many legs simultaneously into thin markets;
  capital is also most constrained during systemic events.
- **data_status:** HAVE — 8h perp price 730d 49 names. Count names with >−8% per period; flag
  periods where count ≥ 3. Basket = EW long those names. Expected n: 20–60 systemic periods.

## Test method
Extend `scripts/h042_deep.py`: compute per-period count of cascading names (>−8%); filter
to periods with ≥3 simultaneous cascades. Build EW basket; measure basket forward 1–2 period
excess return (market-demean at the basket level, period-cluster, cost per leg). Compare to
same-threshold H-042 single-name events in non-systemic periods.

## data_status
HAVE — existing 8h perp cache. Expected n: 20–60 systemic periods in 730d.

## Results (scripts/test_zone1_forcedflow.py — full H-042 hardened protocol)
Periods with ≥3 names simultaneously cascading (<−8%, rising funding); EW basket of all droppers, H2.
```
 events periods   net/trade  clustT(bA)  median  hit   block-CI95         perm_p
   102      15     -0.01%      +0.57     -0.19%  46%   [-0.94%,+1.36%]    0.0002
```
Systemic periods are rare (15 in 730d) and the basket bounce is ~0 (net −0.01%). See also H-077:
breadth predicts a *smaller* bounce, directly contradicting the simultaneity-premium thesis.

## Verdict
[ ] FALSIFIED. The multi-name simultaneous cascade ("systemic event") produces NO larger bounce than
single-name H-042 — the falsifier condition is met. Worse, H-077 shows high-breadth events bounce
*less*. Systemic forced selling drags correlated names down together (beta), it does not create a
bigger per-name overshoot. The edge lives in idiosyncratic single-name flushes, not systemic baskets.

## Score
7.75 / 10
(edge_plausibility 7 × 2 + data_feasibility 9 + novelty 8) / 4

## Status
tested · falsified
