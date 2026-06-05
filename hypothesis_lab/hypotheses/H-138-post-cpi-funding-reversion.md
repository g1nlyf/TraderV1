# H-138 — Post-CPI 8h funding reversion: exit the spike

**Status:** proposed · 2026-06-05
**Zone:** CALENDAR / EVENT-DRIVEN
**Score:** 7.5
**Asset universe:** 29 tradeable Binance perps (funding 8h, 730d)
**Created:** 2026-06-05

## Statement
If funding spikes in the 8h period containing a CPI release (risk-on or risk-off surprise),
then in the 1–2 periods AFTER, leveraged positions are unwound as traders take profit or get
stopped. Funding reverts toward its prior moving average within 16–24h post-CPI. Trade:
enter carry at the post-CPI close (8h after CPI); hold 2 periods (16h); exit. This is the
reversion half of the CPI spike cycle (H-122 is the spike; this is the fade).

Combines with H-122: H-122 enters before CPI (eve spike entry), H-138 enters after CPI
(post-spike fade entry). Together they form a two-leg strategy around CPI events.

## Structural reason (who is forced)
The CPI-surprise directional bets opened in the 8h window contain overleveraged positions
that cannot survive a second 8h period of adverse drift. Forced closure of these positions
drives the reversion. Risk managers at small funds close positions on the close of the
event day as a standard protocol. This is structural and repeated monthly.

## Falsifier
(1) Funding in the 2 periods after CPI does NOT revert relative to the CPI-event period
    (no reversion cycle; funding stays elevated or continues declining monotonically).
(2) The reversion is just the normal mean-reversion of funding (captured by H-021 baseline),
    not incremental to the CPI calendar event.
(3) EV net of costs is negative — the 16h post-CPI window has lower-than-average funding,
    and the carry income does not exceed 11bps.

## Why uncaptured
Requires connecting an economic calendar to carry timing. Low eff-n (24 events but ~12 with
elevated funding). Two-step execution (wait for CPI event, then enter) is operationally complex.

## Data status & effective-n
- data_status: HAVE — funding 8h, timestamps; CPI dates hardcodable.
- eff-n: ~24 CPI events. Filter to events with spike (funding H0 > 90th pctile): reduces n.
- Feasibility: moderate (24 events, within-event paired design has more power).

## One-line test
Extend `funding_leads2.py`: for each CPI date, extract funding in H0 (event period), H+1, H+2;
compute mean(H+1, H+2) − mean(H0); test whether negative (reversion); permute on 24 events;
compute carry EV for entering at H+1 exit.
