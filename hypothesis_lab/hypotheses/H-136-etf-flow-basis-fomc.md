# H-136 — ETF flow proxy via spot-perp basis around FOMC (BLOCKED)

**Status:** proposed · 2026-06-05 — BLOCKED (real-time ETF flows not cached)
**Zone:** CALENDAR / EVENT-DRIVEN
**Score:** 5.5 (BLOCKED — not testable now)
**Asset universe:** would require BTC ETF flow data (not in cache)
**Created:** 2026-06-05

## Statement
BTC ETF flows (BlackRock IBIT, Fidelity FBTC, etc.) show predictable spikes around FOMC
meetings as institutional macro allocators rotate in/out of BTC exposure via ETFs. These
flows BYPASS the perp market but affect spot price, widening or compressing the spot-perp
basis in a predictable FOMC-correlated pattern. Trade: infer ETF flow direction from
spot-perp basis anomaly around FOMC; use as a filter on the H-120/H-121 trade.

## Structural reason (who is forced)
Institutional ETF allocators move capital on FOMC outcomes (risk-on/risk-off reallocation).
They use spot ETFs, not perps — this creates a basis divergence that is structural and
calendar-driven. The flow is forced by the FOMC trigger.

## Falsifier / BLOCKED reason
- BLOCKED: real-time ETF daily flow data (e.g., from Bloomberg IBIT ETF flow series) is NOT
  in the cache. The spot-perp basis is observable (HAVE), but attributing it to ETF flows
  requires the flow data for the causal identification.
- Could be approximated: use SPOT-PERP BASIS CHANGE around FOMC as a PROXY for ETF flow.
  If basis widens on FOMC day, infer net ETF inflow; if compresses, outflow. This PROXY
  is testable from HAVE data — but it's an indirect measure.
- Partial unblock: test basis-change around FOMC (H-133 variant) WITHOUT claiming ETF causality.

## Data status & effective-n
- data_status: BLOCKED (ETF flow data not cached). Partial test possible via basis-change proxy.
- eff-n if partially unblocked: 16 FOMC events (same as H-120/H-121).

## One-line test (if unblocked)
Extend `funding_leads2.py`: around FOMC dates, measure basis_change = (perp_close − spot_close)
delta over the 24h FOMC window; test if basis_change is directionally predictable; permute on 16 events.
