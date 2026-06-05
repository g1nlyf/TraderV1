# H-070 — Cross-name contagion fade (high-corr names underperform after cascade in A)

**Status:** proposed
**Zone:** FORCED-FLOW PREMIA
**Created:** 2026-06-05 (Session 5)

## Statement
After name A cascades (>−8% 8h), names with the highest trailing 30d return-correlation to A
(top tercile) underperform the market in the same period and the following period, because portfolio
managers who are long both A and B face margin calls and must sell B to meet margin — even if B
has no idiosyncratic issue. This is the forced-selling SPILLOVER direction: not the bounce in A
(H-042), but the induced dip in B. Going short B (market-neutral, basis-short) on A's cascade
event harvests the contagion-forced selling in B before B bounces back.

## Quality filter
- **Who is FORCED & cannot stop:** portfolio margin calls force proportional liquidation across
  correlated holdings. The B seller cannot avoid selling B — their margin requirement is calculated
  on the total portfolio, not just A.
- **Falsifier:** high-corr names do not underperform low-corr names in the period of and after A's
  cascade (correlation doesn't predict contagion selling). Or B's underperformance is fully explained
  by A's market impact (demean removes it).
- **Why funds can't capture:** requires real-time cross-asset correlation tracking, short execution
  in a name that is dropping (B may gap through intended entry), and event sparsity.
- **data_status:** HAVE — 8h perp price 730d 49 names. Compute trailing 30d pairwise corr; flag A
  cascades; measure B-excess in same + next period. N: 200–500 B-events across A cascades.

## Test method
Extend `scripts/h042_deep.py`: for each A-cascade event, rank all other names by trailing 30d
corr to A. Flag top-tercile (B names). Measure B forward 1-period and 2-period excess return
(market-demean, B's per-name beta-adjust, period-cluster, cost). Test sign: expect NEGATIVE excess
(contagion underperformance) in period 0–1, potential reversion in period 2.

## data_status
HAVE — existing 8h perp cache. Expected n: 200–500 B-events.

## Score
7.0 / 10
(edge_plausibility 6 × 2 + data_feasibility 8 + novelty 8) / 4

## Status
proposed
