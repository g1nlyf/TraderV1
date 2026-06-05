# H-140 — BTC Realized-Vol Regime as Carry On/Off Gate

**Status:** proposed · 2026-06-05
**Zone:** CROSS-ASSET / MACRO
**ID range:** H-140 (Zone 5 generation)

## Statement
Gate the C-002 carry book FULLY ON or OFF based on BTC 8h realized volatility regime (rolling 21-period, i.e. 7-day, std of BTC 8h log-returns). When BTC realized-vol > 70th percentile of its trailing 90d distribution, go to 0x carry; re-enter when vol drops below 50th percentile (hysteresis band to avoid thrashing). Hypothesis: high-BTC-vol periods are when basis blowouts and forced-unwinds cluster — switching off during these episodes should eliminate the worst carry drawdowns at modest cost in carry revenue.

## Structural logic — who is forced
In high-BTC-vol regimes, levered longs in alts face margin calls triggered by BTC drawdowns; they unwind alt perp longs, compressing or reversing funding. The carry holder (short perp / long spot basis) gets squeezed by spread widening AND by forced position exits. BTC vol is the exogenous trigger because BTC margin requirements ripple into cross-margin accounts holding alt perps. The forced seller here is the levered crypto portfolio holder, not a rational investor — creating a structural temporary carry compression that is regime-clustered.

## Falsifier
Gated carry Sharpe <= always-on Sharpe; or gated periods are statistically no different from ungated (block-bootstrap CI overlaps); or BTC vol gate is just a proxy for low-carry periods (mean funding in ON regime not significantly higher).

## Why uncaptured
Most carry implementations gate on funding level (H-081), not on the macro vol regime of BTC. The key novelty is using BTC realized-vol as a cross-asset regime signal to filter the timing dimension of the carry — a meta-signal rather than a selection signal. Partially related to H-100 (per-name vol filter) but this uses BTC as a systemic risk indicator, not name-level idiosyncratic vol.

## Data status
data_status: HAVE — BTC_8h_klines.npz cached (730d); full funding panel 8h 730d. BTC realized-vol and return regime derivable from existing data.

## Test (one line)
Load panel['btc'] from BTC_8h_klines.npz; compute rolling_21 realized-vol; gate carry PnL series (from funding_harvest.py fixed-selection book) on vol regime; compare gated vs always-on Sharpe/APR via block-bootstrap CI95.

## Score breakdown
- edge_plausibility: 4/5 (liquidation mechanism well-grounded; BTC as cross-asset trigger is real)
- data_feasibility: 5/5 (BTC 8h fully cached, 730d)
- novelty: 4/5 (BTC realized-vol as meta-gate on carry, not just name-vol, is genuinely new)
- **SCORE = (4×2 + 5 + 4)/4 = 17/4 = 4.25 → normalized = 8.5**

## Results (2026-06-05) — `test_carry_cluster.py` — NOT CI-separated (no flag)
BTC rolling-21 realized-vol gate on the fixed-selection C-002 book (1-period-lagged regime, block-
bootstrap CI95). always-on: APR +1.49% · Sh 3.54 · CI95 [+0.78%,+2.08%] · n=657. Best gated (btc-
vol<p60, 0.5× above): APR +1.39% · Sh 3.84 · CI95 [+0.76%,+1.94%]. The Sharpe rises but is **not
CI-separated**, APR is lower, and the ON-mask is ~18 autocorrelated runs (eff-n≈18 → regime-capture-
fragile, H-051 trap). BTC realized-vol as a meta-gate does not beat always-on on a defensible basis.
**Verdict: gate-candidate N.**

## SCORE: 8.5
