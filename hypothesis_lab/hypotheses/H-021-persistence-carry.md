# H-021 — Persistence / fixed name-selection carry

**Status:** tested · 2026-06-04 (Session 2)
**Priority:** P0 — best risk-adjusted edge found to date
**Asset universe:** 29 tradeable Binance perps (real spot leg, ≥90% history)
**Created:** 2026-06-04

## Statement
Select carry names by a STABLE criterion computed on train (funding-sign persistence, or
mean funding level) and **hold them equal-weight** through test, instead of dynamically
re-selecting the top-K each period. Hypothesis: stable name-selection captures durable
structural carry; dynamic chasing pays turnover and buys reverting spikes.

## Rationale ("million dollar idea")
H-13's `single_topk` (dynamic top-K by EWMA funding level) died OOS at −0.1% — it chases
funding spikes that mean-revert and pays turnover. But the carry itself is real (+3.5–5.5%
standalone per name). The edge is in **who you hold, fixed**, not **when you chase**. Names
with persistently positive funding have structural long demand (real holders paying to be
long); that carry is durable. Who's on the other side: leveraged longs who structurally keep
paying funding to hold the position. Friction that protects it: small capacity, requires
holding a 10-name delta-neutral book (operationally heavier than retail will do).

## Test method
Tradeable-29 universe (H-13 filter). Persistence = fraction of TRAIN periods with funding>0.
Select top-10 by persistence (and, for contrast, top-10 by mean level — fixed). Hold EW,
basis-aware (funding + spot_ret − perp_ret), maker 1bp/leg. EWMA-sign entry, no lookahead.
Temporal 70/30 split. `fh.evaluate` + block-bootstrap CI95. Script: `scripts/carry_leads.py`.

## Results (TEST, n=657 8h-periods ≈ 6 months OOS)
```
ALL tradeable (29, EW)        apr +0.77%  sharpe 1.79  CI95 [+0.22%, +1.26%]  VALIDATED  (baseline)
TOP-10 by PERSISTENCE (fixed) apr +1.34%  sharpe 1.45  CI95 [+0.36%, +2.27%]  VALIDATED
TOP-10 by LEVEL (fixed)       apr +1.44%  sharpe 3.20  CI95 [+0.73%, +2.05%]  VALIDATED  ← best single
BOTTOM-10 persistence         apr +0.23%  sharpe 0.61  CI95 [-0.25%, +0.81%]  WEAK
(contrast) H-13 dynamic topk  apr -0.10%  ........................................  REFUTED

Most persistent: UNI/ETH/BTC/LTC/FIL (87-88% periods funding>0). Least: BNB (18%).

STACK (50/50: level-fixed single + xvenue-maker spread, both maker):
  level-fixed single   apr +1.44%  sharpe 3.20  maxDD -0.2%
  xvenue maker         apr +0.59%  sharpe 3.93  maxDD -0.1%
  50/50 STACK          apr +1.02%  sharpe 4.28  maxDD -0.1%  CI95 [+0.53%, +1.41%]
  correlation(level, xvenue) = +0.01   (essentially uncorrelated → diversification ↑ Sharpe)
```

## Verdict
[x] **VALIDATED (best edge to date)** — but point APR < +2% gate unlevered.
Fixed name-selection lifts the carry sleeve +0.77% → +1.44% APR (Sharpe 3.20). The 50/50
stack with the uncorrelated xvenue sleeve gives **Sharpe 4.28, maxDD −0.1%** — a clean
market-neutral book. The discovery vs H-13: the carry edge is in **fixed selection**, not
dynamic chasing (which was the entire reason `single_topk` failed OOS).

## Path to champion / the +5% target — and the leverage TRAP
Tail stress over the full 730d: stack APR +3.16% (full) / +1.02% (OOS), maxDD −0.24% (full).
Naive leverage(budget/maxDD) suggests 8.4× → +27%, 21× → +66%. **This is a trap — REJECTED.**
- maxDD −0.24% is the drawdown of funding accrual + 8h-close basis in a benign window. It does
  NOT model intra-8h gap/liquidation (perp leg killed before the spot leg compensates), the rare
  basis-blowout tail (likely absent from the 2024-26 cache), funding clamps/ADL, or maker-fill
  failure. At 8–42× a single unmodeled gap is fatal. Same lesson as H-001/H-13/H-15: the metric
  measures something that isn't the real risk.
- **Honest path:** unlevered +1–3% APR is real; SANE 2–3× → ~+3–6% APR is the realistic route to
  +5% — but promotion needs (a) tick/1m data to simulate intra-period margin, (b) a basis-blowout
  stress scenario. 8h-close data cannot supply either. Do NOT size on the smoothed-funding maxDD.

## Refinement path
- Longer funding history (collect ≥18 months incl. a crash) → honest tail / leverage capacity.
- Combine level × persistence (names both high AND stable) — but guard against 6mo overfit (low K).
- Add a third uncorrelated sleeve (new-listing carry H-024 hedgeable subset) to raise Sharpe further.
