# CANONICAL STATE — single source of truth

> If any other doc disagrees with this file, **this file wins**. Updated end of every sprint.
> Last update: 2026-06-06 (Sprint 5 — Wallet Intelligence Alpha Engine).

## Champions
| ID | What | Status | Honest number | Promotion basis |
|----|------|--------|---------------|-----------------|
| **C-002** | Cross-margin fixed-selection funding-carry book | **ACTIVE — sole champion** | +1.49% APR unlevered, Sharpe ~3.5, CI95 [+0.78%,+2.08%] APR, n=657 (8h periods, OOS) | leverage-validated to ~3.4× cross-margin → +5% APR target; basis-tail-gated |
| C-001 | Mean-reversion drawdown rule | **DEAD (retired 2026-06-04)** | realized −0.97%, perm_p 0.887, CI95 spans zero | was a win-rate-implied artifact; never had an edge |

## Sleeve candidates (NOT champions)
| ID | What | Status | Honest number | Blocker |
|----|------|--------|---------------|---------|
| H-042 | Liquidation-cascade bounce (market-neutral) | **REAL but SUB-GATE** | −8%/H2 +1.46%/trade, cluster-t 2.24, n=91 periods | magnitude×n×significance frontier: no config clears EV>2% ∧ n>100 ∧ perm/CI at once. Needs forward-collect to grow n |

## Wallet / on-chain alpha — TESTED honestly (Sprint 5), still NOT sized
**LONG: UNPROVEN/DEAD on this data. SHORT: REAL but uncapturable.** The first leakage-controlled
point-in-time test stack (`wallet_alpha/`, SYNTHESIS.md) is built and run. Results (temporal OOS, capped
realized EV, eval_stats gate):
- **Naive smart-wallet copy = −17.7% EV** (cluster-buys mark the local top). Invalidates
  `finetune/pipeline/copy_engine.py` (in-sample + survivorship by construction).
- **H-160 wallet-quality selection: DEAD** — pre-t quality *anti*-predicts (rho −0.37 = in-session
  survivorship); adds ~0 over token-microstructure context. **H-161 archetype: DEAD.**
- **H-162 distribution-sell down-signal: REAL, NOT promotable** — coordinated quality-wallet sells predict
  larger forward drops (wq-sell SHORT +22% EV, perm_p 0.008, CI [+15.9%,+27.6%], n=212; selection edge
  +4.5–5.9% cost-invariant). Blocked: no short venue for microcaps + eff-n=1 session (regime-capture risk).
  Logged as a risk/exit signal, not a champion.

`wallet_leaderboard.json`, `wallet_scores`, `wallet_token_pnl`, GMGN `composite_score` remain **look-ahead
selection labels, not alpha** — never features. **Wallet alpha must not be sized.** See `DEAD_TRACKS.md#naive-leaderboard-copy`.

**Sprint 6 (2026-06-06) update — persistence flywheel built:**
- **Free firehose collector LIVE** (`wallet_alpha/firehose_collector.py`, GeckoTerminal, keyless) — the
  engine that makes cross-day persistence testable. Verified (392 trades/tick; smoke pass). Accruing days.
- **H-162 intra-session persistence HOLDS** (walk-forward +7.7% over base, perm 0.000). Cross-DAY still
  untestable (1 session) = the open question → H-163 once firehose has ≥14 days.
- **Capturable conversions:** all wallet signals are real cross-sectional selectors on a NEGATIVE session
  base → no positive-EV long. Only **exit-overlay** (de-risk a held long on distribution) is capturable
  (+3.9/+5.4%/trade saved, perm 0.000) — a Stage-2 RISK module candidate, not alpha. See CAPTURABILITY_REPORT.md.
- Net: wallet long alpha still **DEAD**; H-162 short signal **real, regime-robust intra-session, not yet
  cross-day, not capturable as long**. Binding constraint = multi-day capture (now unblocking itself).

**Sprint 7 (2026-06-06) update — H-166 productionized + DEMOTED by stronger control:**
- Built `h166_risk_overlay.py` (deterministic, point-in-time, paper-only; 8/8 fixtures) + `backtest_h166.py`
  (drives the real module, all controls) + `firehose_status.py` (health/rollup/target).
- **H-166 DEMOTED.** Through the module with the correct **random-sell control**: exit_h166 −12.84% beats
  hold (−15.08%) and random-time (−13.92%) [perm 0.000] but **LOSES to exit-on-any-random-sell (−11.69%)**.
  The quality-distribution specificity adds **nothing** over "react to any selling." No-trade veto worthless
  (−15.51%, perm 0.910). Sprint-6's shuffled-lag control was too weak. **H-166 = research curiosity /
  one-session artifact, NOT a validated Stage-2 risk module.** Ships SHADOW-ONLY (log, never gate).
- **Compound theory:** distributor-archetype (repeatedly-sells-before-drop) is the **best wallet feature**
  (rho +0.262) but **< token context** (tok_prior_ret +0.332); **co-sell network/cabal DEAD** (rho −0.102).
  No wallet/network layer beats token-only. Keep `distributor_score` as the wallet feature for H-163 only.
- **Firehose volume truth:** GeckoTerminal free ≈ 0.5 sell-clusters/day ≪ 100 needed → too thin; the free
  (already-wired) Bitquery Corecast stream is the volume path for cross-day. Cross-day H-162 = STILL OPEN.

