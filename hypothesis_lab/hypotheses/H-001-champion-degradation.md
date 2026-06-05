# H-001 — Champion Degradation Diagnosis

**When to create:** At hypothesis generation time, BEFORE testing. Populate Results/Verdict/Refinement during and after backtest. Verdict is final — create a new H-XXX for any revised version.

**Status:** proposed
**Priority:** P0 — URGENT
**Asset universe:** Solana memecoins (GeckoTerminal OHLCV)
**Created:** 2026-06-04

## Statement
The mean-reversion rule (drawdown<-10% AND range_pct>median AND buy_pressure_6>median) showed rule_ev=+1.57% on 2026-05-31 and rule_ev=-0.47% on 2026-06-01 (ALERT: EDGE DEGRADING). This hypothesis investigates WHY and what the fix is.

## Rationale ("million dollar idea")
A degrading edge is as valuable as a discovered edge — it tells you the edge was regime-specific. Diagnosing EXACTLY which regime killed it gives you the regime filter for free. The market changed in 1 day: that's a signal about what kind of edge you actually found. Regime-aware trading is how quant funds survive for decades.

## Data required
- `finetune/data/meanrev_log.jsonl` — both walk-forward entries
- `finetune/data/holdout_mom3_eval.jsonl` — the holdout dataset
- GeckoTerminal OHLCV for the tokens added between May 31 and June 1
- SOL price on Binance (regime context: was SOL trending or ranging?)

## Test method
1. Split June 1 holdout into: (a) tokens that existed on May 31 vs (b) new tokens
2. Run rule separately on each subset — does the rule fail on new tokens or on old ones?
3. Check SOL regime on June 1: BTC/SOL 7-day trend. If SOL was trending strongly, rule fails in trend.
4. Check if holdout composition shifted: are new tokens different in volatility, age, or market cap?
5. Temporal holdout standard: compare with permutation null on each subset.

## Parameters
- Subset split: existing vs new tokens
- SOL regime: 7d trend positive/negative/neutral
- Drawdown threshold sweep: -5%, -10%, -15%, -20%, -30%

## Results (2026-06-04 — verified via hypothesis_lab/scripts/h001_verify.py)

**The premise was wrong. The champion did not degrade — it was never an edge.** The
"+1.57% → −0.47%" story is an artifact of the measurement pipeline, confirmed three ways.

### What the walk-forward log actually shows
| date | n | tokens | base_ev (logged, wr-implied) | rule_ev (logged, wr-implied) | params |
|------|---|--------|------|------|--------|
| 05-31 | 941 | 34 | −0.98% | **+1.57%** | range≥.0358, bp≥.475 |
| 06-01 | 1360 | (grown) | −1.56% | **−0.47%** | range≥.0315, bp≥.470 |

The two rows are **not nested in time**. `autoloop_meanrev` re-runs `build_momentum_v3`,
which rebuilds the holdout from `token_ohlcv` over whatever tokens currently have ≥30
candles. n grew 941→1360 because the harvest pulled **more tokens**, not because a market
day passed. Bigger, more-representative sample → measured EV regressed toward the true
(brutally negative) memecoin base rate. The "drift" alert fired on a confound.

### Realized truth (rebuilt from DB, keeping the payoffs the holdout file discarded)
Current full OOS holdout, n=1360, 49 tokens, live calibrated params (dd<−0.10, range>.0315, bp>.470):
```
rule fires:          240 / 1360 (17.6%)
REALIZED rule_ev:    -0.97%     (the rule LOSES money per trade)
REALIZED base_ev:    -0.17%
edge over base:      -0.80%     (rule selects WORSE-than-random events)
permutation perm_p:   0.887     (rule beaten by ~89% of random same-size subsets)
block-bootstrap CI95: [-2.25%, +0.64%]   (spans zero, centered negative)
within-OOS split:    NEGATIVE in BOTH halves (-1.23% early, -0.56% late)
```

### Why win-rate lied (the mechanism)
|              | avg win | avg loss | win rate | realized EV |
|--------------|---------|----------|----------|-------------|
| base (all)   | +11.7%  | −7.5%    | 38.2%    | −0.17%      |
| rule-fired   | +14.3%  | **−11.9%** | 41.7%  | **−0.97%**  |

The rule fires on deep-drawdown names → marginally higher hit-rate, but its losers slam
the −12% stop (−11.9% vs base −7.5%). Pennies in front of a steamroller. The pipeline's
EV was `win_rate*0.20 − (1−win_rate)*0.12 − 0.018` — a win-rate reconstruction that
assumes every trade hits a hard barrier. Most exit by **time** with small payoffs, so the
formula **inverted the sign of the truth**.

### Three instrument defects (root cause)
1. **Unstable-universe walk-forward** — holdout rebuilt over a growing token set each run; cross-run EV deltas confound n+tokens+params. → the fake "degradation".
2. **No permutation/CI gate at promotion** — promoted on 34 tokens; LEGACY H-03 later got perm_p=0.23 on the full set. Fails the locked gate.
3. **Win-rate-implied EV ≠ realized EV** — realized payoffs discarded at build time. → the fake "+1.57%".

## Verdict
[ ] PASS  [x] **FAIL** (champion invalidated)  [ ] INCONCLUSIVE

Realized rule EV −0.97%, perm_p 0.887, CI95 spans zero, negative in every temporal slice.
The mean-reversion drawdown rule has **no out-of-sample edge** on Solana memecoins. It is
*anti*-selective on realized payoff. C-001 retired (see champions/STACK.md).

## Refinement path
The right lesson is **not** "find the regime where it works" (there is none here) — it is
**fix the instrument so this can't recur**, then re-point research at threads with real signal.

Instrument fixes shipped this session (verified end-to-end):
- `finetune/pipeline/eval_stats.py` — single honest scorer (realized EV + perm_p + CI95 + verdict), self-tested.
- `build_momentum_v3.py` — holdout now retains realized `net`, `entry_ts`, `token_mint`.
- `autoloop_meanrev.py` — `rule_ev` is now realized; perm/CI gate added; drift only compared within the same `universe_fp`; `--validate-only` mode added.

Research re-pointing (see ROADMAP / synthesis):
- Memecoin drawdown mean-reversion track (D-005) → demoted; the only signal it ever had was a metric artifact.
- Live threads with genuine structure: **H-13 funding carry** (raw +9% APR, killed only by the tradeable-universe filter — attack the filter) and **H-15 anomaly** (t=7.99 but perm_p=0.666 — resolve the contradiction; likely the same fat-tail/effective-n problem found here).

## Verification script
`hypothesis_lab/scripts/h001_verify.py` — reproduces the pipeline exactly (matches logged
wr-implied −0.4667%), then adds realized EV, 20k-permutation null, block-bootstrap CI95,
and an honest within-OOS temporal split. Run: `py hypothesis_lab/scripts/h001_verify.py`.
