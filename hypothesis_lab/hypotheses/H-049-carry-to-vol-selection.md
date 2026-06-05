# H-049 — Carry-to-vol name selection

**Status:** proposed · priority (Session 3)
**Asset universe:** tradeable Binance perp carry book (H-021 universe)
**Created:** 2026-06-04

## Statement
Select carry names by **funding / realized-vol** (carry per unit of price risk), not raw funding
level. A name with +4% funding and low vol is a better carry than +5% funding with high vol.

## Quality filter
- **Who loses & can't stop:** leveraged longs paying funding; selection just picks the cleanest payers.
- **Falsifier:** carry-to-vol ranking does NOT beat level-ranking (H-021 level-fixed +1.44% Sh3.20) OOS.
- **Why uncaptured:** requires a risk-adjusted ranking + delta-neutral book; retail uses raw APR.
- **Testable now:** yes — funding_cache + perp 8h for realized vol.

## Test method
Per name: train carry-to-vol = mean(funding_train) / std(perp_ret_train). Rank, take top-10 fixed,
hold EW basis-aware maker. Compare TEST APR/Sharpe/CI vs level-fixed and persistence-fixed (H-021).

## Results
```
[pending — Session 3]
```
## Verdict
[ ] PASS [ ] FAIL [ ] INCONCLUSIVE — pending

## Refinement
If it beats level-selection, make it the default selection for the champion-candidate sleeve and
re-run the H-021 stack. Stack with H-051 negative-funding sleeve for a third uncorrelated component.
