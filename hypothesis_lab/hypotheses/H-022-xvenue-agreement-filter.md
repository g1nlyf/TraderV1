# H-022 — Cross-venue agreement as a carry quality filter

**Status:** tested · 2026-06-04 (Session 2)
**Priority:** P1
**Asset universe:** 29 tradeable Binance perps (with Bybit funding)
**Created:** 2026-06-04

## Statement
Gate carry entries to periods where Binance AND Bybit funding agree (same sign,
|fb − fy| < thr·max(|fb|,|fy|)). Hypothesis: agreement = broad structural demand (real
carry); disagreement = venue-specific artefact (noise). Filtering to agreement should raise
realized EV/Sharpe per entry.

## Test method
Tradeable-29, single EW basis-aware maker carry. Positions held only in agreement periods
(else flat). Threshold sweep thr ∈ {0.2, 0.5, 1.0}. Compare TEST APR/Sharpe/n vs unfiltered.
Script: `scripts/carry_leads.py` (`_gated_carry_ew`).

## Results (TEST, n=657)
```
baseline (no gate, span6)   apr -0.43%  sharpe -0.97
agree thr=0.2               apr -1.77%  sharpe -8.45   (37% of both-venue periods agree)
agree thr=0.5               apr -3.06%  sharpe -10.99  (55% agree)
agree thr=1.0               apr -2.80%  sharpe -7.95   (78% agree)
```
(baseline here uses fixed span=6, so its level differs from H-021's tuned-span +0.77%; the
relevant signal is the RELATIVE effect of the gate.)

## Verdict
[x] **REFUTED.** Agreement filtering makes carry strictly WORSE at every threshold. The
mechanism is backwards: when both venues show the same large positive funding, that is the
CROWDED PEAK — funding is about to normalize/reverse, so you enter at the worst time.
Cross-venue agreement is a crowding/extreme indicator, not a quality filter.

## Refinement path
- Inverted use: cross-venue agreement on EXTREME funding could be a fade signal (short the
  crowded carry, expecting funding to revert). But H-14 already found funding-as-directional-
  signal fails OOS — low prior. Park.
- The cross-venue *spread* (not agreement) is the productive use of two venues — see H-13
  xvenue maker (+0.6%) and the H-021 stack. Agreement adds nothing.
