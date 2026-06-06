# H-166 Risk Engine Report (Sprint 7, 2026-06-06)

Built the H-166 distribution overlay as a deterministic, paper-only, point-in-time module
(`h166_risk_overlay.py`, 8/8 fixture tests pass) and backtested it Stage-2-style through the REAL module
over the May-14 cross-section with the full control set (`backtest_h166.py`). **The stronger control demotes
H-166.** Honest verdict below.

## Backtest (H=30m, n=1137 buy candidates, source=ORGANIC raw_trades, single session)
| policy | EV | hit | CVaR5 | perm vs hold | note |
|--------|----|-----|-------|--------------|------|
| hold (baseline) | −15.08% | 0.23 | −98.5% | — | |
| exit_random_time | −13.92% | 0.23 | −98.3% | 0.000 | mechanical early-exit control |
| **exit_random_sell** | **−11.69%** | 0.24 | −97.7% | 0.000 | exit at any random sell — **the strong control** |
| exit_h166 | −12.84% | 0.24 | −98.4% | 0.000 | quality-distribution exit (the module) |
| veto_h166 (kept) | −15.51% | 0.22 | −98.7% | 0.910 | no-trade veto: **no value** |
| combined | −13.65% | 0.24 | −98.7% | 0.000 | veto + exit |

exits fired 406/1137 (36%); vetoes 82 (7%); false-exit rate 23%.

## The decisive finding (a correction to Sprint 6)
- exit_h166 beats **hold** (+2.24%) and **random-time** (+1.08%), perm 0.000 — "exit on selling pressure" is real.
- BUT exit_h166 **loses to random-sell** (−12.84% vs −11.69% = −1.15%). Exiting at *any* sell is better than
  waiting for a *quality-distribution cluster*. **The quality/distribution specificity adds nothing over a
  naive "react to selling" rule.** Sprint 6's "beats shuffled-lag control 100%" used a weaker control
  (time-shuffle ≈ random-time); the random-**sell** control is the correct, stronger one, and H-166 fails it.
- **no-trade veto has no value** (−15.51% vs −15.08%, perm 0.910) — consistent with the buy-after-distribution
  *bounce* (H-042): distribution tokens should be WATCH, not vetoed.
- **CVaR5 ≈ −98% unchanged** — exiting does not fix the rug tail (microcaps gap to ~−100% fast).

## Verdict (the question the sprint asked)
H-166 is **#2/#3: a research curiosity / one-session artifact, NOT a validated Stage-2 risk filter.**
- The generic signal "exit when selling appears" is real (beats hold + random-time, perm 0.000) but is a
  naive reaction; H-166's quality-distribution refinement does not beat exit-on-any-sell.
- It is a single down-session; no drawdown-tail benefit; no-trade veto useless.
- **Do NOT promote. Do NOT wire as an authoritative Stage-2 risk veto.** It may ship only as a SHADOW
  (log-only) signal alongside a plain "exit-on-sell-cluster" rule, clearly labelled unvalidated, pending
  cross-day data (H-163). See H166_STAGE2_INTEGRATION_REPORT.md.

## What is genuinely delivered
- A correct, deterministic, leakage-safe, fully-tested overlay module + adapter shape for Stage-2.
- A rigorous backtest harness with the control that matters (random-sell), which is what caught the demotion.
- The honest conclusion that protects the program from shipping a non-edge as a risk module.
