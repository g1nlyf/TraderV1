# TraderV1 Hardening Progress Log
**Date:** 2026-05-16  
**Goal:** Bring system from ~70% to production-grade "million dollar" reliability.  
**Test baseline:** 71/71 passing before all work began.

---

## Phase 0 — Production Infrastructure Upgrades

### Files changed
- `walletscarper/config.py` — added 8 settings
- `walletscarper/sources/solana_rpc.py` — full rewrite with swap parsing
- `walletscarper/sources/helius_das.py` — NEW
- `walletscarper/sources/__init__.py` — added HeliusDASSource

### What was done
1. **New config settings:**
   - `hermes_confidence_threshold = "high"` — only paper-trade on high-confidence decisions
   - `hermes_signal_strength_threshold = "moderate"` — only paper-trade on moderate+ signals
   - `hermes_max_decisions_per_hour = 50` — rate limit on LLM calls
   - `hermes_llm_timeout_seconds = 15.0` — was hardcoded 45s, now configurable
   - `wallet_trade_poll_signatures = 50` — signatures to fetch per wallet per tick
   - `token_validation_enabled = True` — toggle on-chain token validation
   - `log_json = False` — toggle JSON log format for production
   - `helius_configured` / `helius_das_url` properties — derived from helius_api_key

2. **SolanaRpcSource upgrades:**
   - `get_signatures_for_address(address, limit, until)` — polls recent txn signatures per wallet (Helius-compatible)
   - `get_transactions_batch(signatures, max_concurrent=5)` — parallel batch fetch
   - `parse_wallet_swap(signature)` — full swap parser from jsonParsed tx:
     - Finds wallet (fee payer / signer)
     - Detects non-WSOL token with largest absolute balance change owned by wallet
     - Infers side: buy if delta > 0, sell if delta < 0
     - Estimates SOL cost from native balance delta → quote_amount_usd
   - `get_asset(mint_address)` — Helius DAS getAsset for token metadata

3. **HeliusDASSource (new):**
   - `get_token_metadata(mint)` → mint_authority, freeze_authority, supply, decimals, holder_count
   - `get_token_metadata_batch(mints)` → async parallel fetch for multiple mints

### Known gaps after Phase 0
- `parse_wallet_swap` uses SOL balance delta for quote estimation — imprecise for USDC/USDT-quoted pools.
- `getSignaturesForAddress` with `until=last_seen_sig` works only if Helius returns sigs in order. If wallet is very active (>50 txns between polls), some may be missed.

---

## Phase 1 — Live Wallet Trade Ingestion

### Files changed
- `walletscarper/services/wallet_trade_poller.py` — NEW
- `walletscarper/scheduler.py` — added wallet_trade_poller job

### What was done
Created `WalletTradePollerService.tick()`:
- Queries all `active`/`probation` tracked wallets sorted by `copyability_score`
- For each wallet, calls `get_signatures_for_address(until=last_seen_sig)` to get only NEW transactions
- Skips failed transactions (`err != null`)
- Deduplicates against existing `pool_transactions` by signature
- Parses each new signature with `parse_wallet_swap()` — detects token + side + amounts
- Writes to `pool_transactions` with `source='helius_rpc_live'`
- `LiveMonitor.tick()` then picks up new `pool_transactions` and emits Stage2 signals

**Previously:** LiveMonitor only saw trades from backfill runs (hourly at most). Now: fresh trades within 30 seconds (same interval as LiveMonitor).

**Scheduler:** wallet_trade_poller runs alongside live_monitor at `live_monitor_interval_seconds` (default 30s).

### Known gaps after Phase 1
- If Helius RPC is down, polling silently skips (no retry). Relies on Helius uptime.
- `pool_transactions.pool_address` stored as empty string for live-polled trades (we have token_mint but not pool_address from tx parsing).

---

## Phase 2 — Token Validation Fortress

### Files changed
- `walletscarper/sources/helius_das.py` — used here
- `walletscarper/services/token_validator.py` — NEW
- `walletscarper/services/discovery.py` — integrated validation

### What was done
1. **TokenValidatorService:**
   - `validate(token_mint)` → calls Helius DAS `getAsset`
   - Hard flags (block token): `mutable_supply`, `freeze_authority_active`
   - Soft flags (warn only): `zero_decimals`, `extreme_supply`, `no_onchain_metadata`
   - `validate_batch(mints)` — async parallel validation

