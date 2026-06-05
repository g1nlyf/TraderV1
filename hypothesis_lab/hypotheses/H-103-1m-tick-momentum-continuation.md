# H-103 — 1m tick-momentum continuation on the 10 harvested names

**Status:** proposed · 2026-06-05
**Zone:** MICROSTRUCTURE SIGNALS — 1m tick-momentum continuation
**ID range:** H-103 (Zone 3 generation)

## Statement
On the 10 names with 1m perp data (UNI, LTC, FIL, LINK, ETH, DOGE, AAVE, ADA, XRP, BTC):
a strong 1m return (top decile over trailing 5m) predicts continuation over the next 1–3
minutes with positive EV net of taker cost. The signal is the 1m close return vs its
rolling 5-period mean. "Tick momentum" = short-window autocorrelation in 1m returns.

## Structural logic
**Who is forced / structural inefficiency:** Retail market orders arrive in clusters (copy-trade,
alert-triggered buy waves). A strong 1m candle concentrates aggressive buyer flow; the next
few minutes face FOLLOW-ON retail orders that haven't hit yet. Market makers recycle inventory
by widening bids — creating a brief momentum window before mean-reversion kicks in at longer
horizons. The structural counterparty who can't stop: reactive retail, not prop.

## Falsifier
1m return percentile rank has no predictive value for the next 1–3 minutes on these 10 names;
or predicted EV < 5.5bps/side taker cost; or the autocorrelation is symmetric (holds up-bar
but not momentum in the right direction).

## Why uncaptured
Requires 1m data (until Session 4, absent). Most retail backtests are on hourly+. HFT
already captures sub-second but the 1–3 minute window may be a "retail tail" zone that
HFT doesn't bother with at small size.

## Data status
**HAVE** — `finetune/data/intraday_1m/` has 10 names × perp+spot 1m OHLCV (180d).
Fully testable now.

## Test (one line)
New script on `finetune/data/intraday_1m/`: compute 1m perp close return; for each bar where
return > 90th-percentile trailing 5 bars, measure next 1/2/3-bar return; permutation test
vs random same-size subset; net of 11bps RT cost.

## SCORE: 7.0
(edge_plausibility=3 — 1m momentum is heavily contested, HFT territory; data_feasibility=5;
novelty=3 → (3×2+5+3)/4 = 14/4 = 3.5 → 7.0)
