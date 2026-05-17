# TraderV1 V2.0 Documentation Pack

## Purpose

This package supersedes the current Stage 2 implementation docs for the next implementation pass.

V2.0 is not a move toward script trading. The target system is agentic trading research and paper/shadow execution where scripts are data collectors, parsers and typed tools, while Hermes and specialist AI agents choose what to investigate, what to ignore, which wallets deserve trust, and which token is the best current opportunity.

Canonical principle:

```text
Scripts produce evidence. Agents synthesize evidence. Deterministic services verify, veto and account.
```

## Reading Order

1. [final-vision/00-final-agentic-trading-system.md](final-vision/00-final-agentic-trading-system.md)
2. [final-vision/01-agent-roles-and-decision-freedom.md](final-vision/01-agent-roles-and-decision-freedom.md)
3. [final-vision/02-wallet-funnel-and-market-loop.md](final-vision/02-wallet-funnel-and-market-loop.md)
4. [almanac-v2/README.md](almanac-v2/README.md)
5. [almanac-v2/00-system-invariants.md](almanac-v2/00-system-invariants.md)
6. [almanac-v2/01-domain-data-model.md](almanac-v2/01-domain-data-model.md)
7. [almanac-v2/02-hermes-tool-contracts.md](almanac-v2/02-hermes-tool-contracts.md)
8. [implementation-plan/00-current-readiness-assessment.md](implementation-plan/00-current-readiness-assessment.md)
9. [implementation-plan/01-missing-capabilities.md](implementation-plan/01-missing-capabilities.md)
10. [implementation-plan/02-three-sprint-plan.md](implementation-plan/02-three-sprint-plan.md)
11. [implementation-plan/03-traceability-map.md](implementation-plan/03-traceability-map.md)
12. [RUNTIME-CLOSURE-2026-05-16.md](RUNTIME-CLOSURE-2026-05-16.md)
13. [HARDENING-PROGRESS-2026-05-16.md](HARDENING-PROGRESS-2026-05-16.md) ← Phase 0-6 hardening (Helius, validation, circuit breaker, pump.fun, prod infra)

## V2.0 Scope

V2.0 must deliver the user-described three-agent architecture:

- Token Selection Agent chooses the best tradeable token universe and active token candidates.
- Wallet Intelligence Agent selects, rates and maintains a competitive database of top wallets.
- Hermes Trading Orchestrator combines wallet signals, second-level market data, token context, browser/API research, risk state and memory into paper/shadow trading decisions.

The current repository already contains useful Stage 2 infrastructure, but it is not yet this final system. The main V2.0 work is to turn the existing deterministic services and scrapers into a tool surface controlled by Hermes, and to add the missing data depth required for real wallet and token intelligence.

## Current Baseline

The baseline inspected for this package is the local project at:

```text
C:\Users\hacke\CascadeProjects\Finals1\TraderV1
```

Important current facts:

- `WalletScarper` contains the legacy data collector and the newer `walletscarper.stage2` deterministic services.
- `docs/V2.0/RUNTIME-CLOSURE-2026-05-16.md` is the latest runtime audit and supersedes the older gap-only audit for current pipeline status.
- `run-once` now completes against live configured sources and bridges discovered tokens into Stage 2.
- Stage 2 can normalize live token discovery, build token corpora, calculate wallet outcomes, profile legacy-backed wallet history, and receive real tracked-wallet signals.
- `docs/implementation-progress/reports/final-acceptance-report.md` still reports Stage 2 as `accepted_with_gaps`; shadow readiness remains `gap_report_required`.

## Non-Goal

V2.0 must not add private keys, signer logic, DEX transaction builders or real-money execution. The agent can make paper/shadow decisions and can prepare live-readiness evidence, but live trading remains a gated future extension after positive forward paper/shadow P&L.
