---
type: decision
date: 2026-05-31
project: "[[TraderV1]]"
status: adopted
created: 2026-05-31
updated: 2026-05-31
tags: [trader, evaluation, holdout, triple-barrier, leakage, gating-standard]
ai-first: true
confidence: high
links: [TraderV1]
---

## For future Claude
The gating eval standard is **temporal holdout** (train on the past, test on the future) + **purge/embargo** + **triple-barrier labels**. Do NOT use a token-disjoint split: holding out by token still trains and tests inside the **same time window**, which **leaks the market regime** and inflates results. Implemented in `build_momentum_v3.py`. Any model claiming a win-rate must pass through this harness — numbers from other splits are not trustworthy.

# Decision — Eval standard = temporal holdout + purge/embargo + triple-barrier

## Context
Earlier evals used a **token-disjoint split** (different tokens in train vs test). Because all tokens were sampled from the same window, train and test shared the same market regime, so the split leaked regime information and produced optimistic, non-actionable win-rates.

## Decision
Adopt as the single gating standard:
1. **Temporal holdout** — train strictly on past data, test strictly on future data.
2. **Purge + embargo** — drop samples straddling the train/test boundary so label horizons can't bleed across.
3. **Triple-barrier labels** — label each entry by which barrier (profit-take / stop / time) is hit first.

## Rationale
- Token-disjoint splits **leak market regime** (train + test occupy the same window) → inflated, dishonest win-rates.
- Temporal holdout mirrors live deployment: you only ever have the past to predict the future.
- Purge/embargo removes look-ahead from overlapping label windows; triple-barrier gives a realistic, path-aware outcome instead of a fixed-horizon return.

## Consequences
- Built **`build_momentum_v3.py`** implementing the temporal split + purge/embargo + triple-barrier labeling.
- Produces **honest win-rate numbers** that gate promotion (lower than the old leaky numbers, but real).
- This is **the gating standard**: a model must clear it OOS to be considered. It is how the mean-reversion champion was validated — see [[meanrev-rule-over-llm]].
- Pairs with outcome-based supervision — see [[use-outcome-as-teacher]] — and evaluates the momentum track — see [[momentum-pivot-token-universe]].

## Status
**Adopted as the gating standard.**

## Revisit triggers
- Evidence that purge/embargo windows are mis-sized for the label horizon.
- Moving to walk-forward / rolling-origin if a single holdout split proves too noisy.

## Links
[[TraderV1]] | [[temporal-holdout-triple-barrier-eval]] | [[meanrev-rule-over-llm]] | [[use-outcome-as-teacher]] | [[momentum-pivot-token-universe]]
