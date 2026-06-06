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
**REAL down-signal, logged as risk/exit intelligence; NOT a champion.** This is the strongest wallet-side
lead found, on the SHORT side — consistent with the locked truth that forced/coordinated selling carries
information while FOMO buying is noise (H-042/H-053). See SYNTHESIS.md.

## Sprint 6 update — persistence (intra-session) + capturable conversion (2026-06-06)
Code: `test_h162_persistence.py`, `test_capturable.py`. Reports: H162_PERSISTENCE_REPORT.md,
CAPTURABILITY_REPORT.md, PERSISTENCE_SYNTHESIS.md.
- **Intra-session persistence: HOLDS.** Time-block walk-forward (threshold from past blocks → next block):
  wq-sell SHORT edge +7.74% over base, perm 0.000, CI [+17.8,+25.7], n=431 (@30m; @60m +7.72%, n=469).
  Edge present in 3/4 testable blocks. The +7.7% wq INCREMENT is a within-block relative effect = the
  regime-robust part; the +14–21% short BASE is the May-14 down-regime (untestable cross-day).
- **Cross-day persistence: still UNKNOWN** — one session. firehose_collector now accruing days (target ≥14).
- **Capturable conversions (all real selection, all on a negative base → no positive-EV long):**
  - Buy-AFTER-absorbed-distribution +10.4% rel vs fresh-FOMO (perm 0.001) = H-042 on-chain (flips the naive veto).
  - Rotation targets (sell A→buy B) +0.4–0.6% rel (perm 0.005, n=9369) — real, tiny.
  - **Exit-overlay** (exit held long on during-hold distribution cluster): +3.9%/+5.4% per trade saved,
    perm 0.000 — capturable RISK module candidate (book still −11%, so de-risk not alpha). See CAPTURABILITY_REPORT.
- **NEW IDs:** H-163 (day-level persistence), H-164 (shortable/avoidance subset), H-166 (exit-overlay risk module).
