# H-146 — BTC Vol Regime Predicts Next-Period Alt Funding Richness (Predictive, Not Gate)

**Status:** proposed · 2026-06-05
**Zone:** CROSS-ASSET / MACRO

## Statement
Distinct from H-140 (contemporaneous gate), this tests whether LAGGED BTC realized-vol predicts the NEXT period's alt funding richness. Mechanism: a BTC vol spike causes levered longs to reduce alt positions (funding drops), but survivors who DIDN'T get liquidated re-establish leverage 1-3 periods later (8-24h later) — often more aggressively (they bought the dip). Hypothesis: alt funding at t+1 to t+3 is positively correlated with BTC realized-vol at t (not contemporaneous, but lagged 1-3 periods), creating a timing signal for when to hold max-size carry.

## Structural logic — who is forced
Post-liquidation-cascade, the market has shed the weakest hands. The survivors re-lever into the cleaner market. This re-levering is systematic: dip-buyers who were sidelined during the cascade deploy capital when volatility subsides — creating a predictable cycle of funding compression then recovery. The funding recovery (which benefits carry) is predictable from the prior vol spike.

## Falsifier
Lagged BTC vol has zero cross-correlation with next-period mean alt funding (CCF test, permutation null across time shuffle); or the predictive power evaporates after accounting for same-period funding level.

## Why uncaptured
The predictive (not contemporaneous) relationship between BTC vol and future alt funding has not been tested. H-140 uses contemporaneous vol as a gate. The lagged version is a fundamentally different mechanism — survivor leverage recovery — that could be additive.

## Data status
data_status: HAVE — BTC_8h_klines.npz; full funding panel 8h 730d. Cross-correlation function testable directly.

## Test (one line)
Compute cross-correlation function CCF(BTC_realized_vol_t, mean_alt_funding_{t+k}) for k=1..9 from panel data; permutation-test the peak lag coefficient for significance.

## SCORE: 7.0
(edge_plausibility 3/5, data_feasibility 5/5, novelty 4/5 → (3×2+5+4)/4 = 15/4 = 3.75 → ×2 = 7.5 → 7.0 conservatively for speculative mechanism)
