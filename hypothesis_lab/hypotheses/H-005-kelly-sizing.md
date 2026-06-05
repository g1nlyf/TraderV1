# H-005 — Drawdown-Scaled Kelly Sizing

**Status:** proposed
**Priority:** P1
**Asset universe:** Solana memecoins
**Created:** 2026-06-04

## Statement
Within the mean-reversion framework, deeper drawdowns produce higher win rates (confirmed: >-5% win=38.8%, <-30% win=55.8%). Using Kelly-proportional position sizing (bigger position for deeper drawdowns = higher expected win rate) increases total portfolio EV without changing the base strategy.

## Rationale ("million dollar idea")
Kelly criterion is the mathematically optimal bet sizing formula. If you know that buying a -30% drawdown wins 55.8% of the time vs -5% drawdown winning 38.8%, sizing by Kelly means you automatically allocate more capital where the edge is stronger. This is NOT a new signal — it's extracting more value from an existing signal using math. Free edge from better sizing.

## Data required
- `finetune/data/holdout_mom3_eval.jsonl` — holdout with drawdown buckets and outcomes
- finetune/pipeline/meanrev_strategy.py — for strategy base

## Test method
1. Segment holdout by drawdown depth: [-5% to -10%], [-10% to -20%], [-20% to -30%], [<-30%]
2. Compute win rate and EV per bucket
3. Compute Kelly fraction per bucket: f = (p*b - q) / b where b = payoff ratio, p = win rate, q = 1-p
4. Apply fractional Kelly (50% of full Kelly for safety): f_half = f * 0.5
5. Simulate portfolio with drawdown-scaled sizing vs flat sizing
6. Compare: portfolio EV and Sharpe over holdout period

## Parameters
- Kelly fraction: full (100%), half (50%), quarter (25%)
- Drawdown buckets: as above
- Payoff ratio b: 20%/12% = 1.67 (triple-barrier)

## Results
```
[To be filled]
```

## Verdict
[ ] PASS  [ ] FAIL  [ ] INCONCLUSIVE

## Refinement path
**If Kelly sizing improves portfolio EV:**
→ Combine with regime filter (H-004): Kelly sizing only in ranging regime
→ New champion stack: C-001 + H-004 + H-005

**If Kelly sizing increases drawdown beyond acceptable:**
→ Use capped Kelly: max 2% portfolio per trade regardless of formula
