# H-077 — Cascade breadth predicts individual bounce magnitude

**Status:** tested · 2026-06-05 · **FALSIFIED, INVERTED — breadth predicts SMALLER bounce (slope −0.06%, clustT −2.24)**
**Zone:** FORCED-FLOW PREMIA
**Created:** 2026-06-05 (Session 5)

## Statement
The number of names cascading (>−5%) in a given 8h period is a measure of systemic forced-selling
pressure. Individual names that cascade during high-breadth periods (many names dropping simultaneously)
bounce MORE in the next period than names that cascade in isolation (low-breadth periods). The
mechanism: high-breadth events signal systemic margin calls — the forced-seller pool is maximally
large, meaning the overshoot is more severe and the reversion more reliable. Low-breadth cascades
may be idiosyncratic (bad news, not pure forced flow). Stratify H-042 events by cascade breadth
(count of names >−5% in the same period) and measure differential bounce.

## Quality filter
- **Who is FORCED & cannot stop:** in high-breadth cascade periods, the sell flow is systemic margin
  calls (not news-driven) — fundamentally price-insensitive. In low-breadth cascades, the seller
  may be informational (news), which mean-reverts less reliably.
- **Falsifier:** breadth in the cascade period does not predict incremental excess return for
  individual cascaded names (individual bounce is independent of how many peers also cascaded).
- **Why funds can't capture:** requires real-time breadth tracking across all perps to classify
  the current cascade as systemic vs idiosyncratic before entering — requires a multi-name
  monitoring system that most small shops don't have.
- **data_status:** HAVE — 8h perp price 730d 49 names. Compute per-period cascade count; cross
  with individual H-042 events.

## Test method
Extend `scripts/h042_deep.py`: for each H-042 event (name + period), compute concurrent_cascade_count
(other names >−5% in same period). Stratify: low (count 1–2) vs medium (3–5) vs high (≥6). Compare
excess_net, betaAdj, clustT across breadth strata. Apply full H-042 hardened protocol. Expected n
per stratum: 30–150.

## data_status
HAVE — existing 8h perp cache. Stratification of existing ~325 H-042 events (−5% threshold).

## Results (scripts/test_zone1_forcedflow.py — full H-042 hardened protocol)
OLS of per-name beta-adj forward excess (H2) on cascade breadth (# names <−5% rising, same period),
across all 887 −5% events / 325 periods. Slope t is period-clustered (CR0 sandwich on period groups).
```
 events periods   slope/dropper  clustT   strata (beta-adj excess by breadth)
   887     325       -0.06%       -2.24   lo(1-2)=+1.07% [289]  med(3-5)=-0.06% [182]  hi(>=6)=-0.06% [416]
```
The slope is NEGATIVE and significant (cluster-t −2.24). Low-breadth (1–2 droppers) events carry the
entire bounce (+1.07%); medium and high-breadth events are flat-to-negative.

## Verdict
[ ] FALSIFIED, INVERTED — and informatively so. Breadth predicts a *smaller* bounce, the exact opposite
of the "systemic > idiosyncratic" thesis. The most reliable forced-flow overshoot is the ISOLATED
single-name cascade (low breadth); when many names drop together the move is systemic beta (correlated
margin selling pulling the whole complex down), which the market-demean removes and which does not
revert per-name. This is the sharpest single result of the batch: it pins the H-042 edge as
idiosyncratic forced-liquidation overshoot, *contaminated* (not amplified) by systemic breadth — and it
kills H-071 / the systemic-basket family.

## Score
7.25 / 10
(edge_plausibility 6 × 2 + data_feasibility 9 + novelty 8) / 4

## Status
tested · falsified (inverted)
