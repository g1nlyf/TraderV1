# H-084 — Carry on the Bybit leg vs Binance leg (venue carry spread)

**Status:** proposed · 2026-06-05
**Zone:** Carry & Premia Extensions
**ID range:** H-084 (Zone 2 gen)
**SCORE:** 7.0  (edge_plausibility 7, data_feasibility 8, novelty 7) / 4 = 7.0

## Statement
For names that exist on both Binance and Bybit perps, separately evaluate carry (long spot / short perp) using the Bybit funding rate vs the Binance funding rate. Hypothesis: for some names, Bybit funding is systematically higher than Binance — and the correct venue for the carry short is Bybit, not Binance. This extends the C-002 universe and may lift APR for select names.

## Who is forced / why can't stop
Bybit's user base skews toward retail leveraged longs (historically more aggressive in perps than Binance's more balanced base). For certain assets (smaller caps, higher retail interest), forced payers are concentrated on Bybit. The split creates per-name venue optimization opportunities.

## Falsifier
If Bybit carry APR does not statistically exceed Binance carry APR for any name (perm_p < 0.05 per name, FDR corrected), there is no venue advantage. Also falsified if the Bybit-Binance funding spread is not persistent (agreement is high, H-022 already showed this is broadly true — but the residual venue premium is the new question).

## Why uncaptured
H-022 showed that cross-venue AGREEMENT as a quality gate fails. H-047 showed that cross-venue lead-lag is symmetric. Neither tested whether the absolute level of carry is consistently higher on one venue per name — a venue selection question, not a timing or quality question. The data for Bybit funding already exists in cache.

## Data status
data_status: HAVE
- Bybit funding history cached for 40 names with Binance overlap (see DATA-ASSETS.md)
- Spot leg still Binance; Bybit perp short is the variable

## Test (one line)
Extend `carry_leads.py`: for the 40-name overlap universe, compute mean Bybit funding minus mean Binance funding per name in train; select the top-5 names where Bybit > Binance by >10bps; run carry with Bybit funding as the income signal and compare OOS APR vs Binance-leg baseline.
