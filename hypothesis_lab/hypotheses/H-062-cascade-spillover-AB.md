# H-062 — Cross-name cascade spillover A→B mean-reversion

**Status:** proposed
**Zone:** FORCED-FLOW PREMIA
**Created:** 2026-06-05 (Session 5)

## Statement
When name A experiences a liquidation cascade (>−8% 8h), high-return-correlation names (top tercile
of trailing 30d pairwise corr to A) are dragged down in the same or next period by forced liquidation
of correlated-portfolio holders. Name B's forced drop is not idiosyncratic — it is contagion. The
bounce in B over the next 1–2 periods (excess over market) should be positive and larger when B's own
concurrent drop was steeper (more contagion-forced selling). Trade B market-neutral on A's cascade.

## Quality filter
- **Who is FORCED & cannot stop:** multi-asset portfolio margin calls — when A drops hard, the portfolio
  drops and triggers margin on the correlated book, forcing B selling even if B's own fundamentals
  are unchanged. Cannot defer the margin call.
- **Falsifier:** the B-excess bounce disappears once the market index move is removed — it was all
  systematic (beta). OR correlation to A does not predict the bounce (random at any corr-tercile).
- **Why funds can't capture:** requires real-time cross-asset correlation tracking, entering into a
  contagion crash, managing pairs of hedges, sparse events at the name-pair level.
- **data_status:** HAVE — 8h perp price 730d for 49 names. Compute trailing 30d pairwise corr, flag A
  cascades, isolate B names in top-corr tercile, measure B forward excess.

## Test method
Extend `scripts/h042_deep.py`: for each −8% cascade in name A, compute trailing 30d return-corr to
all other names; flag top-tercile corr names as B. Measure B's period-1 and period-2 forward excess
return (market-demean + B's own per-name beta-adjust + period-clustered eff-n + cost). Compare to
B's excess return in periods without an A cascade.

## data_status
HAVE — existing 8h perp cache. Pairwise corr computed in-sample. Expect n: 200–600 (A-cascade
events × avg correlated names per event).

## Score
7.5 / 10
(edge_plausibility 7 × 2 + data_feasibility 7 + novelty 9) / 4

## Status
proposed
