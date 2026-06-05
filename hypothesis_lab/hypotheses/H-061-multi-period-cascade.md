# H-061 — Multi-period cascade accumulation (−8% across 2 consecutive 8h periods)

**Status:** tested · 2026-06-05 · **FALSIFIED — no deeper-pool bounce (net −0.11%, t 0.50)**
**Zone:** FORCED-FLOW PREMIA
**Created:** 2026-06-05 (Session 5)

## Statement
A name that loses >−8% cumulatively across two back-to-back 8h periods (not necessarily >−8% in any
single period) represents a sustained forced-liquidation event with deeper overcrowding unwound.
The bounce in period 3 should exceed the single-period −8% bounce (H-042) because the forced seller
pool is larger (two waves of margin calls) and the crowding unwind is more complete. Trade long the
name market-neutral into the close of period 2, hold 1–2 periods. Apply H-042 hardened method.

## Quality filter
- **Who is FORCED & cannot stop:** leveraged longs across a wider entry price range get margin-called
  across both periods; trailing-stop orders cluster below the accumulating low. Both cohorts
  price-insensitive. Cannot wait.
- **Falsifier:** cumulative-cascade events show no incremental bounce above single-period −8% events
  (same bA_cT after market-demean). OR n < 30 in OOS window.
- **Why funds can't capture:** requires multi-period cascade tracking, entering after sustained pain,
  capital at risk during the accumulation, event sparsity.
- **data_status:** HAVE — 8h perp price 730d. Filter: rolling 2-period sum of returns < −8% AND neither
  single period alone triggers the −8% threshold (if both trigger, it's a repeat-cascade, H-060).

## Test method
Extend `scripts/h042_deep.py`: define new threshold — 2-period rolling return < −8% (with max single
period > −4% to separate from H-042 single-period events). Measure period-3 excess return with full
H-042 hardened protocol (market-demean + per-name beta-adjust + period-clustered eff-n + cost).

## data_status
HAVE — existing 8h perp cache. Expect n: 50–150 events given the lower per-period threshold.

## Results (scripts/test_zone1_forcedflow.py — full H-042 hardened protocol)
2-period cumulative perp return < −8% with NEITHER single period < −8% (separates from H-042/H-060),
rising funding, period-3 forward (H1 from close of period 2).
```
 events periods   net/trade  clustT(bA)  median  hit   block-CI95         perm_p
   349     165     -0.11%      +0.50     -0.04%  48%   [-0.23%,+0.49%]    0.0002
```
Despite n=165 periods (well above threshold), the bounce is ~0 (net −0.11%, cluster-t 0.50, CI spans 0).

## Verdict
[ ] FALSIFIED. Two back-to-back waves of margin calls do NOT produce a deeper overshoot than a single
−8% period. The "larger forced-seller pool" intuition does not hold — a slow two-period bleed lacks the
acute, simultaneous forced-flow that H-042's single-period crash has. The bounce magnitude tracks the
*acuteness* of the flush, not its cumulative depth.

## Score
8.0 / 10
(edge_plausibility 8 × 2 + data_feasibility 9 + novelty 7) / 4

## Status
tested · falsified
