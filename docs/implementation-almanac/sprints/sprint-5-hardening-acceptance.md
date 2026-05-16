# Sprint 5 - Hardening, Shadow Mode And Final Acceptance

## Goal

Make the final Stage 2 system reliable enough to run continuously and produce an honest Stage 3 shadow readiness result.

## Scope

Build:

- full test suite;
- no-hindsight workflow tests;
- risk veto tests;
- ledger immutability tests;
- job queue failure tests;
- source degradation tests;
- dashboard and alerts;
- configured continuous acceptance run;
- Shadow Mode Gap Report if needed;
- final acceptance report.

## Non-goals

- No live execution.
- No private keys.
- No fake Stage 3 completion.

## Tasks

1. Add invariant test suite.
2. Add end-to-end paper trading test.
3. Add continuous run harness.
4. Configure `AcceptanceRun`.
5. Run system for configured acceptance window.
6. Track invariant violations.
7. Verify dashboard health.
8. Verify operational metrics.
9. Evaluate shadow quote/execution data quality.
10. Produce Shadow Mode Gap Report if needed.
11. Produce final acceptance report.

## Acceptance gate

- Continuous run completes configured window.
- No critical invariant violations.
- Multiple token sessions are monitored.
- Open positions are not starved by discovery.
- Metrics include expectancy, net P&L, drawdown and strategy comparison.
- Failures degrade safely.
- Shadow mode is either honestly implemented or gap-reported.

## Failure conditions

- Continuous run is too short or not configured.
- Invariant violations are ignored.
- Dashboard hides failed fills or source degradation.
- Shadow mode is marked complete without data quality.

