# Almanac V2

## Purpose

This almanac is the implementation contract for TraderV1 V2.0. It keeps the final architecture agentic while giving implementers concrete boundaries, data contracts and acceptance gates.

V2.0 should reuse existing Stage 2 code where it is useful, but it must not inherit the older framing where scripts score and the agent only reads reports. Hermes must become the active orchestrator over typed tools.

## Build Direction

```text
Existing Stage 2 deterministic foundation
  -> V2 data depth for token/wallet intelligence
  -> Hermes write-safe tool surface
  -> AI token selection and wallet rating loops
  -> active market sessions with second-level data
  -> paper/shadow decision loop
  -> forward evaluation and learning
```

## Almanac Files

- [00-system-invariants.md](00-system-invariants.md) - rules every implementation task must preserve.
- [01-domain-data-model.md](01-domain-data-model.md) - V2 domain objects and how they extend the current schema.
- [02-hermes-tool-contracts.md](02-hermes-tool-contracts.md) - typed tools Hermes and agents need.

Implementation sequencing is in [../implementation-plan/02-three-sprint-plan.md](../implementation-plan/02-three-sprint-plan.md).

## Required Implementation Stance

- Prefer extending `walletscarper.stage2` rather than duplicating a second unrelated trading system.
- Keep legacy `WalletScarper` collectors as adapters until their outputs are normalized into Stage 2/V2 evidence.
- Expose tools through Hermes plugin/MCP/API boundaries, not raw database writes from agent text.
- Keep all P&L, fills, risk checks and strategy metrics deterministic.
- Keep all agent decisions auditable and linked to evidence refs.
