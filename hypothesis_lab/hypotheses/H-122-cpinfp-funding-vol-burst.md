# H-122 — CPI/NFP release funding vol burst carry

**Status:** proposed · 2026-06-05
**Zone:** CALENDAR / EVENT-DRIVEN
**Score:** 7.0
**Asset universe:** 29 tradeable Binance perps (funding 8h, 730d)
**Created:** 2026-06-05

## Statement
US CPI (monthly, ~2nd/3rd Tue) and NFP (monthly, 1st Fri) releases trigger sharp BTC-led
vol spikes that manifest in funding rate elevation. Enter carry (short funding) 1 period
(8h) before the release; collect the pre-release funding premium; exit 1 period after.
CPI release in 730d: ~24 events. NFP: ~24 events. Combined: ~48 distinct events.

## Structural reason (who is forced)
Pre-release: traders load directional perp exposure (long/short BTC and alts) positioning
for the print. They pay funding to hold. Post-release: losers (wrong-direction bets) get
stopped out; funding spikes if the move is large, then normalizes. Structural funders:
impatient directional speculators who cannot defer entry to avoid funding cost.

## Falsifier
(1) Funding in CPI/NFP pre-window is NOT different from random monthly days at the same
    calendar position (controls for month-end effects).
(2) Effect disappears when BTC contemporaneous move is included as control — it's just
    vol-correlated, not calendar-event-specific.
(3) Cost exceeds premium (especially if funding didn't actually spike vs normal).

## Why uncaptured
Small funding window (8h), low-n per event type (~24 each), requires live econ-calendar.
Easy for a retail trader to miss the exact window. Low capacity for large funds.

## Data status & effective-n
- data_status: HAVE (funding 8h, timestamps); CPI/NFP dates 2024-2026 hardcodable from BLS
  public release schedule (~48 combined events in 730d).
- eff-n: 48 events (better than FOMC), but cluster by event-type separately first.
- Feasibility: moderate — 48 events allows permutation on events with reasonable power.

## One-line test
Extend `funding_leads2.py`: hardcode CPI+NFP dates, extract funding H-1 period relative
to release; permute on distinct events (not periods); compare mean vs random same-calendar-day.
