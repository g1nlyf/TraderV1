# ADR-0002 - Risk Before Paper Order

## Decision

Paper Trading Engine cannot create `PaperOrder` unless deterministic entry `RiskCheck` has passed.

## Rationale

Risk after order is too late and creates an unsafe mental model. Even paper trading must mirror future live workflow.

## Consequences

- `create_paper_order(signal_id, risk_check_id)` requires both ids.
- Risk check must match signal and config snapshot.
- Agent cannot manually create authoritative risk result.

