# H-118 — Implied vol surface slope as carry-quality gate (BLOCKED)

**Status:** proposed · BLOCKED · 2026-06-05
**Zone:** MICROSTRUCTURE SIGNALS — implied vol as carry gate
**ID range:** H-118 (Zone 3 generation)

## Statement
When the options implied-vol surface for BTC/ETH is in backwardation (near-term IV > far IV),
the market is pricing imminent volatility. This is a systemic risk signal for the carry book:
skip carry on ALL names when BTC/ETH IV term structure is inverted; collect aggressively when
it is in contango (calm, stable vol expectation).

## Structural logic
**Structural:** Backwardated IV = options market pricing jump risk imminently. Jump risk =
basis-blowout tail for carry. The options market is often FASTER than the funding market in
pricing imminent vol because options traders have more sophisticated forecasting.

## Falsifier
IV term structure inversion has no predictive power for same-day funding carry compression
on the 50-name panel; or backwardation periods are too infrequent to gate meaningfully.

## Data status
**BLOCKED** — implied vol surface requires options market data (Deribit, etc.). Not cached,
not in current infrastructure. Not fetchable cleanly within 30 minutes.

## Test (one line)
BLOCKED — needs Deribit IV API; once available, merge daily IV slope with funding panel in
`funding_leads2.py` and test IV-gated carry APR.

## SCORE: 4.0
(edge_plausibility=4, data_feasibility=1, novelty=3 → (4×2+1+3)/4 = 12/4 = 3.0 → 6.0; BLOCKED → 4.0)
