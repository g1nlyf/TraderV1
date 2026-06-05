# H-051 — Negative-funding carry sleeve (the short-crowding side)

**Status:** proposed · priority (Session 3)
**Asset universe:** Binance perps with persistently NEGATIVE funding
**Created:** 2026-06-04

## Statement
Symmetric to the validated positive-funding carry: when funding is persistently NEGATIVE
(crowded shorts paying longs), harvest it via **long-perp / short-spot** (or long-perp delta-hedged).
Hypothesis: this sleeve is **uncorrelated** to the positive-funding sleeve (it fires in different
names/regimes — bearish capitulation), so it raises the stacked carry book's Sharpe further.

## Quality filter
- **Who loses & can't stop:** crowded shorts (bearish leverage) structurally paying funding to longs;
  capitulation shorts can't easily unwind in size.
- **Falsifier:** negative-funding names don't carry net-positive after cost OOS, OR the sleeve is
  highly correlated with the positive sleeve (no diversification benefit).
- **Why uncaptured:** requires shorting spot / borrow (harder leg); negative funding is rarer →
  intermittent, lower capacity; most carry desks only run the positive side.
- **Testable now:** yes — funding_cache (select names by negative train-funding persistence) + spot leg.

## Test method
Mirror H-021: select names by most-negative train funding (fixed), long-perp/short-spot basis-aware
maker, hold EW. TEST APR/Sharpe/CI. Then correlation vs the positive sleeve and the combined 3-sleeve
stack Sharpe (positive-level + xvenue + negative).

## Results
```
[pending — Session 3]
```
## Verdict
[ ] PASS [ ] FAIL [ ] INCONCLUSIVE — pending

## Refinement
If uncorrelated and net-positive: third stack component → pushes the book's Sharpe past 4.28 and,
levered (tail-gated), toward the +5% target. The whole carry program is now a stacking exercise.
