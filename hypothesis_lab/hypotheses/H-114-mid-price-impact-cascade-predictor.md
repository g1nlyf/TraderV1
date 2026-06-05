# H-114 — Mid-price impact (depth-normalized) as cascade predictor

**Status:** proposed · BLOCKED · 2026-06-05
**Zone:** MICROSTRUCTURE SIGNALS — mid-price impact
**ID range:** H-114 (Zone 3 generation)

## Statement
Kyle's lambda (price impact per unit volume) measures how much the mid-price moves per dollar
of flow. When lambda rises (thin book, each trade moves price more), the name is vulnerable to
a cascade: a medium-size sell order causes outsized price drop → triggers more liquidations.
Use rising lambda as a carry-suspension and H-042 probability signal.

## Structural logic
**Structural:** High price impact = illiquidity. Illiquid markets cannot absorb forced selling
without large price moves. This is the MECHANICAL precursor to cascade events.

## Falsifier
Price-impact estimates from OHLCV proxies (e.g. Amihud illiquidity ratio: |return|/volume) are
too noisy to predict cascade events with predictive power beyond the price-drop itself.

## Data status
**BLOCKED (L2 version)** — true mid-price impact needs L2. However, the AMIHUD ILLIQUIDITY RATIO
(|8h return| / 8h volume) is a well-known proxy and IS FETCHABLE with 8h volume klines.
**FEASIBLE PROXY:** fetch 8h volume for 50 names from Binance klines; compute Amihud = |ret|/vol;
test as a carry-gate signal. Reclassify to FETCHABLE if we use Amihud.

## Test (one line)
FETCHABLE PROXY: fetch Binance 8h klines for 50 carry names; compute Amihud illiquidity;
gate carry to low-Amihud periods via `funding_leads2.py`; compare APR/Sharpe.

## SCORE: 6.0
(edge_plausibility=3, data_feasibility=2 [L2 BLOCKED, Amihud proxy FETCHABLE], novelty=4 →
(3×2+2+4)/4 = 12/4 = 3.0 → 6.0; promote to 7.0 if using Amihud proxy explicitly)
