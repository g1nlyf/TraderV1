# H-143 — Alt Funding Cross-Sectional Dispersion vs BTC Vol: Carry Quality Signal

**Status:** proposed · 2026-06-05
**Zone:** CROSS-ASSET / MACRO

## Statement
Cross-sectional funding dispersion (std across all panel names) interacts with BTC realized-vol to produce a 2D carry-quality signal. The richest carry environment is HIGH dispersion + LOW BTC-vol: names are differentiated (real crowding in select alts) but systemic risk is low. The worst is LOW dispersion + HIGH BTC-vol: funding has collapsed uniformly AND the basis blowout risk is elevated. Hypothesis: a 2D regime classifier (dispersion quartile × BTC-vol quartile) identifies the top 2 regime cells that capture most carry with minimal drawdown, and a gate on those cells improves book Sharpe vs H-100 (single-signal vol gate) or H-082 (dispersion only).

## Structural logic — who is forced
Dispersion captures when specific alts have crowded long positioning (forced payers localized). BTC vol captures when systemic risk is low enough that those forced positions unwind orderly (over time, paying funding) rather than via cascade. The interaction term is the key: both conditions must hold. Either alone misclassifies noisy-but-safe (high BTC vol with dispersion just means turbulent) or calm-but-thin (low BTC vol, low dispersion = flat funding everywhere).

## Falsifier
The interaction (dispersion × BTC vol) has no incremental predictive power for carry PnL versus either factor alone (nested model comparison, block-bootstrap).

## Why uncaptured
H-082 tested dispersion in isolation. H-100/H-140 tested BTC vol in isolation. The interaction has not been tested in any prior session. The 2D classifier is novel within this codebase.

## Data status
data_status: HAVE — BTC_8h_klines.npz (730d); full funding panel 8h 730d; both signals derivable.

## Test (one line)
Compute period-wise (cross_std_funding, btc_realized_vol) 2D quartile grid from panel data; evaluate carry book PnL by grid cell; block-bootstrap top-cell vs all-on Sharpe.

## SCORE: 8.0
(edge_plausibility 4/5, data_feasibility 5/5, novelty 4/5 → (4×2+5+4)/4 = 4.25 → ×2 = 8.5 → conservatively 8.0 given interaction-test complexity)
