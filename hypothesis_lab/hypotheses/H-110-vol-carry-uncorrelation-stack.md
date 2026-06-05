# H-110 — H-042 correlation to carry: measure and stack if low

**Status:** proposed · 2026-06-05
**Zone:** MICROSTRUCTURE SIGNALS — uncorrelated sleeve stacking
**ID range:** H-110 (Zone 3 generation)

## Statement
H-042 (liquidation-cascade bounce) is event-driven and market-neutral. C-002 (carry book) is
persistent and market-neutral. If the two strategies are genuinely uncorrelated in their period-
level returns, stacking them at equal weight should significantly raise Sharpe (same principle
that lifted the xvenue carry sleeve to Sh4.28 in Session 2). This hypothesis tests that correlation
empirically and computes the stacked Sharpe.

The key question: do cascade events (H-042 fires) systematically coincide with carry compression
events (C-002 underperforms)? If cascades happen in high-vol regimes and carry also suffers there,
the two are positively correlated and stacking provides less diversification than hoped.

## Structural logic
**Structural:** Carry return = per-period funding accrual (nearly fixed per period, low-vol).
H-042 return = event-specific reversion (high-vol spike). The timing of cascade events vs.
carry compression is the correlation driver. If cascades are random with respect to the carry
funding period, the stack is genuinely diversifying.

## Falsifier
corr(H-042 per-period return, C-002 per-period return) > 0.3 (carry suffers when cascades happen
→ no diversification benefit); or the stacked Sharpe < the better sleeve alone.

## Why uncaptured
H-042 was only just validated (Session 4). The correlation and stack analysis has not been run.
This is the natural "promote to sleeve 2" test.

## Data status
**HAVE** — H-042 per-period excess returns (computed in `h042_deep.py`); C-002 per-period carry
returns (computed in `funding_leads2.py` / `carry_leads.py`). Both aligned on the same 8h period
timeline for the overlapping names.

## Test (one line)
Extend `h042_deep.py`: extract per-period excess returns for the best H-042 config; merge with
C-002 per-period carry returns; compute correlation, EW stack APR/Sharpe; compare to each sleeve
alone; permutation test on the stack.

## SCORE: 8.0
(edge_plausibility=4, data_feasibility=5, novelty=3 → (4×2+5+3)/4 = 4.0 → 8.0)

## Results (2026-06-05) — `test_carry_cluster.py`
**Status: INFORMATIVE / thesis-hardening (sub-gate on n).** Co-tested with H-099/H-149.
- corr(H-042 per-period return, C-002 per-period return) = **−0.077** (co-active, n=39); −0.000 full
  TEST window. Falsifier (r>0.3) NOT triggered: cascades do NOT coincide with carry compression —
  the sleeves are genuinely diversifying.
- Vol-matched stack (sleeve scaled to carry per-period std): 70/30 Sharpe **4.05** vs carry-alone
  3.54 — a lift, but the stack APR CI95 [+0.70%,+1.90%] is NOT separated from carry [+0.78%,+2.08%],
  and H-042 carries only 39 TEST events (n≪100 gate). Second falsifier (stacked Sharpe < better
  sleeve) NOT triggered, but the lift is within noise.
- **Verdict:** uncorrelation confirmed; gate-candidate **N** until H-042 event-count matures.
