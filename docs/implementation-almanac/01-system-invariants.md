# 01. System Invariants

These invariants must hold in every sprint.

## Authority boundaries

- Hermes orchestrates but does not own accounting truth.
- LLM agents propose, summarize and explain.
- Deterministic services calculate, verify and veto.
- Risk Engine is sovereign.
- Paper Trading Engine cannot create `PaperOrder` without passed deterministic entry `RiskCheck`.
- Evaluation Engine is source of truth for metrics.
- Database/ledger is source of truth for history.

## Trading boundaries

- No real-money live execution path is enabled.
- No private keys in code paths or agent context.
- No signer, swap adapter or DEX transaction code.
- Future live execution is an extension, not part of this release runtime.

## No-hindsight boundaries

- `Signal` exists before entry risk check.
- `TradeThesis` exists before order creation.
- `RiskCheck` exists before `PaperOrder`.
- `ExitDecision` exists before simulated exit fill.
- `TradeOutcome` is calculated after fills.
- LLM cannot edit previous signal, thesis, risk check, fill or outcome.

## Data boundaries

- Raw source events are stored before derived metrics.
- Every derived object references source or snapshot ids.
- Browser data is non-canonical for high-confidence P&L.
- Browser-only price can create low-confidence research/shadow-gap evidence only.
- Historical wallet metrics are candidate evidence, not strategy performance.

## Config boundaries

- Risk checks reference `RiskLimitSnapshot`.
- Signals reference `StrategyConfigSnapshot`.
- Experiments reference `PromotionCriteriaSnapshot`.
- Acceptance run references configured acceptance window.
- Promotion/demotion/kill decisions must be auditable.

## Agent boundaries

- Agents do not mutate ledger directly.
- Agents do not create authoritative `RiskCheck`.
- Agents do not calculate canonical P&L.
- Agents do not close positions from free text.
- Agents operate through typed tools and job leases.

