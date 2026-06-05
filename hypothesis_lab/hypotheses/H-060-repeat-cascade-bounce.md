# H-060 — Repeat-cascade bounce (2nd drop within 48h bounces harder)

**Status:** tested · 2026-06-05 · **NEAR-MISS — beats H-042 magnitude (+2.75%) but n-limited (t 1.20, n=29)**
**Zone:** FORCED-FLOW PREMIA
**Created:** 2026-06-05 (Session 5)

## Statement
When the same name drops >−8% in a second 8h period within 48h of a first cascade, the bounce in
the subsequent period is meaningfully larger than the single-cascade bounce (H-042). The second forced
seller flush occurs against a pool of leveraged buyers who entered on the first bounce and are now also
margin-called — compounding the overshoot. Long the name market-neutral (demean + beta-adjust) into
the second cascade; size by inverse funding-vol (H-031 method).

## Quality filter
- **Who is FORCED & cannot stop:** (1) original leveraged longs margin-called on first drop; (2) new dip-buyers
  who entered on the first bounce on leverage and are now liquidated a second time. Both cohorts are
  price-insensitive forced sellers; the second cohort is the incremental edge above H-042.
- **Falsifier:** the incremental bounce (2nd cascade vs 1st) vanishes under market-demean + per-name
  beta-adjust (H-042 method). OR median is negative (lottery). OR cluster-robust t < 2 at n > 50.
- **Why funds can't capture:** requires tracking cascade history per name, entering into a second crash
  within 48h (extreme operational complexity + risk of being early), very sparse events.
- **data_status:** HAVE — perp 8h price 730d 49 names. Extension of h042_deep.py: add recency flag
  for prior cascade within prev 6 periods on same name.

## Test method
Extend `scripts/h042_deep.py`: after flagging an −8% 8h drop, check if the same name had a prior
−8% drop in the preceding 6 periods. Stratify: first-cascade events vs repeat-cascade events.
Compare excess_net, betaAdj, clustT, permP with H-042 hardened protocol (market-demean + per-name
beta-adjust + period-clustered eff-n + taker cost 11bps RT).

## data_status
HAVE — existing 8h perp cache. Expected n: ~15–30 repeat-cascade events (sparse — may need forward-collect).

## Results (scripts/test_zone1_forcedflow.py — full H-042 hardened protocol)
−8% cascade with a prior −8% on the same name within the last 6 periods (48h), rising funding, hold H2.
```
 events periods   net/trade  clustT(bA)  median  hit   block-CI95          perm_p
    44      29     +2.75%      +1.20     -0.03%  50%   [-0.28%,+12.59%]    0.0002
```
Net +2.75%/trade **exceeds the H-042 −8% H2 baseline (+1.46%)** — the repeat-flush does appear to
overshoot harder. BUT cluster-t is only 1.20 at n=29 distinct periods; CI spans zero and the median is
~0 (mean is tail-driven). GATE (net>+2% AND t>2 AND periods>100) fails on significance + n.

## Verdict
[ ] NEAR-MISS — the only Zone-1 variant whose magnitude beats plain H-042, but purely n-limited
(29 periods, t 1.20). Not promotable as-is; the incremental bounce is real-looking but tail-driven and
not significant. **Queue for forward-collection** alongside the H-042 1m-entry work — if more
repeat-cascade events push n>100 with t>2, this is the best amplifier candidate. All other Zone-1
amplifiers failed outright (see `sessions/2026-06-05-test-zone1.md`).

## Score
8.0 / 10
(edge_plausibility 8 × 2 + data_feasibility 9 + novelty 7) / 4

## Status
tested · near-miss (n-limited) · forward-collect queued