**Sprint 8 (2026-06-06) update — Token Lifecycle Model + Beat-Token-Only gate (the promotion machine):**
- Built `token_lifecycle.py`: deterministic token lifecycle state machine (ignition/acceleration/crowded_top/
  distribution/decay/rug_dead/neutral) + a reusable beat-token-only ML gate. See H170_TOKEN_LIFECYCLE_REPORT.md.
- **H-170 lifecycle states: REAL OOS EV separator** (neutral −7.4% vs base −13.1%, edge +8.0%, perm 0.000),
  but on the AVOIDANCE axis (all states negative) and **NOT incremental over continuous token features**
  (state one-hot adds +0.10% to a GBM). Value = interpretable risk states + a +2.3% no-trade avoidance filter.
- **H-171 wallet adds incremental MULTIVARIATE value — REVISES the "wallet dead" verdict.** Beat-token-only
  gate (cluster events, GBM, temporal OOS): token-only edge +9.81% / Spearman +0.400; **token+wallet edge
  +11.36% / Spearman +0.474** (perm 0.000). Wallet/cohesion/wq features add +1.55% edge & +0.074 Spearman
  over token-only — the univariate Sprint-7 kill was too harsh. token+wallet is the best ranker yet (CI upper
  +0.24%, closest to break-even). Needs walk-forward confirm; still negative EV on the down-regime.
- **Nothing clears +2% gate** — all selections negative (ONE down-session). Reconfirmed binding constraint =
  REGIME DIVERSITY (cross-day data), not features/models/architecture. Next decisive test = H-163, not more features.

**Sprint 9 (2026-06-06) update — Alpha Factory OS: validation fix + reusable tournament + flywheel:**
- **VALIDATION BUG FOUND + FIXED.** Sprint-8 `token_lifecycle.py` fed full-sample `all_nets` to the gate while
  firing test-only → contaminated base/perm. Fixed in reusable `tournament.py` (gate runs on POOLED TEST-ONLY
  walk-forward universe). 7/7 harness tests pass incl. `test_gate_test_only_isolation`. See VALIDATION_AUDIT.md.
- **Sprint-8 findings SURVIVE the fix** (not manufactured by contamination): under corrected walk-forward —
  token_gbm edge +4.66% **perm 0.044** (was n.s.), neutral-state +7.34% **perm 0.002**, token+wallet +1.78%
  over token-only **perm 0.000** (CI upper +2.14% via token+wq). **Corrected:** naive avoidance filter n.s.
  (perm 0.117) — superseded by **H-184 rug pre-detection no-trade filter (+4.73%, perm 0.000, robust)**.
- **Built the research OS** (not a one-off): `tournament.py` (reusable harness + candidate registry + persistent
  `tournament_ledger.jsonl` + auto `TOURNAMENT_REPORT.md`), `HYPOTHESIS_QUEUE.md` (20+ compound hypotheses,
  12 test-now), `corecast_adapter.py` (free high-volume flywheel → firehose schema, selftest passes, one
  BITQUERY_TOKEN starts it), `RESUME.md` (loop operating manual). Ran 2 cycles; ledger accumulating.
- **promoted=0 still** — every selection EV<0 on the single May-14 down-regime. The wall is REGIME DIVERSITY;
  the Corecast flywheel is the built, tested, one-token-away unblock. C-002 remains sole champion.

## The promotion gate (CONSTRAINTS.md, enforced by `finetune/pipeline/eval_stats.py`)
A rule is promotable ONLY if, on a temporal OOS holdout with **realized** payoffs:
1. realized net EV > **+2.0%** per trade, AND
2. permutation-null **perm_p < 0.05**, AND
3. block-bootstrap **CI95 excludes zero**, AND
4. **n_OOS > 100** independent events.

Win-rate-implied EV is **banned** (it manufactured C-001). Sharpe-only heuristics are **not** the gate
(they overstate — see `QUESTIONS.md#q8-carry-cluster-gate`).

## Locked structural truths (do not re-litigate without new data)
1. **Memecoins trend, they don't revert** (H-019 fail, H-020 lottery, H-017 lottery).
2. **CEX direct-funding carry is structural but small** (H-13: +9.1% raw NOT capturable → +0.8–1.5% tradeable).
3. **Fixed name-selection > dynamic chasing** for carry (H-021 vs H-13 dynamic single_topk −0.1%).
4. **Forced flow is asymmetric**: liquidation selling mean-reverts (H-042 real); FOMO spikes continue (H-053) = momentum lottery.
5. **Effective-n pathology is systemic**: overlap/regime inflation fooled H-001, H-15, H-051, H-065. Always cluster-robust.
6. **The binding constraint is DATA, not ideas.** Same-data generation = diminishing returns (Sprint 4: 100 generated, 0 promoted).

## Data truth (the fact that reorients Sprint 5)
The "847K trade tape" = `raw_trades` in `walletscarper.sqlite3`: **843,323 trades inside a 5.5-hour window
on 2026-05-14 (10:00–15:31 UTC)** + 3,946 stragglers on 05-16. It is a calendar-SHALLOW, cross-section-DEEP
firehose (120,418 wallets × 12,318 tokens), **not a time series**. Consequences:
- Intraday cross-sectional wallet tests: feasible, large n.
- **Multi-day forward labels: impossible** (calendar price sources overlap only 16/12,318 tokens).
- **Persistence / alpha half-life: untestable** (needs weeks; we have 5.5h). This is the #1 promotion-blocker for wallet alpha.

Full inventory: `DATA_LEDGER.md`. Full audit: `DATA_AUDIT.md`.
