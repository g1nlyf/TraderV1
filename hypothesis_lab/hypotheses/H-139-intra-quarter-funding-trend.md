# H-139 — Intra-quarter funding trend: monotone rise into quarter-end, fade after

**Status:** proposed · 2026-06-05
**Zone:** CALENDAR / EVENT-DRIVEN
**Score:** 7.0
**Asset universe:** 29 tradeable Binance perps (funding 8h, 730d)
**Created:** 2026-06-05

## Statement
Within each calendar quarter, funding rates may exhibit a MONOTONE TREND: rising from
quarter-start (fresh capital deployment, new bets) through quarter-end (peak leverage,
window-dressing) then falling sharply in the first 2 weeks of the new quarter (reset,
de-leveraging post-reporting). This creates an intra-quarter seasonal funding arc.

If confirmed: enter carry at quarter-start (Q+0 to Q+14 days) at BASE WEIGHT; scale up
carry weights through Q+30 to Q+75 days; reduce/exit in the last 5 days (Q-5 to Q-end,
captured better by H-123). This is a WEIGHT-SCALING signal on top of H-021 base carry.

## Structural reason (who is forced)
Portfolio managers deploy capital at quarter-start (new mandates, performance pressure resets).
This builds into leverage through the quarter. At quarter-end, PnL locking + window-dressing
force long positions to be maintained (can't sell into NAV date). Post-quarter: mandatory
de-leveraging and reset. This is a quarterly institutional rhythm documented in equities
and extending to crypto through institutional adoption.

## Falsifier
(1) The intra-quarter funding trend is NOT monotone — funding is flat or random within quarters
    (controlling for BTC contemporaneous price trend).
(2) The trend reverses in bearish quarters (Q-end de-leveraging starts BEFORE quarter-end),
    making the signal unreliable.
(3) The effect is subsumed by H-123 (last-week elevation) without needing the full quarter arc.

## Why uncaptured
Requires intra-quarter day-of-quarter computation (day 1-90 within each quarter). Low
statistical power: only 8 quarters in 730d, so testing monotone trend requires within-quarter
rank correlation — low eff-n. Regime-dependent (works in bull quarters, fails in bear).

## Data status & effective-n
- data_status: HAVE — funding 8h + timestamps. Day-of-quarter derivable from UNIX timestamps.
- eff-n: 8 quarters in 730d. Within each quarter: ~270 periods. The CROSS-QUARTER test has
  eff-n=8; within-quarter slope test has n=270 per quarter.
- Feasibility: moderate — the within-quarter slope test is feasible; the cross-quarter
  consistency test (does trend replicate?) has eff-n=8.

## One-line test
Extend `funding_leads2.py`: for each 8h period, compute day_of_quarter (0-90) from UNIX
timestamp; regress mean_funding ~ day_of_quarter within each quarter; report slope mean ±
SD across 8 quarters; test if mean slope > 0 via within-quarter Spearman rank test.
