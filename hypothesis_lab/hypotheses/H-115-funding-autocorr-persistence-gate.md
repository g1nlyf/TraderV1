# H-115 — Funding autocorrelation persistence as carry-name selection filter

**Status:** proposed · 2026-06-05
**Zone:** MICROSTRUCTURE SIGNALS — funding autocorrelation
**ID range:** H-115 (Zone 3 generation)

## Statement
Names with high positive autocorrelation in their 8h funding rates (AR(1) > 0.5) have PERSISTENT
carry — the funding rate at t predicts the rate at t+1 reliably. Names with low or negative
autocorrelation have erratic funding — the carry is unpredictable and may reverse.
Select carry names by highest funding AR(1), not just highest funding level (H-021).
Hypothesis: AR(1)-filtered selection outperforms level-filtered selection in Sharpe.

## Structural logic
**Structural:** High-AR(1) funding = structural long demand for leverage on that name (Solana
ecosystem plays, L2 tokens with consistent TVL growth). Low/negative AR(1) = funding driven
by short-lived narratives or noise. The market cannot adjust the funding rate instantly; a
persistent high-funding name has a deeper structural base.

## Falsifier
Funding AR(1) is uncorrelated with subsequent funding persistence or carry APR; or the
AR(1)-filtered selection performs worse than level-filtered (high-AR names are already crowded,
so future carry is lower).

## Why uncaptured
H-021 selected names by funding LEVEL. H-031 weighted by funding-vol (1/std). Neither used
autocorrelation structure. AR(1) as a selection criterion is distinct from both.

## Data status
**HAVE** — 8h funding for 50 names × 730 periods. AR(1) computable via np.corrcoef(x[:-1], x[1:])
per name. Fully testable now.

## Test (one line)
Extend `carry_lift.py` or `funding_leads2.py`: compute per-name train-window AR(1) of funding;
select top-10 by AR(1); evaluate carry APR/Sharpe OOS vs top-10-by-level (H-021 baseline);
block-bootstrap CI.

## SCORE: 7.5
(edge_plausibility=4, data_feasibility=5, novelty=3 → (4×2+5+3)/4 = 4.0 → 8.0; capped at 7.5
because AR(1) filter is likely correlated with level selection — marginal new info)

## Results (2026-06-05) — `test_carry_cluster.py` — ties base (NOT CI-separated)
top-10 by train funding AR(1), same risk-parity basis-aware book, OOS:
APR **+1.58%** · Sh **3.85** · maxDD −0.12% · CI95 [+0.94%,+2.15%] · n=657
vs H-021 level base: APR +1.49% · Sh 3.54 · CI95 [+0.78%,+2.08%] · n=657.
AR(1) selection edges base on both point APR and Sharpe (and is the strongest-CI variant, lo +0.94%),
but is **NOT CI-separated** — the APR CIs overlap base almost entirely. Consistent with the score
note that AR(1) and level selection are correlated. **Verdict: ties base; promising but no flag;
gate-candidate N** (not CI-separated). Worth re-checking if H-042 stack matures and a cleaner base is
needed.
