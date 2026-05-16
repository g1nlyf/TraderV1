# Implementation Progress

This folder is the factual execution record for implementation work. It records what was actually built, what was only stubbed or tested, what was skipped, and what must carry forward. It is not a replacement for the implementation almanac; it tracks reality against that plan.

## Sprint Index

| Sprint | Status | Detail |
|---|---|---|
| Sprint 1 - Foundation, Environment, Source Of Truth | Foundation implemented; legacy restore verified by operator | [sprint-1-foundation.md](sprint-1-foundation.md) |
| Sprint 2 - Data, Token Discovery And Wallet Intelligence | Implemented and validated | [sprint-2-data-wallet-intelligence.md](sprint-2-data-wallet-intelligence.md) |
| Sprint 3 - Integrated Signal, Risk And Paper Trading Workflow | Implemented and validated | [sprint-3-signal-risk-paper.md](sprint-3-signal-risk-paper.md) |
| Sprint 4 - Parallel Monitoring, Strategy Search And Memory | Implemented and validated | [sprint-4-parallel-strategy-memory.md](sprint-4-parallel-strategy-memory.md) |
| Sprint 5 - Hardening, Shadow Mode And Final Acceptance | Implemented and validated with Stage 3 shadow gaps reported | [sprint-5-hardening-acceptance.md](sprint-5-hardening-acceptance.md) |
| Post-Stage-2 Shadow Readiness Gap Closure | Partially implemented; Stage 3 still gap-blocked | [post-stage2-shadow-readiness-gap-closure.md](post-stage2-shadow-readiness-gap-closure.md) |
| Operational Launch, Hermes Runtime And Design Sprint | Implemented and validated; Stage 3 still gap-blocked | [operational-launch-design-sprint.md](operational-launch-design-sprint.md) |
| V2 Sprint 1 - Agentic Token And Wallet Intelligence Foundation | Implemented as fixture-tested V2 foundation; real source depth still limited | [v2-sprint-1-agentic-token-wallet-foundation.md](v2-sprint-1-agentic-token-wallet-foundation.md) |
| V2 Sprint 2 - Hermes Orchestrator And Safe Paper/Shadow Path | Implemented as fixture-tested safe orchestration path; real tracked-wallet source depth still unproven | [v2-sprint-2-hermes-orchestrator-paper-shadow-path.md](v2-sprint-2-hermes-orchestrator-paper-shadow-path.md) |

## Current Implementation Status

Sprint 1 foundation components were implemented in `WalletScarper` under `walletscarper.stage2`. The implementation includes a SQLite migration foundation, immutable source/audit/config/domain records, job and lease primitives, monitoring and conflict-review skeletons, deterministic service boundaries, and a read-only `project.health_check` boundary.

Restoration note: during Sprint 1 implementation the legacy `WalletScarper` project directory was accidentally removed from this non-git workspace. The operator restored the legacy Final Free v1 package afterward, including source adapters, SQLite state, dashboard, Telegram UX, batch/Docker files, docs, and known environment configuration. The Stage 2 foundation remains isolated under `walletscarper.stage2`.

Sprint 2 implemented the Stage 2 data and wallet-intelligence evidence layer: legacy/source payload audit and raw ingestion mapping, source registry and health/degradation snapshots, ingestion runs, normalized token and market evidence, browser extraction records, token profiles and configurable triage evidence, reconstructed wallet trades, historical wallet metrics marked as candidate evidence only, wallet profiles, and wallet clusters. Legacy WalletScarper behavior is still not Stage 2 source-of-truth; accepted boundaries map already-obtained source payloads into append-only Stage 2 raw events and derived evidence records with provenance and quality metadata. Sprint 2 does not create trading decisions, risk checks, paper ledger records, P&L truth, strategy metrics, live execution, private-key handling, signing, swap adapters, or DEX transaction paths.

Sprint 3 implemented the risk-gated paper research workflow on top of Sprint 2 evidence: Signal and NoTradeSignal creation, pre-entry TradeThesis records, deterministic entry/exit/position-monitoring RiskChecks, guarded PaperOrders, conservative entry and exit PaperFills, PaperPositions with monitoring jobs/sessions, ExitDecisions, deterministic TradeOutcomes, rejected/missed opportunity logs, and a read-only baseline dashboard CLI. Sprint 3 remains paper-only and does not add Sprint 4 strategy search, promotion/demotion/kill logic, memory workflows, live execution, private-key handling, signing, swap adapters, or DEX transaction paths.

Sprint 4 implemented bounded parallel research primitives and strategy/memory artifacts on top of deterministic Sprint 3 outcomes: monitoring session state transitions, worker registry/leases/heartbeats/artifacts, configurable parallelism limits, conflict review resolution metadata, strategy mutation proposals, strategy experiments, leaderboard v1, promotion/demotion/kill/keep-testing/insufficient-data decision records, post-trade review details, memory proposal and curation events, and a read-only Sprint 4 report CLI. Sprint 4 remains paper-only. It does not start Sprint 5 continuous acceptance, shadow/live execution, live trading, private-key handling, signing, swap adapters, DEX transaction construction, or any new agent framework.

