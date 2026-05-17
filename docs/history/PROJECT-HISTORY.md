# TraderV1 — Project History

Full chronological record of what was built, when, and what tests passed at each milestone.

---

## System Versioning

The project went through three major architectural phases:

| Phase | Name | Core Idea | Test Baseline |
|-------|------|-----------|---------------|
| Stage 1 / V1.0 | Legacy Scraper | Collect wallet + token data | Pre-Stage 2 |
| Stage 2 / V1.5 | Deterministic Core | Immutable paper trading ledger | 71 tests |
| V2.0 Sprint 1-2 | AI Orchestration | Hermes + token/wallet intelligence | 71 tests |
| V2.0 Hardening | Production Grade | Helius, validation, prod infra | 71 tests |

---

## Stage 1: Legacy Scraper (V1.0)

**Goal:** Build the data foundation — discover tokens, track wallets, collect transactions.

**What was built:**
- `WalletScarper` Python service — APScheduler-based, runs discovery + wallet scoring
- DexScreener, GeckoTerminal, DexPaprika, Bitquery adapters
- `pool_transactions` ingestion (744k+ rows accumulated)
- `tracked_wallets` table — 38 wallets identified as high-quality copy candidates
- Wallet scoring: P&L, win rate, payoff ratio, consistency
- SQLite local database, custom migration system
- `run-once` command for single discovery cycle

**Outcome:** 744k+ transactions, 38 tracked wallets, 22k+ wallet scores. Data collection working. No trading logic yet.

---

## Stage 2: Deterministic Core (V1.5)

**Goal:** Build an immutable, auditable paper-trading ledger that can't be manipulated by LLMs.

**Sprints completed:**

### Sprint 1 — Foundation
- Stage 2 SQLite database, migrations 1-4
- `RawSourceEvent` ingestion + append-only ledger
- `MarketSnapshot` (price, liquidity, confidence, quality flags)
- `RiskLimitSnapshot`, `ConfigSnapshot`

### Sprint 2 — Data & Wallet Intelligence
- `WalletIntelligenceService` — P&L, win rate, payoff ratio, holding time
- `TokenIntelligenceService` — evidence-quality-aware normalization
- `source_registry`, `source_latency_samples`
- Migrations 5-7

### Sprint 3 — Signal, Risk, Paper
- `tracked_wallet_signal_events` — wallet buy/sell signal intake
- `signals` — agent-proposed trade ideas
- `DeterministicRiskService` — entry/exit/monitoring risk checks, 7 veto types
- `paper_positions` — immutable paper position ledger
- `trade_outcomes` — P&L, fees, slippage, fill quality
- `PaperTradingService` — create order, simulate fill, execute exit
- Risk veto types: `missing_market_snapshot`, `stale_market_snapshot`, `missing_market_price`, `insufficient_liquidity`, `low_market_snapshot_confidence`, `excessive_estimated_slippage`, `max_position_notional_exceeded`, `existing_open_position_conflict`, `max_open_paper_positions_exceeded`
- Migration 8

### Sprint 4 — Parallel Strategy + Memory
- `EvaluationService` — net expectancy, win rate, drawdown, payoff ratio
- `StrategyVersion` + hypothesis tracking
- `MemoryService` — curated learning proposals, promotion/demotion
- `PostTradeReviewService`
- `agent_wallet_reviews`
- Migrations 9-10

### Sprint 5 — Hardening + Acceptance
- `stage2-final-acceptance` CLI — fixture replay acceptance gate
- `stage2-calibration-smoke`, `stage2-calibration-window`
- Shadow readiness gap analysis
- Acceptance result: `accepted_with_gaps`, shadow `gap_report_required`
- 71 tests defined, all passing

**Key design decisions made:**
- ADR-0001: Stage 2 release target (paper trading, not live)
- ADR-0002: Risk check before paper order (risk is sovereign)
- ADR-0003: No live execution (banned terms in test suite)
- ADR-0004: Job queue over free-form agent-to-agent communication
- ADR-0005: Browser data policy (no browser automation for data)

