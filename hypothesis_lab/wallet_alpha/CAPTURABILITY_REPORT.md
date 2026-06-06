# Capturability Report (Sprint 6, 2026-06-06)

Can the H-162 distribution signal be converted into something a long-only / paper system can actually
capture? Shorting microcaps is not capturable, so we test avoidance, exit, and rotation. Code:
`test_capturable.py`. All returns capped [-1,+1], cost 1.8% RT, gate via `eval_stats`. Temporal context =
the single May-14 session (so a negative base pervades; the question is whether signals beat that base).

## Results (H = 30m / 60m)

| Conversion | n | EV | base | edge | perm | capturable? | verdict |
|------------|---|----|----|------|------|-------------|---------|
| Buy AFTER absorbed distribution | 172/178 | −6.3% / −7.7% | −15.1% / −15.5% | **+8.8% / +7.8%** | 0.001 / 0.003 | long (but EV<0) | real selection, not a long edge |
| Fresh-FOMO buy (no prior selling) | 965/1026 | −16.6% / −16.9% | — | −1.6% / −1.4% | — | — | the local top; avoid |
| Rotation targets (sell A → buy B ≤1h) | 9369/7732 | −11.4% / −11.0% | −15.1% / −15.5% | +0.4% / +0.6% | 0.005 / 0.001 | long (but EV<0) | real, tiny |
| **Exit-overlay (distribution → exit)** | 1137/1204 | −11.2% / −10.2% | −15.1% / −15.5% (hold) | **+3.9% / +5.4%** | 0.000 | **YES (de-risk)** | **real signal-driven risk rule** |

## The exit-overlay control (the rigorous part)
"Exit early in a dump" helps mechanically regardless of signal. To isolate the SIGNAL, we re-ran with a
**shuffled-lag control**: same positions exit early, but at a randomly permuted exit lag (same lag
distribution, wrong timing). 200 shuffles.

| H | hold | signal-exit | shuffled-lag control | signal beats control |
|---|------|-------------|----------------------|----------------------|
| 30m | −15.08% | **−11.22%** | −13.05% | **100% of draws** |
| 60m | −15.53% | **−10.18%** | −12.92% | **100% of draws** |

So of the ~+3.9% improvement @30m, ~+2.0% is mechanical (early exit in a downtrend) and **~+1.8% is the
distribution-timing signal itself** — and it beats the control in 100% of 200 shuffles at both horizons.
The signal carries real exit-timing information.

## Verdict
- **No capturable LONG alpha.** Every signal sits on the −11 to −17% May-14 base; nothing reaches EV>0.
  No rule clears the promotion gate (EV>2% ∧ perm<0.05 ∧ CI>0 ∧ n>100).
- **One real capturable behavior: the exit-overlay (H-166).** Distribution-timed exit beats both
  hold-to-horizon (+3.9/+5.4%, perm 0.000) and a shuffled-timing control (100% of draws). It is a genuine,
  signal-driven **de-risk module** — it reduces loss on a book, it does not create profit. → Stage-2 risk
  filter candidate, **not** alpha. Will only matter once a profitable long book exists (none does yet).
- **Mechanistic keeper:** buy-after-absorbed-distribution >> fresh-FOMO (+8.8%, perm 0.001) = H-042
  forced-flow reversion confirmed in pure on-chain cross-section. Corrects the naive "veto distribution"
  intuition — the right sign is to PREFER post-distribution entries (still not a long here, but a real selector).

## Promotion blockers (all of capturability)
1. Negative session base → no positive-EV long on this data (regime; needs other-day data to test).
2. Exit-overlay is de-risk only (book stays negative); valuable solely as a Stage-2 reject/exit filter.
3. eff-n = 1 day for absolute levels. Cross-day replication (H-163) required before any of this is durable.

## Capturable next steps
- **H-166 exit-overlay** → wire as a *shadow* Stage-2 no-trade/early-exit signal (deterministic, paper-only)
  once a long book exists; until then, keep as validated risk logic. (Integration plan: see ROADMAP Track 5.)
- **H-164** → restrict to CEX/perp-listed tokens where the down-signal is actually shortable/hedgeable.
- All gated on **H-163** (multi-day persistence) — the firehose is now collecting toward it.
