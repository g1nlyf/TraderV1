# H-152 — BTC Dominance Proxy (Top-Cap Ratio) as Carry Gate

**Status:** proposed · 2026-06-05
**Zone:** CROSS-ASSET / MACRO

## Statement
BTC.D (BTC dominance by market cap) is a well-known macro indicator for crypto risk appetite — rising BTC.D means rotation from alts to BTC (de-risking), falling BTC.D means rotation into alts (risk-on). True BTC.D requires total market cap (not cached). However, a proxy can be derived: BTC_price_8h / (ETH_price_8h + SOL_price_8h + BNB_price_8h + ...) as a top-cap dominance ratio from cached spot 8h data. Hypothesis: carry book performance is significantly worse during rising BTC-dominance-proxy periods (rotation to BTC = alt perp funding collapses), so gating off during these periods improves carry Sharpe.

## Structural logic — who is forced
Rising BTC dominance means capital is actively rotating out of alts — forced sellers of alt perps (exiting long perps) and reduced new buyers. This directly compresses alt funding. The carry holder gets caught receiving lower and lower funding while their mark-to-market on alt spot is also declining. The BTC dominance proxy is a leading indicator of this forced rotation.

## Falsifier
BTC-dominance-proxy regime has no predictive power for carry book returns (permutation null); or the proxy is too noisy / diverges from true BTC.D meaningfully enough to lose signal.

## Why uncaptured
BTC.D is a widely monitored indicator in crypto but not as a carry gate in this codebase. The proxy approach (from cached spot ratios) allows testing without external data.

## Data status
data_status: HAVE (proxy) — BTCUSDT_spot_8h, ETHUSDT_spot_8h, SOLUSDT_spot_8h, BNBUSDT_spot_8h all cached 730d. Proxy ratio derivable. Note: proxy quality vs true BTC.D unknown — may diverge during altcoin season for non-top-5 names.

## Test (one line)
Compute BTC_price/(BTC+ETH+SOL+BNB+XRP close) ratio from spot 8h cache; derive uptrend/downtrend regime; gate carry PnL series; block-bootstrap gated vs always-on.

## SCORE: 6.5
(edge_plausibility 3/5, data_feasibility 4/5 — proxy quality uncertain; novelty 3/5 → (3×2+4+3)/4 = 13/4 = 3.25 → ×2 = 6.5)
