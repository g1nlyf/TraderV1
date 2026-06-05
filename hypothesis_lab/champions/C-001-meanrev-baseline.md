# C-001 — Mean-Reversion Baseline (RETIRED — never a real edge)

**Status:** ❌ RETIRED / INVALIDATED (2026-06-04, H-001)
**Promoted:** 2026-05-31 (on a measurement artifact)
**Retired:** 2026-06-04
**Module:** `finetune/pipeline/meanrev_strategy.py`
**Config:** `finetune/inference/entry_champion.json` (marked invalidated — DO NOT TRADE)

## Why retired (one line)
Realized OOS EV = **−0.97%/trade**, edge over base **−0.80%**, perm_p **0.887**, CI95
spans zero, negative in every temporal slice. The "+1.57%" was a win-rate-implied EV
artifact on a 34-token slice. Full diagnosis: `hypotheses/H-001-champion-degradation.md`.

## Rule (Deterministic) — kept for the record
```
Entry when ALL of:
  drawdown_from_high < -0.10
  range_pct > median
  buy_pressure_6 > median
Payoff: triple-barrier +20% / -12% / time exit, cost 1.8% round-trip
```

## The illusion vs the truth
| metric | promoted (wr-implied, n=941, 34 tok) | realized (n=1360, 49 tok) |
|--------|------|------|
| rule win rate | 0.480 | 0.417 |
| **rule EV** | **+1.57%** | **−0.97%** |
| base EV | −0.98% | −0.17% |
| edge over base | (not computed) | **−0.80%** |
| perm_p | (not run) | **0.887** |
| CI95 | (not run) | [−2.25%, +0.64%] |

The rule fires on higher-hit-rate setups whose losers slam the −12% stop (avg loss −11.9%
vs base −7.5%). Higher win rate, worse realized PnL — win-rate-implied EV inverted the sign.

## Disposition
- Position size: **ZERO**. Not tradeable.
- Mean-reversion-drawdown track on memecoins demoted (decisions/TREE.md D-005).
- Instrument that produced the false positive is fixed (TREE.md D-006).
- Do **not** spin up H-004 (regime filter) / H-005 (Kelly sizing) on this rule — there is
  no positive base to filter or size. Those refinements assumed an edge that does not exist.
