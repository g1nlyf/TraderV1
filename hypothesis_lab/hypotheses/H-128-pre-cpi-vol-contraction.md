# H-128 — Pre-CPI vol contraction: funding falls before CPI then spikes

**Status:** proposed · 2026-06-05
**Zone:** CALENDAR / EVENT-DRIVEN
**Score:** 7.0
**Asset universe:** 29 tradeable Binance perps (funding 8h, 730d)
**Created:** 2026-06-05

## Statement
In the 8h period BEFORE a US CPI release (typically 08:30 ET on release day), traders
REDUCE leverage (risk-off into the number), causing funding to compress. Then if CPI surprises,
funding spikes in the 8h post-release. The pre-CPI funding compression creates a LONG-FUNDING
opportunity (enter long perp / short spot) in the 8h before the print; exit at the release.
This is the mirror image of the post-CPI carry trade (H-122).

## Structural reason (who is forced)
Risk managers at prop desks and small funds force position reduction before high-uncertainty
macro prints. They cannot wait for the actual print — risk limits require pre-event de-risking.
Structural counterparty: forced de-riskers who must close regardless of price.

## Falsifier
(1) Funding in the pre-CPI 8h window is NOT lower than the prior 8h window (no compression).
(2) The compression is not asymmetric — it exists pre-NFP and pre-random days equally (not
    CPI-specific; just time-of-day effect since CPI releases at 08:30 ET = predictable time).
(3) The long-funding trade loses to costs: funding compression is <11bps round-trip.

## Why uncaptured
Requires detecting the "before" window relative to an 08:30 ET release time. If the 8h
settlement crosses the CPI release time, the signal straddles two periods (complex alignment).
Low-n (~24 CPI events). Retail doesn't short funding (long perp direction vs spot).

## Data status & effective-n
- data_status: HAVE — funding 8h, timestamps. CPI dates hardcodable from BLS schedule.
  Need to align 8h settlement windows to 08:30 ET release time — some CPI releases fall
  within the 00:00-08:00 UTC window, others in 08:00-16:00 UTC.
- eff-n: ~24 CPI events in 730d. Permute on events.
- Feasibility: moderate (24 events, but window alignment is fiddly).

## One-line test
Extend `funding_leads2.py`: for each CPI date, identify the 8h settlement period containing
08:30 ET; extract the prior period's funding (pre-CPI); compare to same-weekday random control;
permute on 24 events.
