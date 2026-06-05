# H-094 — Carry universe expansion: top-20 vs top-10 name count sensitivity

**Status:** proposed · 2026-06-05
**Zone:** Carry & Premia Extensions
**ID range:** H-094 (Zone 2 gen)
**SCORE:** 6.75  (edge_plausibility 7, data_feasibility 9, novelty 5) / 4 = 6.75

## Statement
Test whether the C-002 book should hold 10, 15, or 20 names. The current champion fixed at 10 by convention (H-021). Hypothesis: the marginal 11th–20th names (by funding level) still carry positive funding after costs, and adding them improves Sharpe by diversification without materially reducing APR.

## Who is forced / why can't stop
Names 11–20 by funding level are still structurally positive carry — the forced-payer dynamic doesn't stop at rank 10. The question is capacity: each additional name adds diversification benefit but may dilute the APR by including weaker carry sources.

## Falsifier
If top-20 Sharpe is NOT statistically better than top-10 (perm_p < 0.05), more names add noise not diversification — and the operational complexity of 20 pairs is not justified. Also test if top-5 concentrates APR better (concentration vs diversification frontier).

## Why uncaptured
H-021 tested K=10 vs K=all-29 and found K=10 optimal (K=all dilutes). The optimal K between 10 and 29 was not swept — only 10 and all. Marginal-name analysis for K=5,10,15,20 is the missing curve.

## Data status
data_status: HAVE
- Full 29-name tradeable panel already available in `carry_leads.py`

## Test (one line)
Extend `carry_leads.py`: loop K in [5, 10, 15, 20]; for each, select top-K by funding level (train); compute OOS APR/Sharpe/maxDD via `fh.evaluate`; plot and report the K vs Sharpe frontier.
