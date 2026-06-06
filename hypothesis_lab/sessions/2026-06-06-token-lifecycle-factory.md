=== SESSION 8 HEARTBEAT — TOKEN LIFECYCLE MODEL + BEAT-TOKEN-ONLY GATE ===
Start 2026-06-06. Operator: Opus 4.8 autonomous. Paper/research only. Free data only.

MISSION: Free-Data Alpha Factory. Budget-bounded -> run the most decisive trunk this turn.

ENTRY TRUTH (respect):
- C-002 sole champion (+1.49% APR unlev, leverage-dependent).
- H-166 DEAD as gate (loses to random-sell). Shadow-log only. DO NOT polish.
- H-162 unresolved, blocked by data VOLUME (GT free ~0.5 clusters/day).
- TOKEN CONTEXT DOMINATES wallet behavior (Sprint 7: tok_prior_ret rho +0.332 >> best wallet +0.262).
- Every wallet feature must beat TOKEN-ONLY, not just hold/random.

DECISION: Trunk 1 (Corecast volume) needs >=14 calendar days -> cannot complete this turn (documented blocker
already in decisions/corecast-volume-path). Highest-value data-AVAILABLE work = Trunk 3 + Trunk 2:
  -> Build TOKEN LIFECYCLE state machine (ignition/accel/top/distribution/decay/rug) from May-14 tape.
  -> Build strong TOKEN-ONLY baseline feature factory (prior_ret, liquidity, age, vol, trade_count, depth).
  -> Build reusable BEAT-TOKEN-ONLY gate (the promotion machine): any signal must add incremental OOS EV
     over token-only, temporal split, perm null, block-bootstrap CI, n>100, strong controls.
  -> Validate: does lifecycle STATE predict forward net EV OOS? Does it beat token-only composite?

CAVEAT baked in: May-14 = ONE session/regime. Cross-token temporal-OOS within session is honest for
cross-sectional state prediction; absolute levels are regime-bound. No cross-day claim.

LOG:
[t0] heartbeat. Recon: tooling (sklearn?), raw_trades schema, existing token features, eval_stats API.

[t1] Recon DONE — sklearn 1.9 + scipy present; wa_eval has gbm/linear scorers + temporal_split + matrix +
     gate; eval_stats has perm + block-bootstrap. Event cache = cluster-conditioned (n=2325, token+wallet+wq
     feats). Decided: build INDEPENDENT token-centric lifecycle sample for PART A; reuse cluster events for PART B.
[t2] Built token_lifecycle.py — PART A (lifecycle state machine + token-only baseline + state increment +
     avoidance + random control) + PART B (beat-token-only: token-only vs token+wallet GBM, temporal OOS).
[t3] RAN. Results:
     PART A (n=1027, base −13.1%): neutral state edge +8.0% perm 0.000 (real separator, avoidance axis, all
       states negative); state one-hot adds +0.10% over continuous token feats (= interpretable packaging,
       not new signal); avoidance filter (skip rug/distribution/decay) +2.3%; random control −1.7% (n.s.).
     PART B (n=1137, base −17.7%): token-only edge +9.81%/Spearman +0.400; token+wallet edge +11.36%/Spearman
       +0.474 (perm 0.000) → WALLET ADDS +1.55% edge & +0.074 Spearman over token-only = REVISES Sprint-7
       univariate "wallet dead". Best ranker yet (CI upper +0.24%, closest to break-even). Still neg EV.
[t4] Docs: H170_TOKEN_LIFECYCLE_REPORT.md + CANONICAL_STATE/INDEX/STACK/DEAD_TRACKS (Sprint-8 blocks).
OUTCOME: Token lifecycle = real OOS EV separator but avoidance-axis + not incremental over continuous feats
     (value = interpretable risk states + +2.3% no-trade filter). Wallet intelligence NOT dead (multivariate
     beats token-only OOS). NOTHING clears +2% gate — all negative on the ONE down-regime. Binding constraint
     reconfirmed = REGIME DIVERSITY (cross-day), not features. C-002 sole champion. Next decisive = H-163.
