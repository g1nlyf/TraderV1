# H-089 — Carry name selection by composite level × persistence score

**Status:** proposed · 2026-06-05
**Zone:** Carry & Premia Extensions
**ID range:** H-089 (Zone 2 gen)
**SCORE:** 7.25  (edge_plausibility 7, data_feasibility 9, novelty 7) / 4 = 7.25

## Statement
Select carry names by the product (mean_funding_level × persistence_fraction) rather than by either alone. Names that are BOTH high-funding AND persistently positive rank highest. Hypothesis: the composite score removes names that have high average funding driven by rare large spikes (which dynamic chasing H-13 tried to capture and failed) and keeps only the structurally durable high-carry names.

## Who is forced / why can't stop
A name with high mean AND high persistence means structurally committed leveraged longs — they are paying every period, not just occasionally. These represent the deepest, most durable forced-payer behavior. Spike-driven high-mean names have episodic forced-payer behavior that reverts (the H-13 trap).

## Falsifier
If the composite-score top-10 does not outperform top-10-by-level (C-002 H-021 baseline) OOS with perm_p < 0.05, the composite adds no value over the simpler level filter. Risk of overfitting is real here — two free parameters (level weight, persistence weight) could be in-sample overfit even with a simple product form. Guard: use train period for selection, test period strictly OOS.

## Why uncaptured
H-021 tested level and persistence SEPARATELY and found level marginally better (1.44% vs 1.34% APR). The INTERACTION (names high on BOTH) was noted in the refinement path but never tested. The product form avoids a parameter choice (no weighting coefficient to overfit).

## Data status
data_status: HAVE
- Funding panel 8h 730d — both mean and persistence computable from same series

## Test (one line)
Extend `carry_leads.py`: compute composite_score = mean_funding × persistence_fraction per name on train; select top-10 by composite; run OOS carry via `fh.evaluate` + block-bootstrap CI95; compare APR/Sharpe vs top-10-by-level and top-10-by-persistence.

## Results (2026-06-05) — `test_carry_cluster.py` — higher APR, Sharpe collapses (no flag)
top-10 by composite = train mean-funding × persistence-fraction, same risk-parity basis-aware book,
OOS: APR **+1.81%** (highest APR of all variants) · Sh **2.46** · maxDD −0.17% · CI95
[+0.87%,+2.65%] · n=657, vs H-021 level base APR +1.49% / Sh **3.54** / CI95 [+0.78%,+2.08%].
The composite chases more raw carry (higher APR, upper CI +2.65%) but the persistence tilt
concentrates into noisier names — **Sharpe drops hard (3.54→2.46)** and the APR CI is not separated
from base. Worse risk-adjusted than level alone. **Verdict: NOT an improvement; gate-candidate N**
(level-fixed selection remains the better book).
