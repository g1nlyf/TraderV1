# Tournament Report — 2026-06-06T23:44:04.281093+00:00

Walk-forward, TEST-ONLY gate (Sprint-9 corrected). Runtime 102s. Promotion = EV>+2% AND perm<0.05 AND CI95>0 AND n>100.

| dataset | candidate | test n | fired% | EV | base | edge | perm | CI95 | verdict |
|---|---|---|---|---|---|---|---|---|---|
| cluster_events | H171b_token+wq_gbm | 205 | 30% | -2.07% | -17.96% | +15.89% | 0.000 | [-7.03%,+2.14%] | FAIL |
| cluster_events | token+wallet_gbm_top30 | 205 | 30% | -2.42% | -17.96% | +15.54% | 0.000 | [-7.21%,+1.69%] | FAIL |
| cluster_events | H171b_token+cohesion_gbm | 205 | 30% | -2.57% | -17.96% | +15.39% | 0.000 | [-7.41%,+1.52%] | FAIL |
| cluster_events | token_gbm_top30 | 205 | 30% | -4.20% | -17.96% | +13.76% | 0.000 | [-9.32%,+0.63%] | FAIL |
| cluster_events | wallet_only_gbm_top30 | 205 | 30% | -8.26% | -17.96% | +9.70% | 0.000 | [-13.03%,-4.11%] | FAIL |
| cluster_events | clu_cohesion_top30 | 489 | 72% | -15.93% | -17.96% | +2.03% | 0.017 | [-19.13%,-13.00%] | FAIL |
| cluster_events | random_top30 | 184 | 27% | -25.06% | -17.96% | -7.11% | 0.997 | [-31.67%,-18.87%] | FAIL |
| lifecycle | H183_neutral_post_distrib | 2 | 0% | +5.57% | -13.26% | +18.83% | 0.181 | [+5.57%,+6.11%] | FAIL |
| lifecycle | neutral_only | 203 | 33% | -5.93% | -13.26% | +7.34% | 0.002 | [-9.99%,-1.34%] | FAIL |
| lifecycle | token+state_gbm_top30 | 186 | 30% | -8.07% | -13.26% | +5.19% | 0.030 | [-13.73%,-2.19%] | FAIL |
| lifecycle | H184_rug_skip_token | 431 | 70% | -8.54% | -13.26% | +4.73% | 0.000 | [-12.41%,-4.47%] | FAIL |
| lifecycle | token_gbm_top30 | 186 | 30% | -8.60% | -13.26% | +4.66% | 0.044 | [-14.29%,-2.87%] | FAIL |
| lifecycle | H183_buy_distribution | 34 | 6% | -9.84% | -13.26% | +3.42% | 0.322 | [-24.75%,-1.02%] | FAIL |
| lifecycle | H185_into_distribution | 6 | 1% | -10.05% | -13.26% | +3.21% | 0.431 | [-58.50%,-7.79%] | FAIL |
| lifecycle | avoid_rug_distrib_decay | 284 | 46% | -10.96% | -13.26% | +2.30% | 0.117 | [-15.18%,-6.28%] | FAIL |
| lifecycle | feat_prior_ret_top30 | 186 | 30% | -17.09% | -13.26% | -3.83% | 0.922 | [-22.83%,-9.83%] | FAIL |
| lifecycle | random_top30 | 172 | 28% | -18.03% | -13.26% | -4.77% | 0.952 | [-25.57%,-10.12%] | FAIL |
| lifecycle | H183_buy_acceleration | 13 | 2% | -22.37% | -13.26% | -9.10% | 0.771 | [-28.61%,-11.27%] | FAIL |

**Promoted this run: 0** (none — all fail the gate)

Interpretation: every selection on May-14 sits on a negative base (down-regime). A candidate that beats base+token-only+random but stays EV<0 is a SHADOW de-risk/ranking signal, not alpha. Promotion to alpha needs a non-dump regime (cross-day data, H-163). See HYPOTHESIS_QUEUE.md.