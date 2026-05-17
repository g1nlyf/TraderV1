# TraderV1 — Current System Status

**Last updated:** 2026-05-17  
**Tests:** 71/71 passing  
**Git:** `https://github.com/g1nlyf/TraderV1` (main)

---

## TL;DR

The system has a working data pipeline, a complete deterministic paper-trading ledger, and a wired-but-untested autonomous AI review loop. It has **never made an autonomous paper trade decision from a real market signal**. That is the primary gap. Everything else is infrastructure waiting for that moment.

---

## Component-by-Component Truth Table

### 1. Legacy Pipeline (Stage 1)

| Component | Status | Detail |
|-----------|--------|--------|
| WalletScarper venv | ✅ Working | `smoke-test` passes |
| Token discovery | ✅ Working | DexScreener + GeckoTerminal + DexPaprika + pump.fun |
| Pool transaction ingestion | ✅ Working | 744,633+ rows in `pool_transactions` |
| Wallet scoring | ✅ Working | 22,818+ wallet scores, completes in ~22s |
| Tracked wallets | ✅ Working | 38 tracked wallets (active/probation) |
| Helius live wallet polling | ✅ Working | `WalletTradePollerService` polls every 30s |
| Token validation (on-chain) | ✅ Working | Helius DAS, hard flags: `mutable_supply`, `freeze_authority_active` |
| Pump.fun source | ✅ Working | `PumpFunSource` discovers trending + new tokens |

**Known caveat:** pump.fun tokens have `mutable_supply` flag (bonding curve), but Phase 2 validator now skips this flag for `dex_id=pump_fun` tokens. Pool address is empty for Helius-polled trades (no pool address in raw tx data).

---

### 2. Stage 2 — Deterministic Core

| Component | Status | Detail |
|-----------|--------|--------|
| Database schema | ✅ Migrations 1-10 applied | SQLite, custom migrations (not Alembic) |
| Legacy → Stage 2 bridge | ✅ Wired | `Stage2IngestBridge` in discovery service |
| Wallet signal bridge | ✅ Wired | `LiveMonitor` → `Stage2WalletSignalBridge` |
| Raw source events | ✅ 103 rows | Real calibration + discovered candidates |
| Token candidates | ✅ 86 | From real discovery pipeline |
| Token profiles | ✅ 48 | Normalized, evidence-quality-aware |
| Trade corpora | ✅ 28 | Token-level trade evidence pools |
| Wallet-token outcomes | ✅ 866 | ROI/PnL per wallet per token |
| Tracked wallet signal events | ✅ 9 total, 7 real_source | Real buys/sells from tracked wallets |
| Signal creation | ✅ Functional | `signal.create` V2 tool |
| Risk checks (entry/exit) | ✅ Functional | `DeterministicRiskService`, 7 veto types |
| Paper orders | ✅ Functional | `paper.create_order`, fill simulation |
| Paper exits | ✅ Functional | `paper.execute_exit`, outcome calculated |
| Post-trade review | ✅ Functional | `review.create_post_trade` |
| Memory proposals | ✅ Functional | `memory.propose` |
| Circuit breaker | ✅ Wired | 3 consecutive losses → veto `circuit_breaker_triggered` |
| Position sizing | ✅ Wired | $1000 portfolio × 2% = $20 max/trade |

**Critical fact:** All Stage 2 deterministic tools are verified working in fixture mode (end-to-end smoke test passes). Zero real paper trades have been created from real signals.

---

### 3. V2.0 — AI Orchestration Layer

| Component | Status | Detail |
|-----------|--------|--------|
| 24 V2 Hermes tools | ✅ All implemented | Not stubs — real code behind each tool |
| Token Intelligence Service | ✅ Implemented | Normalizes raw events → candidates → profiles → triage |
| Wallet Intelligence Service | ✅ Implemented | P&L, win rate, payoff ratio, holding time, bot-flags |
| Hermes Orchestrator Service | ✅ Implemented | Audit trail: decisions → signal → risk → paper |
| `stage2-run-daemon` CLI | ✅ Exists | Continuous Stage 2 scanning loop |
| `Stage2ScannerService` | ✅ Implemented | Token/pool scan → wallet extraction → profiling |
| Sprint 3: Active Token Sessions | ❌ Not implemented | `active_token_sessions` table exists, no lifecycle |
| Sprint 3: Adaptive cadence | ❌ Not implemented | No priority queue, no market polling loop |
| Sprint 3: Continuous worker | ❌ Not implemented | Needs `stage2-run-daemon` + Hermes session combined |

