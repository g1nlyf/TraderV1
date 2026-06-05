# H-088 — Carry in low-liquidity 8h windows (weekend / Asia-session settlement timing)

**Status:** proposed · 2026-06-05
**Zone:** Carry & Premia Extensions
**ID range:** H-088 (Zone 2 gen)
**SCORE:** 6.75  (edge_plausibility 6, data_feasibility 9, novelty 7) / 4 = 6.75 → write because near-threshold, zone 2 context

## Statement
H-043 showed no weekend or settlement-hour seasonality in FUNDING RATE levels. But this is a different question: do carry RETURNS (basis + funding) differ by 8h window within the day? Specifically, test whether the 00:00 UTC funding window (Asia off-peak) produces cleaner carry returns (lower basis volatility, same funding) than the 08:00 UTC (London open) or 16:00 UTC (US session) windows.

## Who is forced / why can't stop
Leveraged longs pay equally across all three 8h windows — the funding obligation is symmetric. But the SPOT market activity and hence basis spread management differs: during the US and London sessions, larger directional flows widen the basis transiently, creating noise in the carry return series. Asia off-peak has thinner spot flow but the same funding income.

## Falsifier
H-043 already killed the seasonality of funding RATE. If carry RETURN also has no window seasonality (perm_p > 0.05 for window selection), this is confirmed dead. The key distinction is that H-043 tested funding level, not the composite carry return (basis + funding accrual). If the distinction holds no difference, auto-kill.

## Why uncaptured
H-043 tested the raw funding rate. This tests the composite carry return (funding + basis leg), which could differ because the basis spread itself varies by session even if funding doesn't. Low-n risk: only 3 windows per day → with 730 days, each window has ~730 periods (adequate), but if the effect is weak the test will be underpowered.

## Data status
data_status: HAVE
- Timestamps available in funding panel times array — window index = (timestamp // 8h_ms) % 3

## Test (one line)
Extend `carry_lift.py`: segment the period series into the three 8h funding windows (indices 0/1/2) via times; compare basis_ret + funding per window with Kruskal-Wallis + pairwise perm test; if any window Sharpe > others perm_p < 0.05 write as conditional execution rule.
