# Final Acceptance Checklist

## Core invariants

- [ ] No real-money live execution path exists.
- [ ] No private-key path exists.
- [ ] No signer/swap/DEX transaction module exists.
- [ ] Hermes cannot mutate ledger.
- [ ] LLM cannot create authoritative `RiskCheck`.
- [ ] LLM cannot calculate canonical P&L.

## Paper workflow

- [ ] Signal is created before entry risk check.
- [ ] TradeThesis is created before PaperOrder.
- [ ] Entry RiskCheck passes before PaperOrder.
- [ ] PaperOrder references Signal and RiskCheck.
- [ ] PaperFill includes fees, slippage and latency.
- [ ] ExitDecision exists before exit fill.
- [ ] Exit RiskCheck exists before exit execution.
- [ ] TradeOutcome is deterministic.

## Data quality

- [ ] Raw events are stored.
- [ ] Market snapshots are timestamped.
- [ ] Browser extraction is non-canonical.
- [ ] Browser-only prices do not promote strategies.
- [ ] Wallet historical P&L is candidate evidence only.

## Strategy

- [ ] StrategyVersion references config snapshot.
- [ ] Signal references strategy config snapshot.
- [ ] Promotion criteria are versioned.
- [ ] Promotion/demotion/kill decision is auditable.
- [ ] Strategy comparison uses forward paper trades.

## Parallel operation

- [ ] Jobs are durable.
- [ ] Worker leases expire safely.
- [ ] Max parallel sessions are enforced.
- [ ] Open positions outrank discovery.
- [ ] Conflicts block instead of overwriting state.

## Final run

- [ ] AcceptanceRun config exists.
- [ ] Configured continuous window completed.
- [ ] No critical invariant violations.
- [ ] Dashboard shows operational health.
- [ ] Shadow mode completed or gap-reported honestly.

