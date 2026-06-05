# H-083 — Funding mean-reversion speed as name-quality filter

**Status:** proposed · 2026-06-05
**Zone:** Carry & Premia Extensions
**ID range:** H-083 (Zone 2 gen)
**SCORE:** 7.25  (edge_plausibility 7, data_feasibility 9, novelty 8) / 4 = 7.25

## Statement
Estimate each name's funding mean-reversion half-life (AR(1) coefficient on the funding rate time series) during the training window. Select for the carry book only names with SLOW mean-reversion (high half-life, high AR(1) coefficient) — meaning their funding stays persistently high rather than spiking and collapsing. This is a structural quality filter, complementary to the existing level and persistence filters.

## Who is forced / why can't stop
Slow mean-reversion indicates a deep, structural long imbalance rather than a speculative spike. The forced payers are holders with fundamental or institutional conviction about the asset who will stay long through cycles. Fast mean-reversion signals speculative crowding (H-13 trap): longs enter, push funding, then exit, and funding collapses — not harvestable on a rolling basis.

## Falsifier
If carry names selected by slow mean-reversion (AR(1) > median threshold) do NOT outperform names selected by fast mean-reversion in OOS test (block-bootstrap perm_p < 0.05, CI95 > 0), the half-life is not a useful name-quality signal. Also falsified if it's redundant with the persistence filter in H-021 (correlation between persistence and AR(1) > 0.9 would suggest overlap).

## Why uncaptured
H-021 uses "fraction of periods with funding > 0" (discrete binary persistence). AR(1) coefficient is a continuous, autocorrelation-based measure of how quickly funding reverts — it captures a different dimension. A name could have 90% positive funding but still have high day-to-day volatility (low AR). The half-life filter selects for "stably elevated" vs "persistently positive but volatile."

## Data status
data_status: HAVE
- Funding panel 8h 730d — AR(1) estimation requires only the time series

## Test (one line)
Extend `carry_leads.py`: compute OLS AR(1) beta for each name on train; select top-K by AR(1) coefficient; compare OOS Sharpe/APR vs top-K by level and persistence baselines via `fh.evaluate`.
