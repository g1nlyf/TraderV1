# H-144 — ETHBTC Ratio Regime vs Alt Funding: Risk-Appetite Gate

**Status:** proposed · 2026-06-05
**Zone:** CROSS-ASSET / MACRO

## Statement
The ETHBTC ratio is a reliable proxy for crypto-native risk appetite: rising ETHBTC = risk-on rotation (retail flows into alts, ETH leads beta), falling ETHBTC = risk-off rotation (BTC dominance trade, alt funding collapses). Hypothesis: during ETHBTC uptrend regimes (EMA-20 > EMA-60 on the ratio, derivable from ETHUSDT and BTCUSDT 8h klines), alt funding rates are structurally elevated AND more stable, making carry richer AND safer. Gate the carry book ON only when ETHBTC is in uptrend regime.

## Structural logic — who is forced
When ETHBTC is rising, retail traders are allocating capital down the risk curve (from BTC to ETH to alts). They use perp leverage to express this view, becoming systematic funding payers. In ETHBTC downtrend, this flow reverses and the forced sellers of the prior regime become the current forced unwind — compressing funding. The ETHBTC ratio captures the structural direction of this retail leverage flow better than BTC price alone (which includes dollar-denominated moves).

## Falsifier
Mean alt funding in ETHBTC-uptrend vs downtrend periods not significantly different; or the ETHBTC-gated carry book has Sharpe no better than always-on.

## Why uncaptured
ETHBTC as a risk-appetite proxy exists in TradFi analogues (e.g., high-yield spreads as credit risk appetite) but has not been tested in this codebase as a carry gate. Derivable from two cached 8h series — no new data needed.

## Data status
data_status: HAVE — ETHUSDT_spot_8h.npz and BTCUSDT_spot_8h.npz both cached 730d; ETHBTC ratio computable from those; full funding panel available.

## Test (one line)
Compute ETHBTC = ETH_close/BTC_close from spot 8h; derive EMA-20/EMA-60 crossover regime; gate carry PnL series; block-bootstrap gated vs always-on Sharpe/APR.

## SCORE: 7.5
(edge_plausibility 3.5/5, data_feasibility 5/5, novelty 3.5/5 → (3.5×2+5+3.5)/4 = 15.5/4 = 3.875 → ×2 = 7.75 → 7.5)
