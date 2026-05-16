# Current Readiness Assessment

## Summary

The current project is a working real-source Stage 2/V2 foundation, but it is not yet the final autonomous V2.0 agentic trading system described by the user.

What exists:

- legacy wallet/token collector;
- deterministic Stage 2 schemas and services;
- risk-gated paper workflow;
- jobs, leases, monitoring sessions, strategy and memory artifacts;
- shadow-readiness evidence tables;
- local dashboard and Windows launch scripts;
- Hermes installed with a V2 Trading Research Director plugin and write-safe tools.
- real-source token discovery bridged into Stage 2 raw events;
- real-source tracked-wallet signals bridged into Stage 2 signal events;
- token-to-wallet corpora and wallet-token outcomes working over live/legacy evidence.

What is missing:

- sustained Hermes autonomous review loop;
- AI token selection as a continuous first-class decision loop;
- AI wallet selection/rating database populated from real candidates;
- normalized Stage 2 wallet trades at production depth;
- adaptive active market loop controlled by Hermes;
- forward wallet competition and learning loop tied to agent decisions.

## Evidence From Repo

| Area | Current state | Evidence |
|---|---|---|
| Legacy token discovery | Exists | `WalletScarper/walletscarper/services/discovery.py` uses DexScreener and GeckoTerminal |
| Legacy transaction parsing | Exists but bounded | `WalletScarper/walletscarper/services/transactions.py` parses pool trades from DexPaprika/GeckoTerminal and optional Solana RPC signer lookup |
| Legacy wallet scoring | Exists | `WalletScarper/walletscarper/services/scoring.py`, `wallet_quality.py`, `tracked_wallets` tables |
| Legacy scheduler | Exists | `WalletScarper/walletscarper/scheduler.py` runs discovery, backfill, live monitor, Telegram, Bitquery if configured |
| Stage 2 deterministic schema | Exists | `WalletScarper/walletscarper/stage2/db/migrations.py` migrations 1-10 |
| Token profile/triage | Exists as deterministic evidence layer | `walletscarper/stage2/token_intelligence/service.py` |
| Wallet metrics/profile | Exists as deterministic candidate evidence | `walletscarper/stage2/wallet_intelligence/service.py` |
| Signal/risk/paper workflow | Exists | `signals/service.py`, `risk/service.py`, `paper_trading/service.py` |
| Strategy/memory | Exists | `strategy/service.py`, `memory/service.py`, `reviews/service.py` |
| Shadow evidence | Partial | `shadow_readiness/service.py`; current reports still show gaps |
| Hermes runtime | Exists | `external/hermes-agent`, `scripts/run-hermes.bat` |
| Hermes project tools | V2 write-safe tools exist | `.hermes/plugins/traderv1_operator` exposes token, wallet, signal, risk, paper, review and memory tools |
| Real source token bridge | Working | `Pipeline.run_once()` writes discovery candidates through `Stage2IngestBridge` |
| Real source wallet signal bridge | Working | `LiveMonitor.tick()` emits `tracked_wallet_signal_events` with `input_mode=real_source` |
| Token-to-wallet runtime | Working sample | `Stage2ScannerService.run_wallet_extraction()` created 866 wallet outcomes in the 2026-05-16 runtime smoke |
| Stage 2 acceptance | Accepted with gaps | `docs/implementation-progress/reports/final-acceptance-report.md` |
| Stage 3 readiness | Not accepted | `docs/implementation-progress/reports/shadow-mode-gap-report.md` |

## Architectural Mismatch

The current system still uses script-generated scoring as an evidence producer:

- legacy `DiscoveryService` assigns `signal_score` and priority;
- legacy `ScoringService` promotes wallets into `tracked_wallets`;
- Hermes has the tools to control the workflow, but no sustained autonomous review session is running by default;
- script scoring still promotes legacy tracked wallets, while V2 `AgentWalletReview` is not yet populated at scale.

These pieces are still useful, but V2.0 must wrap them as evidence/tooling under agent control.

## Readiness By Target Agent

| Target agent | Ready pieces | Missing pieces | Readiness |
|---|---|---|---|
| Token Selection Agent | Token candidates, profiles, triage configs, market snapshots, token agent decision records, Hermes tools | sustained agent loop, richer holder/concentration and growth windows | Partial to good |
| Wallet Intelligence Agent | Token corpora, wallet extraction, wallet-token outcomes, legacy-backed wallet profile, review storage | high-volume agent reviews, normalized Stage 2 wallet trades, forward contribution | Partial |
| Hermes Trading Orchestrator | Signal/risk/paper/evaluation services, reports, Hermes runtime, write-safe V2 tools, real signal intake | sustained autonomous orchestration and adaptive active market loop | Partial |
| Deterministic risk/accounting | Strong paper-only foundation | Real observation windows, route/fill comparison evidence for shadow confidence | Good for paper, partial for shadow |
| Continuous operation | Legacy APScheduler, Windows scripts, `stage2-run-daemon` | priority-aware adaptive market/session loop and autonomous Hermes review loop | Partial |

## Baseline Conclusion

Do not throw away Stage 2. The data foundation and safe tool surface now work. The next implementation must shift the product center from "scripts score wallets/tokens" to sustained Hermes operation: token choice, wallet reviews, paper/shadow decisions, and forward learning.
