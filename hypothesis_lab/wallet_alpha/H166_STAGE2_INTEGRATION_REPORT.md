# H-166 → Stage-2 Integration Report (Sprint 7, 2026-06-06)

How the deterministic `h166_risk_overlay` maps onto the existing Stage-2 `RiskService` — and why it ships
**SHADOW-ONLY (log, do not gate)** this sprint.

## Integration status: SHADOW-ONLY, NOT authoritative
The backtest (`backtest_h166.py`) showed exit_h166 does **not** beat exit-on-any-sell, and the no-trade veto
adds no value (H166_RISK_ENGINE_REPORT.md). Therefore H-166 must **not** become an authoritative Stage-2
veto/exit. It may run in **shadow**: compute the verdict, persist it as evidence, compare to outcomes — but
never block a paper entry or force a paper exit until it clears the gate cross-day (H-163). Paper-only always.

## API mapping (when/if promoted)
Existing contract (`stage2/risk/interfaces.py`, `stage2/risk/service.py`):
- `run_entry_risk_check(signal_id, market_snapshot_id, risk_limit_snapshot_id, config_snapshot_id)` →
  appends to `vetoes`, writes `risk_checks` + `no_trade_signals` + evidence.
- `run_position_monitoring_risk_check(position_id, ...)` → same for open positions.

H-166 adapter (deterministic, point-in-time):
```
verdict = h166_risk_overlay.evaluate_entry(token, as_of=data_as_of, events=pre_t_wallet_trades,
                                           wallet_quality=point_in_time_skill)   # entry
verdict = h166_risk_overlay.evaluate_position(token, as_of, entry_ts, events, wallet_quality)  # monitoring
```
- entry `no_trade`  → append veto code `wallet_distribution_active` (SHADOW: log only).
- entry `watch`     → advisory flag `wallet_distribution_absorbed_bounce` (do not buy immediately; H-042).
- position `exit_candidate` → advisory `wallet_distribution_exit` feeding `create_exit_decision` (SHADOW).
- `verdict.to_evidence_ref()` → `normalized_evidence_refs` / `risk_checks.metadata`.

## Inputs (must be point-in-time; free data)
- `events`: wallet trades for the token with `block_ts < data_as_of` (from `firehose_trades` ∪ `raw_trades`,
  schema-aligned). NEVER `wallet_scores`/`wallet_leaderboard`/`wallet_token_pnl` (look-ahead).
- `wallet_quality`: realized SOL PnL per wallet from PRE-`data_as_of` round-trips (FIFO ledger). If absent →
  module self-degrades to `confidence=low` and never hard-vetoes.
- Stage-2's `data_as_of`/snapshot machinery already enforces the leakage guard (warns if snapshot older).

## Artifacts written (shadow)
- `risk_checks` row (subject_type=signal|position, status=shadow, veto_reason=null authoritative,
  metadata=H-166 evidence dict, `signal_version=h166.v1`).
- `normalized_evidence_refs` with the pressure counts + source_purity (organic|non_organic).
- A shadow comparison log (verdict vs realized outcome) for the cross-day evaluation.

## Rollback / degradation rules
- `confidence=low` (no point-in-time quality) → downgrade `no_trade`→`watch`; never block.
- `source_purity=non_organic` (any fixture/test event) → evidence flagged; excluded from any organic stat.
- Kill-switch: a single config flag disables H-166 evidence emission; default OFF for gating.
- Auto-disable if shadow false-exit rate > 30% over a rolling window (backtest already shows 23%).

## Invalidation condition (when to delete H-166)
If H-163 (cross-day) shows the distributor/wq increment does not survive multiple regimes, OR shadow exit
continues to lose to exit-on-any-sell across days → retire H-166 as authoritative; keep only the generic
"exit-on-sell-cluster" reaction (if even that survives cross-day) as a plain risk heuristic.

## This sprint did NOT modify the live Stage-2 DB
By design: H-166 is unvalidated. The module + adapter shape + this spec are complete and ready; wiring waits
for cross-day proof. No live tables created/altered. Paper/research only.
