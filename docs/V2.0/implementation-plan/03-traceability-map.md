# Traceability Map

## Why This Exists

This map ties the V2.0 documentation to the current codebase so implementation can start from facts, not from a rewritten concept.

## Current Components To Reuse

| Capability | Current file(s) | V2 role |
|---|---|---|
| Legacy continuous pipeline | `WalletScarper/walletscarper/services/pipeline.py`, `scheduler.py` | Adapter and operational reference, not final agent loop |
| Token discovery | `services/discovery.py`, `sources/dexscreener.py`, `sources/geckoterminal.py` | Raw token candidate source for Token Selection Agent |
| Token trade collection | `services/transactions.py`, `sources/dexpaprika.py`, `sources/geckoterminal.py` | Seed for `TokenTradeCorpus` |
| Legacy wallet scoring | `services/scoring.py`, `services/wallet_quality.py` | Existing deterministic metrics to preserve as wallet evidence |
| Legacy tracked wallets | `db.py` tables `tracked_wallets`, `wallet_scores`, `wallet_leaderboard` | Migration source for V2 wallet database |
| Legacy live monitor | `services/live_monitor.py` | Prototype only; must become tracked-wallet event stream |
| Stage 2 schema | `stage2/db/migrations.py` | Main deterministic foundation to extend |
| Token evidence service | `stage2/token_intelligence/service.py` | Base for richer token profile and agent decisions |
| Wallet evidence service | `stage2/wallet_intelligence/service.py` | Base for wallet profiler and wallet-agent review |
| Signal/risk/paper workflow | `stage2/signals/service.py`, `stage2/risk/service.py`, `stage2/paper_trading/service.py` | Keep as safe deterministic trading boundary |
| Strategy/memory | `stage2/strategy/service.py`, `stage2/memory/service.py`, `stage2/reviews/service.py` | Base for forward learning and memory curation |
| Shadow evidence | `stage2/shadow_readiness/service.py` | Base for paper/shadow realism and gap closure |
| Hermes plugin | `.hermes/plugins/traderv1_operator` | Expand from read-only reports to write-safe typed tools |
| Hermes runtime | `external/hermes-agent`, `scripts/run-hermes.bat` | Runtime for Hermes Trading Orchestrator |

## Confirmed Gaps And Evidence

| V2 target | Current gap | Evidence |
|---|---|---|
| AI Token Selection Agent | Current token selection is rule/scoring based, not agentic | `services/discovery.py` calculates `signal_score`; no token-agent decision artifact exists |
| AI Wallet Intelligence Agent | Current wallet rating is deterministic/legacy and candidate-evidence only | `services/scoring.py`, `stage2/wallet_intelligence/service.py`; no `AgentWalletReview` |
| Hermes Orchestrator | Hermes cannot create signals/orders/reviews through tools yet | `.hermes/plugins/traderv1_operator` only exposes health/report/shadow summary |
| Adaptive market loop | Quote observations exist, but no adaptive active candle/session collector controlled by Hermes | `stage2/shadow_readiness/service.py` exists; no candle/OHLCV subsystem found |
| 24/7 V2 runtime | Legacy scheduler exists; Stage 2 has service primitives but no production worker daemon | `docs/implementation-progress/reports/final-acceptance-report.md` notes no long-running production worker daemon |
| Stage 3 shadow readiness | Explicitly gap-blocked | `docs/implementation-progress/reports/shadow-mode-gap-report.md` and `docs/operations/current-system-reality-audit.md` |

## Implementation Starting Points

Sprint 1 should start in:

- `WalletScarper/walletscarper/stage2/db/migrations.py` for schema extensions;
- `WalletScarper/walletscarper/stage2/token_intelligence/` for token-agent artifacts;
- `WalletScarper/walletscarper/stage2/wallet_intelligence/` for wallet funnel and reviews;
- `.hermes/plugins/traderv1_operator/` for first safe V2 tools.

Sprint 2 should start in:

- `config/hermes/system-prompt.md` for the updated Hermes role boundary;
- `.hermes/plugins/traderv1_operator/` for write-safe orchestrator tools;
- `WalletScarper/walletscarper/stage2/signals/`, `risk/`, `paper_trading/`, `evaluation/` for Hermes-driven paper/shadow path.

Sprint 3 should start in:

- `WalletScarper/walletscarper/stage2/monitoring/`, `jobs/`, `workers/` for continuous sessions;
- `WalletScarper/walletscarper/stage2/shadow_readiness/` for adaptive market evidence and cadence degradation;
- `WalletScarper/walletscarper/web/` and reports for V2 acceptance/dashboards.

## Preservation Rules

- Do not delete legacy collectors until their outputs are mapped into Stage 2/V2 artifacts.
- Do not bypass the existing risk and paper-trading services.
- Do not promote Hermes to direct SQL writer.
- Do not implement live execution while closing V2.0 gaps.
