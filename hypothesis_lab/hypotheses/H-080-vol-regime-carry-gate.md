# H-080 — Vol-regime carry gate (carry only in low-realized-vol windows)

**Status:** proposed · 2026-06-05
**Zone:** Carry & Premia Extensions
**ID range:** H-080 (Zone 2 gen)
**SCORE:** 7.5  (edge_plausibility 8, data_feasibility 9, novelty 6) / 4 = 7.75 → rounded 7.5

## Statement
Run the C-002 carry book only when BTC 30-period (10-day) realized vol is below the rolling 60th percentile of its own history. Hypothesis: funding harvesting is cleaner when spot vol is suppressed — the basis stays tight, maker fills are routine, and leveraged longs pay without unusual gap risk.

## Who is forced / why can't stop
Leveraged long holders pay funding continuously regardless of vol regime. Their structural demand is constant — they hold the perp to maintain directional exposure without tying up spot capital. In low-vol regimes, this flow is cleaner: fewer gap moves, less ADL risk, and fewer forced unwinds that could momentarily distort the basis.

## Falsifier
If carry APR in low-vol windows does NOT statistically exceed carry APR in high-vol windows (block-bootstrap perm_p < 0.05), the gate adds no value. If the gate simply removes exposure and lowers APR without lifting Sharpe, it's not worth the complexity.

## Why uncaptured
C-002 runs all-weather. The question of whether funding-harvest reward-to-risk is vol-conditional has not been tested on the current panel. Risk: low-vol windows may simply coincide with lower funding (less demand), netting to no improvement. But if Sharpe improves even at lower APR, the gate has portfolio value.

## Data status
data_status: HAVE
- BTC 8h closes 730d → realized vol computable on 8h windows
- Funding panel 8h 730d, 50 names
- Both aligned — no new data needed

## Test (one line)
Extend `carry_leads.py`: add `btc_rv_gate(panel, pct_threshold=60)` mask on the period series; compare gated vs ungated Sharpe and APR via `fh.evaluate` + block-bootstrap CI95.

## Results (2026-06-05) — `test_carry_cluster.py` — NOT CI-separated (no flag)
BTC rolling-21 realized-vol percentile gate on the C-002 book (decision lagged 1 period, no
lookahead). always-on baseline: APR +1.49% · Sh 3.54 · CI95 [+0.78%,+2.08%] · n=657.
- btc-vol<p50 (off above): APR +0.83% · Sh 2.79 · CI95 [+0.40%,+1.36%] — worse.
- btc-vol<p60 (off above): APR +1.29% · Sh 3.79 · CI95 [+0.68%,+1.83%].
- btc-vol<p60 (0.5× above): APR +1.39% · Sh **3.84** · CI95 [+0.76%,+1.94%].
The p60 variants nudge point-Sharpe up but **fail the falsifier's spirit**: the gate only *removes*
exposure and *lowers* APR (+1.49%→+1.39%); the Sharpe lift (3.54→3.84) is NOT CI-separated (APR CIs
overlap fully) and rests on **eff-n≈18 autocorrelated ON-runs** — a regime-capture shape (H-051
trap). **Verdict: gate adds no separable value; gate-candidate N.**
