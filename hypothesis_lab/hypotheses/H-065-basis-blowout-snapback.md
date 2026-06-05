# H-065 — Basis-blowout mean-reversion (perp/spot snap-back)

**Status:** tested · 2026-06-05 · **FALSE-POSITIVE TRAP CAUGHT — microstructure MR, net < 0**
**Zone:** FORCED-FLOW PREMIA
**Created:** 2026-06-05 (Session 5)

## Statement
When the perp/spot basis (perp_close / spot_close − 1) expands to an extreme relative to the
per-name trailing distribution (top or bottom 5th percentile), it represents a forced disbalancing:
either forced buying of perp by momentum players (perp premium) or forced selling of perp by
liquidation cascades (perp discount). The basis reverts to its mean within 1–3 periods (funding
mechanism enforces this). The edge is: enter the basis trade (short the rich leg, long the cheap
leg) at extreme divergence, exit at normalization. For perp-discount extremes (cascade-driven),
this IS H-042 but measured at the basis level instead of price level — more precise trigger.

## Quality filter
- **Who is FORCED & cannot stop:** for perp-discount: liquidation sellers hit perp (not spot),
  creating a basis discount. Arbitrageurs eventually close it, but the forced sellers have already
  exited. For perp-premium: FOMO buyers bid perp, basis expands, funding corrects it mechanically.
  Both parties cannot sustain the extreme basis position indefinitely.
- **Falsifier:** extreme basis does not predict forward basis reversion faster than the funding
  mechanism would imply (i.e., no excess over the funded cost of the trade).
- **Why funds can't capture:** requires real-time per-name basis monitoring, simultaneous leg
  execution to lock the spread, and capital for both legs per name — too operationally complex
  at small scale.
- **data_status:** HAVE — 8h perp + spot price 730d (~37 names with both legs). Basis = perp/spot − 1.
  Note: C-002 carry book already trades basis at normal levels; this is the EXTREME-event version.

## Test method
Extend `scripts/h042_deep.py` or `leverage_sim.py`: compute per-name rolling 90d basis distribution;
flag 5th-percentile (discount, cascade-driven) and 95th-percentile (premium, FOMO-driven) events.
Measure forward 1–3 period basis reversion, net of round-trip cost (11bps RT). Market-demean the
forward perp price separately from spot (measure basis P&L directly, not price P&L).

## data_status
HAVE — existing 8h perp + spot cache for ~37 names. Expected n: 70–200 extreme events across
both tails.

## Results (scripts/test_zone1_forcedflow.py — full H-042 hardened protocol + trap audit)
Per-name perp/spot basis-return at trailing-90d 5th pct (discount → long basis) or 95th pct
(premium → short basis); forward basis-return reversion over H1 / H3, net of 11bps RT.
```
 variant            events periods   net/trade  clustT   median  hit   block-CI95         perm_p
 H-065 basis5/95 H1   7806   2026     -0.05%    +25.38   +0.04%  82%   [+0.05%,+0.06%]    0.0002
 H-065 basis5/95 H3   7791   2024     -0.05%    +17.84   +0.04%  82%   [+0.05%,+0.06%]    0.0002
```
**TRAP AUDIT: `basis_ret` lag-1 autocorrelation = −0.44, negative on 100% of 36 tradeable names.**

## Verdict
[ ] FALSE-POSITIVE TRAP CAUGHT (the 4th — after H-15, H-001, and the H-042 naive-perm collapse). The
spectacular cluster-t (+25, +18) and 82% hit are NOT alpha — they are a pure microstructure artifact:
non-synchronous spot vs perp 8h closes plus bid-ask bounce give `basis_ret` a mechanical −0.44 one-period
autocorrelation, so any extreme of basis_ret[t] "reverts" by construction at t+1. The decisive tell is
economics: the gross edge is ~6bps, **below the 11bps round-trip cost → net is NEGATIVE (−0.05%/trade).**
A t-stat of 25 on a sub-cost, mechanically-autocorrelated signal is exactly the trap the program is built
to reject. The basis snap-back is not tradeable. (Reaffirms the bid-ask / synchronous-close discipline.)

## Score
7.75 / 10
(edge_plausibility 8 × 2 + data_feasibility 8 + novelty 7) / 4

## Status
tested · false-positive (microstructure), rejected
