# H-137 — Token unlock schedule × funding spike (BLOCKED)

**Status:** proposed · 2026-06-05 — BLOCKED (token unlock schedules not cached)
**Zone:** CALENDAR / EVENT-DRIVEN
**Score:** 5.0 (BLOCKED — not testable now)
**Asset universe:** would require per-token unlock schedule (not in cache)
**Created:** 2026-06-05

## Statement
Major token unlock events (vesting cliffs for team/investor tranches) create predictable
supply pressure on specific dates. In anticipation, short-sellers load up on perp shorts,
elevating NEGATIVE funding rates in the 1–2 weeks before the unlock. After the unlock date,
short-covering causes a funding snapback (short carry opportunity). Trade: enter carry
(long perp / short spot, i.e., short-carry) in the 2 weeks pre-unlock; exit on unlock date.

## Structural reason (who is forced)
Short-sellers opening pre-unlock shorts are FORCED to pay funding (negative side: they
receive it). Forced: the unlock date is fixed; no amount of market action changes when
tokens become liquid. Post-unlock: if price doesn't crash as expected, short-sellers are
forced to cover (stop-outs), driving funding positive.

## Falsifier
- BLOCKED: token unlock schedule (vesting dates, cliff sizes) is not in the current cache.
  Sources: TokenUnlocks.app, Dune Analytics — not real-time cached.

## Data status & effective-n
- data_status: BLOCKED. Token unlock schedules for the 50 names in funding cache are not
  available in project data. Would require scraping or purchasing TokenUnlocks data.
- Collect-forward: if unlock data becomes available, join to funding timestamps and test.

## One-line test (if unblocked)
Join token unlock schedule (unlock_date, token, size_pct) to funding 8h cache; extract
funding in the 7 days pre-unlock for each name; compare to 7 days post-unlock; permute
on unlock events; cluster by name.
