# H-075 — Alt-cascade BTC spillover underperformance

**Status:** proposed
**Zone:** FORCED-FLOW PREMIA
**Created:** 2026-06-05 (Session 5)

## Statement
When 3+ alt names cascade simultaneously (>−8%, same 8h period), systemic forced-selling causes
BTC to underperform its own beta expectation in the following period, as portfolio managers sell
BTC to meet margin on alts. BTC is the most liquid asset in the portfolio and the preferred margin
call exit vehicle. The BTC underperformance is transient (1–2 periods) and reverts when the
alt-cascade selling pressure exhausts. Short BTC (market-neutral vs a simple trend model) during
multi-name cascade events; cover after 1–2 periods.

## Quality filter
- **Who is FORCED & cannot stop:** portfolio margin calls force selling of the most liquid available
  asset first; BTC is that asset. When alt portfolios are margin-called, BTC selling follows
  mechanically and immediately — the seller cannot choose NOT to sell BTC.
- **Falsifier:** BTC does not underperform its own trend in periods following multi-name alt cascades
  (BTC moves are driven by its own factors, not alt margin contagion).
- **Why funds can't capture:** requires multi-name cascade detection AND BTC short execution
  simultaneously; requires being short BTC in a crisis (career risk); event is rare.
- **data_status:** HAVE — BTC 8h 730d + alt perp price 730d. Flag multi-cascade periods (≥3
  names >−8%); measure BTC excess return (vs BTC trailing EWMA trend) in next 1–2 periods.

## Test method
Extend `scripts/h042_deep.py`: count names with >−8% per period; flag ≥3 simultaneous cascade
periods (multi-cascade). Measure BTC return in periods T+1, T+2 vs BTC rolling 30d mean return.
Apply period-cluster eff-n, cost. Expected n: 20–60 multi-cascade periods in 730d.

## data_status
HAVE — existing 8h BTC + alt perp cache. Expected n: 20–60 multi-cascade periods.

## Score
7.0 / 10
(edge_plausibility 6 × 2 + data_feasibility 9 + novelty 7) / 4

## Status
proposed
