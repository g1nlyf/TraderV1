# H-108 — Funding-vol regime switch: carry quality degrades when funding-vol spikes

**Status:** proposed · 2026-06-05
**Zone:** MICROSTRUCTURE SIGNALS — funding volatility regime switching
**ID range:** H-108 (Zone 3 generation)

## Statement
The funding rate's own volatility (rolling std of 8h funding over 5 periods) is a CARRY QUALITY
signal. When funding-vol is low (stable carry), the premium is structural and durable — collect
at full size. When funding-vol spikes (erratic rates), the premium is noisy: sometimes high
funding precedes a cascade (spike-then-reset), sometimes it's a genuine sentiment shift.
Gate: size carry by 1/(1 + funding_vol_zscore) — proportional reduction when funding is unstable.

The distinction from H-100 (price-realized-vol gate) is that funding-vol and price-vol are
imperfectly correlated. Funding can be volatile while price is calm (funding oscillations
independent of liquidation risk), and price can be volatile while funding is stable (sudden
exogenous move with no funding impact). Both signals are independent and stackable.

## Structural logic
**Who is forced / structural:** In high-funding-vol regimes, funding arbitrageurs are actively
trading — meaning the funding rate is already being harvested by fast money. The edge
(excess return over the risk-free) compresses when competition intensifies. Low-funding-vol
regimes = competition has stepped back; the premium is available to patient carry collectors.

## Falsifier
Funding-vol level does not predict subsequent carry APR; or low-funding-vol periods show lower
absolute APR (the spread was smaller, not just more stable).

## Why uncaptured
Funding-vol as a carry-quality (not risk-proxy) signal is subtle. Most implementations use
funding-vol as a RISK proxy (H-031 risk-parity). Using it as a COMPETITION / QUALITY proxy
is an orthogonal framing that hasn't been backtested in this codebase.

## Data status
**HAVE** — 8h funding for 50 names × 730 periods. Funding-vol computable directly from the
funding cache (already loaded in `funding_leads2.py` panel).

## Test (one line)
Extend `funding_leads2.py`: per name per period compute rolling 5-period funding std (zscore);
gate carry evaluation to low-funding-vol periods (zscore < 0); compare APR/Sharpe vs always-on.

## SCORE: 8.0
(edge_plausibility=4, data_feasibility=5, novelty=3 → (4×2+5+3)/4 = 4.0 → 8.0)
