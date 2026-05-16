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
   - `parse_wallet_swap(signature)` — full Raydium/Orca swap parser from jsonParsed tx:
     - Finds wallet (fee payer / signer)
     - Detects non-WSOL token with largest absolute balance change owned by wallet
     - Infers side: buy if delta > 0, sell if delta < 0
     - Estimates SOL cost from native balance delta → quote_amount_usd
   - `get_asset(mint_address)` — Helius DAS getAsset for token metadata

3. **HeliusDASSource (new):**
   - `get_token_metadata(mint)` → mint_authority, freeze_authority, supply, decimals, holder_count
   - `get_token_metadata_batch(mints)` → async parallel fetch for multiple mints

### Known gaps after Phase 0
- `parse_wallet_swap` uses SOL balance delta for quote estimation — imprecise for USDC/USDT-quoted pools. For now acceptable; fix when needed.
- `getSignaturesForAddress` with `until=last_seen_sig` works only if Helius returns all sigs in order. If a wallet is very active (>50 txns between polls), some may be missed. Mitigation: increase `wallet_trade_poll_signatures`.

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
- `pool_transactions.pool_address` is stored as empty string for live-polled trades (we have token_mint but not pool_address from tx parsing). This means some Stage2 pipeline steps that require pool_address may produce incomplete records.
- No Stage2 `wallet_trades` direct write — relies on the existing wallet_extraction pipeline to eventually write to `wallet_trades` from `pool_transactions`. Direct write would be more efficient but requires raw_source_event FK chain.

---

## Phase 2 — Token Validation Fortress

### Files changed
- `walletscarper/sources/helius_das.py` — used here
- `walletscarper/services/token_validator.py` — NEW
- `walletscarper/services/discovery.py` — integrated validation

