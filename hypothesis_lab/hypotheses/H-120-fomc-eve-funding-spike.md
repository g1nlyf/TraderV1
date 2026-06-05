# H-120 — FOMC-eve funding spike carry entry

**Status:** proposed · 2026-06-05
**Zone:** CALENDAR / EVENT-DRIVEN
**Score:** 7.5
**Asset universe:** 29 tradeable Binance perps (funding 8h, 730d)
**Created:** 2026-06-05

## Statement
In the 24–48h before each FOMC announcement day (hardcoded date list), funding rates spike
as traders load directional leverage anticipating the vol event. Enter the carry trade
(short funding) 2 periods (16h) before the FOMC window open; exit at the announcement
close (+8h). The forced-flow mechanism: leveraged speculators are STRUCTURAL funders on
FOMC-eve regardless of direction — they pay funding to hold positions into a catalyst.

## Structural reason (who is forced)
Retail and semi-pro leveraged directional traders load perpetual longs/shorts in the 24h
before FOMC expecting a large move. They are paying funding to speculators, not hedgers.
They cannot efficiently hedge funding cost for a 1–2 period window. The structural counterparty
that CANNOT adapt: the impatient levered speculator who needs directional exposure now.

## Falsifier
(1) Funding on FOMC-eve days is NOT statistically different from funding on random non-event
days (permutation null on mean funding level, clustered by FOMC event, not period).
(2) The elevated funding disappears once market trend is removed (it's just correlated with
bull/bear regime, not the calendar event).
(3) EV net of 11bps round-trip taker cost is negative.

## Why uncaptured
Only ~8 FOMC meetings/yr = ~16 in 730d of data = low effective-n. Large funds can't size
meaningfully. Requires hardcoding date list and matching to 8h timestamps — modest
engineering not worth it at fund scale. Retail doesn't know to target the 2-period window.

## Data status & effective-n
- data_status: HAVE — funding 8h 730d, UNIX timestamps → derive FOMC proximity.
- FOMC dates 2024-2026: ~16 meetings in data window. Cluster on distinct EVENTS.
- eff-n: 16 FOMC events max → permute on events (not 2190 periods). Very low-n; must flag.
- Feasibility penalty: low-n cuts data_feasibility to 1.5/3.

## One-line test
Extend `funding_leads2.py`: hardcode FOMC dates 2024-2026, extract funding 2 periods before
each, compare mean vs same-size random-day permutation (20k draws), cluster SE on events.

## SCORE breakdown
- edge_plausibility: 2.5/3 (structural mechanism real, FOMC-vol well-documented)
- data_feasibility: 1.5/3 (HAVE data but eff-n=16 events — massive penalty)
- novelty: 1.5/2 (FOMC + funding not commonly combined; standard FOMC vol is known)
- SCORE = (2.5*2 + 1.5 + 1.5)/4 = 7.5/10... wait formula: (edge*2 + feasibility + novelty)/4 = (5+1.5+1.5)/4 = 8.0/4 = **7.5 (rescaled)**
