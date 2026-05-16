# 00. Master Build Map

## Release target

Build the final **Stage 2 autonomous real-market paper trading system** with **Stage 3-compatible shadow execution design**.

Stage 3 shadow mode may be partially implemented where data quality supports it. If not, Sprint 5 must produce a Shadow Mode Gap Report. Do not pretend Stage 3 is complete when quote quality, latency model or execution simulation are insufficient.

## Five sprint map

| Sprint | Name | Load-bearing output |
|---:|---|---|
| 1 | Foundation, Environment And Source Of Truth | DB, schemas, audit boundaries, config snapshots, job queue skeleton, Hermes connectivity smoke test |
| 2 | Data, Token Discovery And Wallet Intelligence | Normalized data, token profiles, wallet profiles, evidence quality |
| 3 | Integrated Signal, Risk And Paper Trading Workflow | Signal -> RiskCheck -> PaperOrder -> Fill -> Position -> Exit -> Outcome |
| 4 | Parallel Monitoring, Strategy Search And Memory | Multi-token sessions, worker leases, strategy comparison, curated memory |
| 5 | Hardening, Shadow Mode And Final Acceptance | Full tests, continuous run, dashboard, final acceptance report |

## Dependency order

```text
source-of-truth schema
  -> data normalization
  -> wallet/token evidence
  -> signal contracts
  -> deterministic risk
  -> paper orders/fills
  -> evaluation metrics
  -> parallel sessions
  -> strategy comparison
  -> memory curation
  -> continuous acceptance run
```

## What must never be built early

- Live execution module.
- Private key path.
- DEX swap/signing code.
- LLM-based risk pass/veto.
- LLM-based canonical P&L.
- Strategy promotion without config snapshot.
- Free-form agent-to-agent chat as the internal workflow bus.

## Final operating loop

```text
scan candidates
  -> normalize data
  -> triage token
  -> create token monitoring session
  -> profile wallets/clusters
  -> generate Signal or NoTradeSignal
  -> run deterministic entry RiskCheck
  -> create PaperOrder only if risk passed
  -> simulate PaperFill
  -> open PaperPosition
  -> monitor position
  -> create ExitDecision before exit fill
  -> run deterministic exit RiskCheck
  -> simulate exit PaperFill
  -> calculate TradeOutcome
  -> update metrics
  -> review trade
  -> update strategy comparison
  -> curate memory
  -> reprioritize job queue
```

