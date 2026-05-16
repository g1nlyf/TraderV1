# V2 Sprint 1 - Agentic Token And Wallet Intelligence Foundation

Status: implemented as a V2 foundation layer on top of Stage 2. The implementation is fixture-tested and migration/tool-smoke-tested. It is not real-source-depth-tested for complete wallet history.

## Implemented

- Migration 9 adds V2 tables: `token_agent_decisions`, `token_trade_corpora`, `wallet_token_outcomes`, `agent_wallet_reviews`, `wallet_forward_contributions`, `active_token_sessions`, and `agent_trading_decisions`.
- Agent decision/review/corpus/outcome/forward-contribution rows are append-only through SQLite triggers.
- `TokenAgentDecision` storage supports `reject`, `passive_watch`, `deep_parse`, `active_watch`, and `archive`, with reasons, uncertainties, requested tools, evidence refs, confidence, expiration, and creator.
- `TokenTradeCorpus` builds the best available token/pool corpus from Stage 2 `wallet_trades` and `market_snapshots`, with legacy `pool_transactions` as adapter evidence when Stage 2 trades are absent.
- Wallet candidates can be extracted from a token corpus with buy/sell counts, source refs, data sufficiency, and quality flags.
- `WalletTokenOutcome` uses deterministic FIFO historical estimates for realized PnL, ROI, ROI bucket, notional, entry/exit timing, holding seconds, and review eligibility.
- V2 wallet history profiling reports PnL estimate, win rate estimate, closed trade count, average win/loss, payoff ratio, holding and sizing summaries, one-token concentration, bot-like flags, copyability flags, source quality, and data sufficiency.
- `AgentWalletReview` stores `elite`, `probation`, `watch`, `reject`, and `archive` decisions with ratings, why yes, why no, observed behavior, inferred behavior, unknowns, demotion triggers, evidence refs, and data sufficiency.
- Insufficient wallet history clears inferred behavior and stores explicit unknowns such as `interesting wallet, insufficient data`.
- `WalletForwardContribution` placeholder service stores zero counts and null forward metrics with `sprint1_no_forward_metrics_fabricated`.
- Safe V2 Hermes tools were added through the `traderv1_operator` plugin and `stage2-v2-tool` CLI:
  - `token.scan_universe`
  - `token.get_profile`
  - `token.request_deep_parse`
  - `token.record_agent_decision`
  - `wallet.extract_from_token`
  - `wallet.profile_history`
  - `wallet.get_metrics`
  - `wallet.record_agent_review`
  - `wallet.list_elite`
- Hermes persona docs and prompt now define Sprint 1 as token/wallet intelligence only.

## Partial

- Corpus coverage is honest and source-limited. Small samples and market-only corpora are marked `partial` or `insufficient`.
- Broader wallet profiling is only as complete as available Stage 2 reconstructed trades. It does not claim stable wallet personality from weak samples.
- Token market fields such as holder concentration, route quality, spread, volume growth windows, transaction growth windows, and buy/sell balance are exposed only where existing evidence already carries them. Missing fields remain unknown through quality flags and partial sufficiency.
- `active_token_sessions` and `agent_trading_decisions` are schema foundations only.

## Blocked

- Full wallet-history depth is blocked when free/current sources do not provide enough transaction coverage.
- Real-source wallet personality modeling is intentionally blocked until source depth and forward paper/shadow results exist.

## Fixture-Tested Only

- Token corpus from Stage 2 fixture wallet trades and fixture market snapshots.
- Wallet extraction and deterministic token-level FIFO outcomes.
- Weak-history wallet profile behavior.
- All wallet review decisions.
- Forward contribution placeholder behavior.
- V2 typed tool responses and blocked-tool response shape.

## Real-Source-Tested

- None in this sprint. Validation used empty smoke databases and fixture trade evidence.

## Deferred To Sprint 2

- Active market loop.
- Adaptive market-data cadence for active tokens and open positions.
- Hermes trading orchestration.
- Paper/shadow order creation from Hermes decisions.
- `Signal`, `RiskCheck`, `PaperOrder`, `PaperFill`, and `TradeOutcome` creation from V2 agent decisions.
- Forward wallet contribution metrics from real paper/shadow results.

## Validation Results

- `.\.venv\Scripts\python.exe -m pytest tests\test_v2_sprint1_agentic_token_wallet_foundation.py -q`: 5 passed.
- `.\.venv\Scripts\python.exe -m pytest -q`: 64 passed.
- `.\.venv\Scripts\python.exe -m compileall walletscarper`: passed.
- `STAGE2_DATABASE_PATH=tmp\v2_sprint1_migration_smoke_final.sqlite3 python -m walletscarper stage2-migrate`: migration 9 applied.
- `STAGE2_DATABASE_PATH=tmp\v2_sprint1_migration_smoke_final.sqlite3 python -m walletscarper project-health-check`: database connectivity ok, migration status current, versions 1-9 applied.
- `STAGE2_DATABASE_PATH=tmp\v2_sprint1_tool_smoke_final.sqlite3 python -m walletscarper stage2-v2-tool token.scan_universe`: structured JSON returned; empty smoke DB produced zero candidates and no trading decisions.
- `STAGE2_DATABASE_PATH=tmp\v2_sprint1_tool_smoke_final.sqlite3 python -m walletscarper stage2-v2-tool wallet.list_elite --payload-json "{}"`: structured JSON returned; empty elite list with `no_elite_wallets_recorded`.

## Dangerous-Term Scan

- Broad runtime scan found expected pre-existing Stage 2 paper/risk/evaluation modules and legacy swap/source parsing terminology.
- Focused scan over new V2 token/wallet/Hermes-plugin surfaces returned no matches for private keys, signers, DEX transaction construction, live execution, raw SQL, or direct paper/risk/outcome mutation terms.

## Remaining Risks

- Free data sources may not provide enough historical wallet transaction depth.
- Token trade corpora can be partial when only snapshots or incomplete buy/sell paths exist.
- Source-rate limits may require adaptive cadence in Sprint 2 before any active market loop is credible.
- Historical wallet PnL remains candidate evidence only and is not a proof of future edge.

## Safety Confirmation

Sprint 1 added no live execution, private-key handling, signer path, swap adapter, DEX transaction construction, raw-SQL Hermes mutation, or Hermes path that creates `Signal`, `RiskCheck`, `PaperOrder`, `PaperFill`, or `TradeOutcome`.
