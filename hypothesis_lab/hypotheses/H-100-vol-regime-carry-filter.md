# H-100 — Vol-regime carry filter: enter low-vol, exit high-vol

**Status:** proposed · 2026-06-05
**Zone:** MICROSTRUCTURE SIGNALS — realized-vol regime switching
**ID range:** H-100 (Zone 3 generation)

## Statement
The funding-carry book (C-002) collects carry continuously, but during high-realized-vol regimes
the basis widens unpredictably and the book's mark-to-market suffers noise. Gate: only hold carry
when the 8h realized-vol (rolling 3-period std of 8h perp returns) is below its 60th percentile;
exit (or reduce to 0.5x) when vol is elevated. Re-enter on compression.

## Structural logic
**Who is forced / structural inefficiency:** In low-vol regimes, the carry premium is stable
and competitors' leverage is maxed out (they entered in the same regime). In high-vol, levered
carry traders are squeezed by margin calls, generating the very basis-blowout tail that kills
carry. The gating logic exploits the fact that carry APR (funding rate) does NOT adjust quickly
to intraday vol spikes — so the premium-per-unit-risk is highest in low-vol.

## Falsifier
The vol-gated carry APR is no better than always-on; or the gate has negative value (misses
good carry during vol that doesn't blow out); or the gated Sharpe < ungated.

## Why uncaptured
Vol-gated carry is trivially conceptualized but rarely backtested honestly (requires realized
1m vol, not just VIX-style measure). Most carry desks size by funding level, not by realized-vol
regime — partially because the data is annoyingly granular.

## Data status
**HAVE** — 8h perp close prices for 50 names (730d): can compute rolling realized-vol from
8h returns. The 1m data for 10 names gives intraday vol but 8h-frequency gating is sufficient
for a first test.

## Test (one line)
Extend `funding_leads2.py`: compute rolling 3-period realized-vol of 8h perp returns; restrict
carry evaluation to periods where that vol < 60th percentile; compare gated vs always-on APR/Sharpe.

## Score breakdown
- edge_plausibility: 4/5 (well-grounded, two-sided logic on forced/structural)
- data_feasibility: 5/5 (8h closes fully available)
- novelty: 3/5 (conceptually known but never implemented in this codebase)
- **SCORE = (4×2 + 5 + 3)/4 = 16/4 = 4.0 → raw scale 4/5 = 8.0/10 → normalized = 8.0**

## Results (2026-06-05) — `test_carry_cluster.py` — NOT CI-separated (no flag)
Vol-regime carry filter tested via the BTC realized-vol gate on the C-002 book (p50/p60 percentile,
1-period lag). Best variant (btc-vol<p60, 0.5× above): APR +1.39% · Sh 3.84 vs always-on +1.49% /
3.54. Falsifier triggered: vol-gated carry is **no better** than always-on once CI is respected
(Sharpe lift not CI-separated, APR lower), and the gate rides ~18 autocorrelated ON-runs
(regime-capture risk). **Verdict: gate-candidate N.** (See H-080/H-092/H-116/H-140 — same null.)

## SCORE: 8.0