### What was done
1. **TokenValidatorService:**
   - `validate(token_mint)` → calls Helius DAS `getAsset`
   - Computes flags:
     - `mutable_supply` — mint_authority is not null (team can print more tokens → HARD FLAG)
     - `freeze_authority_active` — freeze_authority is not null (team can freeze wallets → HARD FLAG)
     - `zero_decimals` — unusual, worth flagging
     - `extreme_supply` — supply > 10^18, likely a rugpull indicator
     - `no_onchain_metadata` — DAS returned nothing (can't validate)
   - `is_safe = False` if any HARD FLAG present
   - `validate_batch(mints)` — async parallel validation

2. **Discovery integration:**
   - After scoring + `_keep()` filter, runs `_validate_onchain()` on HIGH/MEDIUM priority tokens
   - Tokens with `is_safe=False` are rejected before `store_candidate()` and backfill
   - LOW/REJECTED tokens skip validation (not worth API calls)
   - Logs count of rejected tokens per run

### Known gaps after Phase 2
- If Helius is not configured (`helius_configured=False`), validation is skipped entirely — all tokens pass. This is safe fallback behavior but means no on-chain protection.
- `no_onchain_metadata` flag does NOT block token (soft flag only). Some legitimate new tokens may not yet be indexed by Helius DAS. Hardening this gate would require a delay-and-retry.
- pump.fun bonding curve tokens have `mint_authority` set (expected — pump.fun controls supply until graduation). This means ALL pre-graduation pump.fun tokens will have `mutable_supply` flag and be REJECTED by the validator. **Action needed:** Add pump.fun bonding curve whitelist OR delay validation until after graduation.

---

## Phase 3 — Hermes Confidence Hardening

### Files changed
- `walletscarper/stage2/hermes_review/service.py` — multiple changes
- `walletscarper/config.py` — 4 new hermes settings

### What was done
1. **Rate limiter:** `_decisions_this_hour()` counts `agent_trading_decisions` with `created_by_agent='hermes_autonomous'` in last 60 minutes. If >= `hermes_max_decisions_per_hour`, skip entire review tick.

2. **Confidence gate:** Before running paper path, check `confidence == hermes_confidence_threshold` (default "high"). If confidence is "medium" or "low", decision is recorded but paper path is NOT triggered. Log reason.

3. **Signal strength gate:** Rank signal strength (strong=3, moderate=2, weak=1, absent=0). Only run paper path if actual rank >= threshold rank (default "moderate" = rank 2). Prevents trading on weak/absent signals even with high confidence.

4. **LLM timeout:** Changed from hardcoded `45` seconds to `settings.hermes_llm_timeout_seconds` (default 15s). Faster failure on hung LLM calls.

### Known gaps after Phase 3
- Rate limiter counts ALL hermes_autonomous decisions including no_trade/wait — not just paper path triggers. Could be refined to count only signal decisions if needed.
- No exponential backoff on LLM rate limit (429). If OpenRouter limits us, we skip the tick and retry in 15 minutes. For high-volume usage, implement backoff with jitter.
- `hermes_confidence_threshold` is a string comparison ("high"). If LLM returns unexpected value (e.g., "HIGH"), it won't match. Mitigation: normalize to lowercase in `_review_one_signal`.

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
   - Circuit breaker limit can be overridden per-trade via `risk_limit_snapshots.limits_json.circuit_breaker_max_consecutive_losses`
   - Respects `circuit_breaker_enabled` global toggle

2. **Position sizing:**
   - Hermes paper path now calculates `max_position_usd = paper_portfolio_usd * paper_max_position_pct` (default: $1000 * 2% = $20 max per trade)
   - Passes as `intended_size` to `paper.create_order` V2 tool
   - Risk service validates against `max_position_notional_usd` from risk limits

### Known gaps after Phase 4
- Circuit breaker uses `trade_outcomes` which are only written after position close. For very fast systems with many open positions, breaker may not trigger until positions close.
- Position sizing is based on portfolio_usd constant, not actual paper P&L. After 10 consecutive wins, position size doesn't grow. Could implement Kelly criterion or trailing equity sizing in future.
- `circuit_breaker_max_consecutive_losses=3` is aggressive for a paper trading system. Consider bumping to 5 for less frequent false positives during initial data collection.

---

## Phase 5 — Multi-Source Signal Fusion

### Files changed
- `walletscarper/sources/pumpfun.py` — NEW
- `walletscarper/sources/__init__.py` — added PumpFunSource
- `walletscarper/services/discovery.py` — integrated pump.fun + consensus scoring

### What was done
1. **PumpFunSource:**
   - `discover_trending(limit=50)` — fetches most recently traded tokens from pump.fun frontend API sorted by last_trade_timestamp
   - `discover_new(limit=50)` — fetches newest launches sorted by created_timestamp
   - Parses mint, bonding_curve address, symbol, name, market_cap, age
   - Uses `dex_id="pump_fun"` for differentiation

2. **Consensus scoring:**
   - `_count_sources(candidates)` tallies how many distinct sources reported each token_mint before deduplication
   - +10 point score boost if 2+ sources agree on same token
   - +15 point score boost if 3+ sources agree
   - Confidence upgraded to "high" if score >= 75 AND 2+ sources agree (was always "medium" for HIGH priority)
   - Rationale: if DexScreener, GeckoTerminal, AND pump.fun all show the same token as active, it's a much stronger signal than any single source

### Known gaps after Phase 5
- **CRITICAL:** pump.fun tokens have `mutable_supply` flag (see Phase 2 gap). Need to either:
  - Whitelist `bonding_curve` address as trusted mint authority in validator
  - OR delay DAS validation until after pump.fun graduation to Raydium
  - OR add `allow_pump_fun_premint` config toggle
  - Until fixed, ALL pump.fun tokens will be rejected by Phase 2 validator when Helius is configured
- pump.fun API is unofficial/undocumented — endpoint URL `frontend-api.pump.fun/coins` may change without notice. Monitor for HTTP errors.
- `discover_trending` called every discovery cycle (60 min default). pump.fun has new tokens every minute — consider increasing discovery frequency to 15-30 min for pump.fun specifically.
- No pump.fun source in `Stage2IngestBridge._SOURCE_MAPPERS` yet — pump.fun tokens go through Stage2 as `source_name="pumpfun"` but normalized via dexscreener fallback mapper. Add dedicated mapper when needed.

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
   - Suitable for Loki, Datadog, CloudWatch, Splunk log aggregators

2. **`/health` endpoint:**
   - Returns `{"status": "ok"|"degraded", "db": bool, "uptime_seconds": int}`
   - 200 if DB reachable, 503 if not
   - Suitable for Kubernetes liveness/readiness probes, load balancer health checks

3. **`/metrics` endpoint (Prometheus text format):**
   - No external dependency (no prometheus_client) — implemented as plain text
   - Exposes: `traderv1_raw_trades_total`, `traderv1_active_wallets`, `traderv1_tokens_total`, `traderv1_signals_total`, `traderv1_open_paper_trades`
   - Scrape-able by Prometheus or Grafana Agent at `GET /metrics`

4. **Graceful shutdown (WalletScarperScheduler):**
   - `asyncio.Event()` stop event wired to SIGTERM/SIGINT
   - Main loop changed from `while True: sleep(3600)` to `await self._stop_event.wait()`
   - On signal: `scheduler.shutdown(wait=True)` — waits for running jobs to complete before exit
   - Windows note: asyncio signal handlers may not work on Windows (`NotImplementedError` caught and ignored)

### Known gaps after Phase 6
- `/metrics` only covers legacy DB counters. Stage2 metrics (paper trades, decisions, circuit breaker state) not yet exposed. Add Stage2 DB queries to metrics endpoint.
- JSON logs don't include trace IDs per decision/signal — no distributed tracing. Add `signal_id`/`decision_id` to log record extra fields in key service methods.
- Stage2Daemon (separate process) has its own shutdown handler but no `/health` or `/metrics`. Should be unified.
- Windows SIGTERM/SIGINT handling remains unreliable for async event loop. On Windows, use `Ctrl+C` to trigger shutdown or implement Windows-specific console event handler.

---

## Open Issues After All 6 Phases

| Priority | Issue | Impact | Fix |
|----------|-------|--------|-----|
| ~~**HIGH**~~ ✅ | pump.fun tokens rejected by Phase 2 validator | Phase 5 pump.fun source produces zero valid candidates when Helius configured | **FIXED**: `_validate_onchain` discards `mutable_supply` flag for `dex_id=="pump_fun"` tokens — bonding curve holds mint_authority until graduation, expected behavior |
| **HIGH** | `pool_address` empty for Helius live-polled trades | Stage2 pipeline steps requiring pool_address produce incomplete records | Parse pool address from Raydium program instruction accounts |
| ~~**MEDIUM**~~ ✅ | LLM confidence value case-sensitivity | "HIGH" != "high" → wrong gate behavior | **FIXED**: `confidence` and `signal_strength` now `.lower()` before comparison in `hermes_review/service.py` |
| **MEDIUM** | Circuit breaker based on closed outcomes only | Doesn't protect against rapid sequence of open-position entries | Add open position count check as secondary breaker |
| **MEDIUM** | `wallet_trades` not written directly by live poller | Stage2 wallet intelligence has delay until next wallet_extraction run | Implement direct Stage2 wallet_trades writer with raw_source_event FK chain |
| **LOW** | pump.fun API endpoint undocumented | May break without warning | Monitor HTTP 4xx/5xx, add health-check logging |
| **LOW** | `/metrics` missing Stage2 counters | Prometheus dashboard incomplete | Extend metrics endpoint with Stage2 DB queries |
| **LOW** | No distributed trace IDs in logs | Hard to correlate signal→decision→order in logs | Add signal_id to LogRecord extra fields in hot paths |

---

## Test Results

| Phase | Tests | Result |
|-------|-------|--------|
| Baseline | 71 | ✅ pass |
| After Phase 0-3 | 71 | ✅ pass |
| After Phase 4-6 | pending | ⏳ |

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
