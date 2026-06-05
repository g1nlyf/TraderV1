# H-111 — Bid-ask spread widening as carry suspension signal

**Status:** proposed · BLOCKED · 2026-06-05
**Zone:** MICROSTRUCTURE SIGNALS — bid-ask spread as liquidity gate
**ID range:** H-111 (Zone 3 generation)

## Statement
When the bid-ask spread on the perp widens (e.g. to >3× its rolling 20-bar median), the
market maker has stepped away. This precedes cascade events. Suspend carry and H-042 entries
during wide-spread conditions; re-enter when spread reverts. The spread regime is an early
microstructure warning.

## Structural logic
Market makers price-in their inventory risk. Spread widening = inventory imbalance or
informational asymmetry. Both are precursors to directional moves that hurt carry.

## Falsifier
Bid-ask spread level does not predict carry compression or cascade probability in the subsequent
8h period.

## Why uncaptured
Completely standard microstructure hypothesis — not captured here because L2 data is BLOCKED.

## Data status
**BLOCKED** — bid-ask spread requires L2 order book data (bid/ask per timestamp). Not cached,
not fetchable cleanly from Binance REST without streaming. Cannot test.

## Test (one line)
BLOCKED — would need `depth` endpoint streaming; extend `leverage_sim.py` once L2 is available.

## SCORE: 5.0
(edge_plausibility=4, data_feasibility=1, novelty=2 → (4×2+1+2)/4 = 11/4 = 2.75 → 5.5; BLOCKED)
