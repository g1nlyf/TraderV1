# H-097 — Quarterly/dated futures basis carry (spot vs quarterly future) [BLOCKED]

**Status:** proposed · blocked · 2026-06-05
**Zone:** Carry & Premia Extensions
**ID range:** H-097 (Zone 2 gen)
**SCORE:** 5.0  (edge_plausibility 8, data_feasibility 1, novelty 6) / 4 = 5.0

## Statement
Harvest the basis between spot and quarterly dated futures (not perpetuals). Quarterly futures on Binance/OKX trade at a premium to spot in bull markets; the basis decays to zero at expiry, providing a guaranteed return if the spot leg is hedged. Unlike perpetual carry (C-002), there is no funding rate risk — the basis is locked in at entry and decays deterministically.

## Who is forced / why can't stop
Leveraged longs in quarterly futures pay the basis premium upfront (embedded cost of capital). They use quarterly futures for clean balance sheet exposure without daily funding rate risk. The carry harvester captures this structural premium.

## Falsifier
If the quarterly basis on a risk-adjusted basis does NOT exceed perpetual funding carry APR, quarterly carry adds no incremental value over C-002. Also falsified if execution risk (roll management, OI concentration near expiry) eliminates the gross edge.

## Why uncaptured
Quarterly/dated futures basis is NOT cached. OKX quarterly futures data is not accessible. Binance quarterly delivery futures would require a new cache build. This is blocked until quarterly futures klines are fetched and matched with contemporaneous spot.

## Data status
data_status: BLOCKED — Quarterly/dated futures not cached. Would need Binance COIN-M or USDT delivery futures klines (different endpoint: dapi.binance.com). Collection feasible but not yet built.

## Test (one line)
Once data available: build quarterly_basis_carry.py analogous to carry_leads.py; compute basis_at_entry − basis_at_exit (deterministic) vs spot_ret hedge; measure net APR with roll cost at expiry.
