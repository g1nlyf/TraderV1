# H-159 — Funding Rate Skewness Across Panel as Market Sentiment Asymmetry Signal

**Status:** proposed · 2026-06-05
**Zone:** CROSS-ASSET / MACRO

## Statement
Compute the cross-sectional skewness of funding rates across all panel names each period. High positive skewness means a few names have VERY high funding while the rest are moderate — the distribution is fat-tailed positive (a small number of meme-lotto names are excessively crowded). High negative skewness means a few names are deeply negative (crowded shorts). Hypothesis: periods of high positive funding skewness are the RICHEST carry environments (the far-right tail names pay enormous funding), and concentrating carry in high-skew periods improves APR meaningfully over flat-weighted always-on carry.

## Structural logic — who is forced
When funding skewness is high, the market has identified 2-3 names that are irrationally crowded by retail — these are the richest forced-payer environments. Holding only those high-skew names (or overweighting in high-skew periods) extracts the premium from the most irrationally levered cohort. The skewness collapses when the crowding unwinds — itself a signal to reduce.

## Falsifier
High-skew periods carry no more APR than low-skew periods after accounting for the fact that high-skew periods tend to also have higher mean funding (skewness is just proxying for level); or the skew-selected names underperform vs full book in OOS.

## Why uncaptured
H-082 tested cross-sectional std (dispersion). Skewness captures the asymmetric tail structure — a distinct dimension. The fat-right-tail environment is when carry is most valuable, and it's not captured by mean or std alone.

## Data status
data_status: HAVE — full funding panel 8h 730d; cross-sectional skewness (scipy.stats.skew) computable per period trivially.

## Test (one line)
Compute period-wise cross-sectional skewness of funding rates; evaluate carry PnL by skewness quartile; test high-skew-gated carry vs always-on Sharpe + APR via block-bootstrap CI95.

## SCORE: 7.5
(edge_plausibility 3.5/5, data_feasibility 5/5, novelty 3.5/5 → (3.5×2+5+3.5)/4 = 15.5/4 = 3.875 → ×2 = 7.75 → 7.5)
