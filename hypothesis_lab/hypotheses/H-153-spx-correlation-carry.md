# H-153 — SPX Regime vs Crypto Carry (Cross-Asset Correlation Gate)

**Status:** proposed · BLOCKED · 2026-06-05
**Zone:** CROSS-ASSET / MACRO

## Statement
During SPX risk-off regimes (SPX drawdown > 5% from recent high), crypto funding rates compress as institutional crypto holders de-risk alongside equities. Gate carry book off during SPX drawdown episodes. The cross-asset correlation between crypto carry and equity risk is real but regime-dependent.

## Data status
data_status: BLOCKED — SPX not on Binance, not cached. Would require Yahoo Finance, FRED, or similar external source. Cannot test in <30min.

## Test (one line)
BLOCKED: fetch SPX OHLCV from Yahoo Finance; merge on 8h-aligned timestamps; gate carry PnL; block-bootstrap.

## SCORE: 5.5
(edge_plausibility 3.5/5, data_feasibility 1/5 — blocked; novelty 3/5 → (3.5×2+1+3)/4 = 11/4 = 2.75 → ×2 = 5.5)
