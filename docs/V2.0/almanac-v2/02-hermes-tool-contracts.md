# Hermes Tool Contracts

## Goal

Hermes needs more than read-only reports. V2.0 requires a safe typed tool surface that lets Hermes run the agentic loop without direct database mutation.

Tools should be exposed through the current Hermes plugin first, then promoted to MCP/internal API if long-running use requires it.

## Token Tools

| Tool | Purpose | Mutates canonical trading state |
|---|---|---|
| `token.scan_universe` | Collect and normalize token candidates from configured sources | No trading state |
| `token.get_profile` | Return token profile, source quality and recent snapshots | No |
| `token.request_deep_parse` | Queue full trade/wallet parsing for a token | Job only |
| `token.record_agent_decision` | Store Token Selection Agent attention decision | Agent decision only |
| `token.start_active_session` | Create active token session for high-frequency monitoring | Session only |
| `token.close_active_session` | Close/degrade/pause active session with reason | Session only |

## Wallet Tools

| Tool | Purpose | Mutates canonical trading state |
|---|---|---|
| `wallet.extract_from_token` | Build wallet candidate set from token trade corpus | No trading state |
| `wallet.calculate_token_outcomes` | Calculate token-specific wallet ROI/P&L outcomes and +20% review eligibility | No trading state |
| `wallet.profile_history` | Reconstruct recent multi-token wallet history | No |
| `wallet.get_metrics` | Return deterministic wallet metrics and source quality | No |
| `wallet.record_agent_review` | Store Wallet Intelligence Agent rating and reasons | Agent review only |
| `wallet.list_elite` | Return current elite/probation/watch wallets | No |
| `wallet.track` | Activate wallet tracking after approved review | Tracking state only |
| `wallet.demote` | Demote tracked wallet with reason/evidence | Tracking state only |
| `wallet.forward_contribution_report` | Return deterministic contribution metrics | No |

## Market Tools

| Tool | Purpose | Mutates canonical trading state |
|---|---|---|
| `market.observe_adaptive` | Record a snapshot/candle using the session cadence policy | Market evidence only |
| `market.set_cadence_policy` | Lower or raise observation cadence based on priority and source health | Session policy only |
| `market.get_recent_window` | Return last N seconds/minutes of active market data | No |
| `market.get_route_quality` | Return route-quality and spread evidence | No |
| `market.open_browser_research` | Queue browser/API extraction for non-canonical facts | Browser evidence only |

## Decision Tools

| Tool | Purpose | Mutates canonical trading state |
|---|---|---|
| `agent.record_trading_decision` | Store Hermes pre-action synthesis | Agent decision only |
| `signal.create` | Create structured `Signal` from Hermes decision | Signal only |
| `signal.create_no_trade` | Create structured `NoTradeSignal` | No-trade only |
| `risk.check_entry` | Create deterministic entry `RiskCheck` | Risk state |
| `paper.create_order` | Create paper/shadow order only after passed risk | Paper ledger |
| `paper.simulate_fill` | Create deterministic paper/shadow fill | Paper ledger |
| `paper.create_exit_decision` | Record exit decision before simulated exit | Paper ledger |
| `risk.check_exit` | Create deterministic exit `RiskCheck` | Risk state |
| `paper.execute_exit` | Simulate exit fill after passed exit risk | Paper ledger |

## Review And Learning Tools

| Tool | Purpose |
|---|---|
| `metrics.session_report` | Active token/session metrics |
| `metrics.wallet_report` | Wallet contribution and degradation |
| `metrics.strategy_report` | Strategy P&L, expectancy, win rate, drawdown |
| `review.create_post_trade` | Agent post-trade review linked to deterministic outcome |
| `memory.propose` | Propose curated memory from evidence |
| `memory.curate` | Accept/reject/archive/supersede memory proposal |

## Tool Output Requirements

Every tool response must include:

- `ok`;
- `artifact_id` or `job_id` when created;
- `source_refs`;
- `data_as_of`;
- `quality_flags`;
- `confidence`;
- `cadence_state` when the tool touches market observation;
- `blocked_reason` when blocked;
- `next_suggested_tools` when useful.

## Forbidden Tool Behavior

No tool may:

- expose private keys;
- sign transactions;
- place real orders;
- let Hermes write raw SQL;
- create authoritative P&L from LLM text;
- create risk checks with `created_by_service` other than deterministic risk service;
- update append-only records.
