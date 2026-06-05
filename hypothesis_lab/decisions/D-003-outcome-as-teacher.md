---
type: decision
date: 2026-05-31
project: "[[TraderV1]]"
status: adopted
created: 2026-05-31
updated: 2026-05-31
tags: [trader, ml, training-target, backtest, reward-modeling]
ai-first: true
confidence: high
links: [TraderV1]
---

## For future Claude
Train TraderV1 models on **realized market outcomes**, never on the deterministic composite-scoring formula. The formula was backtested and is **unprofitable** (net-EV −0.0119, signal precision 0.377), so imitating it just inherits the loss. Teacher signal = reward-filtered + replay datasets keyed to actual price outcomes. If you are about to build a dataset that labels examples with the composite score, STOP — that is the discredited path.

# Decision — Outcome-as-teacher: train on realized outcomes, not the composite-scoring formula

## Context
The original supervision signal was the deterministic composite-scoring formula (the rule-based scorer that ranked tokens/wallets). Imitation-learning a model to reproduce that score is only worth doing if the score itself makes money. A backtest of the formula settled the question.

## Decision
Use **realized market outcomes** as the training target. Models learn from what actually happened to price, not from the heuristic score. Concretely: build **reward-filtered datasets** (keep examples whose realized outcome cleared a reward threshold) and **replay datasets** (historical price paths) as the teacher.

## Rationale
- Backtest proved the composite formula **unprofitable**: **net-EV −0.0119 per signal**, **signal precision 0.377**.
- Cloning an unprofitable policy inherits its expected loss — the student cannot beat a teacher whose own EV is negative.
- Outcomes are ground truth and are immune to the formula's biases.

## Consequences
- Datasets are **reward-filtered + replay** keyed to realized price paths (see [[temporal-holdout-triple-barrier-eval]] for the labeling/eval standard).
- Requires the price-path backfill / replay corpus as a hard dependency.
- The composite scorer is demoted from "target" to at most a weak feature.
- Aligns with the entry-timing track where a deterministic rule beat the LLMs — see [[meanrev-rule-over-llm]].

## Status
**Adopted.**

## Revisit triggers
- A revised composite formula backtests to positive net-EV.
- Reward-filtered + replay training underperforms the discredited imitation baseline OOS.

## Links
[[TraderV1]] | [[use-outcome-as-teacher]] | [[temporal-holdout-triple-barrier-eval]] | [[meanrev-rule-over-llm]]
