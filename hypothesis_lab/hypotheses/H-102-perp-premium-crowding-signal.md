# H-102 — Perp premium (basis) as crowding signal for carry entry timing

**Status:** proposed · 2026-06-05
**Zone:** MICROSTRUCTURE SIGNALS — perp premium vs spot as crowding proxy
**ID range:** H-102 (Zone 3 generation)

## Statement
The perp/spot price ratio (basis = perp_close / spot_close − 1) reflects how crowded the long-perp
side is. When basis is elevated (perp > spot), leveraged longs have bid up the perp and funding
is about to compress (or spike then reset). Use basis level as a CARRY TIMING filter: only collect
carry when basis is in the lower 40th percentile (perp not overcrowded), and exit/reduce when
basis is in the upper 20th percentile (crowd too large, compression risk imminent).

## Structural logic
**Who is forced:** When basis is high, the longs who drove it up are leveraged and vulnerable
to a cascade (H-042). When basis is low or negative, the crowd has already been flushed —
the carry collected now faces less directional headwind from a forced-unwind. This is a
carry-quality timing signal, not a direction signal.

## Falsifier
Basis level (perp premium) has no predictive value for subsequent funding carry APR; or
low-basis periods underperform high-basis periods (carry is highest precisely when crowding
is highest, so timing against crowd is net-negative).

## Why uncaptured
Basis is derivable from perp+spot closes, but most carry implementations do not segment by
basis percentile. The interaction between crowding and carry compression is subtle and requires
joint perp+spot data.

## Data status
**HAVE** — perp 8h closes for 50 names + spot 8h closes (730d). Basis = perp/spot − 1 is
directly derivable. This is fully testable now.

## Test (one line)
In `funding_leads2.py`: compute per-name 8h basis = perp_close/spot_close − 1; restrict carry
evaluation to periods where basis < 40th-percentile; compare APR/Sharpe to always-on carry.

## SCORE: 8.0
(edge_plausibility=4, data_feasibility=5, novelty=3 → (4×2+5+3)/4 = 4.0 → 8.0)
