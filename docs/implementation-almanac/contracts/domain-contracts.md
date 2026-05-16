# Domain Contracts

This file describes required logical fields. Exact schema syntax can vary, but semantics must remain.

## Signal

Required:

- `signal_id`
- `created_at`
- `data_as_of`
- `token_id`
- `strategy_version_id`
- `strategy_config_snapshot_id`
- `promotion_criteria_snapshot_id` if experiment-related
- `source_refs`
- `confidence`
- `thesis_ref`
- `invalidation_condition`
- `expected_holding_time`
- `estimated_risk`
- `estimated_slippage`
- `status`

Rule: `Signal` is immutable after entry risk check starts.

## TradeThesis

Required:

- `thesis_id`
- `signal_id`
- `entry_reason`
- `exit_plan`
- `expected_holding_time`
- `proof_wrong`
- `context_snapshot_id`
- `created_at`

Rule: must exist before `PaperOrder`.

## RiskCheck

Required:

- `risk_check_id`
- `check_scope`: `entry | exit | position_monitoring`
- `subject_type`: `signal | paper_order | paper_position | exit_decision`
- `subject_id`
- `market_snapshot_id`
- `risk_limit_snapshot_id`
- `config_snapshot_id`
- `data_as_of`
- `passed`
- `veto_reason`
- `warnings`
- `created_at`

Rule: authoritative `RiskCheck` is created only by deterministic Risk Engine.

## PaperOrder

Required:

- `paper_order_id`
- `signal_id`
- `risk_check_id`
- `strategy_version_id`
- `side`
- `intended_size`
- `intended_price_ref`
- `created_at`
- `status`

Rule: Paper Trading Engine creates `PaperOrder` only from approved `Signal` and passed entry `RiskCheck`.

## PaperFill

Required:

- `paper_fill_id`
- `paper_order_id`
- `fill_time`
- `fill_price`
- `fees`
- `slippage`
- `latency_assumption`
- `liquidity_constraint`
- `failed_fill_reason`
- `market_snapshot_id`

Rule: no perfect fills.

## PaperPosition

Required:

- `position_id`
- `token_id`
- `strategy_version_id`
- `entry_order_id`
- `entry_fill_id`
- `size`
- `cost_basis`
- `opened_at`
- `status`

Rule: open position must have active monitoring job.

## ExitDecision

Required:

- `exit_decision_id`
- `position_id`
- `created_at`
- `data_as_of`
- `market_snapshot_id`
- `exit_reason`
- `exit_trigger`
- `expected_exit_logic`
- `created_by`

Rule: must exist before simulated exit fill.

## TradeOutcome

Required:

- `outcome_id`
- `position_id`
- `exit_decision_id`
- `gross_pnl`
- `net_pnl`
- `fees`
- `slippage`
- `duration`
- `max_drawdown`
- `calculated_at`

Rule: created only by deterministic Evaluation Engine.

