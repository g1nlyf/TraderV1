# Wallet Distribution Theory — compound-layer findings (Sprint 7, 2026-06-06)

Tested whether richer behavioral/network layers add specificity beyond a naive "react to selling" rule, for
predicting forward DOWN-magnitude on sell-cluster events. Code: `distributor_theory.py`. Temporal OOS
(n=390 test), label = SHORT payoff (capped), base SHORT EV +17.57% (= the May-14 down-regime).

## Ablation — Spearman(feature, short-payoff) OOS + top-half SHORT EV
| layer | rho (OOS) | top-half SHORT EV | read |
|-------|-----------|-------------------|------|
| **tok_prior_ret** (token) | **+0.332** | +26.10% | tokens that already ran up drop more — strongest signal |
| **tok_cum_sol** (token) | **+0.284** | +26.00% | bigger pre-t volume → bigger drop |
| **distributor_score** (wallet archetype) | **+0.262** | +25.45% | **best WALLET feature** — wallets who repeatedly sold before drops |
| wallet_quality (wallet) | +0.231 | +22.22% | quality sellers → bigger drop (H-162) |
| cohesion (co-sell network) | −0.102 | +18.56% | **network/cabal co-sell does NOT help** |
| sell_count (naive baseline) | −0.044 | n/a (discrete-median degenerate) | raw count carries ~no rank info |

(Harness note: `sell_count` is discrete (≥4); the >median split fired 0 → nan. The honest baselines are the
regime base (+17.57%) and the token features; every wallet layer is compared against those.)

## Findings
1. **Token lifecycle context dominates.** `tok_prior_ret` (+0.33) and `tok_cum_sol` (+0.28) out-rank every
   wallet feature. *What* the token is doing predicts the drop better than *who* is selling. (Same conclusion
   as H-160/H-161: token microstructure > wallet identity.)
2. **The distributor archetype is REAL and the best wallet feature** (rho +0.262, top-half +25.45% vs base
   +17.57% ≈ **+7.9% increment**, comparable to the wq-sell increment). "Wallets that repeatedly sell before
   collapse" is a genuine, point-in-time, label-free-trainable behavioral type. **Keep it** as the wallet
   feature for the cross-day test (H-163) — it is more interpretable and slightly stronger than raw wq PnL.
3. **Network / co-sell cabal theory: NOT supported.** Cohesion rho −0.102 — coordinated co-sellers do not
   out-drop independent sellers. The "cabal distributes together → bigger crash" hypothesis fails here.
   (Caveat: cohesion used full-session co-sell membership, a generous/slightly-leaky definition; it still
   failed → robust negative.)
4. **No wallet/network layer beats token context OOS**, and all sit on the +17.57% regime base. So none is
   separately capturable; they would only matter fused with token context, and even then token context
   already carries the signal.

## Implication for H-166 / the program
- H-166's quality-distribution specificity is **not rescued** by archetype or network: token features +
  "exit-on-any-sell" already capture the available signal (consistent with `backtest_h166.py`, where
  exit-on-random-sell beat exit-on-quality-distribution).
- The **one keeper** is `distributor_score` as a behavioral feature for the cross-day H-163 test — if any
  wallet signal survives multiple regimes, the distributor archetype is the candidate, not network cohesion.

## Compound theories tested vs the genius-level menu
- A Distribution state machine: partially (absorbed vs active distribution in the overlay) — absorbed→bounce confirmed (H-042).
- B Distributor archetype: **DONE — real, best wallet feature, but < token context.**
- C Network co-sell cabal: **DONE — NOT supported (rho −0.10).**
- D Rotation after distribution: done Sprint 6 (real but tiny, +0.4–0.6%).
- E CEX/market-structure fusion: **BLOCKED** — overlap of microcap tokens with CEX-listed proxies ≈ 16/12,318 (DATA_LEDGER). Not testable on this universe.
