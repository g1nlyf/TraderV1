# Validation Audit — Sprint 8 → Sprint 9 (2026-06-06)

Audited the Sprint-8 gate (`token_lifecycle.py`), found a contamination bug, fixed it in the reusable
`tournament.py` harness, and re-ran every claim under a TEST-ONLY walk-forward gate. Conclusion: **the
Sprint-8 signals SURVIVE the fix (contamination did not manufacture them); one fragile claim was corrected;
one new robust finding emerged.** Trust restored, with the standing single-regime caveat.

## The bug (confirmed)
`token_lifecycle.py` computed gates via `gate_mask(rows, mask)` which passed **full-sample** `all_nets`
(train+test) into `eval_stats.evaluate_selection` while firing **test-only** selections:
- The permutation null drew k samples from the **train+test** universe, not the test fold → wrong null.
- `base_ev` and `edge_over_base` were computed over **train+test**, not the test fold.
- Worse, the per-state (A1) gates used a **full-timeline** mask (train+test rows of a state) → not OOS at all.

In a single down-trending session train/test base EVs differ, so this biases edges and p-values.

## The fix (tested)
`tournament.py` gate ALWAYS runs on the **pooled TEST-ONLY universe** across expanding-window walk-forward
folds: base = mean(pooled test nets), perm draws k from pooled test only, bootstrap CI on fired test nets.
Proven by `test_tournament.py::test_gate_test_only_isolation` — a dataset with train EV −0.5 / test EV +0.5
reports base **+0.167 (test-only mean)**, not the contaminated −0.10 (full-sample). 7/7 harness tests pass.

## Before → after (corrected, walk-forward k=3, TEST-ONLY)
| claim | Sprint-8 (contaminated, single split) | Sprint-9 (corrected, walk-forward) | verdict |
|-------|----------------------------------------|------------------------------------|---------|
| token-only GBM top30 (lifecycle) | edge +1.87%, perm 0.301 (n.s.) | edge +4.66%, **perm 0.044** | **STRENGTHENED** — real |
| neutral-state separator | edge +8.0%, perm 0.000 (full-sample) | edge +7.34%, **perm 0.002** | holds (honest p) |
| token+state increment | +0.10% | +0.53% (perm 0.030) | small, holds |
| **naive avoidance filter** (skip rug/distrib/decay) | **+2.3% "capturable"** | **edge +2.30%, perm 0.117 (N.S.)** | **CORRECTED — fragile/single-split luck** |
| token+wallet vs token-only (cluster) | +1.55% edge, Spearman +0.074 | **+1.78% edge (+15.54% vs +13.76%), perm 0.000** | **CONFIRMED** under walk-forward |

## New robust finding (Sprint-9 cycle 2)
- **H-184 rug pre-detection no-trade filter**: GBM predicts P(net<−50%) from PRE-entry token features; keep the
  70% lowest rug-risk → **edge +4.73%, perm 0.000, n=431**. This is the *correct* way to do avoidance (the
  naive state-skip filter was n.s.). Robust, capturable de-risk. Still EV<0 (down-regime) → shadow filter.
- **H-171b ablation**: the wallet increment is carried by **both** wq (token+wq +15.89%, CI upper **+2.14%**)
  AND cohesion (token+cohesion +15.39%) — distributed across wallet features, not a single artifact.

## Other audit checks
- **Overlapping windows (cluster events):** clusters form in 900s windows and can overlap in time → effective
  n < nominal n=1137. Mitigated by walk-forward + block-bootstrap CI (the honest interval). Lifecycle sample
  is explicitly non-overlapping (≥H spacing, tested). Treat cluster n as an upper bound.
- **Single split → walk-forward:** all claims now use 3 expanding folds, pooled test. (Nested walk-forward
  with more folds is the next hardening step; queued as H-171b extension.)
- **Session/time artifact:** GBM could learn time-of-session. Temporal split (train always before test) blocks
  forward leakage, but on ONE session "time" and "regime" are confounded — we CANNOT rule out that the model
  learns "later-in-the-dump = worse." This is exactly the cross-day blocker; only multi-regime data resolves it.
- **Source purity:** all evidence = organic raw_trades / cluster events. Fixtures excluded. Corecast rows
  carry `source="corecast"`; GeckoTerminal `source="geckoterminal"` — both organic, both queryable.

## Verdict
Sprint-8's core conclusions are **not** artifacts of the contamination — under the corrected TEST-ONLY
walk-forward gate they hold or strengthen (token_gbm 0.044, neutral 0.002, token+wallet 0.000). The one
fragile claim (naive avoidance filter) is corrected to n.s. and **superseded** by the robust H-184 rug-skip
filter. Every selection remains EV<0 on the May-14 down-regime → **promoted=0**, unchanged. The validator is
now reusable (`tournament.py`) so this contamination class cannot recur.
