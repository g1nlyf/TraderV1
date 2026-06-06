# H-162 — Distribution (sell) clusters as a forward down-signal

**Status:** tested · **REAL, gate-clears statistically · NOT promotable (capture + regime blocked)** · 2026-06-06
**Code:** `wallet_alpha/test_h162_sells.py` (+ capturability frontier)
**Data:** raw_trades 5.5h cross-section. Sell-cluster events (k=4 distinct wallets SELL / 15min).

## Hypothesis
Coordinated selling — especially by higher-PnL wallets — predicts larger forward drops (forced-flow /
distribution). Are smart-wallet sells/rotations more predictive than buys?

## Method
Same point-in-time engine, cluster side = sell. Long-side label + SHORT payoff (−Δprice − cost). Gate on
short side; wallet-quality sharpening; buy-vs-sell asymmetry; slippage-capturability frontier.

## Result (temporal OOS, both horizons)
- **Long after sell-cluster: −21% EV** (hit 20%) — coordinated selling precedes further drops.
- **SHORT side gate-clears:** wq_mean_pnl>median → **+22.1% EV, perm_p 0.008, CI95 [+15.9%,+27.6%], n=212,
  gates [YYY] PASS**; GBM short-select → +29.9% EV, perm_p≈0, n=195, PASS. Holds @30m and @60m.
- **Wallet quality SHARPENS sells** (rho(quality, long-ret) −0.23/−0.27) — opposite of buys (where quality
  anti-helped via survivorship). Real asymmetry.
- **Ordering (cost-invariant selection edge):** random < buy-cluster short +14.3% < sell-cluster +17.6% <
  high-wq-sell +22.1%. The wq-increment (+4.5–5.9%) is **constant across any flat cost** (it's a difference).

## Why NOT promotable (blocker list)
1. **No capture venue** — microcaps have no perp/borrow; this is an avoid/exit signal, not long-book alpha.
2. **eff-n = 1 session (5.5h, 2026-05-14).** The −17% universe dump is almost certainly a down-regime; cannot
   separate cross-sectional selection skill from regime (the H-051 regime-capture trap). Only the cost-invariant
   wq-increment is regime-robust, and even that needs multi-session proof.
3. **Flat 1.8% cost vs real 5–20% memecoin slippage** — base short dies ~20% RT (wq-increment survives, capture doesn't).
4. **No persistence evidence** (single snapshot).

## Verdict
**REAL down-signal, logged as risk/exit intelligence; NOT a champion.** Sharpest next test = H-163
(replicate wq-sell cross-sectional ordering across ≥30 daily captures → kill regime-capture) + H-164
(shortable/CEX-listed subset where it is capturable). This is the strongest wallet-side lead found, and it
is on the SHORT side — consistent with the locked truth that forced/coordinated selling carries information
while FOMO buying is noise (H-042/H-053). See SYNTHESIS.md.
