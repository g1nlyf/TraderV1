# H-076 — Forced long exit after sustained high-funding persistence (≥10 periods)

**Status:** proposed
**Zone:** FORCED-FLOW PREMIA
**Created:** 2026-06-05 (Session 5)

## Statement
A name with ≥10 consecutive 8h periods in the top-quartile funding for that name (trailing 90d) is
a severely over-leveraged long book. At some point the book MUST unwind — carry drain forces the
weakest hands out. The unwind signal: when funding DROPS by more than 20% in a single period after
a streak of ≥10 elevated periods, the forced-long unwind is beginning. This is the first observable
footprint. Go market-neutral short (perp long/spot short = basis short) on the funding-drop signal;
the price decline that follows is forced (longs are being squeezed out, not choosing to exit).
Cover after 2–3 periods when funding stabilizes.

## Quality filter
- **Who is FORCED & cannot stop:** longs who have been paying 10+ periods of elevated carry have
  progressively thinner margin; any financing disruption or small P&L move triggers mass forced
  exit. The funding drop is the exit footprint — it means OI is falling involuntarily.
- **Falsifier:** the funding-persistence-break does not predict forward price underperformance
  (funding drops for structural reasons, e.g., the asset's funding cyclically normalizes, not
  because of forced unwinding).
- **Why funds can't capture:** requires per-name streak tracking across funding history; the signal
  fires rarely and requires short-position execution when carry is still positive; event timing
  uncertain.
- **data_status:** HAVE — 8h funding 730d 50 names. Compute per-name consecutive high-funding
  streak; flag streak ≥10 followed by ΔF < −20% in one period.

## Test method
Extend `scripts/funding_leads2.py`: compute per-name consecutive top-quartile funding streak
(rolling 90d threshold); flag streak ≥10 → streak_break (first period where ΔF < −20%). Measure
forward price excess return (market-demean, per-name beta-adjust) over 2–3 periods. Apply period-
cluster eff-n, cost 11bps RT. Expected n: 30–80 streak-break events in 730d.

## data_status
HAVE — existing 8h funding cache. Expected n: 30–80 events.

## Score
7.25 / 10
(edge_plausibility 7 × 2 + data_feasibility 9 + novelty 6) / 4

## Status
proposed
