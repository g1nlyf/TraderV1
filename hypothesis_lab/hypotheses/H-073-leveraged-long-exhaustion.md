# H-073 — Leveraged-long exhaustion via funding persistence (pre-cascade signal)

**Status:** tested · 2026-06-05 · **FALSIFIED, WRONG SIGN — predicts continuation (net −0.72%, t −0.28)**
**Zone:** FORCED-FLOW PREMIA
**Created:** 2026-06-05 (Session 5)

## Statement
A name that sustains elevated positive funding for >5 consecutive 8h periods (top-quartile funding
per period for 5+ periods in a row) has a maximally crowded leveraged-long book. Any trigger
(not necessarily a −8% cascade) will produce a sharper forced-exit wave because the book is
overloaded. When a price decline of >−5% occurs in this elevated-persistence state, the forward
bounce (H-042 method, market-neutral) should be larger than a −5% cascade without prior funding
persistence. The persistence flag is the crowding diagnostic; the price trigger is the forced-flow
moment.

## Quality filter
- **Who is FORCED & cannot stop:** leveraged longs who have been paying elevated carry for >5
  periods are already at thin margin — the combination of cumulative carry drain plus any price
  move makes margin calls inevitable. They are the most marginal holder in the market.
- **Falsifier:** the interaction of funding-persistence + price cascade does not produce
  incrementally larger bounce than price cascade alone (H-042). The persistence flag adds noise
  (predicts continuation, not reversion, per H-053).
- **Why funds can't capture:** requires per-name funding-persistence tracking AND cascade monitoring;
  two-condition event is rare; entering during cascade requires speed.
- **data_status:** HAVE — 8h funding + price 730d 50 names. Count consecutive periods where
  funding > per-name 75th percentile trailing-90d; flag ≥5 streaks; cross with >−5% price drop.

## Test method
Extend `scripts/h042_deep.py`: compute per-name consecutive high-funding streak; flag events
where streak ≥5 AND price < −5% in same period. Compare excess_net vs base H-042 −5% events
without persistence flag. Full hardened protocol: market-demean, per-name beta-adjust, period-
cluster eff-n, cost 11bps RT.

## data_status
HAVE — existing 8h price + funding cache. Expected n: 50–150 events.

## Results (scripts/test_zone1_forcedflow.py — full H-042 hardened protocol)
≥5 consecutive periods of per-name top-quartile (≥75th pct trailing-90d) funding, AND a −5% cascade
in the same period, hold H2.
```
 events periods   net/trade  clustT(bA)  median  hit   block-CI95         perm_p
    68      31     -0.72%      -0.28     -0.73%  35%   [-1.14%,+1.34%]    1.0000
```
Net is NEGATIVE (−0.72%), cluster-t −0.28, hit 35%, perm_p 1.0 — the worst row in the batch.

## Verdict
[ ] FALSIFIED, WRONG SIGN. Funding-persistence + cascade predicts CONTINUATION, not reversion — exactly
the falsifier ("persistence predicts continuation per H-053"). Names that have sustained crowded-long
funding for 5+ periods keep bleeding after a −5% drop rather than bouncing. This reaffirms the H-053
finding that the forced-flow signal in *funding* is momentum-like; the bounce edge comes purely from the
acute price flush (H-042), not from any crowding diagnostic layered on top.

## Score
7.5 / 10
(edge_plausibility 7 × 2 + data_feasibility 9 + novelty 7) / 4

## Status
tested · falsified (wrong sign)
