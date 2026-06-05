# H-098 — USDC-margined perp carry split (USDC vs USDT margin funding differential) [BLOCKED]

**Status:** proposed · blocked · 2026-06-05
**Zone:** Carry & Premia Extensions
**ID range:** H-098 (Zone 2 gen)
**SCORE:** 4.75  (edge_plausibility 7, data_feasibility 1, novelty 6) / 4 = 4.75

## Statement
Test whether USDC-margined perps on Binance or Bybit carry different (higher or lower) funding rates than USDT-margined equivalents for the same underlying. Hypothesis: collateral-driven liquidity fragmentation creates systematic funding differentials between the two margin types — particularly for names where USDC liquidity is thin.

## Who is forced / why can't stop
Longs on USDC perps face a separate liquidity pool from USDT perps. If USDC-perp OI is concentrated in committed institutional holders (who prefer USDC as collateral for accounting reasons), the forced-payer premium may be higher and more stable on the USDC leg.

## Falsifier
If USDC and USDT funding rates are co-integrated with no persistent spread, collateral type doesn't matter. Also falsified if USDC perp OI is too thin to trade at scale (liquidity constraint).

## Why uncaptured
Stablecoin-margined perp split is NOT cached. Binance USDC-M perpetuals use a different API namespace. Not in current data infrastructure.

## Data status
data_status: BLOCKED — USDC-margined perp funding not cached. Collection feasible via Binance USDC-M endpoint but not yet built.

## Test (one line)
Once data available: extend funding_harvest.py with USDC-margin panel; compute USDC_funding − USDT_funding per name per period; test persistence of the spread via block-bootstrap on the differential series.
