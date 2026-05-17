# Gaps and Blockers — What's Needed for Production

**Last updated:** 2026-05-17

This document answers the question: **"What would it take for this system to responsibly manage real money?"**

The answer is not "just remove the paper-trading flag." There are structural, validation, and operational requirements that must be met first. This document lists all of them honestly.

---

## The "Million Dollar" Standard

To manage $1M+ in trades responsibly, the system needs:
1. **Proven positive net expectancy** — statistically significant paper P&L from real signals
2. **Validated exit discipline** — consistent, non-hindsight exit execution
3. **Stable risk controls** — circuit breaker, position limits, max drawdown enforcement
4. **Real execution simulation quality** — accurate fees, slippage, latency, failed fills
5. **Operational resilience** — 24/7 uptime, Helius dependency handled, graceful degradation
6. **Audit trail completeness** — every decision logged with pre-trade reasoning
7. **Human oversight layer** — at minimum Stage 4 (human-confirmed) before Stage 5 (autonomous)

None of these are fully met yet. Below is the honest gap list.

---

## CRITICAL GAPS (Blocking Path to Real Money)

### GAP-C1: Zero Real Paper Trades From Real Signals

**Status:** ❌ Never happened  
**Impact:** Can't claim positive expectancy without real paper P&L history

The system has:
- 7 real wallet signal events (tracked wallets buying real tokens)
- A complete paper trading path (verified in fixture mode)
- A wired Hermes review loop

But: zero `agent_trading_decisions` linked to real signals. Zero paper positions from real market events. The core value proposition — "copy-trading AI that learns" — has never been exercised on real data.

**Fix:** Run scheduler with `HERMES_ENABLED=true` for 1-2 weeks. Verify `agent_trading_decisions` and `paper_positions` populate from real signals.

---

### GAP-C2: No Validated Paper P&L

**Status:** ❌ No real P&L history  
**Impact:** Cannot claim system has positive net expectancy

Without real paper trades, there is no P&L to evaluate. The system might have positive expectancy, neutral expectancy, or negative expectancy — we don't know. All P&L data is from fixture runs.

**Fix:** Requires GAP-C1 to be resolved first. Then accumulate 50-100 paper trades from real signals before drawing statistical conclusions.

---

### GAP-C3: Shadow Mode Not Unlocked

**Status:** ❌ `shadow_status: gap_report_required`  
**Impact:** Cannot proceed to Stage 3 (shadow mode)

Shadow mode requires:
- Real live quote observation windows (not calibration fixtures)
- Route quality evidence (deep enough pool depth)
- Fill-vs-quote comparisons (paper fill price vs. actual market price at that moment)
- Cross-source quote freshness (DexScreener/GeckoTerminal timestamps)

**Fix:** Run calibration window against live tokens for 24+ hours. Accumulate real `live_data_acceptance_windows` with sufficient evidence.

---

### GAP-C4: Sprint 3 — Adaptive Market Loop Not Built

**Status:** ❌ Not started  
**Impact:** System cannot autonomously monitor open positions at adaptive cadence

Without Sprint 3:
- No `ActiveTokenSession` lifecycle management
- No priority polling (open positions vs. research candidates)
- No automated exit monitoring
- System can't run fully autonomously 24/7

**Fix:** Implement `ActiveTokenSessionService`, add adaptive cadence scheduler, add continuous worker daemon that runs Hermes sessions without manual CLI invocation.

---

## HIGH PRIORITY GAPS (Need Before Scale)

### GAP-H1: Hermes Model Is Free 20B — Not Frontier

**Status:** ⚠️ Using `openai/gpt-oss-20b:free`  
**Impact:** Decision quality limited vs. frontier models

A free 20B model makes different quality decisions than GPT-4o or Claude 3.5 Sonnet. For a paper-only research system, this may be acceptable. For real money, decision model quality matters significantly.

**Fix:** Upgrade to `anthropic/claude-3.5-sonnet` or `openai/gpt-4o` for production. Cost: ~$0.003–0.015/decision.

---

### GAP-H2: Pool Address Empty for Helius Live-Polled Trades

**Status:** ⚠️ Known issue  
**Impact:** Stage 2 pipeline records incomplete for live-polled trades

Helius `getSignaturesForAddress` + tx parsing gives token_mint + side + amounts, but pool_address is empty string. Some Stage 2 pipeline steps that need pool_address produce incomplete records.

**Fix:** Parse pool address from Raydium program instruction accounts in `parse_wallet_swap()`.

---

### GAP-H3: wallet_trades Table Sparse

**Status:** ⚠️ Legacy fallback works  
**Impact:** Wallet history profiling relies on fallback path

`wallet_trades` (Stage 2 normalized trades) has few rows. `wallet.profile_history` falls back to legacy `pool_transactions`. This works but is slow and means less structured wallet analysis.

**Fix:** Implement direct Stage 2 wallet_trades writer in `WalletTradePollerService` with raw_source_event FK chain.

---

### GAP-H4: No Distributed Tracing

**Status:** ⚠️ Logs exist, no trace IDs  
**Impact:** Hard to correlate signal → decision → order in logs

When debugging why a signal was rejected or accepted, there's no trace ID to follow through logs. Must grep by wallet/token manually.

**Fix:** Add `signal_id` and `decision_id` to LogRecord extra fields in key service methods.

---

### GAP-H5: Stage 2 Metrics Not in /metrics

**Status:** ⚠️ `/metrics` only has legacy DB counters  
**Impact:** Incomplete Prometheus dashboard

Stage 2 counters (paper trades, decisions, circuit breaker state, Hermes review rate) not exposed.

**Fix:** Add Stage 2 DB queries to metrics endpoint.

---

## MEDIUM PRIORITY GAPS

