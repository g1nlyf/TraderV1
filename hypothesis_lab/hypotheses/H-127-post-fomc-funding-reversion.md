# H-127 — Post-FOMC funding reversion: spike then mean-revert within 24h

**Status:** proposed · 2026-06-05
**Zone:** CALENDAR / EVENT-DRIVEN
**Score:** 7.5
**Asset universe:** 29 tradeable Binance perps (funding 8h, 730d)
**Created:** 2026-06-05

## Statement
If funding spikes on FOMC announcement (H-120 thesis), then in the 1–2 periods AFTER the
announcement, funding mean-reverts as stop-outs and voluntary closures reduce net leverage.
Trade: enter carry (short perp, long spot) at the FOMC announcement close (after the vol
spike); exit 2 periods later (16h). This captures both the residual spike AND the reversion.
Complement to H-120 (eve entry) and H-121 (day compression). Together they describe a
spike-and-revert cycle around FOMC.

## Structural reason (who is forced)
In the 2 periods after FOMC: losing directional bets are closed (stop-outs or voluntary
admission of being wrong). The spike in net long exposure reverts as longs close. The carry
trader who entered at or after the announcement is short the reversion and long the carry
accrual simultaneously. Double-counting of the carry + reversion premium.

## Falsifier
(1) Funding in the 2 periods after FOMC is NOT lower than funding in the 2 periods before
    FOMC (no reversion cycle exists — it's just a level shift).
(2) The post-FOMC excess return is negative for the carry trader (basis divergence exceeds
    funding collected during the spike).
(3) The spike-and-revert cycle doesn't exist: funding is higher post-FOMC than pre-FOMC
    permanently (hawkish Fed = sustained risk-on).

## Why uncaptured
Requires live FOMC calendar. Low eff-n (16 events). Speed requirement — must enter within
one 8h period of the announcement. Operationally heavy.

## Data status & effective-n
- data_status: HAVE — funding 8h, timestamps; FOMC dates hardcodable.
- eff-n: 16 FOMC events; measure spike (H0 window) vs post (H+1, H+2) — within-event paired test.
- Feasibility: moderate for a within-event test (more power than cross-event comparison).

## One-line test
Extend `funding_leads2.py`: for each FOMC date, extract funding H0 (announcement 8h window)
vs H+1 and H+2; within-event paired mean test; permute on 16 events; compute carry EV H+1 to H+2.
