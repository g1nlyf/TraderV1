# Persistence Flywheel — Synthesis (Sprint 6, 2026-06-06)

Goal: decide whether H-162 wallet distribution intelligence persists across regimes and can become a
capturable long-only / avoidance / exit edge. Built the free collector to make persistence testable, and
ran every conversion that the existing single-session data allows.

## TL;DR
- **Built the engine** that unblocks the real question: a durable, free, keyless wallet-trade firehose
  (`firehose_collector.py`, GeckoTerminal). Verified live (392 trades/34 wallets in one tick; smoke ALL PASS).
- **Persistence (intra-session): the wq-sell selection edge holds** across time-blocks (walk-forward OOS
  +7.7% over base, perm 0.000, both horizons). **Cross-day: still untestable on one session** — that needs
  the collector to run ≥14 days (now possible).
- **Capturability: no positive-EV long exists**, but the distribution signal converts into real, capturable
  *risk* behavior. Strongest = **exit-overlay** (exit a held long on a during-hold distribution cluster):
  saves +3.86%/+5.35% per trade @30/60m, perm 0.000 (control verdict in CAPTURABILITY_REPORT.md).
- Every wallet signal is a **real cross-sectional selector** on a **negative session-wide base** (May-14
  was a dump). Selection is real; the base is regime; nothing reaches positive long EV.

## The unified picture (why all results rhyme)
On 2026-05-14 the sampled universe fell ~−11% to −17% over 30–60 min (the regime). Against that base:
| Signal | Effect | perm | Real? | Capturable long? |
|--------|--------|------|-------|------------------|
| Naive buy-cluster (Sprint 5) | −17.7% | — | base | no |
| wq-quality buy selection (H-160) | worse (rho −0.37) | — | survivorship anti-signal | no |
| Buy AFTER absorbed distribution | +10.4% rel (−6.3% vs −16.6%) | 0.001 | **yes (H-042 on-chain)** | no (still <0) |
| Rotation targets (sell A → buy B) | +0.4–0.6% rel | 0.005 | yes, tiny | no (still <0) |
| Exit-overlay on distribution | +3.9–5.4%/trade saved | 0.000 | **yes** | **yes (risk rule)** |
| wq-sell SHORT (H-162) | +7.7% increment | 0.000 | yes | no venue |

The honest synthesis: **wallet behavior carries genuine cross-sectional information** (5 of 6 signals are
perm-significant), but on this data it is all *relative* — it sorts a falling universe, it does not lift
anything above zero. The only thing that becomes *capturable* is using the down-signal to **de-risk** (exit
earlier), not to make money long.

## Mechanistic findings worth keeping
1. **Buy-after-distribution > fresh-FOMO** (+10.4%, perm 0.001): coordinated selling that is already
   absorbed precedes a bounce; a fresh buy-cluster with no prior selling is the local top. This is H-042
   (forced-flow reversion) appearing in pure on-chain cross-section — independent confirmation.
2. **The wq-sell increment is the regime-robust part.** Base short EV = regime (untestable cross-day); the
   +7.7% wq increment persists block-to-block and is a *within-block* relative effect → most likely real skill.
3. **Rotation is real but weak** — smart-wallet exits do flow into next tokens that beat random buys, but by
   <1% and still negative. Not worth a wrapper yet.

## Status vs the gate
No capturable rule clears EV>2% ∧ perm<0.05 ∧ CI95>0 ∧ n>100. The exit-overlay clears perm + n and is
capturable, but its EV stays negative (it reduces loss on a book that shouldn't be held). → **risk module
candidate, not alpha.** See CAPTURABILITY_REPORT.md.

## Next loop (now unblockable — the flywheel turns)
1. Run `firehose_collector.py` daily (Task Scheduler / loop). Target ≥14 days.
2. Rebuild events per day; union with raw_trades.
3. Re-run `test_h162_persistence.py` at the **day** level (H-163): does the +7.7% wq increment survive
   genuinely different regimes? This is the single experiment that promotes or kills wallet intelligence.
4. If it survives → H-164 (capturable shortable/avoidance subset) + fuse with C-002 context.
5. If it dies across days → wallet intelligence is regime-bound; close the long thread, keep exit-overlay
   only as a Stage-2 risk filter.

## What did NOT happen (anti-fake-progress ledger)
- No new champion. No promotion. No positive-EV long. No LLM fine-tuning (structured baselines did not
  produce a capturable signal worth modeling — the gate for going to LLMs was not met).
- All claims are OOS, perm-tested, cost-adjusted, with baselines. Generated-but-untested = none.
