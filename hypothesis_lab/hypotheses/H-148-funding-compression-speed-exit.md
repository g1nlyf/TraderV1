# H-148 — Funding Compression Speed as Carry Exit Signal

**Status:** proposed · 2026-06-05
**Zone:** CROSS-ASSET / MACRO

## Statement
The C-002 carry book holds positions continuously. However, funding does NOT compress uniformly: it sometimes compresses rapidly (3+ consecutive periods of declining funding per name), signaling that the forced-payer regime is ending. Hypothesis: when the rate-of-change of funding (1st derivative, computed as rolling 3-period slope) crosses below -0.01% per period for a given name, exit that name's carry position and re-enter when slope recovers. This momentum-in-funding approach protects against the transition from "funding is falling" to "funding flipped negative" by exiting early.

## Structural logic — who is forced
Rapid funding compression indicates the crowded long cohort is unwinding faster than new longs are entering. This is often precedes a carry-flip (funding goes negative) which devastates the carry holder who is short perp. The funding slope is a real-time signal of the balance between forced payers entering vs exiting.

## Falsifier
Funding-slope exit does not improve carry Sharpe; or the exit fires during temporary compression that recovers (whipsaw), generating more costs than saved carry deterioration.

## Why uncaptured
C-002 holds continuously. The dynamic exit based on funding slope (not just level) has not been tested in this codebase. The risk-parity sizing (H-031) adjusts weights but does not exit names.

## Data status
data_status: HAVE — full funding panel 8h 730d; rolling slope computable from panel. Per-name slope signal straightforward.

## Test (one line)
Compute rolling-3-period OLS slope of funding per name; modify fixed-selection carry evaluation to exclude periods where slope < -threshold for that name; compare exit-gated vs always-on Sharpe/APR.

## SCORE: 7.0
(edge_plausibility 3/5, data_feasibility 5/5, novelty 3.5/5 → (3×2+5+3.5)/4 = 14.5/4 = 3.625 → ×2 = 7.25 → 7.0)
