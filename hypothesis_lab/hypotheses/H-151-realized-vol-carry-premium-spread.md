# H-151 — Funding Rate / Realized-Vol Spread as Carry Quality Filter (Per-Name)

**Status:** proposed · 2026-06-05
**Zone:** CROSS-ASSET / MACRO

## Statement
For each name, compute funding_rate / realized_vol (funding rate divided by realized volatility of the perp — a "carry-to-vol" ratio, similar to Sharpe of raw carry). Names with HIGH carry-to-vol ratio offer the richest risk-adjusted carry premium. Select the top-N names by carry-to-vol each period. Hypothesis: carry-to-vol selection (at the per-name level, updated dynamically) improves Sharpe vs the static fixed-selection (H-021) and the basic level-selection (H-049 tested this with limited success — but this version uses per-name realized-vol, not cross-sectional rank).

## Structural logic — who is forced
A high carry-to-vol ratio means: a lot of funding premium per unit of price risk. This is the signature of a captive forced-payer whose trading is driven by structural reasons, not speculation: the price doesn't move much (low vol) but they're still paying a lot of funding (they're stuck long). This is the ideal carry counterparty profile.

## Falsifier
Dynamic carry-to-vol name selection has no better Sharpe than fixed-selection H-021 (permutation test across random fixed selections of same size).

## Why uncaptured
H-049 tested carry/vol at a cross-sectional z-score level but marginally. This version uses raw per-name vol (8h perp realized-vol, rolling 21-period) as the denominator — a cleaner signal. The per-name ratio (not cross-sectional z) is a distinct formulation.

## Data status
data_status: HAVE — full perp 8h price + funding panel 730d. Per-name realized-vol computable. Identical data to H-049 but different signal construction.

## Test (one line)
Compute per-name funding/(rolling-21 realized-vol of perp returns); select top-K names dynamically each period; evaluate via funding_harvest.py + block-bootstrap vs H-021 fixed-selection.

## SCORE: 7.0
(edge_plausibility 3/5, data_feasibility 5/5, novelty 3/5 → (3×2+5+3)/4 = 14/4 = 3.5 → ×2 = 7.0)
