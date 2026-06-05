# H-145 — Cross-Name Funding Beta to BTC 8h Returns: Carry Selection Signal

**Status:** proposed · 2026-06-05
**Zone:** CROSS-ASSET / MACRO

## Statement
Each alt's funding rate has a beta to contemporaneous BTC 8h returns: when BTC rises sharply, alts with high funding-beta see their funding spike (retail piles in via leverage). Compute rolling 60-period beta of each name's funding rate to BTC returns. Names with LOW funding-beta are "carry-stable": their funding is structurally driven by their own crowding dynamics, not by BTC momentum flows. Hypothesis: selecting the carry book from low-funding-beta names produces more stable, less cyclically-vulnerable carry with higher Sharpe than the current fixed-selection (H-021).

## Structural logic — who is forced
High funding-beta names have funding driven by BTC-momentum FOMO traders who lever up when BTC pumps — these are flighty, non-captive payers. Low funding-beta names have captive forced-payers who are structurally long for idiosyncratic reasons (e.g., yield farmers, protocol participants, or spot-holders hedging via perps). The low-beta carry is more defensible because it doesn't collapse when BTC momentum reverses.

## Falsifier
Low-funding-beta name selection has no better Sharpe or APR than random fixed selection (permutation test); or low-beta names have lower mean funding (so the premium is just lower), not better risk-adjusted.

## Why uncaptured
H-021 (fixed selection) used level funding to pick names. The beta-to-BTC dimension as a stability filter is new. Standard carry selection uses level or z-score, not beta-corrected stability. No prior session tested beta as a selection criterion.

## Data status
data_status: HAVE — BTC_8h_klines.npz (730d); full perp funding panel 8h 730d for all ~50 names. Rolling OLS beta computable from panel data.

## Test (one line)
Compute rolling-60 OLS beta(funding_i ~ BTC_return) per name; select bottom-tercile beta names each rebalance period; compare fixed-beta-filtered carry Sharpe/APR vs H-021 baseline via block-bootstrap.

## SCORE: 7.5
(edge_plausibility 3.5/5, data_feasibility 5/5, novelty 3.5/5 → 7.5)

## Results (2026-06-05) — `test_carry_cluster.py` — ties base (NOT CI-separated)
Selected top-10 by LOWEST |beta(name carry-pnl ~ BTC 8h return)| on train, same risk-parity
basis-aware book, OOS:
APR +1.50% · Sh **3.97** (highest Sharpe of all selection variants) · maxDD −0.17% · CI95
[+0.89%,+2.06%] · n=657, vs H-021 level base APR +1.49% / Sh 3.54 / CI95 [+0.78%,+2.08%].
Low-BTC-beta selection gives the best point Sharpe but **identical APR** and is **NOT CI-separated**
from base (APR CIs overlap fully) — i.e. it trims BTC-cyclical variance without adding return,
matching the falsifier's "premium is just lower-vol, not higher risk-adjusted-edge" branch within
noise. **Verdict: ties base; gate-candidate N.** A defensible Sharpe-stabilizer if ever combined,
but not a standalone edge.