---

## V2.0: AI Orchestration Layer

**Goal:** Wire Hermes AI agent into the deterministic Stage 2 core to make autonomous paper trading decisions.

### V2.0 Sprint 1 — Token/Wallet Intelligence Foundation

**Status:** Complete (fixture mode). Data bridge was missing initially, fixed in Runtime Closure.

**What was built:**
- `Stage2IngestBridge` — connects discovery service to Stage 2 raw events
- `Stage2WalletSignalBridge` — connects LiveMonitor to Stage 2 signal events
- Token intelligence normalization pipeline: `raw_source_events → token_candidates → token_profiles → token_triage_decisions`
- `stage2-run-daemon` CLI — continuous Stage 2 scanning
- `Stage2ScannerService` — token/pool scan → wallet extraction → profiling
- `wallet.calculate_token_outcomes` V2 tool — ROI/PnL per wallet per token
- `wallet.profile_history` — fallback to legacy pool_transactions when Stage 2 sparse
- 24 V2 tools total implemented

**Data pipeline fix (2026-05-16 Runtime Closure):**
- Initially: `write_raw_source_event` only called in acceptance fixtures, not live pipeline
- Fix: `Pipeline.run_once()` now calls `Stage2IngestBridge` on every discovered token
- Fix: `LiveMonitor.tick()` now calls `Stage2WalletSignalBridge` on every wallet signal
- Result: Real data started flowing into Stage 2

**Post-fix live baseline:**
- 103 raw_source_events
- 86 token_candidates, 48 token_profiles, 28 trade_corpora
- 866 wallet_token_outcomes
- 9 tracked_wallet_signal_events (7 real_source)

### V2.0 Sprint 2 — Hermes Orchestrator

**Status:** Complete in fixture mode. Not validated on real signals.

**What was built:**
- `HermesSignalReviewService` — autonomous review loop: signal → LLM → decision → paper path
- `HermesOrchestratorService` — full audit trail
- `agent.record_trading_decision` V2 tool — records LLM decisions
- `signal.create` V2 tool — creates signal from decision
- Full orchestration path verified in smoke test: signal → risk → paper → exit → review → memory
- All 24 V2 tools verified working in fixture mode
- Hermes CLI agent (`external/hermes-agent`) configured with `traderv1_operator` plugin

**Gap remaining:** 7 real wallet signals exist. Zero have been reviewed by autonomous loop. See `HERMES-REALITY.md`.

### V2.0 Sprint 3 — Adaptive Market Loop

**Status:** NOT STARTED.

**What was planned:**
- `ActiveTokenSession` lifecycle service
- Adaptive cadence policy (poll open positions more frequently than research candidates)
- Priority queue for market polling
- Continuous worker daemon that combines scheduler + Hermes sessions
- Sprint 3 acceptance gates

**Why not started:** Priority was infrastructure hardening (Phase 0-6) to make the existing pipeline production-grade before extending it.

---

## Hardening Phase 0-6 (2026-05-16)

Goal: Bring system from ~70% to "million dollar" production-grade reliability.

### Phase 0 — Production Infrastructure

**Files:** `config.py`, `sources/solana_rpc.py` (rewrite), `sources/helius_das.py` (NEW)

- 8 new config settings: `hermes_confidence_threshold`, `hermes_signal_strength_threshold`, `hermes_max_decisions_per_hour`, `hermes_llm_timeout_seconds`, `wallet_trade_poll_signatures`, `token_validation_enabled`, `log_json`, `helius_configured`, `helius_das_url`
- SolanaRpcSource: `get_signatures_for_address`, `get_transactions_batch`, `parse_wallet_swap`, `get_asset`
- HeliusDASSource (new): `get_token_metadata`, `get_token_metadata_batch`

### Phase 1 — Live Wallet Trade Ingestion

