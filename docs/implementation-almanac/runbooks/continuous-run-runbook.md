# Continuous Run Runbook

## Purpose

Run the final acceptance window for the Stage 2 paper trading system.

## Prerequisites

- Sprint 1-4 acceptance gates passed.
- Config snapshots created.
- Risk limits configured.
- Promotion criteria configured.
- Data sources enabled.
- Dashboard available.
- No live execution path enabled.

## Procedure

1. Create `AcceptanceRun`.
2. Record config snapshot ids.
3. Start data ingestion.
4. Start job queue workers.
5. Start Hermes orchestration.
6. Enable token discovery.
7. Enable paper trading workflow.
8. Monitor dashboard.
9. Record invariant violations.
10. End run after configured acceptance window.
11. Generate final report.

## During run

Monitor:

- source health;
- queue depth;
- lease timeouts;
- open positions;
- missed exit checks;
- failed fills;
- risk vetoes;
- net P&L;
- expectancy;
- drawdown;
- invariant violations.

## Abort criteria

Abort or fail acceptance if:

- live execution path is discovered;
- ledger mutability violation occurs;
- paper order created without risk check;
- exit fill created without exit decision;
- P&L is not deterministic;
- open positions stop being monitored;
- source data silently corrupts output.

## Output

- AcceptanceRun result.
- Metrics report.
- Invariant report.
- Shadow Mode Gap Report if applicable.
- Final acceptance decision.

