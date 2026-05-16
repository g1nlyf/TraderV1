# V2 Sprint 2 - Hermes Orchestrator And Safe Paper/Shadow Path

Date: 2026-05-16

Status: implemented as a safe fixture-tested paper/shadow orchestration path. Real tracked-wallet source depth is still not proven by this sprint.

## Implemented

- Added migration 10, `v2_sprint2_hermes_orchestrator_paper_shadow_schema`.
- Added append-only V2 Sprint 2 tables:
  - `tracked_wallet_signal_events`
  - recreated/extended `agent_trading_decisions`
  - `agent_trading_decision_artifact_links`
  - `wallet_contribution_reports`
- Added append-only triggers for tracked wallet signals, Hermes trading decisions, artifact links, and wallet contribution reports.
- Extended `agent_trading_decisions` to support:
  - `signal`
  - `no_trade`
  - `wait`
  - `exit`
  - `downgrade_wallet`
  - `downgrade_token`
- Added a tracked wallet signal intake service for buy/sell events with source refs, latency metadata, cluster/correlation refs, input mode, data sufficiency, and quality flags.
- Added an orchestrator service for auditable Hermes decisions and artifact linking.
- Added safe typed V2 Hermes tools for:
  - `wallet.record_signal_event`
  - `agent.record_trading_decision`
  - `signal.create`
  - `signal.create_no_trade`
  - `risk.check_entry`
  - `paper.create_order`
  - `paper.simulate_fill`
  - `paper.create_exit_decision`
  - `risk.check_exit`
  - `paper.execute_exit`
  - `review.create_post_trade`
  - `memory.propose`
  - `metrics.wallet_report`
- Added a fixture orchestrator smoke CLI:
  - `python -m walletscarper stage2-v2-orchestrator-smoke --mode fixture`
- Updated Hermes persona from Sprint 1 token/wallet-only mode to Trading Research Director mode for paper/shadow research.
- Added targeted Sprint 2 tests for tracked wallet signals, Hermes decisions, signal/no-trade paths, risk/order/fill gates, exit/outcome gates, review/memory links, wallet contribution reports, and tool safety invariants.

## Paper/Shadow Path Proven By Fixture Smoke

The fixture smoke validates this controlled path:

1. tracked wallet buy signal
2. `AgentTradingDecision(signal)`
3. `Signal`
4. `TradeThesis`
5. deterministic entry `RiskCheck`
6. guarded `PaperOrder`
7. conservative entry `PaperFill`
8. `PaperPosition`
9. tracked wallet sell signal
10. `AgentTradingDecision(exit)`
11. `ExitDecision`
12. deterministic exit `RiskCheck`
13. exit `PaperFill`
14. deterministic `TradeOutcome`
15. post-trade review
16. memory proposal
17. wallet contribution draft/report

Hermes records reasoning and requests approved tools. Deterministic services still own risk checks, paper ledger mutation, fills, positions, and outcome/P&L calculation.

## Partial

- Tracked wallet signal intake supports `real_source`, `fixture`, and `smoke` modes, but validation used fixture/smoke inputs only.
- Wallet forward contribution reporting can compute draft metrics only from actual linked paper outcomes. With no forward outcomes, it returns insufficient evidence instead of fabricating metrics.
- Cluster/correlation refs are stored and flagged so correlated signals are not treated as independent confirmations, but full clustering intelligence remains a later runtime/data-source concern.
- `agent_trading_decisions` preserves Sprint 1 legacy rows by migrating them to `agent_trading_decisions_sprint1_legacy` before recreating the stronger Sprint 2 table.

## Blocked Or Source-Limited

- Real tracked-wallet buy/sell stream quality was not proven in Sprint 2.
- Real source latency and completeness were not proven in Sprint 2.
- Free-source wallet history limits still apply from Sprint 1. Weak wallet history must stay explicit as partial or insufficient data.

## Fixture-Tested Only

- End-to-end orchestrator paper/shadow path.
- Tracked wallet buy/sell event intake.
- Agent trading decisions for entry and exit.
- Signal creation from Hermes decision.
- Risk-gated paper order and fill path.
- Exit decision, exit risk, exit fill, deterministic outcome.
- Post-trade review and memory proposal.
- Wallet contribution draft report with one fixture outcome.

