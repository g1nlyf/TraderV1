---
type: research
date: 2026-06-04
tags:
  - research
  - trader
  - experiments-ledger
ai-first: true
status: tested
---
## For future Claude
Part of the [[index|TraderV1 experiment ledger]]. This note defines the procedures and statistics used across [[hypotheses-register]]. Definitions only — what each procedure computes, not what any result means.

# Methods

## Out-of-time split (OOT)
Timeline split chronologically: first 70% = train (parameter/grid selection), last 30% = test (metrics reported once). Parameters never selected on test data.

## Permutation null
A label-free significance procedure. The statistic of interest (e.g. mean outcome of a selected subset, or a portfolio mean) is recomputed under many random re-assignments that destroy the hypothesized structure while preserving marginals: (a) shuffling forward returns across assets within each rebalance, or (b) drawing random same-size subsets to compare against a selected subset. `perm_p` = fraction of permutations whose statistic ≥ the observed statistic. Robust to overlapping-sample autocorrelation.

## Block bootstrap (CI95)
Moving-block resample of a per-period return series (block length ≈ autocorrelation horizon), 1,500–2,000 iterations; the 2.5/97.5 percentiles of the resampled means form the 95% interval.

## Triple-barrier payoff (H-03)
Forward outcome labeled by which barrier is touched first: upper +20%, lower −12%, with a fixed cost of 1.8%. `EV = win·0.20 − (1−win)·0.12 − 0.018`.

## Dollar-neutral cross-sectional weighting (H-10, H-12, H-14)
At each rebalance, demean the signal across assets; weight ∝ ±demeaned signal; normalize so Σ|w| = 1 and Σw = 0. Forward pnl = Σ w·forward return. Turnover cost = fee·Σ|wₜ − wₜ₋₁|.

## Time-series drawdown signal (H-11, H-15)
Per asset, drawdown = close / rolling-`look`-window high − 1 (≤ 0). Event fires when drawdown < threshold; optional filter on range relative to peers.

## Index / market hedge (H-11, H-15)
Beta neutralization by subtracting a market forward return from the asset forward return: equal-weight index (H-11) or SOL (H-15). Engine selftest for H-15 confirms pure-beta tokens net to ≈0 after hedge.

## Funding carry construction (H-13)
Funding paid every 8h; position side chosen at t−1 from sign(EWMA of past funding). Per-period net = side·funding − fee·|Δside| (+ price leg `spot_ret − perp_ret` in the basis-aware variant). "Long-carry-only" holds only the receiving side; "cross-venue" trades the funding spread between two perps. Top-K selects the K highest-EWMA-funding names each period.

## Impermanent loss (H-16)
Constant-product full-range LP, price ratio k = p_end/p_start: LP value ratio = √k; HODL value ratio = (1+k)/2; IL (cost) = (1+k)/2 − √k. Fee income (fraction of capital) = fee_rate·Σvolume/reserve. Engine selftest confirms IL(1)=0, IL(4)=0.5, IL(0.25)=0.125, gas monotonicity, and a price-crash case (k=0.01 → unhedged ≈ −84%).

## Funding z-score (H-14)
Per-name rolling z-score of the funding rate over a window, computed from values up to and including t (the funding settled at t is known at t); cross-sectional demeaning across names at each rebalance.

## Early-buyer reconstruction (H-18)
Pool signature pagination (newest-first) toward a target early window; Enhanced parse; trader = transaction `feePayer`; swap decoded from `tokenTransfers` + `nativeTransfers`. Features: distinct early buyers, overlap with a tracked/scored wallet set, early buy-SOL sum, buyer concentration (max share of total buy-SOL).

## Forward outcome collection (H-18)
Snapshot a new launch's early buyers from chain at discovery (pool page-1), store as pending; after the horizon, fetch forward price from OHLCV and finalize the record (including tokens with no later price). Permutation-null feature test runs once n≥30 finalized.

## Self-tests
Each engine ships gate tests run before measurement: random-input → ≈0 statistic; injected-signal → detected; cost monotonicity; no-lookahead (entry-delay or reversed-time checks); dollar-neutrality; well-behaved permutation null on random input. All engines reported passing gates on 2026-06-04. See [[tools]].
