---
type: decision
date: 2026-05-31
project: "[[TraderV1]]"
status: adopted
created: 2026-05-31
updated: 2026-05-31
tags: [trader, momentum, entry-timing, dataset, geckoterminal, wallet-copy]
ai-first: true
confidence: high
links: [TraderV1]
---

## For future Claude
The wallet-copy path is **blocked by data**, not code: the DB has rich wallet-metrics (~7 wallets) and price-outcomes (~9 tokens) but they **DON'T overlap** — there is no single complete `wallet + outcome` record to learn from. So the pivot is to build a **token entry-timing (momentum) model** from a harvested **GeckoTerminal OHLCV** universe (197 tokens), which needs only price data. This runs **parallel** to wallet-copy and **composes** with wallet signals later once overlapping records exist.

# Decision — Pivot to a momentum (entry-timing) model on a harvested token universe

## Context
The intended primary path was wallet-copy (learn which smart wallets to mirror). Auditing the DB showed two disjoint islands: wallet behavioral metrics existed for ~7 wallets, and price/outcome data existed for ~9 tokens, but the sets did not intersect. Training wallet-copy needs joined `wallet → token → realized-outcome` rows, and **zero complete records existed**.

## Decision
Build a **token entry-timing (momentum) model** parallel to the blocked wallet-copy path, sourced from a freshly **harvested GeckoTerminal OHLCV universe**. Momentum needs only price series, so it sidesteps the wallet-join blocker entirely.

## Rationale
- Wallet-metrics (~7) and price-outcomes (~9) **do not overlap** ⇒ no complete wallet+outcome record ⇒ wallet-copy is unlearnable today.
- Momentum/entry-timing depends only on OHLCV, which we can harvest at scale immediately.
- Keeps the project shipping a profitable-capable model while the wallet dataset is grown.

## Consequences
- **197-token GeckoTerminal harvest** + momentum datasets built.
- Momentum is a standalone signal now and **composes later with wallet signals** once overlapping records accumulate (the two tracks are additive, not exclusive).
- Eval uses the temporal-holdout + triple-barrier standard — see [[temporal-holdout-triple-barrier-eval]].
- Training target is realized outcomes, not the composite score — see [[use-outcome-as-teacher]].
- Champion entry-timing model so far is a deterministic rule — see [[meanrev-rule-over-llm]].

## Status
**Adopted; composes later with wallet signals.**

## Revisit triggers
- Wallet-metrics and price-outcomes accumulate enough overlapping rows to make wallet-copy trainable.
- Momentum universe harvest can be widened beyond the initial 197 tokens.

## Links
[[TraderV1]] | [[momentum-pivot-token-universe]] | [[use-outcome-as-teacher]] | [[temporal-holdout-triple-barrier-eval]] | [[meanrev-rule-over-llm]]
