# H-068 — Deep-threshold cascade (−15% 8h) — extreme liquidation bounce

**Status:** proposed
**Zone:** FORCED-FLOW PREMIA
**Created:** 2026-06-05 (Session 5)

## Statement
H-042 shows monotonically increasing excess bounce with deeper thresholds (−5%: +0.22%, −8%: +1.46%,
−10%: +2.36%). The −15% threshold should yield a larger excess still (~3–5%+), as the liquidation
pool at this depth is almost entirely forced (voluntary sellers would have exited earlier). The n
will be small (~15–25), so this hypothesis requires forward-collection to reach n>100, but the
magnitude may already clear the +2% gate in-sample. Build on H-042 hardened method exactly.

## Quality filter
- **Who is FORCED & cannot stop:** at −15% in a single 8h period, only forced margin-call execution
  remains — no rational seller accepts −15% intraday unless compelled. The entire seller pool is
  liquidation, maximally price-insensitive.
- **Falsifier:** excess bounce at −15% threshold is NOT larger than at −8% in market-neutral terms
  (the overshoot does not scale with cascade depth). OR n is too small for any inference.
- **Why funds can't capture:** −15% drops are extremely rare, require standing limit orders deep
  in the order book, and require rapid delta hedging — no systematic fund runs this at scale.
- **data_status:** HAVE (partial) — 8h perp price 730d. Expect very few events (~10–20 in 730d
  across 49 names). Forward-collect to build n. Can test now for magnitude calibration.

## Test method
Extend `scripts/h042_deep.py`: add −15% threshold row to the threshold loop. Apply same hardened
protocol: market-demean, per-name beta-adjust, period-clustered eff-n, taker cost 11bps RT.
Flag as n-blocked if OOS n < 30; report magnitude as directional signal for forward-collection
priority. Also test holding period H3 (3 periods) given the deeper dislocation.

## data_status
HAVE (n-limited) — expect n~10–20 now, need forward-collect to n>100.

## Score
7.5 / 10
(edge_plausibility 8 × 2 + data_feasibility 8 + novelty 6) / 4

## Status
proposed
