# H-092 — BTC vol-regime conditional carry (on/off binary regime switch)

**Status:** proposed · 2026-06-05
**Zone:** Carry & Premia Extensions
**ID range:** H-092 (Zone 2 gen)
**SCORE:** 7.5  (edge_plausibility 8, data_feasibility 9, novelty 6) / 4 = 7.75 → 7.5

## Statement
Divide the 730-day history into BTC-high-vol and BTC-low-vol regimes (binary, based on BTC 30-period realized vol vs its rolling median). Measure carry APR and Sharpe separately in each regime. Hypothesis: carry in low-vol BTC regime is substantially better than carry in high-vol regime — both because basis risk is lower AND because funding tends to be more stable (persistent longs rather than fearful/greedy reactors).

## Who is forced / why can't stop
In BTC-low-vol regimes, long holders are structurally committed: they have made a calculated decision to hold with low expected volatility. These are the "quality" forced payers — they are not reactively entering/exiting based on price swings. In high-vol regimes, leveraged longs are in distress; some are liquidated (disrupting funding), basis spreads widen, and maker fills may be delayed.

## Falsifier
If carry APR/Sharpe in high-vol BTC regime is NOT statistically lower than low-vol regime (perm_p < 0.05 for the regime difference), the binary on/off gate provides no value. The important test: does running carry ONLY in low-vol regime lift Sharpe meaningfully vs always-on (H-080 tests a continuous version; this is a binary on/off)?

## Why uncaptured
H-080 tests a continuous vol percentile gate. This tests a cleaner binary regime classification — which is more operationally legible and easier to implement as a live trading rule. If H-080 and H-092 both validate, H-080 is the continuous version and H-092 confirms the binary operating rule for C-002.

## Data status
data_status: HAVE
- BTC 8h closes 730d → realized vol and regime classification trivially computable
- Funding panel aligned on same 8h grid

## Test (one line)
Extend `carry_lift.py`: compute rolling 30p BTC realized vol; define regime = 1 if vol < rolling 183p median else 0; compute carry series separately in each regime; compare Sharpe/APR/n via `fh.evaluate` with block-bootstrap CI95 per regime subset.

## Results (2026-06-05) — `test_carry_cluster.py` — NOT CI-separated (no flag)
Binary BTC-vol regime gate (ON when prev-period rolling-21 BTC-vol < train percentile; tested p50 &
p60, OFF and 0.5× above). Best = btc-vol<p60 0.5×-above: APR +1.39% · Sh 3.84 vs always-on +1.49% /
3.54. The falsifier holds: running carry only in low-vol does NOT meaningfully lift Sharpe — the
3.54→3.84 move is within CI (APR CI95 [+0.76,+1.94] overlaps [+0.78,+2.08]) and APR falls. The ON
mask is **~18 autocorrelated runs** in TEST (eff-n≈18) → any apparent gain is regime-capture-fragile
(H-051). **Verdict: binary gate provides no value; gate-candidate N.**
