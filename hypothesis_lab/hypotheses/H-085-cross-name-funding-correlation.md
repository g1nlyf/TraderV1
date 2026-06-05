# H-085 — Cross-name funding correlation for book construction (min-corr sleeve)

**Status:** proposed · 2026-06-05
**Zone:** Carry & Premia Extensions
**ID range:** H-085 (Zone 2 gen)
**SCORE:** 7.0  (edge_plausibility 7, data_feasibility 9, novelty 7) / 4 = 7.0

## Statement
Construct the carry book by selecting names that minimize pairwise funding-return correlation (rather than maximizing funding level). Within the tradeable-29 universe, find the 10-name subset with highest average funding level AND lowest average pairwise correlation of their funding time series. Hypothesis: a lower-correlation book harvests more independently-sourced funding flows, providing better Sharpe improvement than adding correlated high-funding names.

## Who is forced / why can't stop
Different asset classes attract different forced-payer communities: BTC/ETH longs are institutional; altcoin longs are retail; DeFi tokens attract protocol-native demand. Selecting across these communities minimizes the risk that a single market event (risk-off, BTC crash) simultaneously kills funding across all positions.

## Falsifier
If the min-correlation 10-name book does not have higher OOS Sharpe than the top-10-by-level book (H-021 C-002 baseline), correlation optimization is not worth the complexity. Also falsified if funding correlations are too unstable (train-estimated correlations don't predict test-period correlations).

## Why uncaptured
C-002 uses risk-parity sizing (1/funding-vol) which implicitly downweights volatile names but does not explicitly minimize cross-name funding correlation. The selection of "top-10 by level" may cluster in correlated names (e.g., ETH ecosystem tokens all paying similarly). Portfolio optimization on the funding correlation matrix is a new selection dimension.

## Data status
data_status: HAVE
- Full funding panel 8h 730d — correlation matrix trivially computable
- No new data needed

## Test (one line)
Extend `carry_leads.py`: compute train-period funding-return correlation matrix; run greedy max-level + min-avg-corr selection to pick 10 names; compare OOS Sharpe/APR vs top-10-by-level (C-002 baseline) via `fh.evaluate` + block-bootstrap CI95.
