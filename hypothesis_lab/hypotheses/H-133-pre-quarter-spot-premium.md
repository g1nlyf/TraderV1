# H-133 — Pre-quarter-end spot premium: perp basis widens as futures desks roll

**Status:** proposed · 2026-06-05
**Zone:** CALENDAR / EVENT-DRIVEN
**Score:** 7.0
**Asset universe:** 29 tradeable Binance perps (perp + spot price, 8h, 730d)
**Created:** 2026-06-05

## Statement
In the week before quarterly futures expiry (last-Fri of Mar/Jun/Sep/Dec), futures basis
traders begin rolling from the expiring contract to the next quarter. Rolling involves:
buying next-quarter futures + selling the expiring contract. The spot leg is NOT automatically
moved — they hold spot. Net effect: BASIS (perp-minus-spot spread) WIDENS as demand for
next-quarter futures creates an apparent premium on the forward curve, which spills into
perp pricing through basis arbitrage.

Trade: enter LONG BASIS (short perp, long spot) in the last 5 days before quarterly expiry;
collect the basis compression as it narrows at and after expiry. Distinct from H-129 which
focuses on funding-rate level; this targets the BASIS SPREAD directly.

## Structural reason (who is forced)
Quarterly roll desks must move to next-quarter contracts before expiry — they cannot defer.
The rolling creates systematic demand for next-quarter futures premium, which elevates the
basis. This is a mechanical flow with predictable timing.

## Falsifier
(1) Perp-minus-spot basis does NOT widen in the week before quarterly expiry vs a matched
    non-expiry week in the same quarter.
(2) Basis widening exists but is too small to exceed 11bps round-trip taker cost.
(3) The effect is absorbed by volatility — the basis reversal is noisy and the trade loses
    on most of the 8 events even if the mean is positive.

## Why uncaptured
Low eff-n (8 quarterly events). Basis measurement requires precise perp and spot price
synchronization — small desks may measure this noisily. Large desks ARE the mechanism.

## Data status & effective-n
- data_status: HAVE — perp 8h price + spot 8h price (basis = perp − spot). Quarterly expiry
  dates HARDCODABLE. ~8 events in 730d.
- eff-n: 8 events. Very low; flag explicitly.
- Feasibility: low-n but basis is directly observable — no derivation needed.

## One-line test
Extend `funding_leads2.py`: for each quarterly expiry (hardcoded last-Fri), compute mean
basis (perp_close − spot_close) in the 5 days before vs 5 days after expiry; permute on 8
expiry events; gate on signed mean > 11bps.
