# H-002 — Funding Carry: Why Does the Tradeable Universe Kill the Edge?

**Status:** proposed
**Priority:** P1
**Asset universe:** Binance + Bybit perpetual futures
**Created:** 2026-06-04

## Statement
H-13 showed funding carry (maker, top-10 by funding rate): TEST +9.0% APR, Sharpe 11.3, CI95 [+6.1%, +12.5%]. But when filtered to "tradeable" universe (real spot + ≥90% history coverage, 24 names): TEST +0.7% APR, Sharpe 2.14. The edge collapses by 8.3% APR when applying realistic constraints. This hypothesis identifies EXACTLY which constraint kills the edge and finds a path to capture the raw edge in practice.

## Rationale ("million dollar idea")
+9% APR with Sharpe 11.3 is a real edge — hedge funds would kill for it. The "tradeable" constraint is probably over-conservative or measuring the wrong thing. The gap between theoretical and tradeable is where fortunes are made: everyone sees the raw edge, no one figures out the execution. If the constraint is "real spot exists" — maybe you don't need spot. If it's "90% history" — maybe 60% is enough. If it's "token category" — the tokenized equities (NVDA, MSTR) that show up in top-10 have different dynamics.

## Data required
- `finetune/data/funding_cache/` — all funding rate data
- Binance spot availability list for all 44+ assets
- History coverage % per asset
- Identity of top-10 by funding rate (from H-13 results)

## Test method
1. Identify the exact 24 "tradeable" assets vs 44 full universe — which 20 are excluded and why?
2. Run the top-10 strategy on: (a) all 44, (b) top-10 excluding tokenized equity/commodity perps, (c) top-10 from "alt mid-cap" subset
3. Test execution: what is the actual maker fee fill rate for high-funding assets? (Maker orders may not fill if spread is too tight.)
4. Test with taker fees instead — what APR survives taker execution?
5. Find the minimum history coverage % where the edge survives

## Parameters
- Universe: full 44 / tradeable 24 / no-tokenized-equity / mid-cap-alt
- Fee tier: maker 1.0 bps / taker 5.5 bps
- History coverage threshold: 60%, 70%, 80%, 90%
- Top-K: 5, 10, 15, 20

## Results
```
[To be filled]
```

## Verdict
[ ] PASS  [ ] FAIL  [ ] INCONCLUSIVE

## Refinement path
**If tokenized equities inflate the raw edge:**
→ Exclude NVDA/MSTR/XAG/XAU and retest — does edge survive in pure crypto?

**If maker fill rate is the real constraint:**
→ H-009: Adaptive maker/taker — use maker during low-volume, taker when funding is extreme

**If history coverage filter is too strict:**
→ Lower threshold to 60% — test if edge remains robust
