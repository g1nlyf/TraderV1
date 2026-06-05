# Decision Tree

## Locked Decisions (Do Not Revisit Without Strong Evidence)

```
ROOT: How do we find profitable trading edge?
│
├── D-001: Eval standard = temporal holdout + triple-barrier (LOCKED)
│   └── Rationale: Token-disjoint split leaks regime. Only temporal split is honest.
│
├── D-002: LLMs demoted from entry signal generation (LOCKED)
│   ├── Evidence: v2-v6 all in-sample-leaky or noise-fit OOS
│   └── Exception: LLMs may work as RESIDUAL (trained only on rule's errors)
│
├── D-003: Train on realized outcomes, not composite score (LOCKED)
│   ├── Evidence: composite formula net-EV = -0.0119 (negative teacher)
│   └── Action: use reward-filtered datasets, not formula imitation
│
├── D-004: Momentum pivot (token entry-timing) parallel to blocked wallet-copy (ACTIVE)
│   ├── Reason: wallet_metrics and token_outcomes don't overlap (zero complete records)
│   └── Status: wallet data growing via forward_collector — revisit when n>100
│
├── D-005: Mean-reversion > momentum for Solana memecoins (SUPERSEDED 2026-06-04)
│   ├── Evidence: momentum features had Cohen's d < 0.07 (no signal)
│   ├── Mean-reversion features: d = 0.247-0.449 (separable FEATURES)
│   └── Status: SUPERSEDED — feature separability ≠ tradeable edge. H-001 showed the
│       mean-reversion rule has realized OOS EV −0.97% (perm_p 0.887), anti-selective.
│       Cohen's d on features did not survive into realized payoff. Track demoted.
│
└── D-006: EV = realized mean payoff, gated by permutation + CI95 (LOCKED 2026-06-04)
    ├── Evidence: C-001 promoted on win-rate-implied EV (+1.57%); realized was −0.97%.
    │   Win-rate rose (41.7% vs 38.2%) while realized PnL fell — fat left tail.
    ├── Action: all scoring goes through finetune/pipeline/eval_stats.py. Win-rate-implied
    │   EV is banned as a promotion metric. Walk-forward drift compared only within same universe.
    └── Revisit triggers: none — this is a methodology floor, not a hypothesis.

## Open Decision Nodes
- Should we explore Bitcoin/ETH strategies in parallel? (user said yes, not yet assigned H-number)
- Should we continue Vertex AI SFT pipeline? (paused — decision pending)
- At what EV threshold do we switch from research to live execution?
```

## Decision Template
```markdown
## D-XXX: [Decision statement]
**Date:** YYYY-MM-DD
**Status:** locked | active | superseded
**Evidence:** [what data drove this decision]
**Rationale:** [why]
**Revisit triggers:** [what new evidence would change this]
```
