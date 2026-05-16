# Sprint 1 - Foundation, Environment And Source Of Truth

## Goal

Create the foundation that later modules cannot bypass.

## Scope

Build:

- project structure for final system;
- runtime/config loading;
- database connection and migrations;
- raw event log;
- audit event log;
- config snapshot tables;
- domain contract skeletons;
- paper ledger/event skeleton;
- job queue and lease skeleton;
- monitoring session skeleton;
- deterministic service boundaries;
- Hermes connectivity smoke test.

## Non-goals

- No signal intelligence.
- No strategy search.
- No real trading.
- No private keys.
- No live execution module.
- No LLM-driven research workflows yet.

## Tasks

1. Create application skeleton.
2. Create config loader.
3. Create database migrations.
4. Create raw event schema.
5. Create audit event schema.
6. Create `ConfigSnapshot`, `RiskLimitSnapshot`, `StrategyConfigSnapshot`, `PromotionCriteriaSnapshot`, `AcceptanceRun`.
7. Create skeleton tables for `Signal`, `TradeThesis`, `RiskCheck`, `PaperOrder`, `PaperFill`, `PaperPosition`, `ExitDecision`, `TradeOutcome`.
8. Create job queue tables: `Job`, `WorkerLease`, `MonitoringSession`, `ConflictReview`.
9. Create deterministic service interfaces for risk, paper and evaluation.
10. Create harmless Hermes tool smoke test.
11. Add unit tests for append-only records and config snapshot creation.

## Acceptance gate

- DB stores raw events, audit events, jobs, sessions, config snapshots and ledger skeleton records.
- Hermes can call one harmless project tool.
- Hermes-driven trading/research workflows are not enabled.
- Job lease/timeout mechanics pass tests.
- Append-only audit policy is tested.
- Domain contracts exist before behavior implementation.

## Failure conditions

- Any live execution or private-key path exists.
- Hermes can mutate ledger directly.
- Paper order can be created without risk check skeleton.
- No config snapshot mechanism exists.

