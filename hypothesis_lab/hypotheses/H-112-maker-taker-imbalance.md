# H-112 — Maker-taker ratio imbalance as directional pressure proxy

**Status:** proposed · BLOCKED · 2026-06-05
**Zone:** MICROSTRUCTURE SIGNALS — maker-taker ratio
**ID range:** H-112 (Zone 3 generation)

## Statement
When taker volume >> maker volume (aggressive buyers/sellers dominate), the order flow is
directional and non-adaptive. High taker-sell ratio precedes cascade events; high taker-buy
ratio sustains momentum. Use maker-taker ratio as a carry entry filter and H-042 timing refiner.

## Structural logic
Taker sellers are price-insensitive (urgent); maker buyers are patient. Taker-sell dominance
means forced or momentum-driven selling. The structural counterparty is the taker.

## Falsifier
Maker-taker ratio has no predictive value for subsequent 1m returns or carry compression at horizons >30s (HFT already priced in).

## Data status
**BLOCKED** — maker-taker volume split requires trade-level data (aggressor side). Not available
from OHLCV klines. Would need Binance AggTrades stream or tick data. Not cached, not cleanly fetchable.

## Test (one line)
BLOCKED — needs trade-level aggressor data; not available in current infrastructure.

## SCORE: 4.5
(edge_plausibility=3, data_feasibility=1, novelty=3 → (3×2+1+3)/4 = 10/4 = 2.5 → 5.0; BLOCKED → 4.5)
