# H-129 — Quarterly futures last-Friday basis compression

**Status:** proposed · 2026-06-05
**Zone:** CALENDAR / EVENT-DRIVEN
**Score:** 7.5
**Asset universe:** 29 tradeable Binance perps (funding 8h + spot price, 730d)
**Created:** 2026-06-05

## Statement
Binance quarterly futures expire on the last Friday of each quarter (Mar/Jun/Sep/Dec).
In the 3 periods (24h) before expiry, basis traders unwind: they are long spot / short
quarterly futures, and as futures converge to spot, they simultaneously close both legs.
The spot selling + futures short-cover creates a NET PERP FUNDING ELEVATION as basis
arb traders shift to perps. Enter carry (short perp, long spot) 24h before quarterly
expiry; exit 8h after expiry. ~8 quarterly expiries in 730d.

Hardcodable last-Friday dates 2024-2026:
- 2024: Mar 29, Jun 28, Sep 27, Dec 27
- 2025: Mar 28, Jun 27, Sep 26, Dec 26
- 2026: Mar 27 (if in data window)

## Structural reason (who is forced)
Quarterly basis arb desks MUST unwind at expiry — the contract terminates. They cannot
roll indefinitely. The expiry-forced unwind creates predictable flow pressure on spot and
perps in the 24h window. Structural: contract expiry is physically forced.

## Falsifier
(1) Funding in the 24h before quarterly expiry is NOT higher than funding in a 24h window
    5 days before expiry (matched control, same quarter-week).
(2) The effect is absorbed by H-123 (quarter-end week) — it's a subset of the week effect,
    not the specific last-Friday.
(3) The basis trade has already converged 3+ days before expiry; no flow pressure remains.

## Why uncaptured
Only 8 events in 730d. Last-Friday expiry schedule is public, but the funding impact requires
connecting basis unwind → perp demand, which most traders don't model. Large funds ARE the
mechanism and can't arb themselves.

## Data status & effective-n
- data_status: HAVE — funding 8h, timestamps. Quarterly expiry dates HARDCODABLE (last Friday
  of Mar/Jun/Sep/Dec for Binance quarterly futures). ~8 events in 730d.
- eff-n: 8 events — very low; must flag. Permute on 8 events only.
- Feasibility: low-n penalty; but strong structural mechanism.

## One-line test
Extend `funding_leads2.py`: hardcode quarterly expiry dates (last-Fri of Mar/Jun/Sep/Dec);
extract funding H-3 through H+1 relative to expiry; compare H-3..H-1 mean vs H-5..H-3 mean;
permute on 8 events.
