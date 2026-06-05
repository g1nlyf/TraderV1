# H-141 — BTC Trend Regime vs Alt Funding Level Interaction

**Status:** proposed · 2026-06-05
**Zone:** CROSS-ASSET / MACRO

## Statement
During BTC uptrend regimes (8h EMA-20 > EMA-60, or price > trailing 30d high), alt perp funding rates are structurally elevated because retail flows into alts during BTC bull phases. The carry premium is RICHER in BTC uptrend and LOWER in BTC downtrend. Hypothesis: carry book APR is predictably higher when BTC is trending up, but that same period has elevated basis risk. Test whether time-weighted carry is meaningfully higher in uptrend periods and whether a trend-conditional sizing (1.5x in trend, 0.5x in downtrend) improves risk-adjusted returns.

## Structural logic — who is forced
In BTC uptrend, retail and momentum traders lever up on alts expecting beta-carry. They become forced payers of funding — a captive structural cohort. In downtrend, funding compresses as leveraged longs deleverage (or flip short). The carry collector benefits most from the uptrend forced-payer but also has higher drawdown risk when the trend reverses sharply.

## Falsifier
Average alt funding in BTC-up vs BTC-down periods not significantly different (t-test on funding level by regime); or trend-conditional sizing has no better Sharpe than equal-weight.

## Why uncaptured
C-002 fixed-selection carry (H-021) is always-on and doesn't scale with BTC regime. The interaction of macro trend regime and carry richness is known conceptually but not exploited in this book — carry desks generally just hold through regimes.

## Data status
data_status: HAVE — BTC_8h_klines.npz (730d); full alt funding panel 8h 730d. BTC trend derivable from klines.

## Test (one line)
Compute BTC EMA-20/EMA-60 crossover from BTC_8h_klines.npz; split funding panel returns by BTC regime; test mean funding difference + carry book Sharpe by regime via block-bootstrap.

## SCORE: 7.5
(edge_plausibility 3.5/5, data_feasibility 5/5, novelty 3/5 → (3.5×2+5+3)/4 = 15/4 = 3.75 → ×2 = 7.5)
