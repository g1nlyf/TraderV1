# H-124 — Time-to-8h-settlement premium (enter N periods before, exit after)

**Status:** proposed · 2026-06-05
**Zone:** CALENDAR / EVENT-DRIVEN
**Score:** 8.0
**Asset universe:** 29 tradeable Binance perps (funding 8h, 730d) + 1m 180d (10 names)
**Created:** 2026-06-05

## Statement
Binance perp funding settles every 8h (00:00, 08:00, 16:00 UTC). In the N periods (N*8h)
BEFORE settlement, funding accrues linearly to the settlement timestamp. A carry trade
entered 1h before the 8h settlement captures ~7/8 of the 8h funding accrual with only
~1/8 of the time-at-risk. Risk-adjusted carry is highest when entered closest to settlement.

Specifically: on 1m data (HAVE 180d, 10 names), enter short-perp/long-spot position
60min before settlement close; exit 5min after settlement. Capture the final-hour
funding accrual while minimizing exposure to intra-period vol.

## Structural reason (who is forced)
Funding accrues continuously from settlement to settlement. Leveraged longs who entered
hours ago have ALREADY incurred most of the funding liability — they are locked in and
cannot efficiently exit to avoid the payment. The carry trader entering late captures the
pre-paid accrual with minimal time exposure. Structural advantage: the early-entrant levered
long cannot undo his funding liability; the late-entrant carry provider collects it.

## Falsifier
(1) Return in the 60min pre-settlement window is NOT different from a random 60min window
    sampled from the same names (permute on settlement events, cluster by name).
(2) Basis risk (intra-hour perp vs spot divergence) exceeds the captured funding — net negative.
(3) The effect is symmetric: the 60min post-settlement is equally profitable (meaning it's just
    random intraday momentum, not funding accrual).

## Why uncaptured
Requires 1m-level execution precision (rare for most researchers using 8h data). Small window
makes it appear low-capacity. Operationally requires watching the clock; automated execution
needed. Retail doesn't know the settlement schedule.

## Data status & effective-n
- data_status: HAVE — 1m 180d on 10 names. Settlement timestamps derivable (every 8h from
  epoch: 00:00, 08:00, 16:00 UTC). 180d = 540 settlements per name × 10 names = 5,400 events.
- eff-n: 5,400 settlement events — STRONG. Permute on settlement events, cluster by name.
- Feasibility: HIGH — 5,400 events on 10 names, good statistical power.
- Caveat: 10 names is a narrow universe; generalization TBD.

## One-line test
Extend `funding_leads2.py` with 1m data: for each 8h settlement timestamp, compute spot-perp
return in the 60min window [-65min, -5min]; compare mean to random 60min windows; cluster by name.
