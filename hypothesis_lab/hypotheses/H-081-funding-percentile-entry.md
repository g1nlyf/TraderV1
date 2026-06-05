# H-081 — Funding-percentile entry (enter carry only when funding is in top X% of own history)

**Status:** proposed · 2026-06-05
**Zone:** Carry & Premia Extensions
**ID range:** H-081 (Zone 2 gen)
**SCORE:** 7.25  (edge_plausibility 7, data_feasibility 9, novelty 7) / 4 = 7.25

## Statement
For each carry name in C-002 book, enter (or overweight) only when its current funding is above the Nth percentile of its own rolling 180-day funding history. Exit (or underweight) when it drops below the (N-20)th percentile. Hypothesis: carry at historically-high own-funding has better reward-to-risk than carry at average funding — you're buying when the structural crowding is at its peak.

## Who is forced / why can't stop
The forced buyers are leveraged longs who have committed to their position. When funding is at the 90th percentile of its own history, the imbalance is especially acute — more longs are trapped, unwilling to unwind because of profit/loss or portfolio commitment. This is the "pain of the trapped long" at its maximum.

## Falsifier
If OOS Sharpe from the percentile-filtered subset does NOT exceed the always-in Sharpe (with perm_p < 0.05), the filter is noise. Also falsified if the filter leaves fewer than 100 OOS active periods (n insufficient).

## Why uncaptured
C-002 uses a fixed-name selection by mean level (train set), but does NOT time entry within those names by own-history percentile. The funding level across names was tested (H-049 carry-to-vol), but intra-name historical percentile is new. Risk: high own-percentile funding may precede mean-reversion (the spike that H-13 dynamic chasing tried and failed to capture) — but the fixed-name setup avoids that trap since we're already committed to the book; this is an intra-name sizing question.

## Data status
data_status: HAVE
- Funding panel 8h 730d — rolling percentile trivially computable
- All 10 C-002 names available

## Test (one line)
Extend `carry_lift.py`: for each period, compute each name's rolling 180d funding percentile; weight names proportionally to I(percentile > N) and compare Sharpe vs equal-weight baseline via `fh.evaluate`.