## Real-Source-Tested

No new Sprint 2 tracked-wallet orchestration behavior was validated against real source events in this implementation pass.

The existing source adapters remain available as evidence producers, but this sprint's validation proves the safe orchestration contract, not real-world signal profitability or source completeness.

## Intentionally Deferred To Sprint 3

- Continuous runtime daemon.
- Adaptive high-frequency active market loop.
- 24/7 wallet tracking workers.
- Adaptive polling priority for ordinary tokens, active tokens, and open positions.
- Full runtime scheduling/backpressure when free sources cannot sustain requested frequency.
- Real-source tracked-wallet stream hardening.
- Promotion from fixture/smoke orchestration to sustained shadow observation windows.

## Validation Results

Commands were run from `WalletScarper` unless noted.

- `.\.venv\Scripts\python.exe -m pytest tests\test_v2_sprint2_hermes_orchestrator_paper_shadow_path.py -q`
  - Result: passed, 5 tests.
- `.\.venv\Scripts\python.exe -m pytest -q`
  - Result: passed, 69 tests.
- `.\.venv\Scripts\python.exe -m compileall walletscarper`
  - Result: passed.
- `STAGE2_DATABASE_PATH=..\tmp\v2_sprint2_migration_smoke_final.sqlite3 .\.venv\Scripts\python.exe -m walletscarper stage2-migrate`
  - Result: Stage 2 migrations applied through version 10.
- `STAGE2_DATABASE_PATH=..\tmp\v2_sprint2_migration_smoke_final.sqlite3 .\.venv\Scripts\python.exe -m walletscarper project-health-check`
  - Result: `database_connectivity=ok`, `migration_status=current`, migrations 1 through 10 applied.
- `STAGE2_DATABASE_PATH=..\tmp\v2_sprint2_orchestrator_smoke_final.sqlite3 .\.venv\Scripts\python.exe -m walletscarper stage2-v2-orchestrator-smoke --mode fixture`
  - Result: `ok=true`; created entry decision, signal, thesis, entry risk, paper order, entry fill, position, exit decision, exit risk, exit fill, deterministic outcome, post-trade review, memory proposal, and wallet report.
- `STAGE2_DATABASE_PATH=tmp\v2_sprint2_tool_agent_smoke_ok.sqlite3 python -m walletscarper stage2-v2-tool agent.record_trading_decision --payload-json <escaped-json>`
  - Result: `ok=true`; missing evidence became an uncertainty/quality flag instead of a fabricated conclusion.

## Dangerous Scan Results

Scan scope:

- `WalletScarper/walletscarper/stage2/orchestrator`
- `WalletScarper/walletscarper/stage2/hermes_integration/v2_tools.py`
- `.hermes/plugins/traderv1_operator`
- `config/hermes`

Strict scan terms:

- `private key`
- `private_key`
- `signer`
- `dex transaction`
- `live execution`
- `live_execution`
- `swap adapter`
- `raw sql`
- `secret`
- `seed phrase`
- `mnemonic`

Result:

- No runtime implementation matches for private keys, signers, swaps, DEX transaction construction, raw SQL mutation, secrets, seed phrases, or mnemonics.
- The only strict-scan match was the Hermes prompt prohibition line that forbids private keys, signers, swap adapters, DEX transaction construction, and live execution paths.
- Broad scan found expected references to paper orders, paper fills, trade outcomes, and canonical P&L in the approved deterministic service/tool boundaries and safety text.

## Remaining Risks

- Fixture success does not prove real tracked-wallet edge.
- Wallet contribution metrics become meaningful only after forward paper/shadow outcomes accumulate from real observation windows.
- Source rate limits and data gaps must be handled by Sprint 3 adaptive scheduling and honest degradation.
- Hermes decisions must continue to be treated as auditable research synthesis, not as deterministic risk approval.

## Safety Confirmation

Sprint 2 did not add live execution, private-key handling, signer paths, swap adapters, DEX transaction construction, raw-SQL Hermes mutation, direct Hermes ledger mutation, or direct Hermes canonical P&L calculation.

Paper orders remain blocked without passed deterministic entry risk. Exit fills remain blocked without an exit decision and passed deterministic exit risk. Trade outcomes remain calculated by deterministic evaluation services.
