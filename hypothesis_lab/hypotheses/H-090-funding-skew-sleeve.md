# H-090 — Funding skewness filter (select names with right-skewed funding distributions)

**Status:** proposed · 2026-06-05
**Zone:** Carry & Premia Extensions
**ID range:** H-090 (Zone 2 gen)
**SCORE:** 6.75  (edge_plausibility 6, data_feasibility 9, novelty 8) / 4 = 6.75

## Statement
Select carry names where the train-period funding distribution has positive skew (skewness > 0.5). Hypothesis: positively skewed funding means the name occasionally pays very high funding (extreme long crowding events), while the median stays positive. This implies the structural long imbalance is deep and occasionally intensifies — a better quality signal than just high mean.

## Who is forced / why can't stop
Positive skew in funding indicates periodic extreme forced-payer events: moments when leveraged longs become especially concentrated (post-rally, pre-unlock, narrative-driven accumulation). Even when these spikes occur rarely, the name's carry is structurally supported by a long-biased community that occasionally goes into a frenzy. Between spikes, the funding stays solidly positive (high persistence).

## Falsifier
If positively-skewed names do NOT outperform symmetric/negatively-skewed names OOS (perm_p < 0.05), skewness adds no selection value. Negatively-skewed names (occasional funding drops) might still have high mean — so this is testing whether the distribution shape matters beyond the mean.

## Why uncaptured
Level, persistence, and AR(1) (H-083) capture central tendency and autocorrelation. Skewness is a third moment that has not been used as a carry name-quality filter. Risk: positive skew may select names that are in the H-13 spike-chasing regime (though H-089 composite would help control this).

## Data status
data_status: HAVE
- Full funding time series available — skewness computable trivially (scipy.stats.skew)

## Test (one line)
Extend `carry_leads.py`: compute skewness of each name's train-period funding; select top-10 by skewness; run OOS `fh.evaluate` + block-bootstrap CI95; compare vs level-selected baseline.
