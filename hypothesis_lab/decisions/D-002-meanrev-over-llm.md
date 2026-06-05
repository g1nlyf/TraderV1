---
type: decision
date: 2026-05-31
project: "[[TraderV1]]"
status: adopted
created: 2026-05-31
updated: 2026-05-31
tags: [trader, mean-reversion, entry-timing, champion, llm, overfitting]
ai-first: true
confidence: high
links: [TraderV1]
---

## For future Claude
For **entry timing**, the **champion is a deterministic mean-reversion rule** — it beats every LLM tried. The LLM entry models were either **in-sample-leaky** or **noise-fit**; the rule is robust: **+1.57% net EV per trade**, **validated OOS**, **no endpoint throttling**, low overfit. The LLM is **demoted to an optional residual model** (predict only what the rule leaves on the table), not the primary signal. Champion config lives at `finetune/inference/entry_champion.json`. Don't replace the rule with an LLM unless it clears the [[temporal-holdout-triple-barrier-eval]] gate by a real margin.

# Decision — Deterministic mean-reversion rule is the entry-timing champion over any LLM

## Context
Two families competed for the entry-timing slot: trained **LLM** models vs a **deterministic mean-reversion rule**. Evaluated under the temporal-holdout + triple-barrier standard — see [[temporal-holdout-triple-barrier-eval]].

## Decision
Make the **deterministic mean-reversion rule the champion** for entry timing. Demote the LLM to an **optional residual model** layered on top, only if it adds signal beyond the rule.

## Rationale
- LLM entry models were **in-sample-leaky or noise-fit** — their apparent edge did not survive honest evaluation.
- The rule is **robust**: **+1.57% net EV/trade**, **validated out-of-sample**, **no endpoint throttling** (no dependence on API rate limits / latency), and **low overfit**.
- A simple, transparent, robust rule beats a fragile black box for a signal that must run live.

## Consequences
- **Champion shipped** at **`finetune/inference/entry_champion.json`**.
- LLM is **optional / residual**, not on the critical path → lower inference cost and no LLM endpoint dependency for the core entry decision.
- Confirms the broader pattern that outcome-grounded, leak-free evaluation flips "fancy model wins" conclusions — see [[use-outcome-as-teacher]] and [[momentum-pivot-token-universe]].

## Status
**Adopted; champion in `finetune/inference/entry_champion.json`.**

## Revisit triggers
- An LLM (or other model) clears the temporal-holdout + triple-barrier gate with net EV materially above +1.57%/trade OOS.
- The mean-reversion edge decays in forward shadow-collection.

## Links
[[TraderV1]] | [[meanrev-rule-over-llm]] | [[temporal-holdout-triple-barrier-eval]] | [[use-outcome-as-teacher]] | [[momentum-pivot-token-universe]]