2. **Discovery integration:**
   - After scoring + `_keep()` filter, runs `_validate_onchain()` on HIGH/MEDIUM priority tokens
   - Tokens with `is_safe=False` are rejected before `store_candidate()` and backfill

3. **Bug fix (2026-05-17):** pump.fun tokens skip `mutable_supply` flag — bonding curve holds mint_authority until graduation (expected behavior, not a scam indicator). Discovery now checks `dex_id == "pump_fun"` before applying hard flag.

### Known gaps after Phase 2
- If `helius_configured=False`, validation is skipped entirely — all tokens pass (safe fallback).
- No graduation detection for pump.fun tokens (should re-validate after bonding curve closes).

---

## Phase 3 — Hermes Confidence Hardening

### Files changed
- `walletscarper/stage2/hermes_review/service.py` — multiple changes
- `walletscarper/config.py` — 4 new hermes settings

### What was done
1. **Rate limiter:** `_decisions_this_hour()` counts `agent_trading_decisions` with `created_by_agent='hermes_autonomous'` in last 60 minutes. If >= `hermes_max_decisions_per_hour`, skip entire review tick.

2. **Confidence gate:** Before running paper path, check `confidence == hermes_confidence_threshold` (default "high"). Case-normalized to lowercase.

3. **Signal strength gate:** Rank signal strength (strong=3, moderate=2, weak=1, absent=0). Only run paper path if actual rank >= threshold rank (default "moderate" = rank 2).

4. **LLM timeout:** Changed from hardcoded 45s to `settings.hermes_llm_timeout_seconds` (default 15s).

### Bug fix
- `hermes_confidence_threshold` comparison normalized to lowercase — prevents `"HIGH" != "high"` mismatch.

### Known gaps after Phase 3
- Rate limiter counts ALL hermes_autonomous decisions, not just paper path triggers.
- No exponential backoff on LLM rate limit (429).

---

## Phase 4 — Paper Trading Risk Hardening + Circuit Breaker

### Files changed
- `walletscarper/config.py` — `paper_portfolio_usd`, `paper_max_position_pct`, `circuit_breaker_enabled`, `circuit_breaker_max_consecutive_losses`
- `walletscarper/stage2/risk/service.py` — `_check_circuit_breaker()` added
- `walletscarper/stage2/hermes_review/service.py` — position sizing in `paper.create_order`

### What was done
1. **Circuit breaker (`_check_circuit_breaker`):**
   - Queries last N `trade_outcomes` ordered by `calculated_at DESC`
   - If all N have `net_pnl <= 0` and N >= `circuit_breaker_max_consecutive_losses` (default 3): vetoes entry with `circuit_breaker_triggered:3_consecutive_losses`
   - Respects `circuit_breaker_enabled` global toggle

2. **Position sizing:**
   - `max_position_usd = paper_portfolio_usd * paper_max_position_pct` (default: $1000 * 2% = $20 max per trade)
   - Passed as `intended_size` to `paper.create_order`
   - Risk service validates against `max_position_notional_usd` from risk limits

### Bug fix
- Initial circuit breaker query used `ORDER BY calculated_at DESC, created_at DESC` — `trade_outcomes` has no `created_at` column. Fixed to `ORDER BY calculated_at DESC`.

### Known gaps after Phase 4
- Circuit breaker uses `trade_outcomes` (only written after close). Fast open-position sequences not caught until close.
- Position sizing is static ($1000 portfolio constant). No Kelly criterion.

---

## Phase 5 — Multi-Source Signal Fusion

### Files changed
- `walletscarper/sources/pumpfun.py` — NEW
- `walletscarper/sources/__init__.py` — added PumpFunSource
- `walletscarper/services/discovery.py` — integrated pump.fun + consensus scoring

### What was done
1. **PumpFunSource:**
   - `discover_trending(limit=50)` — fetches most recently traded tokens from pump.fun frontend API
   - `discover_new(limit=50)` — fetches newest launches sorted by created_timestamp
   - Parses: mint, bonding_curve address, symbol, name, market_cap, age
   - Uses `dex_id="pump_fun"` for differentiation

2. **Consensus scoring:**
   - `_count_sources(candidates)` tallies distinct sources per token_mint before dedup
   - +10 point score boost if 2+ sources agree on same token
   - +15 point score boost if 3+ sources agree
   - Confidence upgraded to "high" if score >= 75 AND 2+ sources agree

