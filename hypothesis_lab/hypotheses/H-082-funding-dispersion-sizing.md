# H-082 — Multi-name funding dispersion as book sizing signal

**Status:** proposed · 2026-06-05
**Zone:** Carry & Premia Extensions
**ID range:** H-082 (Zone 2 gen)
**SCORE:** 7.0  (edge_plausibility 7, data_feasibility 9, novelty 7) / 4 = 7.0

## Statement
Measure the cross-sectional standard deviation (dispersion) of funding rates across the C-002 book names each period. Scale total book leverage proportionally to dispersion: when dispersion is high, there is genuine differentiation across names — carry signals are informative and worth pressing. When dispersion collapses (all names pay similarly low funding), the edge is thinner, scale back.

## Who is forced / why can't stop
When funding dispersion is high, certain names have extremely crowded long positioning while others don't — meaning the forced-payer effect is concentrated in the names you hold. Wide dispersion also indicates the market is not in a risk-off mode (where correlations spike and all funding collapses together). The signal measures the health of the carry opportunity itself.

## Falsifier
If book Sharpe conditioned on high-dispersion windows is not statistically greater than low-dispersion windows, dispersion is not a valid sizing signal. Also falsified if dispersion is simply a proxy for mean funding level (in that case H-081 already captures it).

## Why uncaptured
C-002 risk-parity sizing (H-031) weights names by 1/funding-vol of each name. Dispersion-as-book-scalar is a different dimension: it scales aggregate exposure up/down based on cross-sectional information content. Interaction with risk-parity sizing needs to be checked — they may be partially redundant or additive.

## Data status
data_status: HAVE
- Full funding panel 8h 730d, all 50 names available — dispersion computable trivially

## Test (one line)
Extend `carry_lift.py`: compute cross-sectional std of book-name funding each period; scale period PnL by dispersion_percentile and compare Sharpe/APR vs flat-weighted via `fh.evaluate` + block-bootstrap CI95.
