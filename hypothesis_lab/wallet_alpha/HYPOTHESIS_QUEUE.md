# Hypothesis Queue — Free-Data Alpha Factory (Sprint 9, 2026-06-06)

Machine-consumable backlog for `tournament.py`. The loop: pick `test-now` candidates → register in tournament
→ run walk-forward gate vs base/token-only/random/prev-best → promote/demote → log to ledger → regenerate this
queue. `collect` items are blocked only on data volume (Corecast flywheel), NOT on thinking/building.

Status legend: **test-now** (data on hand) · **collect** (needs cross-day/volume) · **dead** (killed) · **later** (needs new infra).
Gate = realized net EV>+2% ∧ perm<0.05 ∧ CI95>0 ∧ n>100, TEST-ONLY walk-forward, controls stronger than signal.

## Cluster 1 — Wallet behavioral / archetype (token-only must be beaten)
| id | hypothesis (compound) | structural why-works | why-fails | data | validation | control | capturability | horizon | status |
|----|----|----|----|----|----|----|----|----|----|
| H-180 | Archetype-consensus: cluster 130+ wallets into degen/bot/sniper/hodler by trade-sequence features; ≥3 same-archetype buys in 6h = signal; size by archetype alpha half-life | different archetypes = different information; consensus within a type filters noise | archetype is a proxy token-context already holds (H-161 dead) | raw_trades + wallet histories | walk-forward, per-archetype EV vs token-only | random-wallet consensus, token-only GBM | entry/sizing | 4–48h | **test-now** |
| H-181 | Wallet behavioral-fingerprint embedding (timing/selection/hold/exit) → consensus weighted by historical alpha → GBM with token feats | richer wallet repr than scalar quality; may add multivariate lift (H-171 showed wallet adds +1.78%) | embeddings overfit on 1 session; eff-n low | raw_trades | nested walk-forward, fingerprint stability across folds | token-only, scalar-wq | entry ranker | 30–60m | **test-now** |
| H-171b | Confirm wallet multivariate increment with repeated walk-forward + feature ablation (which wallet feat carries it: wq vs cohesion vs clu_sol) | H-171 found +1.78% increment; isolate the carrier | increment is fold-luck / time artifact | cluster events | k-fold walk-forward, drop-one-feature ablation | token-only | entry ranker | 30m | **test-now** |
| H-182 | Wallet-token FIT: does a wallet's prior win-rate ON SIMILAR tokens (by lifecycle state at entry) predict better than global win-rate? | skill may be state-specific (sniper good at ignition, not decay) | data-thin per (wallet,state) cell | raw_trades + lifecycle | walk-forward, fit-score vs global-wq | global-wq, token-only | entry ranker | 30–60m | **test-now** |
| H-160/H-161 | naive wallet-buy consensus / archetype mix as standalone alpha | — | DEAD (token dominates, survivorship) | — | — | — | — | — | **dead** |

## Cluster 2 — Token lifecycle (the dominant axis)
| id | hypothesis | why-works | why-fails | data | validation | control | capturability | horizon | status |
|----|----|----|----|----|----|----|----|----|----|
| H-170 | Lifecycle state predicts forward EV (neutral best) | states = structural flow regimes | avoidance-axis only; all negative on 1 regime | raw_trades | walk-forward per-state gate | random, token-only GBM | no-trade/sizing | 30m | **test-now (done; neutral perm 0.002)** |
| H-183 | Lifecycle CONTINUATION vs REVERSAL: at acceleration, does momentum continue (long) or revert? at distribution, does it bounce (H-042) or bleed? conditioned on volume/holder breadth | forced-flow asymmetry (H-053): forced reverts, voluntary continues | state boundaries fuzzy; n per state low | raw_trades | walk-forward, per-state forward sign | token-only, random-time | entry/exit | 30–120m | **test-now** |
| H-184 | Rug-PRE-DETECTION: predict gap-to-zero BEFORE entry (single-wallet supply concentration, LP pull proxy, buyer_hhi, age) → no-trade filter | rugs are not exit-fixable (gap); must avoid pre-entry | rug signal = also kills legit early winners | raw_trades | walk-forward, precision/recall on −80% tail + EV of kept | random-skip, token-only | no-trade filter | pre-entry | **test-now** |
| H-185 | Lifecycle TRANSITION events (accel→top, top→distribution) predict better than static state | transitions = information events | transition detection lags | raw_trades | walk-forward, transition-fire EV | static-state, random | entry/exit | 30m | **test-now** |
| H-170-onehot | explicit state one-hot as ML feature | — | adds +0.10–0.53% over continuous feats; redundant | — | — | — | — | **dead (feature)** |

## Cluster 3 — Liquidity migration / rotation / network
| id | hypothesis | why-works | why-fails | data | validation | control | capturability | horizon | status |
|----|----|----|----|----|----|----|----|----|----|
| H-186 | Liquidity migration: smart-wallet EXIT of A + liquidity/wallets appearing in new pool B within 24h = rotation; B inherits network effect | flow follows attention; rotation is real microcap behavior | 1-session window too short for 24h; cross-pool linkage noisy | raw_trades (intra) + **Corecast (cross-day)** | walk-forward, B-target EV vs random-token | random-token, token-only | entry (rotation) | 1–24h | **collect** |
| H-168 | Co-sell network / cabal cohesion predicts bigger drops | — | DEAD (rho −0.10) | — | — | — | — | — | **dead** |
| H-187 | Co-BUY network cluster entry (≥3 graph-linked wallets buy A in 2h) beats single-wallet entry, adjusted for cluster dissipation speed | coordinated informed entry; dissipation = insider-exit risk gauge | coordination = pump risk; 1 session | raw_trades | walk-forward, cluster-entry vs single, by dissipation | single-wallet, random | entry/sizing | 1–72h | **test-now (intra) / collect (72h)** |