Sprint 5 implemented hardening and final acceptance artifacts: final invariant checks, an end-to-end deterministic fixture replay acceptance harness, `AcceptanceRun` execution tracking, invariant violation records, operational health snapshots, final acceptance reports, and a shadow-readiness assessment that produces a Shadow Mode Gap Report when quote freshness, latency, route-quality, or fill-comparison evidence is insufficient. The validated fixture run decision is `accepted_with_gaps`: Stage 2 paper-mode construction is accepted by the harness with zero critical invariant violations, while Stage 3 shadow readiness is explicitly not claimed. Sprint 5 remains paper-only and adds no live execution, private-key handling, signing, swap adapters, DEX transaction construction, or new agent framework.

## Final Release Verification Artifacts

The current Stage 2 release verification package was rerun and exported on 2026-05-15 against `WalletScarper/tmp/final_release_validation.sqlite3`.

- Final release validation summary: [reports/validation-summary.md](reports/validation-summary.md)
- Final acceptance report export: [reports/final-acceptance-report.md](reports/final-acceptance-report.md) and [reports/final-acceptance-report.json](reports/final-acceptance-report.json)
- Shadow Mode Gap Report export: [reports/shadow-mode-gap-report.md](reports/shadow-mode-gap-report.md) and [reports/shadow-mode-gap-report.json](reports/shadow-mode-gap-report.json)

The exported `docs/implementation-progress.zip` must include this README, Sprint 1 through Sprint 5 progress files, and the `implementation-progress/reports/` release verification artifacts.

## Post-Stage-2 Workstream

The Shadow Readiness Gap Closure workstream is tracked separately from Sprint 1-5 and must not be called Sprint 6.

- Progress note: [post-stage2-shadow-readiness-gap-closure.md](post-stage2-shadow-readiness-gap-closure.md)
- Gap-closure report export: [reports/shadow-readiness-gap-closure-report.md](reports/shadow-readiness-gap-closure-report.md) and [reports/shadow-readiness-gap-closure-report.json](reports/shadow-readiness-gap-closure-report.json)
- Release baseline note: [../release-baselines/stage2-accepted-with-gaps-baseline-20260515.md](../release-baselines/stage2-accepted-with-gaps-baseline-20260515.md)

Current result: implementation support exists for observation-only quote capture, latency samples, route-quality evidence, fill-vs-quote comparisons, and live data acceptance windows. Stage 3 shadow readiness remains not accepted until real observation-window evidence closes all gaps.

## Operational Launch Layer

The operational launch sprint added Windows launch scripts, a local read-only FastAPI operator dashboard, Hermes checkout/config for OpenRouter free-model usage, a read-only Hermes project plugin, operations docs, and safe calibration smoke/window wrappers. The calibration window now supports DexScreener, GeckoTerminal, DexPaprika, and `all_free` no-key source collection.

- Operations docs: [../operations/current-system-reality-audit.md](../operations/current-system-reality-audit.md), [../operations/hermes-runtime.md](../operations/hermes-runtime.md), [../operations/free-data-sources.md](../operations/free-data-sources.md), [../operations/operator-runbook.md](../operations/operator-runbook.md), [../operations/hermes-agent-persona.md](../operations/hermes-agent-persona.md)
- Launch scripts: `scripts/*.bat`
- Dashboard: `http://127.0.0.1:8787` via `scripts/run-dashboard.bat`
- Hermes runtime: `external/hermes-agent`, configured through `scripts/run-hermes.bat`
- Hermes project toolset: `.hermes/plugins/traderv1_operator`
- Dust/SOL calibration note: [reports/dust-sol-calibration-note.md](reports/dust-sol-calibration-note.md)

Current result: local launch and inspection are wired. Stage 3 remains not accepted until a real observation-only calibration window passes.

## V2 Agentic Token/Wallet Foundation

V2 Sprint 1 adds the first agentic research foundation on top of Stage 2. Scripts remain evidence producers; `TokenAgentDecision`, `TokenTradeCorpus`, `WalletTokenOutcome`, `AgentWalletReview`, and `WalletForwardContribution` are auditable V2 artifacts for token and wallet intelligence. Hermes now has safe typed token/wallet tools, but Sprint 1 still forbids paper orders, trading decisions, live execution, private keys, signers, swaps, DEX transaction construction, raw-SQL mutation, and direct risk/accounting mutation.

- Progress note: [v2-sprint-1-agentic-token-wallet-foundation.md](v2-sprint-1-agentic-token-wallet-foundation.md)

Current result: V2 Sprint 1 is implemented and fixture-tested. Real wallet-history completeness remains source-limited and must be treated honestly as partial or insufficient until deeper sources and Sprint 2 forward paper/shadow evidence exist.

## V2 Hermes Orchestrator And Paper/Shadow Path

V2 Sprint 2 upgrades Hermes from token/wallet-only research assistant to Trading Research Director for safe paper/shadow research. Hermes can now record auditable `AgentTradingDecision` rows, consume tracked wallet buy/sell signal events, create `Signal` or `NoTradeSignal` through typed tools, request deterministic risk checks, request guarded paper orders/fills, request exit decisions and exit fills, create post-trade review/memory proposals, and produce a first wallet contribution draft/report.

- Progress note: [v2-sprint-2-hermes-orchestrator-paper-shadow-path.md](v2-sprint-2-hermes-orchestrator-paper-shadow-path.md)

Current result: V2 Sprint 2 is implemented and fixture-tested end to end. The smoke path proves safe orchestration boundaries, not real tracked-wallet profitability. Real tracked-wallet source depth, adaptive polling, and continuous runtime are deferred to Sprint 3.
