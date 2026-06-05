# H-031 — Risk-parity carry sizing

**Status:** proposed · priority (Session 3)
**Asset universe:** tradeable Binance perp carry book (H-021 universe)
**Created:** 2026-06-04

## Statement
Weight each name's carry leg ∝ 1/σ(funding) (inverse funding-volatility), not equal-weight.
Names with steady funding get more capital; spiky names less. Target: raise the champion-
candidate's Sharpe (currently level-fixed 3.20 / stack 4.28) → higher leverage-adjusted return.

## Quality filter
- **Who loses & can't stop:** same carry counterparty — leveraged longs structurally paying funding.
- **Falsifier:** inverse-vol weights do NOT beat EW Sharpe OOS (block-bootstrap CI overlap).
- **Why uncaptured:** operational complexity of a re-weighted multi-name delta-neutral book; small capacity.
- **Testable now:** yes — `funding_cache`, reuse `funding_harvest` + `carry_leads.py`.

## Test method
Compute trailing funding-vol per name (train). Weight ∝ 1/σ within the H-021 fixed-selected set.
Compare TEST APR / Sharpe / maxDD / CI95 vs EW (H-021 baseline +1.44% Sharpe 3.20). eval_stats CI.

## Results
```
[pending — Session 3]
```
## Verdict
[ ] PASS [ ] FAIL [ ] INCONCLUSIVE — pending

## Refinement
Combine with H-049 (carry-to-vol selection) and H-036 (beta-hedge) — sizing + selection + hedge
together. Guard against 6-month overfit; keep weights smooth, low turnover.
