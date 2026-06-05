# H-147 — BTC Return Regime as H-042 Event Filter: Only Bounce When BTC Stabilizes

**Status:** proposed · 2026-06-05
**Zone:** CROSS-ASSET / MACRO

## Statement
H-042 fires on alt perp drops ≥8% in one 8h period. However, not all drops bounce: drops that coincide with BTC itself falling sharply (BTC 8h return < -3%) are more likely to continue (BTC drag, not idiosyncratic) rather than bounce (overshoot correction). Hypothesis: conditioning H-042 entry on BTC being flat-to-positive in the same period (BTC 8h return > -1%) isolates the idiosyncratic overshoots that are more likely to revert, improving H-042 mean payoff and reducing the false-positive rate.

## Structural logic — who is forced
An alt dropping 8% while BTC is flat is almost certainly an idiosyncratic cascade — forced selling in that specific name. An alt dropping 8% while BTC drops 5% is likely beta drag — the alt may continue falling with BTC. The H-042 bounce thesis requires the forced selling to be localized and exhausted; BTC co-movement is evidence it is NOT localized.

## Falsifier
H-042 mean payoff conditioned on BTC-flat (BTC return > -1% at event) is not statistically better than unconditioned H-042; or conditioning kills enough events to drop n below the OOS threshold.

## Why uncaptured
H-042 was validated using all events regardless of BTC co-movement. The BTC regime filter is a natural refinement that eliminates the most obvious false positives.

## Data status
data_status: HAVE — BTC_8h_klines.npz (730d); perp 8h for all names (730d). Merge on timestamp straightforward.

## Test (one line)
Filter H-042 events to those where concurrent BTC 8h return > -1%; re-run h042_deep.py permutation + block-bootstrap on filtered subsample; compare mean payoff and n vs unconditioned.

## SCORE: 8.0
(edge_plausibility 4/5, data_feasibility 5/5, novelty 3.5/5 → (4×2+5+3.5)/4 = 16.5/4 = 4.125 → ×2 = 8.0)
