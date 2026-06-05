# H-064 — Funding change-rate crowded-unwind mean-reversion

**Status:** proposed
**Zone:** FORCED-FLOW PREMIA
**Created:** 2026-06-05 (Session 5)

## Statement
A rapid acceleration in funding rate (large positive ΔF over 2–3 consecutive 8h periods, top quartile
of per-name distribution) signals a crowded trade building at an unsustainable rate. The acceleration
itself forces late-arriving longs to pay ever-higher carry, crowding the book until a small price move
triggers a cascade of forced exits. The name mean-reverts within 2 periods of the peak acceleration,
excess of market. Trade short (or basis-short) the name at peak ΔF, cover 2 periods later.

## Quality filter
- **Who is FORCED & cannot stop:** leveraged longs entering into an accelerating funding market pay
  progressively higher carry; when the acceleration peaks and stalls, anyone who bought on the
  acceleration faces P&L reversal + carry drain — forced out by combined cash-carry and mark-to-market.
- **Falsifier:** funding acceleration (ΔF) does not predict forward excess return. This could fail
  because acceleration correlates with momentum (FOMO), which H-053 showed continues.
- **Why funds can't capture:** requires multi-period funding-velocity tracking, short-only positioning
  in perp market while carry is actively running against you, event sparsity.
- **data_status:** HAVE — 8h funding 730d. Compute per-name 3-period ΔF, flag top-quartile.

## Test method
Extend `scripts/funding_leads2.py`: compute 3-period rolling ΔF per name; flag events where ΔF >
per-name 75th percentile. Measure forward 1–2 period excess return (market-demean, per-name beta-
adjust, period-cluster, cost). Key cross-check: stratify by concurrent price move to separate funding
acceleration WITH price (FOMO) from funding acceleration WITHOUT price (crowding).

## data_status
HAVE — existing funding cache. Expected n: 300–600 events.

## Score
7.25 / 10
(edge_plausibility 7 × 2 + data_feasibility 9 + novelty 6) / 4

## Status
proposed