## Cluster 4 — Forced-flow / CEX / carry frontier
| id | hypothesis | why-works | why-fails | data | validation | control | capturability | horizon | status |
|----|----|----|----|----|----|----|----|----|----|
| H-042 | Liquidation-cascade bounce (market-neutral) | forced selling overshoots | sub-gate; needs more independent events | funding/forward collector | walk-forward (live) | random, demean | entry | 2h | **collect (forward)** |
| H-188 | CEX/on-chain class fusion via SECTOR/BETA proxy (not direct overlap): map microcap "class" to a CEX beta proxy; does proxy funding/vol regime condition on-chain EV? | links structural premium to on-chain when direct overlap (16/12,318) is too thin | proxy mapping arbitrary; correlation ≠ tradeable | raw_trades + funding cache | walk-forward, regime-conditioned EV | unconditioned, random regime | no-trade/sizing | session | **later (design proxy first)** |
| C-002 | Persistence-selected funding carry (CHAMPION) | structural premium | leverage-dependent; near-optimal | funding cache | held-out (done) | — | sized | 8h | **champion (harden, don't overfit)** |

## Cluster 5 — Portfolio / meta
| id | hypothesis | why-works | why-fails | data | validation | control | capturability | horizon | status |
|----|----|----|----|----|----|----|----|----|----|
| H-189 | Stack uncorrelated WEAK edges (C-002 carry × token+wallet ranker × lifecycle filter) — r≈0 → Sharpe adds | diversification of independent edges multiplies Sharpe | on-chain legs still EV<0 on 1 regime; nothing to stack yet | all | cross-edge corr + combined Sharpe | single-edge | portfolio | mixed | **collect (needs +EV on-chain leg)** |
| H-190 | Sizing overlay: confidence from token+wallet GBM score → position size; does size-weighted EV beat equal-weight? | concentrate on highest-conviction | overfits score calibration | cluster events | walk-forward, size-weighted vs EW EV | equal-weight, random-size | sizing | 30m | **test-now** |
| H-191 | Regime tagger: classify each day's regime (up/flat/dump) from breadth/vol; gate ALL on-chain signals to non-dump regimes | the recurring wall is regime; tag + condition it | needs cross-day to have >1 regime | **Corecast (cross-day)** | day-level walk-forward | unconditioned | meta-filter | day | **collect (THE unblock)** |

## Priority order for next tournament cycles (test-now, by expected leverage)
1. **H-171b** (isolate wallet increment carrier + repeated walk-forward) — cheap, sharpens the one live revision.
2. **H-184** (rug pre-detection no-trade filter) — addresses the rug-tail blind spot directly; high capturability.
3. **H-183** (continuation vs reversal by state) — exploits the dominant lifecycle axis for a directional signal.
4. **H-180** (archetype-consensus) — re-test the genius-level wallet idea under the corrected gate.
5. **H-182** (wallet-token fit) + **H-190** (sizing overlay) + **H-185** (transitions) + **H-187 intra** (co-buy cluster).

## Cycle log (tournament results, append per cycle)
- **2026-06-06 cyc1-2** (walk-forward, corrected gate): token_gbm +4.66% perm 0.044; neutral +7.34% perm 0.002;
  token+wallet +1.78% over token-only perm 0.000 (CI upper +2.14% via token+wq); **H-184 rug-skip +4.73% perm
  0.000** (ROBUST). Naive avoidance filter CORRECTED to n.s. (0.117). promoted=0.
- **2026-06-06 cyc3** (added H-183/H-185 via prev_state): H183_buy_acceleration −9.1% n.s. (**continuation
  FAILS** → status dead); H183_buy_distribution +3.4% n.s. (reversal weak); **H183_neutral_post_distrib +5.57%
  EV** (only positive seen) but **n=2** (status: promising, DATA-STARVED → GMGN volume); H185 transitions too
  sparse (n=6, status: DATA-STARVED). promoted=0. Ledger=43 rows.

## Status updates after cycles
- **test-now → tested:** H-170 (separator, avoidance-axis), H-171/H-171b (wallet increment CONFIRMED, carried by
  wq+cohesion), H-184 (rug-skip ROBUST, shadow no-trade filter), H-183 (continuation dead / reversal weak),
  H-185 (transition data-starved).
- **DATA-STARVED → needs GMGN cross-day volume (the unblock now running):** H-183 post-distribution bounce
  (n=2!), H-185 transitions, H-186 liquidity migration, H-191 regime tagger, H-189 edge stack.
- **Heavy, deferred to GMGN cross-day (single-regime cousins already dead → don't re-run on May-14):** H-180
  archetype-consensus (needs KMeans; cf. H-161 dead), H-187 co-buy cluster (needs graph; cf. H-168 dead),
  H-182 wallet-token fit (needs per-(wallet,state) win-rate). H-190 sizing overlay needs a sizing-aware gate
  (separate metric from selection gate) — build next.

## The binding constraint (honest)
Every on-chain candidate sits on a NEGATIVE base (May-14 dump). Edges over base are real and now walk-forward-
robust (token_gbm perm 0.044, neutral perm 0.002, token+wallet perm 0.000), but **absolute EV stays <0** → no
promotion until a non-dump regime exists. `collect` items (H-186/H-191/H-189) are gated on the **Corecast
flywheel** (`corecast_adapter.py`) accumulating ≥14 days. That is the single highest-leverage unblock — but it
does NOT block the test-now queue above, which sharpens the signal library so it is ready the moment data lands.
