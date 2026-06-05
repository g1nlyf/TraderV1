# H-063 — Funding-spike forced long exit → price reversion

**Status:** proposed
**Zone:** FORCED-FLOW PREMIA
**Created:** 2026-06-05 (Session 5)

## Statement
When 8h funding rate for a name spikes to the top decile of its own trailing 90d distribution (not
just high in absolute terms — per-name normalized), leveraged longs face cash drain that forces
involuntary position closure even without a price move triggering margin. The forced exit (funding-
margin squeeze) leads to price decline in the next 1–2 periods as a wave of leveraged longs unwind.
Go short the name market-neutral (or fade the basis: long perp, short spot) at the spike, cover after
1–2 periods. Distinct from H-042: the trigger is funding rate, not price; the forced party is the
ongoing long, not the margin-called long.

## Quality filter
- **Who is FORCED & cannot stop:** leveraged longs paying extreme funding cannot sustain the cash cost
  indefinitely; a funding spike at 0.1–0.3%/8h (annualized >100%) mechanically drains margin and
  forces unwind or closure — not a choice, a cash constraint.
- **Falsifier:** extreme per-name funding does not predict forward price decline (price continues up,
  consistent with H-053's FOMO-continuation finding on the upside). Must verify the direction:
  funding spike alone (without cascade) may signal momentum, not reversion.
- **Why funds can't capture:** the forced exit is gradual, not a single event; timing the unwind
  requires per-name funding history, positions are long-only unfriendly (need perp short), and
  the carry cost of holding the short while funding is extreme is high.
- **data_status:** HAVE — 8h funding 730d 50 names. Key risk: H-053 showed up-spikes CONTINUE,
  not fade — must stratify: is this funding-spike without price-spike, or both?

## Test method
Extend `scripts/h042_deep.py` or `funding_leads2.py`: define entry as funding > per-name 90th
percentile (trailing 90d rolling), no concurrent price cascade (to isolate from H-042). Measure
forward 1–2 period excess return (market-demean, per-name beta-adjust, period-cluster, cost).
Stratify by whether a price move > +5% also occurred (FOMO case, likely continues) vs funding-only
spike (unwind case, hypothesis).

## data_status
HAVE — existing funding cache. Expected n: 100–300 events per name-decile definition.

## Score
7.5 / 10
(edge_plausibility 7 × 2 + data_feasibility 9 + novelty 7) / 4

## Status
proposed
