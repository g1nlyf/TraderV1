# OPEN QUESTIONS — what we don't know, ranked by how much it would change

> Each question has: status, what we'd need to answer it, and what the answer would change.

## Sprint-5 mission review questions (the crux)
- **Strongest reason wallet alpha could work:** wallet behavior may encode private information, coordination, or a repeatable discovery advantage that precedes full price reaction.
- **Strongest reason it could fail:** historical wallet "alpha" is luck + leaked labels (GMGN/leaderboard survivorship) + uncapturable latency.
- **Hidden assumption under test:** the 847K tape is point-in-time enough to reconstruct pre-outcome knowledge. **PARTIAL ANSWER (Sprint 5 audit): YES within 2026-05-14, NO across days** — it is a 5.5h snapshot, so within-session reconstruction is valid, cross-day persistence is not even askable.
- **Evidence that would change my mind:** a temporal-OOS wallet/consensus/fusion model that beats token-only AND naive-copy baselines with n>100, perm_p<0.05, CI95>0, net of cost.
- **Still not learned:** whether wallet intelligence has *persistent forward* alpha (not just attractive historical labels). **Data-blocked until multi-day capture exists.**

## Q1 — Does point-in-time wallet quality add power over token-only context? {#q-consensus}
- Status: **UNDER TEST** (`wallet_alpha/test_h160_consensus.py`).
- Need: cluster events + pre-t wallet skill (from pre-t completed round-trips) + forward intraday label + GBM vs token-only ablation.
- Changes: if YES OOS → first wallet-alpha lead. If NO → confirms leaderboard edge was survivorship; pivot to data collection.

## Q2 — Are smart-wallet sells more predictive (down) than buys (up)? {#q-sells}
- Status: **UNDER TEST** (`wallet_alpha/test_h162_sells.py`). raw_trades has side; intraday forward label.
- Changes: a short/avoid signal is independently valuable and harder to fake than buy-side hype.

## Q3 — Do archetypes (sniper/bot/swing/rotator) differ in intraday forward edge? {#q-archetype}
- Status: **UNDER TEST intraday** (`wallet_alpha/test_h161_archetype.py`). Half-life specifically = **BLOCKED** (5.5h span).
- Changes: lets us weight clusters by *who* is in them, not just how many.

## Q4 — Network density: do dense co-buy clusters beat loose ones? {#q-network}
- Status: PLANNED (graph edges = wallets co-buying same token within window). Folded into consensus test as a feature (cluster cohesion).

## Q8 — test_carry_cluster.py emits non-gate "gate-candidate" text {#q8-carry-cluster-gate}
- Status: **CONFIRMED BUG → FIXED Sprint 5.** The script rolled its own Sharpe/CI heuristic and printed
  "gate-candidate Y / HARDENS C-002" without calling `eval_stats.evaluate_selection` (the real
  EV>2% ∧ perm_p<0.05 ∧ CI95>0 ∧ n>100 gate). It could pass on a vol-matched blend while the H-042
  sleeve had n=39. Fix: route the stack sleeve through eval_stats and relabel heuristic text as advisory.
  See `wallet_alpha/` sprint log + the patched script.

## Standing methodological questions
- Are intraday forward VWAP labels capturable in practice given memecoin slippage? (cost model = 0.018 round-trip; need real slippage curve by liquidity bucket — currently a flat assumption, a promotion-blocker.)
- Is token-level temporal split enough, or do we need wallet-disjoint folds to prevent a wallet's two clusters leaking across train/test? (Sprint 5 uses time split + reports wallet overlap.)
