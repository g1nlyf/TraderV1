# H-125 — Month-end perp-expiry basis compression

**Status:** proposed · 2026-06-05
**Zone:** CALENDAR / EVENT-DRIVEN
**Score:** 7.0
**Asset universe:** 29 tradeable Binance perps (funding 8h + spot price, 730d)
**Created:** 2026-06-05

## Statement
At calendar month-end, perpetual funding compresses (or briefly turns negative) as:
(1) Monthly-expiry futures settle and basis traders unwind the long-spot/short-future leg,
    creating net spot selling pressure and perp demand reduction.
(2) Portfolio-level PnL locking causes simultaneous leverage reduction.
The funding compression window is typically the last 2–3 periods of each month (last 16–24h).
730d = ~24 month-ends → eff-n=24 events.

## Structural reason (who is forced)
Futures basis traders unwind at contract expiry — they must. They are price-insensitive to
the exact moment of unwind because basis has converged; they just need the spot and futures
to clear. This creates a short burst of coordinated spot selling + perp demand collapse.
Who's forced: basis arb desks with expiring contracts.

## Falsifier
(1) Funding in the last 2 periods of each month is NOT lower than funding in the first 2
    periods of the same month (matched control).
(2) Effect exists only in months with quarterly expiry (not a monthly effect but a quarterly one
    — this would mean H-123 subsumes it).
(3) Net EV is negative — the carry reduction exceeds the window entry cost.

## Why uncaptured
Low eff-n (~24 events, shared with multiple hypotheses). Large desks know this and front-run
it, making the signal noisy for everyone else. Retail doesn't trade with the calendar.

## Data status & effective-n
- data_status: HAVE — funding 8h + timestamps; month-end derivable from UNIX timestamp.
- eff-n: 24 month-ends in 730d. Better than FOMC (16) and quarter-end (8).
- Feasibility: moderate. Permute on month-end events.

## One-line test
Extend `funding_leads2.py`: flag last 3 periods of each month from UNIX timestamps; compute
mean funding vs first 3 periods of same month; permute on 24 month-end events (not periods).
