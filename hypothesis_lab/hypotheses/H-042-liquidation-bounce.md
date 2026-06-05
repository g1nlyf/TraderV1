# H-042 — Liquidation-cascade bounce (market-neutral)

**Status:** tested · 2026-06-05 (Session 4) · **REAL but sub-gate — first non-carry edge to survive full trap-hardening**
**Asset universe:** tradeable Binance alt perps (49 names with perp 8h price + spot leg)
**Created:** 2026-06-05

## Statement
After a forced-liquidation cascade (proxy: a perp prints < −5/−8/−10% in one 8h period while
funding is *rising* — dip-buyers leveraging in), the name bounces **more than the market** over the
next 1–2 periods. Forced, non-adaptive sell flow overshoots; whoever supplies liquidity into it is
paid the reversion. Trade it **market-neutral** (long the dropped name, short the index) so the edge
is the per-name overshoot, not market recovery.

## Quality filter
- **Who loses & can't stop:** liquidated leverage — margin-called longs are *forced* sellers, price-
  insensitive, cannot wait. The structural counterparty that can't adapt.
- **Falsifier:** the forward bounce disappears once the market move is removed (it was just beta), OR
  collapses under period-clustering (eff-n), OR is a tail-driven lottery (median<0), OR < cost.
- **Why uncaptured:** sparse events, requires fast execution into a crash, market-neutral hedging,
  small per-event size — operationally heavy for retail; too small-capacity for large funds.
- **Testable now:** yes — perp 8h price cache + funding. (1m would sharpen entry; queued.)

## Results (scripts/h042_deep.py — trap-hardened)
Shallow test gave +0.68% fwd, perm_p 0.0001 — then hardened against the H-15/H-001 traps:
market-demean (remove recovery beta), per-name beta-adjust, collapse to PERIOD-level (honest eff-n),
median/hit (lottery), net of taker cost (11bps RT).
```
 thr  H  events periods  raw_fwd  excess  exc_net  betaAdj  bA_cT  median  hit  clustT  permP
 -5%  1     892     326   +0.69%  +0.14%   +0.03%   +0.11%  +1.67  -0.10%  48%   +1.67  0.0002
 -5%  2     887     325   +0.88%  +0.33%   +0.22%   +0.31%  +2.49  -0.19%  46%   +2.47  0.0002
 -8%  1     195      92   +2.32%  +0.66%   +0.55%   +0.62%  +1.52  +0.24%  54%   +1.58  0.0002
 -8%  2     191      91   +3.44%  +1.57%   +1.46%   +1.54%  +2.24  +0.43%  55%   +2.27  0.0002
-10%  2      66      36   +4.59%  +2.47%   +2.36%   +2.45%  +1.59  -0.28%  48%   +1.60  0.0002
```
- **Survives both demean and beta-adjust** (betaAdj ≈ excess): NOT recovery beta — genuine per-name overshoot.
- **Recovery beta WAS most of the raw bounce** (−5%: raw +0.69% → excess +0.14%). Removing it is essential.
- **Cluster-robust t = 1.5–2.5** (period-level eff-n), far below the naive perm_p 0.0001 — eff-n inflation real but partial.

## Verdict
[x] **REAL, market-neutral, trap-hardened — but SUB-GATE on the magnitude×n×significance frontier.**
No single config clears all four bars at once:
- magnitude ≥+2%/trade: only −10% H2 (+2.36%) — but n=36, t=1.6 (not significant)
- significance (t>2) + n>100: only −5% H2 (t 2.49, n=325) — but +0.22%/trade (too small)
- sweet spot −8% H2: +1.46%/trade, median +0.43%, hit 55%, t 2.24 — but n=91 (just under 100)

The edge is genuine; it sits one data-increment under promotion. **Best new lead since the carry book.**

## Path to champion
1. **Forward-collect** more alt-perp 8h history → push −8% H2 past n=100 and tighten t>2 → gate pass.
2. **1m entry** (harvest in progress): enter intra-cascade at the actual −8% touch, not the 8h close →
   likely larger, cleaner excess (the 8h close already partially recovered).
3. **Stack:** market-neutral and event-driven → ~uncorrelated to the carry book → a 2nd sleeve.
   Measure corr to carry; if low, the stacked Sharpe rises (the program's core lever).
