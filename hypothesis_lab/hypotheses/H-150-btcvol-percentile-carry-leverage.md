# H-150 — BTC Vol Percentile as Dynamic Leverage Scalar for C-002

**Status:** proposed · 2026-06-05
**Zone:** CROSS-ASSET / MACRO

## Statement
Rather than a binary on/off gate (H-140), use BTC realized-vol as a CONTINUOUS leverage scalar: leverage = base_leverage × (1 - btcvol_percentile). At BTC vol p10 (quiet), run 3.4x (full C-002 target). At BTC vol p50, run 1.7x. At BTC vol p90 (turbulent), run 0.3x. The C-002 leverage sim validated 3.4x in normal conditions; this proposal modulates it dynamically to reduce tail exposure.

## Structural logic — who is forced
The basis-blowout tail in the leverage simulation was the key risk. BTC realized-vol is the best real-time observable of when basis-blowout risk is elevated (cascade margin calls create the very basis gaps the model fears). Dynamic de-leveraging on high BTC vol is a mechanically sound response to this specific tail risk.

## Falsifier
Risk-adjusted returns (Sharpe) of BTC-vol-scaled carry are no better than always-3.4x; or the vol-scaling reduces returns without proportionally reducing drawdown (i.e., the downscaling fires at the wrong times).

## Why uncaptured
C-002 leverage sim used fixed 3.4x. Dynamic leverage modulation based on a macro vol signal is a standard institutional practice but not implemented in this codebase.

## Data status
data_status: HAVE — BTC_8h_klines.npz; carry period PnL series; leverage sim from existing runs.

## Test (one line)
Compute btcvol_percentile (trailing-90d) at each period; rerun C-002 carry PnL series with leverage = 3.4 × (1 - percentile); compare scaled vs fixed-3.4x Sharpe, max-drawdown, APR via block-bootstrap.

## SCORE: 7.5
(edge_plausibility 3.5/5, data_feasibility 5/5, novelty 3/5 → (3.5×2+5+3)/4 = 15/4 = 3.75 → ×2 = 7.5)

## Results (2026-06-05) — `test_carry_cluster.py` — REFUTED (no value-add)
Tested as a de-risk / leverage-scalar rule alongside H-091. A basis-vol-scaled book (proxy for the
percentile-leverage idea) lowered both Sharpe (3.54→3.21) and APR (+1.49%→+1.16%) with maxDD
essentially flat (−0.19%→−0.17%). Separately, the BTC-vol *gate* variants (H-080/092/100/116/140)
also failed to CI-separate (see those files). Scaling leverage down by a vol percentile sheds return
without a corresponding risk reduction in-sample (book maxDD already −0.19%). **Verdict: refuted as a
performance lever; gate-candidate N. Keep only as un-sampled-tail insurance, not a backtested edge.**
