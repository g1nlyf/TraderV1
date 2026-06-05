# H-066 — Post-vol-spike forced deleveraging → funding decay carry

**Status:** proposed
**Zone:** FORCED-FLOW PREMIA
**Created:** 2026-06-05 (Session 5)

## Statement
After a large realized-vol spike (8h price move >+/−8% in absolute value, market-wide — not a single
name), leveraged participants deleverage across the book. Funding rates compress or flip in the 1–3
periods following the vol event as leveraged longs unwind. Names that had high funding before the vol
spike now offer elevated carry-per-vol after deleveraging reduces open interest, creating a transient
carry opportunity beyond the carry book's static selection. Enter carry (long spot/short perp) on the
highest-funding names immediately after the vol spike. The forced party has already exited — the
opportunity is in the aftermath vacuum.

## Quality filter
- **Who is FORCED & cannot stop:** leveraged longs across the market are forced to deleverage by margin
  calls or risk-limit hits when realized vol spikes. They cannot choose their timing — margin calls
  are immediate. Their exit creates an OI vacuum that elevates relative funding for remaining names.
- **Falsifier:** funding rates after vol spikes do not systematically differ from baseline funding
  (the carry book's static selection already captures this). OR the forward carry of the top-funding
  names in the post-spike window is no better than random periods.
- **Why funds can't capture:** requires intra-event monitoring, fast leg execution post-spike
  (entering carry when everyone is deleveraging), and vol-spike event timing is unpredictable.
- **data_status:** HAVE — 8h perp + spot price + funding 730d. Flag periods where cross-sectional
  median |return| > 5% as vol-spike periods; measure funding of top-5 names in next 3 periods.

## Test method
Extend `scripts/h042_deep.py` or `funding_leads2.py`: define market vol-spike as median |8h return|
across all names > 5th percentile of the distribution. Flag the following 1–3 periods; compute carry
yield for top-funding names. Compare carry-yield in post-spike vs non-spike periods. Apply period-
cluster eff-n, cost model.

## data_status
HAVE — existing 8h price + funding cache. Expected n: 50–150 vol-spike events in 730d.

## Score
7.25 / 10
(edge_plausibility 7 × 2 + data_feasibility 9 + novelty 6) / 4

## Status
proposed
