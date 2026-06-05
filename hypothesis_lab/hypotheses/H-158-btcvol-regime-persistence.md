# H-158 — BTC Vol Regime Persistence: Autocorrelation Structure for Carry Timing

**Status:** proposed · 2026-06-05
**Zone:** CROSS-ASSET / MACRO

## Statement
BTC realized-vol regimes are persistent (high-vol regimes cluster, low-vol regimes cluster). Quantify the autocorrelation of BTC vol regime at lags 1-9 (8h-72h). If ACF(lag=1) is high (>0.7), it means that knowing today's vol regime gives strong signal for next period's regime — and therefore carry on/off decisions based on yesterday's vol are forward-looking enough without a contemporaneous signal. Hypothesis: the ACF structure of BTC vol regime is strong enough that a lagged-by-1-period gate (fully non-lookahead-free in a trivial way) captures nearly all of the contemporaneous gate benefit from H-140.

## Structural logic — who is forced
Vol regime transitions are slow relative to the 8h carry period. Volatility clusters because the market processes information sequentially: a large move triggers risk-off positioning, which generates further instability, which sustains high vol for multiple periods. The persistence means the gate doesn't need to be contemporaneous — avoiding any timing contamination in the backtest.

## Falsifier
ACF at lag=1 < 0.5 (vol regimes flip quickly, lagged gate loses most of the signal vs contemporaneous).

## Why uncaptured
H-140 uses contemporaneous BTC vol (no lookahead anyway since vol is observable at period end before next entry). But explicitly quantifying the ACF structure validates the regime-gate design philosophy and informs optimal lookback window selection.

## Data status
data_status: HAVE — BTC_8h_klines.npz (730d). ACF computation is trivial from numpy.

## Test (one line)
Compute rolling-21 BTC realized-vol series; compute ACF at lags 1-12 via statsmodels; plot regime clustering; test lagged-1 gate vs contemporaneous gate carry PnL via block-bootstrap.

## SCORE: 6.5
(edge_plausibility 3/5 — mainly diagnostic; data_feasibility 5/5; novelty 2.5/5 → (3×2+5+2.5)/4 = 13.5/4 = 3.375 → ×2 = 6.75 → 6.5)
