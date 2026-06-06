# Wallet Intelligence Alpha Engine — Synthesis (Sprint 5, 2026-06-06)

Ranking of alive vs dead paths after building the first honest point-in-time wallet-alpha test stack.
All numbers are temporal-OOS on the raw_trades 5.5h cross-section, realized capped EV, through the
canonical gate (`finetune/pipeline/eval_stats.py`). Reproduce: `py test_h160_consensus.py` etc.

## The one-paragraph answer
On the data we have, **there is no capturable wallet/on-chain LONG alpha.** Naive smart-wallet copy is a
**−17% EV loser** (cluster-buys mark local tops). Point-in-time wallet "quality" does **not** rescue it —
it slightly *anti*-predicts (the session's high-PnL wallets are survivorship artifacts whose later buys
reverse hardest, rho −0.37). Token-microstructure context carries **real OOS signal** (rho +0.55,
perm_p≈0) but only lifts the best-selected half to ≈breakeven; wallet features add ~nothing on top.
The one genuinely real, gate-clearing signal is on the **short/avoid side**: coordinated selling —
especially by higher-PnL wallets — predicts larger forward drops (wq-sell short +22% EV, perm_p 0.008,
CI [+15.9%,+27.6%], n=212, cost-invariant edge +4.5–5.9%). But it is **not promotable**: no venue to short
microcaps, and with a single 5.5h session the headline level is almost certainly **regime-capture**
(May-14 was a down session). It is logged as a risk/exit signal and the sharpest multi-day next test.

## Scoreboard
| Path | Best OOS result | Gate | Verdict |
|------|-----------------|------|---------|
| **Naive wallet-copy** (copy_engine premise) | −17.7% EV, hit 21% | FAIL | **DEAD** — buying consensus = buying the top |
| **H-160 consensus quality** (pre-t wallet PnL/winrate) | wq-select −22.9% (rho −0.37); +wq over token Δ≈0 | FAIL | **DEAD** — survivorship anti-signal; adds nothing to token context |
| **H-161 archetype mix** (KMeans sniper/swing/bot/hodler) | arch-only rho +0.06–0.10; token+arch ≈ token | FAIL | **DEAD** — archetype is a weak proxy token context already holds |
| Token-microstructure model (baseline) | top-50% → −0.3% EV @60m, rho +0.55, perm_p≈0 | FAIL (EV<2%, CI spans 0) | **REAL-but-unprofitable** — predicts relative badness, can't reach +2% |
| **H-162 distribution-sell down-signal** | wq-sell SHORT +22% EV, perm_p 0.008, CI>0, n=212 | PASS (statistically) | **REAL, NOT capturable** — no short venue + eff-n=1 regime risk |

## What we learned (mechanisms, not just verdicts)
1. **Consensus = crowding, not edge.** ≥4 wallets buying a memecoin within 15 min is the local top, not a
   discovery signal. The same lesson as H-022 (cross-venue agreement = crowded extreme) on the wallet side.
2. **In-session wallet "skill" is survivorship.** Wallets ranked by realized PnL *within the session* are
   the ones who already rode the pump; their *next* cluster-buys reverse. This is precisely why the
   look-ahead leaderboard "worked" and why copy_engine's in-sample backtest was meaningless.
3. **Asymmetry confirmed on-chain.** Selling is a stronger forward-down signal than buying is forward-up
   (sell-cluster short base +17.6% vs buy-cluster +14.3%), and wallet quality *sharpens sells* (rho −0.23)
   while it *anti-helps buys*. Consistent with the locked truth: forced/coordinated selling carries
   information; FOMO buying is noise.
4. **Token microstructure > wallet identity.** Whatever little OOS signal exists is in age/liquidity/
   imbalance/prior-return, not in who is trading. Wallet features are redundant given context.

## Promotion-blocker list for the one live signal (H-162)
1. **No capture venue** — microcaps have no perp/borrow; the short is an avoid/exit signal, not long-book alpha.
2. **eff-n = 1 session** — 5.5h of one day. The −17% universe dump is likely a down-regime; cannot separate
   cross-sectional selection skill from regime (the H-051 trap). The cost-invariant wq-*increment* (+4.5%)
   is the part most likely to survive, but needs multi-session proof.
3. **Flat 1.8% cost** — real microcap slippage is 5–20%/side. Base short dies by ~20% RT; the wq-increment
   is a *difference* so it is cost-invariant, but absolute capture is not.
4. **No persistence evidence** — the mission's "still not learned" stays not-learned on this data.

## Sharpest next hypotheses (data-gated)
- **H-163 (multi-session sell-skill replication):** capture the bitquery firehose daily for ≥30 days; test
  whether high-wq sell-clusters out-drop random sells *across* sessions (kills regime-capture; eff-n = days).
- **H-164 (shortable subset):** intersect cluster tokens with CEX/perp-listed names; test the down-signal
  where it is actually capturable; fuse with C-002 funding/basis context.
- **H-165 (exit-overlay):** use quality-sell-cluster as an exit trigger for any future on-chain long book
  (saves ~5% per the H-162 increment) — only meaningful once a profitable long book exists (none yet).

## Bottom line for the program
The binding constraint is reconfirmed: **DATA, not ideas.** The wallet substrate is cross-sectionally rich
but temporally a single snapshot. Spend cycles on **multi-day capture** (highest leverage — unlocks
persistence, regime-separation, multi-day labels) rather than more single-session variants. C-002 remains
the sole champion; H-042 remains the sole sub-gate sleeve; wallet alpha remains **unproven (long) /
real-but-uncapturable (short)**.
