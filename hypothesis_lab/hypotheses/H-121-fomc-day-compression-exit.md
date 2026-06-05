# H-121 — FOMC-day funding compression exit

**Status:** proposed · 2026-06-05
**Zone:** CALENDAR / EVENT-DRIVEN
**Score:** 7.0
**Asset universe:** 29 tradeable Binance perps (funding 8h, 730d)
**Created:** 2026-06-05

## Statement
On FOMC announcement day (hardcoded), funding rates compress as leveraged positions are
forcibly unwound (stop-outs) or voluntarily closed into the announcement. EXIT existing
carry positions (or enter a long-funding / short-carry) in the 8h period starting at the
FOMC announcement. The forced-flow: margin calls and stop-outs during high-vol move cause
simultaneous position closures, collapsing funding demand.

## Structural reason (who is forced)
Levered longs hit stops during the FOMC move; margin-called accounts must close.
Simultaneously, discretionary traders take profits. Both reduce funding demand sharply.
Carry holders lose the funding income stream for this period; the reversal is a known risk.

## Falsifier
(1) Funding on FOMC days (announcement 8h window) is not measurably lower than average.
(2) The compression is not directional — funding falls equally in bull and bear FOMC outcomes.
(3) EV of exiting carry just before FOMC is negative vs holding through (i.e., the premium
    accrued during the event outweighs the compression).

## Why uncaptured
Operationally complex: requires live FOMC calendar feed and an automated rule to pause
carry entries on FOMC day. Small funds skip it. Retail doesn't know to exit systematically.

## Data status & effective-n
- data_status: HAVE — funding 8h, UNIX timestamps; FOMC dates hardcodable.
- eff-n: 16 FOMC events in 730d → cluster on EVENTS.
- Feasibility penalty: same as H-120 (eff-n=16).

## One-line test
Extend `funding_leads2.py`: for each FOMC date, extract funding in the 8h announcement
window; permute on events (not periods); test mean(FOMC period funding) vs mean(random days).
