# H-149 — C-002 Carry + H-042 Bounce Stack: Correlation and Sizing

**Status:** proposed · 2026-06-05
**Zone:** CROSS-ASSET / MACRO

## Statement
C-002 (carry book) and H-042 (liquidation bounce) are both market-neutral strategies but with opposite sensitivities to BTC vol regimes: carry suffers in high-vol, H-042 is richer in high-vol. Hypothesis: the two strategies have negative period-level correlation (one is up when the other is down), making a stack meaningfully Sharpe-enhancing beyond either alone. Compute the empirical correlation between C-002 period PnL and H-042 period PnL, and size a 60/40 or optimal-ratio stack.

## Structural logic — who is forced
Carry (C-002) and liquidation-bounce (H-042) are both mechanisms of extracting premium from forced flows — but forced flows of OPPOSITE types. Carry harvests slow-drip forced payers; H-042 harvests the post-panic snap-back. The natural anti-correlation (carry hurts in panics; H-042 fires in panics) creates a natural hedge. This is the core stack case for a two-sleeve book.

## Falsifier
Period-level correlation between C-002 and H-042 is not negative (>=0); or stacked Sharpe is no better than max(C-002 Sharpe, H-042 Sharpe) — in which case just use the better one.

## Why uncaptured
C-002 and H-042 have been validated separately. Their stack has not been tested. The correlation analysis and optimal weighting is a necessary step before presenting a two-sleeve strategy.

## Data status
data_status: HAVE — C-002 period PnL series derivable from existing funding_harvest.py output; H-042 period PnL from h042_deep.py. Merge on 8h period timestamp.

## Test (one line)
Merge C-002 and H-042 period PnL time series on timestamp; compute Pearson + Spearman correlation; evaluate stacked Sharpe at [50/50, 60/40, 40/60] via block-bootstrap; compare vs each alone.

## SCORE: 8.5
(edge_plausibility 4.5/5 — complementarity is mechanically grounded; data_feasibility 5/5; novelty 3.5/5 — standard portfolio theory applied to specific validated sleeves → (4.5×2+5+3.5)/4 = 17.5/4 = 4.375 → ×2 = 8.75 → 8.5)

## Results (2026-06-05) — `test_carry_cluster.py`
**Status: INFORMATIVE / thesis-hardening (sub-gate on n).** Co-tested with H-099/H-110.
- Pearson r(C-002 period PnL, H-042 period PnL) = **−0.077** (co-active, n=39); −0.000 full window.
  The hypothesis predicted *negative* correlation: realized r is slightly negative but
  **statistically indistinguishable from zero** — the falsifier (r≥0) is not cleanly cleared; the
  honest read is "uncorrelated," not "anti-correlated hedge."
- Stack at 50/50 and 70/30 (vol-matched — required because the per-event bounce is not a per-8h
  rate): best Sharpe 4.05 (70/30) vs carry 3.54 and vs the sleeve's own (per-event Sh 8.47 on n=39,
  not comparable). Stacked Sharpe > carry-alone but **NOT CI-separated** (APR CI95 overlap).
- **Verdict:** complementarity confirmed as uncorrelated (not negatively correlated); gate-candidate
  **N** — Sharpe lift within CI and H-042 sub-gate (39 TEST events).
