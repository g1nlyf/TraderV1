# H-123 — Quarter-end funding elevation (last week of quarter)

**Status:** proposed · 2026-06-05
**Zone:** CALENDAR / EVENT-DRIVEN
**Score:** 7.5
**Asset universe:** 29 tradeable Binance perps (funding 8h, 730d)
**Created:** 2026-06-05

## Statement
In the last 5 trading days of each calendar quarter (last week of Mar/Jun/Sep/Dec), funding
rates elevate as institutional desks and crypto-native funds window-dress positions and as
quarterly futures/perp-like instruments approach expiry, causing leveraged long demand to
spike. Enter carry (short perp, long spot) on day Q-5 of each quarter; exit on quarter-end
close. 730d spans ~8 full quarter-ends.

## Structural reason (who is forced)
(1) Quarterly futures traders roll positions to next contract — creates synthetic demand
    pressure on perpetuals as arb desks set up next-quarter basis trades.
(2) Fund window-dressing: portfolios add long crypto exposure into quarter-end to show
    performance on NAV date — forced buyers regardless of rate.
(3) Retail "end of quarter FOMO": seasonal positioning has been documented in equities
    and exports to crypto.
Who can't adapt: funds with mandated quarter-end reporting.

## Falsifier
(1) Funding in Q-end week is NOT higher than funding in Q-start week (symmetric test).
(2) Effect disappears when conditioning on BTC trend direction — it's just trend-correlated.
(3) Net EV after costs is negative (funding premium exists but below 11bps RT threshold).

## Why uncaptured
Only 8 quarter-ends in 730d. Large funds ARE the mechanism; they know, but can't arb
themselves. Retail doesn't know the quarterly window. Low-capacity signal.

## Data status & effective-n
- data_status: HAVE — funding 8h + timestamps. Q-end dates derivable from UNIX timestamps
  (last 5 trading days of Mar/Jun/Sep/Dec).
- eff-n: 8 quarter-ends → very low. Permute on QUARTER-END EVENTS (not periods).
- Feasibility penalty: eff-n=8 is the worst case here; treat with extreme caution.

## One-line test
Extend `funding_leads2.py`: derive quarter-end flag from UNIX timestamp (month in {3,6,9,12}
and day >= 25); compute mean funding in Q-end week vs Q-start week; permute on 8 events.
