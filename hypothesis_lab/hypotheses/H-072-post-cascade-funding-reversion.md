# H-072 — Post-cascade funding collapse → carry restoration

**Status:** proposed
**Zone:** FORCED-FLOW PREMIA
**Created:** 2026-06-05 (Session 5)

## Statement
After a liquidation cascade (>−8% 8h), funding rates for the cascaded name collapse in the
following 1–2 periods as surviving longs exit and OI drops. This creates a transient funding
trough below the name's own baseline. In the 2–4 periods after the cascade, funding restores
(new leveraged longs re-enter at cheaper prices), creating an elevated carry window. Enter the
carry trade (long spot/short perp, H-021/C-002 method) during the funding trough period; exit
when funding restores to pre-cascade levels. The forced-flow event (cascade) creates a temporary
carry entry that doesn't exist in normal markets.

## Quality filter
- **Who is FORCED & cannot stop:** post-cascade OI drop is involuntary — the margin-called longs
  have already exited and cannot hold. The funding collapse is a mechanical consequence.
  New carry entrants in the trough are the adaptive counterparty taking the other side.
- **Falsifier:** funding does NOT systematically drop after cascades vs non-cascade periods,
  OR the post-cascade carry yield is no better than random-period carry yield for the same names.
- **Why funds can't capture:** requires tracking cascade events AND having capital available
  immediately post-crash to enter carry — most funds are reducing risk during cascades, not
  adding. Event-driven carry execution is operationally distinct from static carry books.
- **data_status:** HAVE — 8h price + funding 730d. Flag −8% cascade events; measure funding
  level in periods T+1 through T+4 vs trailing 30d median. Expected n: ~90 events (H-042 base).

## Test method
Extend `scripts/h042_deep.py` or `funding_leads2.py`: for each −8% cascade event, compute
funding in T+1, T+2, T+3, T+4. Compare to trailing 30d median funding for same name. Measure:
(a) funding trough depth (T+1 vs baseline); (b) carry yield in T+2–T+4 window vs baseline
carry for same name. Apply period-cluster eff-n, cost model (maker rate, 1bp/side).

## data_status
HAVE — existing 8h price + funding cache. Expected n: ~90 cascade events with funding data.

## Score
7.25 / 10
(edge_plausibility 7 × 2 + data_feasibility 9 + novelty 6) / 4

## Status
proposed