### GAP-M1: No Human Oversight Layer Before Live Trading

**Status:** ❌ Not implemented  
**Impact:** No Stage 4 (human-confirmed live trading) path exists

The autonomy stages are 0-6. Stage 4 = human confirms each trade before execution. This stage doesn't exist in the codebase.

**Fix:** Build a notification + approval API (`/pending-decisions/{id}/approve`) before any live execution work.

---

### GAP-M2: Wallet Signal Volume Too Low for Statistics

**Status:** ⚠️ 7 signals in DB  
**Impact:** Cannot derive statistical conclusions from 7 samples

7 signals is not enough to evaluate strategy performance. Need 50+ to detect meaningful patterns.

**Fix:** Continue running live monitoring. Wallet signals will accumulate as tracked wallets trade.

---

### GAP-M3: Circuit Breaker Based on Closed Outcomes Only

**Status:** ⚠️ Known limitation  
**Impact:** Doesn't protect against rapid open-position sequence during live session

Circuit breaker triggers after `trade_outcomes` are written (positions closed). If 3 positions are opened simultaneously before any close, breaker doesn't trigger.

**Fix:** Add open position count check as secondary breaker (`max_simultaneous_open_positions`).

---

### GAP-M4: Hermes Agent Has Never Been Run Interactively

**Status:** ⚠️ Configured but unused  
**Impact:** No validation of human-in-loop Hermes usage

The Hermes CLI agent (`scripts/run-hermes.bat`) is configured with 24 V2 tools but has never been run by the operator. Its usefulness for ad-hoc research is completely untested from the operator's perspective.

**Fix:** Run it once. Try: `health check`, `scan for new token candidates`, `review wallet [address]`.

---

### GAP-M5: pump.fun Tokens Need Validation Strategy

**Status:** ⚠️ Partial fix  
**Impact:** pump.fun tokens skip mutable_supply hard flag

Phase 2 fix: tokens with `dex_id=pump_fun` skip `mutable_supply` flag (bonding curve expected). But full `freeze_authority_active` check still applies. After graduation to Raydium/Orca, these tokens should go through full validation. No graduation detection exists.

**Fix:** Add graduation detection (check if bonding_curve is closed) and re-validate post-graduation.

---

## LOW PRIORITY GAPS

| Gap | Impact | Fix |
|-----|--------|-----|
| No forward learning from real outcomes | Memory doesn't improve from real trades | Requires real paper trades first (GAP-C1) |
| Windows SIGTERM unreliable | Graceful shutdown may not work on Windows | Use Linux for production |
| Stage 2 Daemon has no `/health` endpoint | Can't probe Stage 2 daemon health | Add `/health` to Stage2Daemon |
| LLM response parsing fragile | If model returns non-JSON, decision is dropped | Add retry + structured output enforcement |
| No alerting on circuit breaker trigger | Operator doesn't know when trading is halted | Add webhook/email alert |
| DexScreener timestamps missing | Cannot verify quote freshness for shadow mode | Known upstream limitation |
| pump.fun API is unofficial | Endpoint may break without notice | Monitor 4xx/5xx rates |

---

## Path to Production — Ordered Milestones

```
MILESTONE 1: First Real Paper Trade (1-2 weeks)
  ✓ Hermes review loop processes 7 existing real signals
  ✓ At least 1 paper position opened from real wallet signal
  ✓ Position closes with real P&L calculated

MILESTONE 2: Statistical Sample (4-8 weeks)
  ✓ 50+ real paper trades accumulated
  ✓ Net expectancy calculable
  ✓ Win rate, payoff ratio, drawdown measured
  ✓ Circuit breaker tested on real losing streak

MILESTONE 3: Sprint 3 Complete (2-4 weeks dev)
  ✓ ActiveTokenSession lifecycle working
  ✓ Hermes runs autonomously without CLI
  ✓ Adaptive market loop polling open positions

MILESTONE 4: Shadow Mode (2-4 weeks data)
  ✓ Real quote observation windows accumulated
  ✓ Route quality evidence sufficient
  ✓ Fill-vs-quote comparisons passing
  ✓ stage2-final-acceptance → accepted (not accepted_with_gaps)

MILESTONE 5: Pre-Live Readiness (1-2 months total)
  ✓ Positive net expectancy on 200+ paper trades
  ✓ Human oversight layer (Stage 4) built
  ✓ Risk limits reviewed for real capital
  ✓ Model upgraded to frontier (Claude/GPT-4o)
  ✓ Operational runbook tested
  ✓ Pool address parsing fixed
  ✓ Alert system active

MILESTONE 6: Stage 4 Live (future)
  → Human-confirmed live trading, very small size
  → NOT YET IN SCOPE
```

---

## What Would Make This System "Million Dollar Ready"

A system managing $1M+ in trades daily needs **all** of the following:

- [ ] Statistically significant positive net expectancy (p < 0.05 on 200+ trades)
- [ ] Max drawdown < 15% on paper P&L history
- [ ] Circuit breaker tested and confirmed to halt trading in losing streaks
- [ ] Shadow mode passed (real quote quality, fill simulation quality)
- [ ] Human approval layer for each trade (Stage 4 minimum)
- [ ] Frontier LLM for decision quality (GPT-4o or Claude 3.5 Sonnet+)
- [ ] Helius uptime dependency handled (fallback for polling failures)
- [ ] Pool address parsing complete (no empty pool addresses)
- [ ] Operational monitoring: alerts, dashboards, on-call runbook
- [ ] Legal/compliance review if managing 3rd party funds
- [ ] Security audit (API keys, no private key exposure, access control)
- [ ] Stress test: what happens with 100 open positions simultaneously?

**Current score: 3/15 checked** (circuit breaker design, risk limits design, no live trading gate)
