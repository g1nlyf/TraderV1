# H-019 / H-020 — Memecoin cross-sectional reversion & momentum (dollar-neutral)

**Status:** tested · 2026-06-04
**Priority:** P1 (the corrected H-15)
**Asset universe:** Solana memecoins (geckoterminal:hour1, 33 tokens ≥60 candles, ~58d)
**Created:** 2026-06-04

## Statement
At each non-overlapping rebalance, rank memecoins by trailing return and trade them
**dollar-neutral within the memecoin cross-section** (no SOL hedge needed — the common
move cancels by construction). H-019 = reversion (long losers / short winners).
H-020 = momentum (long winners / short losers).

## Rationale (why this is the right corrected test)
H-15's +17.59% was SOL-down recovery beta (long-biased, 91% of events one regime, eff n≈6).
A within-cross-section neutral book removes the common SOL factor that manufactured that
result. The honest null is the **cross-sectional permutation** (shuffle forward returns across
tokens within each rebalance): does the loser/winner RANK predict, beyond the common move?
Non-overlapping rebalances keep effective-n honest (no overlap inflation).

## Test method
Temporal 70/30 split (config chosen on TRAIN Sharpe). Non-overlapping rebalances (step=hold).
Dollar-neutral gross-1 weights ∝ ∓(ret − cross-sec mean). Realized net after 0.9%/side cost on
turnover. Cross-sectional permutation null (20k). Block-bootstrap CI95. Script:
`hypothesis_lab/scripts/h019_memecoin_xs_reversion.py [--momentum]`.

## Results
```
Universe: 33 tokens, ~58d, median 12 tokens alive/hour. Test rebalances n=15 (HONEST count).

H-019 REVERSION (look=24h hold=24h):
  gross EV/rebal = -10.78%   net = -11.96%   perm_p = 0.902   CI95 [-23.96%, -0.67%]
  => the reversion rank is ANTI-predictive. Memecoins do not revert cross-sectionally.

H-020 MOMENTUM (look=6h hold=24h):
  gross EV/rebal = +200.6%   net = +199.3%   perm_p = 0.0027   CI95 [-5.32%, +246.16%]
  hit rate 46.7%, Sharpe 1.06
  => the momentum rank GENUINELY predicts (perm_p 0.003) — winners continue. BUT the payoff
     is a lottery: hit rate <50%, mean dominated by a few explosive longs, CI95 spans zero.
```

## Verdict
[ ] PASS  [x] **FAIL (both)**  [ ] INCONCLUSIVE
- H-019 reversion: refuted (wrong sign, perm_p 0.90).
- H-020 momentum: the directional signal is REAL (perm_p 0.003) but unsizeable — CI95 spans
  zero, hit <50%, mean = a few moonshots. Same lottery distribution as H-17. Not a stable edge.

## Key insight (feeds synthesis)
Memecoins **trend, they don't revert** — every mean-reversion bet in this program (C-001,
H-15, H-019) failed; cross-sectional momentum is the only memecoin signal that beats its null
(perm_p 0.003). But the return distribution is option-like (right-skew lottery), so naive
linear sizing can't harvest it. n=15 — underpowered; the lottery character is the binding
constraint regardless of n.

## Refinement path
- The momentum signal is real but the payoff is convex. To harvest it you need a payoff
  transform, not linear sizing: e.g., capped-loss long-only baskets (option-like), or
  volatility-targeted small-size many-bet exposure. But 1.8% round-trip cost + <50% hit make
  this very hard — likely still a lottery after transformation.
- More data (longer window, more simultaneous tokens) would tighten n, but will not change the
  fat-tail character. Deprioritized vs structural-carry directions.
