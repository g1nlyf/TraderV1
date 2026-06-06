# H-162 Persistence Report (2026-06-06)

**Question:** does coordinated quality-wallet selling predict further drops *across time/regimes*, or was
the Sprint-5 result a single May-14 artifact?

**Hard limit:** raw_trades is ONE 5.5h session (May-14 10:06–14:31 UTC for sell events). True cross-day
persistence is **not testable** until the firehose collector accrues days (now running; target ≥14 days).
What IS testable now: **intra-session** stability via time-block walk-forward. Code: `test_h162_persistence.py`.

## Result — intra-session walk-forward (5 time-blocks)
Walk-forward = set the wq threshold on past blocks, apply to the next block, aggregate OOS fired events.

| H | OOS n | wq-sell SHORT EV | base (all sells) | edge | perm_p | CI95 | gates |
|---|-------|------------------|------------------|------|--------|------|-------|
| 30m | 431 | **+21.55%** | +13.81% | **+7.74%** | 0.000 | [+17.76%, +25.70%] | [perm✓ CI✓ n✓] |
| 60m | 469 | **+22.41%** | +14.69% | **+7.72%** | 0.000 | [+18.63%, +26.52%] | [perm✓ CI✓ n✓] |

Per-block edge (wq-sell minus all-sell short EV), H=30m:
- block1 (n=55, early): −4.99% (perm 0.75) — noisy/tiny
- block2 (n=434): **+10.59%** (perm 0.000)
- block3 (n=241): **+8.09%** (perm 0.000)
- block4 (n=243): +2.81% (perm 0.15)

## Interpretation — two layers, separated
1. **The SHORT base (+14–21%) = the regime.** Everything sold off all session. This level is a
   single-session market state and is the part that **cannot** be claimed as persistent. A different day
   could be flat/up and this base would vanish or invert.
2. **The wq INCREMENT (+7.7%, walk-forward, perm 0.000) = cross-sectional selection.** High-pre-t-skill
   wallets' sell-clusters drop *more* than random sell-clusters, and this holds in 3 of 4 testable blocks
   and survives walk-forward. Because it is a *relative* (within-block) effect, it is far more regime-robust
   than the base — this is the part most likely to be real skill rather than regime.

## Verdict
- **Intra-session: the wq-sell selection edge PERSISTS** (walk-forward OOS, perm 0.000, both horizons).
- **Cross-day/cross-regime: UNKNOWN** — structurally untestable on one session. NOT promotable.
- The May-14 down-regime inflates the headline; the durable claim is the +7.7% cross-sectional increment.

## Promotion blockers (unchanged + sharpened)
1. eff-n at the **day** level is still 1. Block-level persistence ≠ regime independence.
2. No capture venue (microcap short). The increment is a *ranking* signal, not a long.
3. Flat 1.8% cost; the increment is a difference so cost-invariant, but absolute capture is not.

## Next (data-gated, now unblockable)
Run `firehose_collector.py` daily ≥14 days → rebuild events per day → re-run this block walk-forward at the
**day** level (H-163). If the +7.7% wq increment survives across genuinely different days/regimes, it
becomes a real, regime-robust cross-sectional signal worth a capturable wrapper (H-164 shortable subset).
