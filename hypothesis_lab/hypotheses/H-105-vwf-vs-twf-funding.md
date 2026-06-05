# H-105 — Volume-weighted vs time-weighted funding as name-selection signal

**Status:** proposed · 2026-06-05
**Zone:** MICROSTRUCTURE SIGNALS — volume-weighted vs time-weighted funding
**ID range:** H-105 (Zone 3 generation)

## Statement
Standard funding rate is time-weighted (equal weight per 8h period). Volume-weighted funding
(VWF) would weight each period's rate by the trading volume in that period. Names where VWF >>
time-weighted funding (TWF) earn most of their carry during HIGH-volume — meaning the carry
is "backed" by real activity, not low-liquidity stale quotes. These names are hypothesized to
show more durable carry (lower carry-compression risk) because a deeper market is pricing the
funding rate against actual demand.

**Proxy construction (without order-book data):** use 8h volume from klines as the weight.
VWF − TWF > 0 means carry is concentrated in active sessions. Use as a name-selection filter.

## Structural logic
**Structural inefficiency:** Funding rates in illiquid periods can be manipulated by small
flow. High-volume periods reflect real aggregate demand for leverage. Names whose funding is
concentrated in high-volume windows have carry that is structurally demanded — less susceptible
to compression by a single actor.

## Falsifier
VWF/TWF spread has no predictive value for subsequent carry APR or carry-compression events;
or VWF>TWF names actually compress faster because they are also more crowded.

## Why uncaptured
Requires matching 8h volume klines to funding rates — trivially available from Binance API
(FETCHABLE) but never constructed in this codebase. The VWF concept is theorized in carry
literature but rarely implemented with crypto 8h data.

## Data status
**FETCHABLE <30min** — Binance 1h klines (OHLCV) for all USDT pairs available via API.
Aggregate to 8h volume. Funding cache already has 50 names × 730 periods.

## Test (one line)
Fetch 8h volume for the 50 carry names via Binance klines API; compute VWF and TWF; rank names
by VWF−TWF spread; compare top-decile vs bottom-decile subsequent carry APR using
`funding_leads2.py` panel structure.

## SCORE: 7.0
(edge_plausibility=3, data_feasibility=4, novelty=4 → (3×2+4+4)/4 = 3.5 → 7.0)
