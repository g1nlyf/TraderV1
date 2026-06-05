# H-130 — Settlement-hour 1m entry: last 15min before 8h tick, harvest accrual

**Status:** proposed · 2026-06-05
**Zone:** CALENDAR / EVENT-DRIVEN
**Score:** 8.0
**Asset universe:** 10 names with 1m 180d data (Binance perp + spot)
**Created:** 2026-06-05

## Statement
Refines H-124. Funding accrues on a CONTINUOUS basis between settlements but is PAID at the
8h tick. A position entered 15min before the 8h settlement captures 15/480 = 3.1% of the
settlement period but receives the FULL 8h settlement payment in the NEXT accounting moment.
Wait — the actual mechanic: Binance funding settles every 8h; the accrued amount is paid to
or charged from accounts at 00:00, 08:00, 16:00 UTC. A position held THROUGH the settlement
receives the full 8h payment.

Sharper version: the funding rate is FIXED for the entire 8h period (calculated 1h before
settlement based on premium index). Enter the carry trade at T-60min (when rate is known
and locked); hold 60min to capture the full settlement payment; exit at T+5min.
Expected: collect ~100% of the 8h funding with ~12.5% of the time exposure.

If average 8h funding is 0.02% (positive), this means 0.02% / 12.5% time ratio = 1.28%
annualized equivalent per locked minute. The question is whether execution cost (11bps RT)
exceeds the 0.02% single-event capture.

Reality check: average 8h funding on Binance is ~0.01-0.03%. Single event at 15min: 0.01-0.03%
gross. With 11bps (0.11%) RT cost: this is LOSS-MAKING on average. HOWEVER, if we filter to
only HIGH-FUNDING-RATE events (e.g., funding > 0.05% in the settlement period), the entry is
profitable. That selective entry is the testable hypothesis.

## Structural reason (who is forced)
Leveraged longs cannot exit 15min before settlement without losing their position; closing
and re-entering costs more than paying funding. They are locked in at T-60min. The carry
trader enters at exactly the moment the rate is known and locked — pure information advantage.

## Falsifier
(1) Filtered entry (funding > 0.05%) does NOT produce positive net EV after 11bps RT cost
    (i.e., the high-funding-rate events are too rare to matter, or the basis risk in 60min
    exceeds the funding captured).
(2) Returns in the 60min pre-settlement window are NOT different from random 60min windows —
    the "funding lock" effect doesn't concentrate vol asymmetrically.
(3) The trade works on 8h data too (no 1m required) — meaning the 1m precision adds nothing.

## Why uncaptured
Requires 1m data and execution with ~5min precision around the settlement tick. Most researchers
use 8h data only. Retail can't monitor 3 settlement windows per day reliably.

## Data status & effective-n
- data_status: HAVE — 1m 180d on 10 names. Settlements: every 8h = 3/day × 180d × 10 names
  = 5,400 events. Filtered (funding > 0.05%): fewer, depends on distribution.
- eff-n: thousands of settlement events; filter reduces to hundreds — still strong.
- Feasibility: HIGH given 1m data availability.

## One-line test
Extend `funding_leads2.py` with 1m: for each settlement (8h tick), filter periods where
8h funding rate > 0.05%; compute spot-perp return from T-65min to T+5min; permute on events,
cluster by name; gate on realized EV > 11bps RT cost.
