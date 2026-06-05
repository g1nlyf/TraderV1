# H-079 — Funding sign-flip post-cascade (positive→negative) → stronger bounce

**Status:** tested · 2026-06-05 · **FALSIFIED — sign-flip is not a predictor (net −0.07%, t 0.57)**
**Zone:** FORCED-FLOW PREMIA
**Created:** 2026-06-05 (Session 5)

## Statement
H-042's base requires funding to be rising (positive) at the cascade moment (to confirm the
dip-buying leverage hypothesis). H-079 adds a post-cascade filter: when funding FLIPS from positive
to negative in the period following the cascade, it confirms that the long-side crowding has been
fully purged (funding turned negative because the forced sellers have created a net-short OI
imbalance). The name then bounces in period 2 (the next period) MORE than H-042's base case
because the long-side is now UNDER-crowded (funding went negative = shorts are now crowded).
The forced party in period 1 is the new short who sold into the panic.

## Quality filter
- **Who is FORCED & cannot stop:** in the post-cascade period, new shorts pile on into the funding-
  negative environment; if the cascade's selling was forced (involuntary) and over-shot, the
  subsequent short crowding (shorts paying funding) faces a forced-short-cover squeeze in period 2.
  The short cannot hold if funding turns deeply negative (they are now paying carry to be short).
- **Falsifier:** the funding sign-flip does not predict incremental forward bounce vs H-042 base
  events without sign-flip (the sign-flip is noise or persistent, not a reversion predictor).
- **Why funds can't capture:** requires real-time monitoring of funding sign after cascade; the
  period-1 window (when funding flips) is the optimal entry — but this requires acting during
  an already-volatile post-cascade period.
- **data_status:** HAVE — 8h price + funding 730d. Subset of H-042 −8% cascade events where
  period-1 funding < 0. Expected n: 15–40 (subset of H-042's n=91 at −8% threshold).

## Test method
Extend `scripts/h042_deep.py`: for each −8% cascade event (H-042 base), check if period-1
funding < 0 (sign flip from positive cascade). Measure period-2 excess return vs market.
Compare to H-042 base events where funding stays positive after cascade. Full hardened protocol:
market-demean, per-name beta-adjust, period-cluster eff-n, cost 11bps RT. Also test period-1
entry (enter when funding flips negative) with period-2 exit.

## data_status
HAVE — subset of existing H-042 events with funding data. Expected n: 15–40 qualifying events.

## Results (scripts/test_zone1_forcedflow.py — full H-042 hardened protocol)
−8% cascade at t where funding flips positive(t)→negative(t+1); enter close of t+1, measure period-2
forward excess (H1 from t+1), beta-adjusted.
```
 events periods   net/trade  clustT(bA)  median  hit   block-CI95         perm_p
   121      58     -0.07%      +0.57     -0.18%  48%   [-0.59%,+1.46%]    0.0002
```
Net ~0 (−0.07%), cluster-t 0.57. The funding sign-flip carries no incremental forward bounce.

## Verdict
[ ] FALSIFIED. A post-cascade funding flip from positive to negative does NOT signal a stronger period-2
bounce — the "long-side fully purged → under-crowded → squeeze" story is not borne out. The sign-flip is
either noise or simply confirms the move already happened; it is not a forward reversion predictor.

## Score
8.0 / 10
(edge_plausibility 8 × 2 + data_feasibility 9 + novelty 7) / 4

## Status
tested · falsified
