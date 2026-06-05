# H-099 — C-002 + H-042 stack correlation measurement and sizing

**Status:** proposed · 2026-06-05
**Zone:** Carry & Premia Extensions
**ID range:** H-099 (Zone 2 gen)
**SCORE:** 8.0  (edge_plausibility 9, data_feasibility 8, novelty 7) / 4 = 8.25 → 8.0

## Statement
Directly measure the realized correlation between C-002 carry book returns and H-042 liquidation-bounce returns on the overlapping time period. Then test whether a 50/50 or optimized-weight stack of C-002 + H-042 produces a Sharpe exceeding either standalone strategy. This is the primary hardening TODO listed in C-002 ("measure H-042 corr-to-carry for the stack").

## Who is forced / why can't stop
C-002 carry: leveraged longs pay funding continuously (slow drip). H-042 liquidation-bounce: forced sellers hit the market (episodic spikes). These represent two fundamentally different forced-flow regimes — structural demand-side and distress supply-side. The theoretical correlation should be near zero or weakly negative (liquidation events often occur in high-vol regimes that temporarily suppress carry efficiency). If verified, the stack is a genuine diversification.

## Falsifier
If C-002 and H-042 return series are positively correlated (r > 0.3 in OOS overlap period), the diversification benefit is limited and the stack provides minimal Sharpe lift. If H-042 never exits sub-gate (n < 100 OOS) in the correlated time window, the stack remains theoretical until H-042 matures.

## Why uncaptured
C-002 champion doc explicitly identifies this as an open TODO: "measure H-042 corr-to-carry for the stack." H-042 is currently sub-gate (n=91 at the −8% H2 threshold). This hypothesis formalizes the stack measurement as a testable procedure, not just a qualitative goal — specifically testing the correlation and stack Sharpe on whatever overlap period is available, even if H-042 n is marginal.

## Data status
data_status: HAVE (partial) — C-002 basis-return series computable from funding panel; H-042 signal requires 1m data (180d, 10 names). Overlap may be short (~6 months). Adequate for correlation measurement; marginal for full stack Sharpe test (need H-042 n to grow).

## Test (one line)
In `carry_lift.py`: compute C-002 period basis-returns and H-042 period-return series (from `h042_deep.py` output) on overlapping time window; compute Pearson r and block-bootstrap CI95; test 50/50 stack Sharpe vs each standalone via `fh.evaluate`.

## Results (2026-06-05) — `test_carry_cluster.py`
**Status: INFORMATIVE / thesis-hardening (sub-gate on n) — NOT a gate-candidate.**
- **Correlation measured: r(C-002 carry per-8h pnl, H-042 sleeve per-8h beta-adj-excess) = −0.077
  on co-active periods (n=39), −0.000 over the full TEST window.** Falsifier (r>0.3) NOT triggered —
  the two sleeves are genuinely ~uncorrelated, exactly the C-002 hardening TODO answered.
- H-042 sleeve = −8% perp drop + rising funding + tradeable, H=2, per-period mean beta-adjusted
  EXCESS forward (market-neutral; reuses h042_deep). 91 event-periods total, **39 in TEST (n≪100)**.
- Stack must be VOL-MATCHED (per-event bounce std ~1415× the carry per-8h std; raw 50/50 capital
  blend is meaningless). Vol-matched (k=0.0028): 50/50 Sh 3.93, 70/30 Sh **4.05** vs carry 3.54.
- The Sharpe lift is real but **NOT CI-separated**: stack APR CI95 [+0.70%,+1.90%] overlaps carry
  [+0.78%,+2.08%] entirely, and the sleeve is sub-gate (39 events). Per the gate rule (Sharpe
  improvement must be CI-separated), this does not promote. Banks only once H-042 n clears >100.
- Baseline reproduced exactly: C-002 TEST +1.49% APR, Sh 3.54, CI95 [+0.78%,+2.08%], n=657.
- **Verdict:** uncorrelation CONFIRMED (hardens the stack thesis); gate-candidate **N** (n sub-gate,
  Sharpe lift not CI-separated). C-002 status unchanged.
