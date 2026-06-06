# H-161 — Wallet archetype mix as a cluster-quality signal

**Status:** tested · **FAIL (DEAD)** · 2026-06-06 (Sprint 5)
**Code:** `wallet_alpha/test_h161_archetype.py`
**Data:** raw_trades 5.5h cross-section. Buy-cluster events (k=4/15min).

## Hypothesis
Define wallet archetypes by **unsupervised** clustering of label-free behavior (trade count, token breadth,
size, hold time, churn). The archetype MIX of a cluster's participants ("smart swing wallets" vs
"bots/snipers") predicts forward intraday return OOS and beats token-only + the gate.

## Method
- KMeans (k=5) on standardized log-features of all wallet profiles (no forward labels used). Clusters named
  from centroids. Each event gets a participant archetype-mix vector. GBM on mix; ablation token vs token+arch.
- Caveat (documented): archetype computed over full session = mild look-ahead on a wallet's own later trades,
  but archetype is a ~stationary, label-independent TYPE → a FAIL here is robust (leak could only help).

## Result
- Clean archetypes emerged: **swing** (hold ~350–680s), **sniper** (hold 13–43s, fast 0.6–0.95),
  **hodler** (hold ~1160s, sells 0.04). Sniper-dominated clusters do **worst** (−20% to −31%);
  swing-dominated least-bad (−5% to −9%) but n<30 and CI spans zero.
- **arch-only model: rho +0.06–0.10** (near-noise). **token+arch ≈ token-only** (archetype adds nothing).
- **0 gate-clearing rules.**

## Verdict
**DEAD.** Archetype mix is a weak proxy for what token-microstructure context already captures. Who is in
the cluster matters far less than the token's state. No capturable alpha. See SYNTHESIS.md.
