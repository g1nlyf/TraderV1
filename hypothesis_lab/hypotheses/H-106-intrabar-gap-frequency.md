# H-106 — Intrabar gap frequency as carry-risk early warning

**Status:** proposed · 2026-06-05
**Zone:** MICROSTRUCTURE SIGNALS — intrabar gap frequency
**ID range:** H-106 (Zone 3 generation)

## Statement
For the 10 names with 1m data: count per-8h-period the number of 1m "gaps" (|open − prev_close|
> X bps, e.g. 20bps). A rising gap frequency signals thin liquidity / market-maker withdrawal —
an early warning that the name is vulnerable to a basis-blowout cascade. Gate: suspend carry
for a name in the next period if its gap frequency (trailing 8h) exceeds the 80th percentile.

## Structural logic
**Who is forced / structural:** Market makers continuously step away from thin books during
news events or pre-cascade periods. When they step away, the 1m open-to-close gaps widen
because the book is thin. This is an early leading indicator of the exact tail event (basis
blowout) that kills levered carry — and it is observable within a period, before the 8h close.

## Falsifier
Gap frequency does not predict subsequent 8h carry compression or cascade events; or the
gated carry APR is indistinguishable from always-on.

## Why uncaptured
Requires 1m tick data (unavailable until Session 4 harvest). Even with 1m data, per-period
gap frequency is a microstructure metric most carry implementations ignore — they use only
the period funding rate.

## Data status
**HAVE** — 1m perp OHLCV for 10 names (180d) in `finetune/data/intraday_1m/`. Gap = |open − prev_close| / prev_close. Fully computable from the npz files.

## Test (one line)
New script on `finetune/data/intraday_1m/`: for each 8h period, count 1m gaps > 20bps; flag
next-period as "high-gap"; compare carry return in flagged vs unflagged periods; permutation test.

## SCORE: 7.0
(edge_plausibility=3, data_feasibility=5, novelty=4 → (3×2+5+4)/4 = 3.75 → 7.5; reduction for
small n=10 names and likely thin signal → 7.0)
