# H-074 — Intraday cascade entry sharpening (enter at −8% 1m touch, not 8h close)

**Status:** proposed
**Zone:** FORCED-FLOW PREMIA
**Created:** 2026-06-05 (Session 5)

## Statement
H-042 enters at the 8h close, after the cascade has already partially recovered. The −8% 8h close
means the name hit −8% at some intraday point but has already bounced to the close level (which is
the realized datapoint). Entering at the actual intraday −8% touch (using 1m data) captures the
reversion FROM the true overshoot low, not from the partially-recovered close. The excess return
measured from the 1m entry point should be materially larger than H-042's 8h-close entry, with
similar or better hit rate. This is an execution improvement on a validated signal, not a new signal.

## Quality filter
- **Who is FORCED & cannot stop:** same as H-042 — margin-called longs at the intraday −8% touch.
  The difference is purely timing: the forced seller is at maximum distress at the intraday low,
  not at the 8h close.
- **Falsifier:** the intraday −8% touch entry does NOT produce larger excess than the 8h-close
  entry of H-042 (the intraday low is random noise, not the systematic overshoot point).
- **Why funds can't capture:** requires sub-minute monitoring and execution at the cascade low —
  operationally intense, requires standing limit orders or algorithmic detection. No systematic
  fund runs this at scale for small alt perps.
- **data_status:** FETCHABLE<30min for the 10 priority names (UNI LTC FIL LINK ETH DOGE AAVE ADA
  XRP BTC, 180d 1m already harvested). For full 49 names: FETCHABLE but would take hours.

## Test method
Extend `scripts/h042_deep.py` (1m mode): for each 8h period where the 8h close drops >−8%,
use 1m data to find the intraday low (the −8% touch point). Define entry at that 1m bar.
Measure forward return from that bar to the 8h close of the cascade period (period 0 intra-period
recovery) plus periods 1–2 excess return (market-demean, per-name beta-adjust, period-cluster,
cost). Compare to H-042 8h-close baseline for same events.

## data_status
HAVE (10 names, 180d 1m) — run now for UNI/LTC/FIL/LINK/ETH/DOGE/AAVE/ADA/XRP/BTC.
FETCHABLE<30min for remaining 39 names if needed.

## Score
8.0 / 10
(edge_plausibility 9 × 2 + data_feasibility 8 + novelty 6) / 4

## Status
proposed
