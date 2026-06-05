# H-087 — Basis-compression timing entry (enter after basis spike, not at arbitrary time)

**Status:** proposed · 2026-06-05
**Zone:** Carry & Premia Extensions
**ID range:** H-087 (Zone 2 gen)
**SCORE:** 7.0  (edge_plausibility 7, data_feasibility 8, novelty 7) / 4 = 7.0

## Statement
Time carry ENTRY per-name by detecting when the spot-perp basis has just experienced an elevated spread (basis > rolling 80th percentile) followed by compression. Hypothesis: entering after a basis spike resolves (when the spread has just tightened) avoids the period where the basis is widening — which is the dangerous window for basis-blowout risk — and captures the subsequent stable carry.

## Who is forced / why can't stop
After a basis spike, the forced payers are still paying (their position hasn't changed), but the abnormal basis spread has partially resolved. Entering at this point captures the ongoing funding flow with a more favorable initial spread — you don't enter when the basis widening could continue to hurt the spot-vs-perp leg value.

## Falsifier
If carry APR for entries made after basis compression does NOT exceed entries made at arbitrary times (all-in baseline), the timing adds no value. Also falsified if basis spike frequency is too low (n < 100 OOS entry events), making the test statistically underpowered.

## Why uncaptured
C-002 uses EWMA-sign entry, which is a funding momentum signal. Basis spread level (spot minus perp) as a timing signal for entry is unexplored in the current infrastructure. The basis_ret field is already computed in the carry pipeline but has not been used as an ENTRY timing signal — only as a cost/quality measure.

## Data status
data_status: HAVE
- basis_ret 8h 730d computed in funding panel
- Can compute rolling percentile of basis spread

## Test (one line)
Extend `carry_leads.py`: compute rolling 90d percentile of abs(basis_spread) per name; restrict entry events to periods where prior-period spread was > 80th pct AND current-period spread < prior; compare gated vs ungated Sharpe via `fh.evaluate`.