---

### 4. Hermes AI Systems

> **See `HERMES-REALITY.md` for full detail. Summary:**

| System | Status | Has Made Real Decisions? |
|--------|--------|--------------------------|
| Hermes CLI agent (`scripts/run-hermes.bat`) | ✅ Configured, functional | Never run interactively by the operator |
| `HermesSignalReviewService` (autonomous loop) | ⚠️ Code complete, wired to scheduler | 0 decisions linked to 7 real signals |

The autonomous review loop (`HermesSignalReviewService`) calls OpenRouter API with model `openai/gpt-oss-20b:free`. It is gated behind `HERMES_ENABLED=true` and `HERMES_API_KEY` being set in `.env`. The OpenRouter key was added manually to `.env` by the operator (2026-05-16). The loop has not demonstrably processed any real signals yet.

---

### 5. Production Hardening (Completed 2026-05-16)

| Feature | Status | Detail |
|---------|--------|--------|
| JSON structured logging | ✅ Done | `LOG_JSON=true` → Loki/Datadog-compatible |
| `/health` endpoint | ✅ Done | `{"status":"ok"\|"degraded", "db":bool, "uptime_seconds":int}` |
| `/metrics` endpoint | ✅ Done | Prometheus text format, 5 counters (no external dep) |
| Graceful shutdown | ✅ Done | SIGTERM/SIGINT → `scheduler.shutdown(wait=True)` |
| Helius DAS integration | ✅ Done | Token metadata, batch validation |
| Wallet trade poller | ✅ Done | `getSignaturesForAddress` every 30s |
| Token validator | ✅ Done | Hard flags: mutable_supply, freeze_authority_active |
| Pump.fun discovery | ✅ Done | Trending + new token discovery |
| Multi-source consensus scoring | ✅ Done | +10/+15 boost for 2/3+ sources |

See `V2.0/HARDENING-PROGRESS-2026-05-16.md` for full phase-by-phase detail.

---

### 6. Test Suite

```
71/71 tests passing (2026-05-17)
Runtime: ~193 seconds

Key test groups:
  - test_stage2_foundation.py          — core invariants, no-live-execution check
  - test_stage2_shadow_readiness_gap_closure.py — fill/quote, append-only, schema
  - test_stage2_v2_*.py               — V2 tools, orchestration, token/wallet intelligence
```

Security test `test_no_live_execution_private_key_signer_swap_or_dex_path_added` scans ALL `.py` files for banned terms: `private_key, secret_key, seed phrase, signtransaction, sendtransaction, versionedtransaction, swap adapter, dex transaction, jupiter, raydium`. All clean.

---

## What Has Never Happened (Critical Gaps)

1. **Autonomous paper trade from real signal**: The system has 7 real wallet signal events. Zero have been reviewed by the LLM → zero have produced paper trades. The full decision path (`wallet signal → Hermes review → signal create → risk check → paper order`) has only been tested in fixture/smoke mode.

2. **Positive paper P&L from real market conditions**: No real paper trades = no real P&L. We have fixture-mode P&L only.

3. **Hermes CLI run interactively**: The operator has never opened `scripts/run-hermes.bat` and chatted with the Hermes agent.

4. **Shadow mode**: `stage2-final-acceptance` returns `accepted_with_gaps`, shadow status `gap_report_required`. Needs real quote observation windows.

5. **Sprint 3**: Adaptive Market Loop has not been implemented.

---

## Live Data State (2026-05-16 runtime baseline)

```
Legacy DB:
  pool_transactions:     744,633+
  tracked_wallets:       38
  wallet_scores:         22,818+
  tokens:                36+
  pools:                 40+

Stage 2 DB:
  raw_source_events:     103
  token_candidates:      86
  token_profiles:        48
  token_triage_decisions: (populated)
  token_trade_corpora:   28
  wallet_token_outcomes: 866
  tracked_wallet_signal_events: 9 (7 real_source, 2 fixture)
  agent_trading_decisions: fixture rows only
  paper_positions:       fixture rows only
  trade_outcomes:        fixture rows only
```

---

## How to Check Current State

```bash
# Run all tests
cd WalletScarper && python -m pytest tests/ -q

# Run pipeline + check Stage 2 population
python -m walletscarper run-once
python -m walletscarper stage2-v2-tool token.scan_universe

# Check health
curl http://127.0.0.1:8787/health

# Start Hermes CLI interactively (never been done — try it)
scripts/run-hermes.bat
```