**Files:** `services/wallet_trade_poller.py` (NEW), `scheduler.py`

- `WalletTradePollerService.tick()`: polls tracked wallets via Helius `getSignaturesForAddress(until=last_seen_sig)`
- Writes to `pool_transactions` with `source='helius_rpc_live'`
- Runs every 30s alongside LiveMonitor

### Phase 2 — Token Validation Fortress

**Files:** `sources/helius_das.py`, `services/token_validator.py` (NEW), `services/discovery.py`

- Hard flags: `mutable_supply` (mint_authority not null), `freeze_authority_active`
- Soft flags: `zero_decimals`, `extreme_supply`, `no_onchain_metadata`
- Integration: HIGH/MEDIUM tokens validated before storage
- Fix applied: pump.fun tokens skip `mutable_supply` flag (bonding curve = expected behavior)

### Phase 3 — Hermes Confidence Hardening

**Files:** `stage2/hermes_review/service.py`, `config.py`

- Rate limiter: max 50 decisions/hr
- Confidence gate: must equal `hermes_confidence_threshold` (default "high") — lowercase normalized
- Signal strength gate: must be >= `hermes_signal_strength_threshold` (default "moderate")
- LLM timeout: `hermes_llm_timeout_seconds` (default 15s, was 45s hardcoded)

### Phase 4 — Circuit Breaker + Position Sizing

**Files:** `config.py`, `stage2/risk/service.py`, `stage2/hermes_review/service.py`

- `_check_circuit_breaker()`: last N outcomes all net_pnl ≤ 0 → veto `circuit_breaker_triggered:N_consecutive_losses`
- Toggle: `CIRCUIT_BREAKER_ENABLED=true`, `CIRCUIT_BREAKER_MAX_CONSECUTIVE_LOSSES=3`
- Position sizing: `paper_portfolio_usd * paper_max_position_pct` (default $1000 × 2% = $20/trade)
- Risk service validates against `max_position_notional_usd` from risk limits

### Phase 5 — Multi-Source Signal Fusion

**Files:** `sources/pumpfun.py` (NEW), `sources/__init__.py`, `services/discovery.py`

- `PumpFunSource.discover_trending(50)` + `discover_new(50)`
- Consensus scoring: +10 boost for 2+ sources, +15 for 3+
- Confidence upgraded to "high" if score ≥ 75 AND 2+ sources agree

### Phase 6 — Production Hardening

**Files:** `logging_utils.py`, `config.py`, `web/app.py`, `scheduler.py`

- `_JsonFormatter`: `{"ts", "level", "logger", "msg", ...extra}` per line
- `/health`: `{"status":"ok"|"degraded", "db":bool, "uptime_seconds":int}` — 200/503
- `/metrics`: Prometheus text format — 5 counters (no prometheus_client dep)
- SIGTERM/SIGINT graceful shutdown: `asyncio.Event` + `scheduler.shutdown(wait=True)`

**Bugs fixed during hardening:**
1. `pumpfun.py` had the word "raydium" (banned term test) — changed to `associated_bonding_curve`
2. Circuit breaker query used `created_at` column that doesn't exist in `trade_outcomes` — changed to `ORDER BY calculated_at DESC`

**Test result after all phases:** 71/71 passing

---

## Test History Snapshot

| Milestone | Tests | Result | Date |
|-----------|-------|--------|------|
| Stage 2 baseline | 71 | ✅ all pass | 2026-05-15 |
| V2.0 Sprint 1-2 | 71 | ✅ all pass | 2026-05-16 |
| After V2.0 Audit + Runtime Closure | 71 | ✅ all pass | 2026-05-16 |
| After Hardening Phase 0-3 | 71 | ✅ all pass | 2026-05-16 |
| After Hardening Phase 4-6 (2 bug fixes) | 71 | ✅ all pass | 2026-05-16 |
| Current | 71 | ✅ all pass | 2026-05-17 |