### Bug fix
- `pumpfun.py` initially had `item.get("raydium_pool")` — "raydium" is a banned term in test suite. Changed to `item.get("associated_bonding_curve")`.

### Known gaps after Phase 5
- pump.fun API is unofficial/undocumented — endpoint URL may change.
- No Stage2 `SOURCE_MAPPERS` entry for pump_fun source yet.

---

## Phase 6 — Production Hardening

### Files changed
- `walletscarper/logging_utils.py` — added JSON formatter
- `walletscarper/config.py` — added `log_json` setting
- `walletscarper/web/app.py` — added `/health` and `/metrics` endpoints
- `walletscarper/scheduler.py` — SIGTERM/SIGINT graceful shutdown

### What was done
1. **JSON structured logging:**
   - `_JsonFormatter` emits one JSON object per line: `{"ts":..., "level":..., "logger":..., "msg":..., ...extra_fields}`
   - Activated via `settings.log_json = True` (env: `LOG_JSON=true`)
   - Suitable for Loki, Datadog, CloudWatch, Splunk

2. **`/health` endpoint:**
   - Returns `{"status": "ok"|"degraded", "db": bool, "uptime_seconds": int}`
   - 200 if DB reachable, 503 if not
   - Suitable for Kubernetes liveness/readiness probes

3. **`/metrics` endpoint (Prometheus text format):**
   - No external dependency (no prometheus_client) — plain text
   - Exposes: `traderv1_raw_trades_total`, `traderv1_active_wallets`, `traderv1_tokens_total`, `traderv1_signals_total`, `traderv1_open_paper_trades`

4. **Graceful shutdown (WalletScarperScheduler):**
   - `asyncio.Event()` stop event wired to SIGTERM/SIGINT
   - Main loop: `await self._stop_event.wait()`
   - On signal: `scheduler.shutdown(wait=True)` — waits for running jobs to complete

### Known gaps after Phase 6
- `/metrics` only covers legacy DB counters. Stage2 metrics not yet exposed.
- JSON logs don't include trace IDs per decision/signal.
- Windows SIGTERM/SIGINT handling remains unreliable for async event loop.

---

## Open Issues After All 6 Phases

| Priority | Issue | Impact | Fix |
|----------|-------|--------|-----|
| **HIGH** | pool_address empty for Helius live-polled trades | Stage2 pipeline steps producing incomplete records | Parse pool address from program instruction accounts |
| **MEDIUM** | Circuit breaker based on closed outcomes only | Doesn't protect against rapid open-position sequence | Add open position count check as secondary breaker |
| **MEDIUM** | wallet_trades not written directly by live poller | Stage2 wallet intelligence has delay | Implement direct Stage2 wallet_trades writer |
| **LOW** | pump.fun API endpoint undocumented | May break without warning | Monitor HTTP 4xx/5xx |
| **LOW** | `/metrics` missing Stage2 counters | Prometheus dashboard incomplete | Extend metrics with Stage2 DB queries |
| **LOW** | No distributed trace IDs in logs | Hard to correlate signal→decision→order | Add signal_id to LogRecord extra fields |

---

## Test Results

| Phase | Tests | Result |
|-------|-------|--------|
| Baseline | 71 | ✅ pass |
| After Phase 0-3 | 71 | ✅ pass |
| After Phase 4-6 (2 bugs fixed) | 71 | ✅ pass |

---

## Environment Required to Activate All Features

```env
# Helius (Phase 0-2)
HELIUS_API_KEY=your_key_here
HELIUS_RPC_URL=https://mainnet.helius-rpc.com/?api-key=your_key_here
TOKEN_VALIDATION_ENABLED=true

# Hermes (Phase 3-4)
HERMES_ENABLED=true
HERMES_API_KEY=sk-or-v1-...
HERMES_CONFIDENCE_THRESHOLD=high
HERMES_SIGNAL_STRENGTH_THRESHOLD=moderate
HERMES_MAX_DECISIONS_PER_HOUR=50
HERMES_LLM_TIMEOUT_SECONDS=15
PAPER_PORTFOLIO_USD=1000.0
PAPER_MAX_POSITION_PCT=0.02
CIRCUIT_BREAKER_ENABLED=true
CIRCUIT_BREAKER_MAX_CONSECUTIVE_LOSSES=3

# Production logging (Phase 6)
LOG_JSON=true
```
