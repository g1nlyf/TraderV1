# H-126 — Funding in 24h after BTC halving anniversary

**Status:** proposed · 2026-06-05 — COLLECT-FORWARD (n=1 in data)
**Zone:** CALENDAR / EVENT-DRIVEN
**Score:** 6.5
**Asset universe:** 29 tradeable Binance perps (funding 8h, 730d)
**Created:** 2026-06-05

## Statement
BTC halving (2024-04-20) is a known supply-shock date. In the 24h AFTER the halving event
(and annually on its anniversary), retail and media attention peaks, driving leveraged long
demand and funding rate elevation. Trade: enter carry on halving day, collect the 3 periods
of post-halving elevated funding, exit.

BTC halving 2024-04-20 is in the data window. Anniversary 2025-04-20 is also in the 730d
window if data extends to Apr 2026. That gives at most 2 events.

## Structural reason (who is forced)
Media-driven FOMO creates structural leveraged longs on the specific calendar date. These
traders cannot efficiently time their entry to avoid the funding spike — they are reactive,
not adaptive. Who's forced: the retail FOMO crowd on a known calendar date.

## Falsifier
(1) Funding in the 24h after halving is NOT different from the 24h before halving (symmetric
    test controls for trend).
(2) Effect is just BTC-trend correlated — removing BTC contemporaneous return kills the signal.
(3) n=1 or n=2 is not testable — this is definitionally true if data only contains one event.

## Why uncaptured
n=1 (or at best n=2) — statistically untestable. The event is unique and rare. Large funds
know this date and position for it, but can't backtest. The "edge" may be a single observation.

## Data status & effective-n
- data_status: HAVE — 2024-04-20 halving is in the 730d window. Anniversary 2025-04-20 likely
  in window if data extends to late 2025. HARDCODABLE dates.
- eff-n: 1–2 events. This is DEFINITIONALLY too small for any permutation null.
- Feasibility: very low (eff-n=1-2). Collect-forward; do NOT test now.
- data_status tag: HAVE but n-blocked.

## One-line test (collect-forward)
Extend `funding_leads2.py`: hardcode halving date 2024-04-20 + 2025-04-20; extract the 3
periods of post-halving funding; descriptive only until n>=5 events (next halvings).
