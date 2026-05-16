# Sprint 3 - Integrated Signal, Risk And Paper Trading Workflow

## Goal

Make the core trading research loop work end-to-end under no-hindsight rules.

## Scope

Build:

- `Signal`;
- `NoTradeSignal`;
- `TradeThesis`;
- entry `RiskCheck`;
- `PaperOrder`;
- entry `PaperFill`;
- `PaperPosition`;
- monitoring risk check;
- `ExitDecision`;
- exit `RiskCheck`;
- exit `PaperFill`;
- `TradeOutcome`;
- baseline dashboard.

## Non-goals

- No strategy self-search yet.
- No live execution.
- No private keys.
- No free-text close position API.

## Required sequence

```text
Signal
  -> TradeThesis
  -> entry RiskCheck
  -> PaperOrder
  -> entry PaperFill
  -> PaperPosition
  -> monitoring
  -> ExitDecision
  -> exit RiskCheck
  -> exit PaperFill
  -> TradeOutcome
```

## Tasks

1. Implement `create_signal`.
2. Implement `create_no_trade_signal`.
3. Implement `run_entry_risk_check`.
4. Implement `create_paper_order(signal_id, risk_check_id)`.
5. Make order creation reject missing/mismatched/failed risk checks.
6. Implement conservative fill simulation.
7. Implement paper position creation.
8. Implement position monitoring jobs.
9. Implement `create_exit_decision`.
10. Implement `run_exit_risk_check`.
11. Implement `execute_paper_exit(exit_decision_id, risk_check_id)`.
12. Implement deterministic `TradeOutcome`.
13. Log rejected and missed trades.
14. Add dashboard metrics.

## Tests

- No order without passed entry risk check.
- No exit fill without prior exit decision.
- No free-text close API.
- P&L deterministic unit tests.
- Fees/slippage/latency included.
- Failed fills represented.
- Signal and thesis immutable after order.

## Acceptance gate

- Real token candidate can flow to signal/no-trade.
- Passing signal creates paper order only through risk engine.
- Paper position opens, monitors, exits and calculates net P&L.
- Every decision is timestamped before outcome.
- Dashboard shows basic P&L, expectancy and drawdown.

## Failure conditions

- Risk check occurs after paper order.
- Agent can manually create authoritative `RiskCheck`.
- Agent can close position with `position_id + reason`.
- Evaluation uses LLM-generated metrics.

