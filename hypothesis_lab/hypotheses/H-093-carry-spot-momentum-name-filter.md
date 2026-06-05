# H-093 — Carry name filter by spot momentum direction (long carry only in uptrending names)

**Status:** proposed · 2026-06-05
**Zone:** Carry & Premia Extensions
**ID range:** H-093 (Zone 2 gen)
**SCORE:** 6.75  (edge_plausibility 6, data_feasibility 8, novelty 7) / 4 = 6.75

## Statement
Within the C-002 fixed-name book, apply an additional filter: hold the carry position only on names where the spot price 30-period momentum (spot_ret > 0 over the past 10 days) is positive. Hypothesis: longs pay funding more persistently when the spot trend supports their thesis — a downtrending spot causes leveraged longs to capitulate, reducing funding and increasing basis-blowout risk.

## Who is forced / why can't stop
Leveraged longs on uptrending names are "comfortable" forced payers — their position is profitable, reducing the urge to unwind. Leveraged longs on downtrending names are distressed forced payers — some will capitulate (liquidation cascade, H-042) while others stubbornly hold but with higher dropout risk. The uptrend names represent the more durable forced-payer pool.

## Falsifier
If carry APR conditioned on spot_momentum > 0 is NOT statistically better than unconditional carry (perm_p < 0.05, CI95 > 0), spot momentum is not a useful carry quality filter. Risk: this could simply select bull-market periods (regime bias) rather than a genuine per-name quality signal.

## Why uncaptured
The carry book is constructed as delta-neutral, so one might assume spot direction doesn't matter. But funding rates ARE directionally influenced (longs pay in up markets). This tests whether conditioning carry on the SPOT direction of each individual carry name — as a within-name funding quality predictor — adds value beyond the fixed-name selection.

## Data status
data_status: HAVE
- Spot 8h closes 730d available for all carry names in the funding cache

## Test (one line)
Extend `carry_lift.py`: compute per-name rolling 30p spot return; zero-weight each name when its spot momentum < 0; compare momentum-filtered carry book Sharpe/APR vs always-on baseline via `fh.evaluate`.
