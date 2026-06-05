# H-078 — Post-cascade second-wave re-drop and bounce (3rd-period reversion)

**Status:** proposed
**Zone:** FORCED-FLOW PREMIA
**Created:** 2026-06-05 (Session 5)

## Statement
After a cascade (H-042: −8%, period 0) and the initial bounce (period 1), some names attract new
leveraged longs into the recovery — creating a fresh crowded book at the new lower price. If funding
rises again in period 1 (new longs paying carry on the bounce), a second mini-cascade occurs in
period 2 (the new longs get squeezed) and the name AGAIN bounces in period 3. This is a 3rd-period
reversion signal triggered by: (cascade in period 0) + (funding rise in period 1) + (price decline
in period 2). The forced party in period 2 is the new leveraged buyer from period 1.

## Quality filter
- **Who is FORCED & cannot stop:** new leveraged longs who bought the period-1 bounce at elevated
  funding face the same margin-call mechanism as period-0 longs. They entered voluntarily but
  cannot exit voluntarily when the period-2 price decline hits their margin threshold.
- **Falsifier:** the 3-period sequence (drop → bounce → drop) does not reliably predict a 4th-period
  bounce above the market (the pattern is noise, not forced flow). OR the sequence is too rare for
  inference.
- **Why funds can't capture:** requires tracking a 3-period event sequence per name with funding
  overlay — very sparse, multi-period monitoring, small per-event opportunity.
- **data_status:** HAVE — 8h price + funding 730d. Subset of H-042 cascade events where period 1
  shows funding rise AND period 2 shows a price decline >−3%. Expected n: 10–30 (very sparse).

## Test method
Extend `scripts/h042_deep.py`: post-H-042 event (−8% in period 0), check period 1 (funding > prior
period by >10%, AND price > 0%) AND period 2 (price < −3%). Measure period-3 excess return.
Apply H-042 hardened protocol. Flag as n-blocked if OOS n < 20; collect-forward.

## data_status
HAVE (n-limited) — expected n~10–25 qualifying sequences in 730d. Forward-collect needed for gate.

## Score
7.25 / 10
(edge_plausibility 6 × 2 + data_feasibility 8 + novelty 9) / 4

## Status
proposed
