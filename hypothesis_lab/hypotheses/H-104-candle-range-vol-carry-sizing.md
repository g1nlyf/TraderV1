# H-104 — Candle-range (1m high-low) as realized-vol proxy for carry sizing

**Status:** proposed · 2026-06-05
**Zone:** MICROSTRUCTURE SIGNALS — candle-range as vol proxy for sizing
**ID range:** H-104 (Zone 3 generation)

## Statement
Use the rolling 8h sum of 1m candle ranges (high−low)/close as a real-time realized-vol proxy.
Size the carry book INVERSELY proportional to this measure: high candle-range = high intraday
vol = reduce carry exposure (liquidation risk elevated); low range = expand to full carry size.
This is a dynamic sizing rule layered on top of C-002.

## Structural logic
**Structural inefficiency:** The existing risk-parity carry sizing (H-031) uses funding-rate
volatility (8h-period funding std) as the risk measure — but funding vol lags by up to one
full 8h period. The 1m candle-range is a REAL-TIME vol signal available within the period.
When intraday vol spikes, the basis can widen dramatically before the 8h funding period closes.
Sizing down in real-time avoids the intra-period drawdown that lags-based sizing misses.

## Falsifier
Dynamic sizing by candle-range does not improve carry Sharpe vs static H-031 risk-parity sizing;
or the candle-range predicts vol that doesn't translate into basis risk (noise vol, not tail vol).

## Why uncaptured
Requires 1m intraday data per 8h period to compute pre-close sizing adjustments. Standard carry
implementations use 8h-end data only. The per-period candle-range aggregation is a novel
real-time risk signal for intraday carry management.

## Data status
**HAVE** — 1m perp OHLCV for 10 names (180d) in `finetune/data/intraday_1m/`. Can aggregate
per-8h-period candle-range sum. Carry panel has 8h funding for those names.

## Test (one line)
Extend `leverage_sim.py`: compute per-8h-period candle-range sum from 1m highs/lows; at each
period, scale carry position by 1/candle_range (normalized); compare cumulative carry return
and Sharpe vs constant H-031 sizing on the same 10 names.

## SCORE: 7.5
(edge_plausibility=4, data_feasibility=4, novelty=4 → (4×2+4+4)/4 = 4.0 → 8.0; capped at 7.5
because n=10 names limits the OOS draw; effect size from sizing marginal improvements is historically small)
