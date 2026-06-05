# Session 2 Synthesis — 2026-06-04

## 1. What the three leads found
| Lead | Verdict | Result |
|------|---------|--------|
| **H-021** persistence / fixed name-selection carry | **VALIDATED — best edge to date** | level-fixed top-10 +1.44% APR Sharpe 3.20; 50/50 stack w/ xvenue Sharpe **4.28**, corr +0.01 |
| **H-022** cross-venue agreement filter | **REFUTED** | gate makes carry worse at every threshold (agreement = crowded extreme) |
| **H-024** new-listing funding decay | **FAIL** | no systematic decay (early≈mature, perm_p 0.55-0.99); hedgeable hint +20-32% but n=8 |

## 2. The breakthrough (such as it is)
**The carry edge is in FIXED name-selection, not dynamic chasing.** H-13's dynamic `single_topk`
died at −0.1% purely on turnover + buying reverting spikes. Selecting good carry names once on
train and holding them = +1.44% APR, Sharpe 3.20. Stacking the level-fixed sleeve with the
**uncorrelated** (corr +0.01) cross-venue maker sleeve → **Sharpe 4.28, maxDD −0.1%**.

This is the program's first **champion-candidate**: a clean, market-neutral, leverageable carry
book. Unlevered +1.0–1.4% APR is below the +2% gate, but Sharpe 4.28 levers toward +5%.
**Tail stress (full 730d) and the leverage TRAP:** stack APR +3.16% (full)/+1.02% (OOS),
maxDD −0.24%. Naive leverage(budget/maxDD) implies 8.4×→+27%, 21×→+66%. **Rejected.** maxDD
−0.24% is the drawdown of funding accrual + 8h-close basis in a benign window; it does not model
intra-8h gap/liquidation, the rare basis-blowout (likely out-of-sample), funding clamps, or
maker-fill failure. At 8–42× one unmodeled gap is fatal (LTCM mode). The program's recurring
lesson appears AGAIN: the metric measures something that isn't the real risk. Honest path: SANE
2–3× → ~+3–6% APR is the realistic route to +5%, gated on tick/1m margin simulation + a
basis-blowout stress scenario that 8h-close data cannot supply.

## 3. Patterns across both sessions — where the edge hides
- **Positive EV only appears as structural carry/premia.** Two sessions, ~10 tests: every
  directional/reversion bet died; only funding carry is positive, and only when selected fixed.
- **Stacking uncorrelated sleeves is the lever.** corr +0.01 between level-carry and xvenue-spread
  pushed Sharpe 3.20 → 4.28 with no new alpha — just diversification. The path to +5% is MORE
  uncorrelated carry/premia sleeves, then lever the stack (tail-gated), not one big edge.
- **Rare-event ideas are n-blocked.** H-024 (20 listings), liquidation bounces, etc. have honest
  effective-n ≪ 100 in cached data. They need forward collection, not more in-sample slicing.
- **The one real memecoin signal (XS momentum, perm_p 0.003) is convex.** Harvest it as an
  option-like capped basket, not linear sizing.

## 4. Generation batch — 12 ideas scored (edge_plausibility×2 + feasibility + novelty, /4)
Constraints honored: no memecoin reversion, no liquid directional, no win-rate EV, honest eff-n.

### Survivors (avg ≥ 7.0) — written / queued
| ID | Idea | who loses & can't stop | testable now? | score |
|----|------|------------------------|---------------|-------|
| **H-031** | Risk-parity carry sizing (weight ∝ 1/funding-vol) | leveraged longs (carry payer) | yes (funding_cache) | 7.25 |
| **H-049** | Carry-to-vol selection (rank by funding/realized-vol) | same | yes | 7.25 |
| **H-051** | Negative-funding sleeve (long-perp/short-spot on persistent neg funding) | crowded shorts paying funding | yes | 7.25 |
| **H-032** | Funding-acceleration selection (rising Δfunding = building crowding) | early leveraged longs | yes | 7.25 |
| **H-036** | BTC-beta-neutralize the carry book (hedge residual beta) | n/a (risk cleanup) | yes (BTC 8h) | 7.25 |
| **H-037** | Convex memecoin momentum baskets (perm_p-0.003 signal, capped-loss basket) | late retail chasing winners | yes (memecoin DB) | 7.25 |
| **H-043** | Funding seasonality (settlement-of-day / weekend premium) | time-zone-clustered retail leverage | yes | 7.0 |
| **H-047** | Cross-venue funding lead-lag (Binance→Bybit funding prediction) | slower-venue arbs | yes (both venues) | 7.0 |
| **H-042** | Liquidation-cascade bounce (proxy: big adverse move + funding flip) | forcibly liquidated leverage | yes (proxy, 8h) | 7.0 |
| **H-040** | Smart-money early-buyer overlap (tracked wallets → early winners) | late retail | FORWARD-COLLECT (Helius growing) | 7.75 |

### Cut (avg < 7.0 or not testable with cached data)
- H-033 USDC-vs-USDT-margined funding differential — no margin-split data cached.
- H-034 perp-vs-quarterly basis term premium — no dated-futures data cached.
- H-038 memecoin momentum × on-chain confirmation — wallet/token data overlap = 0.
- H-041 CEX-listing pre-positioning — no listing-announcement/labeling data.
- H-044 BTC/ETH options skew risk-gate — no options (Deribit) data cached.
- H-045 OI × funding divergence — no open-interest data cached.
- H-046 vol-conditioned carry — marginal vs H-031/H-049.
- H-048 new-listing price fade — low-n (≈20 listings), same block as H-024.
- H-050 memecoin TS index momentum — directional/long-biased, dead family.
- H-035 funding-momentum overlay — subsumed by H-032.

## 5. Roadmap — next session priority
1. **H-031 / H-049 / H-036** — lift the champion-candidate sleeve toward +2% unlevered and clean
   its Sharpe (risk-parity sizing, carry-per-risk selection, beta-hedge). These directly raise the
   leverage-adjusted return of the validated book.
2. **H-051** — add the negative-funding sleeve as a third uncorrelated component (stack Sharpe ↑).
3. **H-037** — the one novel non-carry test: convex memecoin momentum basket.
4. **Forward collectors:** queue new-listing-with-spot carry (H-024 subset) + smart-money early
   buyer (H-040). Both n-blocked now; collect over coming weeks.
5. **Tail-risk work:** collect ≥18mo funding history (incl. a crash) to honestly bound the carry
   book's left tail → unblock leverage sizing → the realistic path to +5%.

## 6. Closeout
- OOS tested Session 2: 3 (H-021 VALIDATED, H-022 REFUTED, H-024 FAIL).
- Champion stack: still no promoted champion, but first **champion-candidate** logged
  (carry book, Sharpe 4.28, +1.0–1.4% APR unlevered, leverage gated on tail risk).
- New hypotheses: 10 survivors documented (H-031–H-040 family), 10 cut with reasons.
- **Key insight:** the edge is *fixed selection + stacking uncorrelated carry sleeves + leverage*,
  not a single big alpha. Path to +5% = more sleeves (H-031/049/051) + honest tail bound for leverage.
- **#1 priority for Session 3:** H-031 (risk-parity sizing) + H-051 (negative-funding sleeve) —
  raise the stacked carry book's leverage-adjusted return toward the +2% gate, then the +5% target.
