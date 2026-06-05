# H-091 — Carry basis-vol de-risk rule (dynamic leverage scaling by realized basis vol)

**Status:** proposed · 2026-06-05
**Zone:** Carry & Premia Extensions
**ID range:** H-091 (Zone 2 gen)
**SCORE:** 8.0  (edge_plausibility 8, data_feasibility 9, novelty 8) / 4 = 8.25 → 8.0

## Statement
This is the explicit hardening of C-002 Risk Rule 1 ("de-risk to ≤2× if realized basis-vol spikes"). Operationalize it as a quantitative rule: compute rolling 30-period realized vol of the book's aggregate basis-return series. When this vol exceeds the 80th percentile of its train-period distribution, scale book leverage to 50% of baseline. When it exceeds the 95th percentile, scale to 25%. Hypothesis: this simple vol-of-vol scaling avoids the tail events (basis blowouts) identified as the primary risk in C-002.

## Who is forced / why can't stop
When basis vol spikes, the book's delta-neutrality is under stress (the two legs temporarily diverge beyond normal). Forced payers (leveraged longs) continue paying, but the gap risk rises. The de-risk rule cuts exposure precisely when the unmodeled basis-blowout risk (C-002's caveat) is highest — converting the qualitative champion rule into a tested quantitative gate.

## Falsifier
If the de-risked book does not have lower maxDD AND statistically comparable (or better) Sharpe vs fixed-weight book (one-sided CI95, perm_p < 0.10 acceptable given it's a risk rule not an alpha generator), the operationalized rule adds no value and is just complexity. Also tested: does APR drop too much during de-risk periods to be worth it?

## Why uncaptured
C-002 lists "de-risk to ≤2× if realized basis-vol spikes" as a qualitative operating rule. It has not been backtested as a quantitative mechanism. This is the direct implementation of the hardening TODO: converting the qualitative risk rule into a tested, parametric gate before live sizing.

## Data status
data_status: HAVE
- basis_ret 8h series already computed in carry pipeline
- Rolling percentile of portfolio basis-vol straightforward

## Test (one line)
Extend `carry_lift.py`: compute rolling 30p realized basis-vol; apply leverage scalar (1.0 / 0.5 / 0.25) based on (< 80th / 80-95th / > 95th pct) quantile; compare maxDD, Sharpe, APR vs baseline at 3× fixed leverage via `fh.evaluate`.

## Results (2026-06-05) — `test_carry_cluster.py` — REFUTED (no value-add)
Rolling-30p book basis-vol → leverage scalar (1.0/0.5/0.25 at train q80/q95), applied with 1-period
lag (no lookahead); de-risked 38% of TEST periods.
- fixed (1.0×):  APR +1.49% · Sh 3.54 · maxDD **−0.19%** · CI95 [+0.78%,+2.08%] · n=657
- basis-vol scaled: APR +1.16% · Sh **3.21** · maxDD −0.17% · CI95 [+0.53%,+1.64%] · n=657
Falsifier triggered: the de-risked book has **lower** Sharpe AND lower APR, with maxDD essentially
unchanged (−0.19%→−0.17%). The book's drawdown is already trivially small in-sample, so there is no
tail to cut here — the rule only sheds return. **Verdict: refuted as an alpha/Sharpe lever; retains
value ONLY as an un-sampled-tail insurance rule (its original C-002 framing), not a backtested edge.
Gate-candidate N.**
