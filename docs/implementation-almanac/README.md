# Implementation Almanac

This folder is the execution manual for building the final system.

It is intentionally more detailed than the conceptual docs. Use it as the source of step-by-step implementation truth for the coding agent.

## Goal

After all five sprints in this almanac are implemented, verified and accepted, the system should be a complete **Stage 2 autonomous real-market paper trading system with Stage 3-compatible shadow execution design**.

The system is not complete because files exist. It is complete only when every sprint gate and final acceptance run pass.

## Non-negotiable implementation rules

- No real-money live execution path is enabled in this release.
- No private-key path, signer, swap adapter or DEX transaction code is created in this release.
- Signal must pass deterministic entry `RiskCheck` before `PaperOrder`.
- Exit must create `ExitDecision` before simulated exit fill.
- Paper ledger is append-only for critical events.
- Browser-only prices cannot promote strategies or create canonical high-confidence P&L.
- Historical wallet P&L is candidate evidence, not strategy performance.
- Strategy promotion/demotion/kill decisions require versioned config snapshots.
- Adding a framework is not progress unless it removes a measured bottleneck.

## Reading order

1. [00-master-build-map.md](00-master-build-map.md)
2. [01-system-invariants.md](01-system-invariants.md)
3. [02-architecture-decisions.md](02-architecture-decisions.md)
4. [contracts/README.md](contracts/README.md)
5. [contracts/domain-contracts.md](contracts/domain-contracts.md)
6. [contracts/service-api-contracts.md](contracts/service-api-contracts.md)
7. [contracts/config-snapshots.md](contracts/config-snapshots.md)
8. [sprints/sprint-1-foundation.md](sprints/sprint-1-foundation.md)
9. [sprints/sprint-2-data-wallet-intelligence.md](sprints/sprint-2-data-wallet-intelligence.md)
10. [sprints/sprint-3-signal-risk-paper.md](sprints/sprint-3-signal-risk-paper.md)
11. [sprints/sprint-4-parallel-strategy-memory.md](sprints/sprint-4-parallel-strategy-memory.md)
12. [sprints/sprint-5-hardening-acceptance.md](sprints/sprint-5-hardening-acceptance.md)
13. [checklists/final-acceptance-checklist.md](checklists/final-acceptance-checklist.md)
14. [runbooks/continuous-run-runbook.md](runbooks/continuous-run-runbook.md)
15. [decisions/ADR-0001-release-target.md](decisions/ADR-0001-release-target.md)
16. [decisions/ADR-0002-risk-before-paper-order.md](decisions/ADR-0002-risk-before-paper-order.md)
17. [decisions/ADR-0003-no-live-execution.md](decisions/ADR-0003-no-live-execution.md)
18. [decisions/ADR-0004-job-queue-over-freeform-a2a.md](decisions/ADR-0004-job-queue-over-freeform-a2a.md)
19. [decisions/ADR-0005-browser-data-policy.md](decisions/ADR-0005-browser-data-policy.md)

## Completion model

Each sprint has:

- purpose;
- scope;
- explicit non-goals;
- implementation tasks;
- contracts to create or modify;
- tests;
- acceptance gate;
- failure conditions.

A sprint is not accepted until its gate passes. The final system is not accepted until Sprint 5 and the final continuous run pass.

