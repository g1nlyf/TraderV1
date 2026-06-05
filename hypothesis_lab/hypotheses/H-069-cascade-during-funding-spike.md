# H-069 — Cascade DURING funding spike (liquidation into crowded longs)

**Status:** tested · 2026-06-05 · **FALSIFIED — no funding synergy (net +0.37%, t 0.15, n=23)**
**Zone:** FORCED-FLOW PREMIA
**Created:** 2026-06-05 (Session 5)

## Statement
H-042's base trigger is a >−8% 8h drop WITH rising funding. H-069 sharpens this: require that
funding at the cascade moment is in the top tercile of the per-name trailing 90d distribution
(not merely positive-and-rising, but elevated). A cascade into an elevated-funding environment
means the long-side is more crowded — the overshoot is deeper because both margin-called longs
AND funding-squeezed longs exit simultaneously. The forward bounce (H-042 hardened method) should
be larger, and hit rate higher, because the forced-seller pool is maximally concentrated.

## Quality filter
- **Who is FORCED & cannot stop:** (1) margin-called longs from the price drop; (2) funding-cost-
  squeezed longs who were already straining and the price drop pushes them over margin threshold.
  Two forced-exit mechanisms fire simultaneously — neither cohort can wait.
- **Falsifier:** the interaction effect (cascade AND high funding) does not produce incrementally
  larger bounce than cascade alone (H-042 base). The two conditions are not synergistic.
- **Why funds can't capture:** requires real-time per-name funding-level tracking alongside price
  monitoring, entering into the most acute crash moments, sparse events.
- **data_status:** HAVE — 8h price + funding 730d 49 names. Subset of H-042 events where funding
  is also in top-tercile. Expected n: 20–50% of H-042's n=91 events at −8% threshold.

## Test method
Extend `scripts/h042_deep.py`: add a sub-filter on H-042 events where current_funding >
per-name trailing-90d 66th percentile. Compare excess_net, betaAdj, bA_cT, median, hit,
clustT, permP for the filtered subset vs base H-042. Full hardened protocol: market-demean,
per-name beta-adjust, period-cluster eff-n, cost 11bps RT.

## data_status
HAVE — subset of existing H-042 events. Expected n: 30–60 at −8% threshold with funding filter.

## Results (scripts/test_zone1_forcedflow.py — full H-042 hardened protocol)
−8% cascade where funding is in the per-name trailing-90d top tercile (≥66th pct), rising funding, H2.
```
 events periods   net/trade  clustT(bA)  median  hit   block-CI95         perm_p
    41      23     +0.37%      +0.15     -0.24%  46%   [-1.42%,+2.95%]    0.0002
```
The funding sub-filter cuts H-042's −8% events from 91 periods to 23 and the bounce collapses to ~0
(net +0.37%, cluster-t 0.15, median negative).

## Verdict
[ ] FALSIFIED. No synergy between cascade and elevated funding. "Crowded longs + margin call" is not
incrementally more forced than a plain cascade — the extra condition only shreds n. The dual-forced-exit
mechanism is not supported.

## Score
8.0 / 10
(edge_plausibility 8 × 2 + data_feasibility 9 + novelty 7) / 4

## Status
tested · falsified
