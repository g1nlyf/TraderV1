# H-024 — New-perp-listing funding decay (harvest launch-hype crowding)

**Status:** proposed · priority-test (top untested survivor of 2026-06-04 generation)
**Priority:** P0 for next session
**Asset universe:** Binance/Bybit USDT perps, conditioned on listing age (funding_cache)
**Created:** 2026-06-04

## Statement
Newly listed perps carry **elevated, decaying positive funding** in their first weeks
(launch hype → crowded leveraged longs with no easy arbitrageur yet). Harvest it: hold a
short-perp carry position (delta-hedged where a spot/borrow leg exists, or basket-hedged)
during the first N days post-listing, scaling out as funding normalizes to the mature level.

## Rationale ("million dollar idea")
**Who loses & why they can't stop:** retail FOMO-ing a hot new listing pile into leveraged
longs in the first days (the most attention, the least float). Funding spikes positive to
clear the one-sided demand; with no cheap arbitrageur (no spot, no borrow, listing risk),
the premium persists and decays slowly. This is a *recurring, structural* crowding event —
every new listing reprints it, and the losing side (attention-driven retail) is structurally
replenished. Unlike a static factor (B-03 non-stationarity), it's conditioned on a fresh
structural extreme each time, so it should not arb away.

**Why a top fund hasn't vacuumed it:** capacity is tiny (new listings are small-notional),
the spot/borrow leg is often missing early (hard to run clean delta-neutral), and listing/
liquidity/delisting risk is real. Friction, not absence — which is exactly where retail-scale
edge survives.

## Data required (all cached — testable now)
- `funding_cache/*_binance.npz`, `*_bybit.npz`: first funding timestamp ≈ listing date.
  Recently-listed names present: PUMP, ASTER, VVV, MAGMA, XPL, H, OPN, STO, EPIC, CRCL, ...
- `*_spot_8h.npz` / `*_perp_8h.npz` where available for delta-neutral basis leg.

## Test method
1. Event study: per name, compute mean funding APR in age buckets {day 1-3, 4-7, 8-30, 31+}.
   Test that early-bucket funding > mature-bucket (paired across names; permutation over the
   age-label assignment to control for the cross-section).
2. Carry backtest: short-perp (delta-hedged where possible) entered at listing, EWMA-sized,
   exited at age horizon. Realized net pnl after maker cost. Temporal OOS split across the
   *listing calendar* (train on earlier listings, test on later). Score through `eval_stats`
   (realized EV + perm_p + CI95). Effective-n = number of distinct listings (keep honest;
   do not overlap-inflate within a single listing's window).
3. Cost/holding sweep; regime (BTC trend) split.

## Parameters
- Age horizon N ∈ {3, 7, 14, 30} days. EWMA span ∈ {1,3,6}. Maker 1bp/leg, taker 5.5bps.

## Results (2026-06-04 Session 2, scripts/carry_leads.py)
```
Genuinely new in-window listings (first funding > window_start+14d): 20 names.

Funding APR by listing age (mean across 20 listings):
  d1-3:  +5.2%    d4-7:  -3.0%    d8-30: +1.4%    d31+:  +4.6%
=> NO monotonic decay. Early (d1-3) ≈ mature (d31+); a dip at d4-7. Hypothesis premise wrong.

Paired early-vs-mature (permutation over age labels, 10k):
  d1-7 vs d31+:  excess -4.6%   perm_p 0.848
  d1-3 vs d31+:  excess +0.1%   perm_p 0.550
  d1-14 vs d31+: excess -12.5%  perm_p 0.999
=> early funding NOT systematically higher than mature. Refuted on the cross-section.

Hedgeable subset (has spot leg, n=8): early_APR +20.3% (d1-7) / +31.6% (d1-3) / +11.3% (d1-14).
```

## Verdict
[ ] PASS  [x] **FAIL / INCONCLUSIVE**  — premise refuted on the full cross-section.
The "elevated decaying launch funding" pattern is NOT robust across 20 listings (early ≈
mature, perm_p 0.55–0.99). A subsample hint exists: the 8 new listings WITH a spot leg show
high early funding (+20–32% APR) — but n=8 listings is far below the gate and likely a noisy
selection (the spot-bearing new listings are the bigger, more-hyped ones). Effective-n =
distinct listings (~20), so this cache CANNOT clear n>100 regardless — it is collect-forward
limited. Not promotable now.

## Refinement path (forward-collection, not now)
- The hedgeable-new-listing hint (+20–32% early APR, n=8) is the only live thread. To test it
  honestly needs forward collection of MANY new listings with spot legs (≥30) over coming
  months, then the H-021 fixed-selection carry on the first-week window. Queue as a background
  collector, not a now-test.
- Cross-venue maker spread on new listings (no spot needed) — same n<100 limit; park with the
  forward collector.

## Refinement path
- If early-funding premium is real but not capturable delta-neutral (no spot leg): test the
  cross-venue (Binance−Bybit) maker spread on new listings specifically — H-13 showed xvenue
  maker is the only way to touch spot-less names (+0.6% baseline; new listings may be richer).
- If real: this stacks with the validated carry sleeves (STACK.md) as a higher-APR, episodic
  carry overlay — the most plausible path toward the +2% gate found so far.
