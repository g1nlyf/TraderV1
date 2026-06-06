# H-160 — Point-in-time wallet-consensus quality alpha

**Status:** tested · **FAIL (DEAD)** · 2026-06-06 (Sprint 5)
**Code:** `wallet_alpha/build_events.py` + `wallet_alpha/test_h160_consensus.py`
**Data:** raw_trades 5.5h cross-section (DATA_AUDIT.md). Buy-cluster events, k=4 wallets / 15 min window.

## Hypothesis
Among cluster-buy events (≥4 distinct wallets buy a token within 15 min), selecting by **point-in-time
wallet quality** (each participant's realized SOL PnL / win-rate from round-trips completed *before* the
event) produces forward intraday EV that clears the gate and beats naive-copy + token-only baselines, OOS.
This is the honest replacement for `copy_engine.py` (which was in-sample + survivorship).

## Method
- Point-in-time wallet skill via avg-cost FIFO ledger, binary-searched to `block_time < t` (no look-ahead;
  never uses wallet_scores/leaderboard/wallet_token_pnl, all of which are full-history aggregates).
- Realistic execution: entry = VWAP in (t, t+5min] (you buy *after* seeing the cluster, at public price);
  label = forward VWAP near t+H over entry − 1.8% RT cost. Returns capped to [-1,+1] (capturable convention).
- Temporal OOS split (60/40 by form_ts). Baselines: naive-copy, token-only model. Models: HistGBM + ridge.
- Gate: eval_stats.evaluate_selection (EV>2% ∧ perm_p<0.05 ∧ CI95>0 ∧ n>100).

## Result (test fold, n=455 @30m / 482 @60m)
- **Naive-copy = −17.7% EV** (hit 21%): cluster-buys mark the local top.
- **Wallet-quality selection is WORSE:** wq_mean_pnl>median → −22.9% EV, edge −5.2%, **rho −0.37**.
  The session's high-PnL wallets are survivorship artifacts; their *later* cluster-buys reverse hardest.
- Token-context model: top-50% lifts EV to −6.3% (30m) / −0.3% (60m), **rho +0.55, perm_p≈0** — real signal
  but only reaches ≈breakeven (CI spans zero).
- **Wallet quality adds ≈0 over token context** (Δ fired-EV +1.3%/−0.2%, Δrho +0.00/+0.02).
- **0 rules clear the gate at any horizon.**

## Verdict
**DEAD.** Wallet-consensus quality is not capturable intraday long alpha. Consensus = crowding (buy the
top); in-session "skill" = survivorship that anti-predicts. Confirms copy_engine's positive backtest was
an in-sample artifact. See SYNTHESIS.md. Mechanism mirrors H-022 (agreement = crowded extreme).
