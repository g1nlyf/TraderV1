# H-096 — OKX carry sleeve (third-venue funding premium) [BLOCKED]

**Status:** proposed · blocked · 2026-06-05
**Zone:** Carry & Premia Extensions
**ID range:** H-096 (Zone 2 gen)
**SCORE:** 5.25  (edge_plausibility 8, data_feasibility 1, novelty 7) / 4 = 5.25

## Statement
Add OKX perpetual funding as a third venue. For names where OKX funding systematically exceeds Binance+Bybit, route the carry short to OKX. Hypothesis: OKX's retail-heavy user base in Asian markets creates structural overpayment on certain altcoin perps not well-arbitraged by market makers who focus on Binance/Bybit.

## Who is forced / why can't stop
OKX's leveraged retail long community is geographically and liquidity-isolated from Western venues. For some assets, the crowding is persistent and the funding premium is large enough that cross-venue arbitrageurs can't fully flatten it (capacity constraints, API limits, margin allocation).

## Falsifier
If OKX funding is not persistently higher than Binance for any name (once data is available), no venue premium exists. Also falsified if the Binance-OKX basis spread risk eliminates the funding advantage.

## Why uncaptured
OKX funding data is NOT cached (BLOCKED). Would need to build a new OKX funding collector (API: GET /api/v5/public/funding-rate-history). Estimated 2-4 weeks of forward collection before a meaningful test is possible.

## Data status
data_status: BLOCKED — OKX funding not cached. Estimated collection time: 2-4 weeks forward.

## Test (one line)
Once data available: extend `funding_harvest.py` with OKX loader; run same name-selection pipeline vs Binance/Bybit panel; compare venue-level funding APR per name.
