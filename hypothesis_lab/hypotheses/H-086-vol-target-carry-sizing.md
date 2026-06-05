# H-086 — Carry with vol-target leverage sizing

**Status:** proposed · 2026-06-05
**Zone:** Carry & Premia Extensions
**ID range:** H-086 (Zone 2 gen)
**SCORE:** 7.5  (edge_plausibility 8, data_feasibility 9, novelty 6) / 4 = 7.75 → 7.5

## Statement
Instead of fixed leverage (C-002 uses 3-4×), dynamically scale the entire carry book's gross exposure to target a constant annualized portfolio volatility (e.g., 2% annualized, measured on the 8h basis-return series). When realized basis-vol is low, lever up; when it spikes, delever. Hypothesis: vol-targeting produces a better risk-adjusted series by cutting exposure precisely when the basis-blowout tail risk rises, which is the dominant risk identified in C-002's caveat list.

## Who is forced / why can't stop
Forced payers (leveraged longs) don't change their payment obligation when basis-vol rises — so funding income is relatively stable while risk rises. This creates a dynamically improving Sharpe in low-vol windows and a natural de-risk in high-vol windows, which is exactly the tail risk management C-002 needs (identified as a hardening TODO in the champion doc).

## Falsifier
If vol-targeted book Sharpe is not statistically better than fixed-leverage baseline (perm_p < 0.05, block-bootstrap CI95), the dynamic sizing adds only complexity. Also falsified if vol-targeting is purely a Sharpe artifact from lower-vol periods having higher Sharpe inherently (regime selection bias).

## Why uncaptured
C-002 risk-parity (H-031) sizes names relative to each other by individual funding-vol. Vol-targeting is a BOOK-LEVEL lever scalar — it rescales total gross exposure based on realized basis vol of the aggregate portfolio. These two operate at different levels and are additive. Vol-targeting is the explicit hardening mechanism for C-002's "de-risk if basis-vol spikes" rule (Rule 1 in the champion doc).

## Data status
data_status: HAVE
- 8h basis returns (funding + spot_ret − perp_ret) already computed in carry pipeline
- Rolling realized vol straightforward to compute

## Test (one line)
Extend `carry_lift.py`: compute rolling 30-period realized portfolio vol on basis-return series; scale each period's position by (vol_target / realized_vol); compare Sharpe/APR/maxDD vs fixed-weight baseline via `fh.evaluate` + block-bootstrap CI95.
