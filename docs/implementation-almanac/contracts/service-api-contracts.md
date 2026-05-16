# Service API Contracts

These are logical service/tool contracts. They may be implemented as MCP tools, internal HTTP APIs or direct service calls.

## Data and discovery

- `scan_token_candidates(source_set, config_snapshot_id)`
- `get_token_profile(token_id, market_snapshot_id?)`
- `create_monitoring_session(type, target_ref, strategy_version_id?)`

## Wallet intelligence

- `profile_wallet(wallet_id, token_context_ref?, config_snapshot_id)`
- `profile_wallet_cluster(cluster_ref, config_snapshot_id)`

Historical wallet outputs are candidate evidence only.

## Signal

- `create_signal(payload)`
- `create_no_trade_signal(payload)`

Signal creation must include strategy and config snapshot references.

## Risk

- `run_entry_risk_check(signal_id, market_snapshot_id, risk_limit_snapshot_id, config_snapshot_id)`
- `run_exit_risk_check(exit_decision_id, market_snapshot_id, risk_limit_snapshot_id, config_snapshot_id)`
- `run_position_monitoring_risk_check(position_id, market_snapshot_id, risk_limit_snapshot_id, config_snapshot_id)`

Risk API returns authoritative `RiskCheck`.

## Paper trading

- `create_paper_order(signal_id, risk_check_id)`
- `simulate_entry_fill(paper_order_id, market_snapshot_id)`
- `create_exit_decision(position_id, payload)`
- `execute_paper_exit(exit_decision_id, risk_check_id)`

Rules:

- `create_paper_order` rejects unless risk check passed and matches signal.
- `execute_paper_exit` rejects unless exit decision exists before fill and risk check matches position/exit.
- No `close_position(position_id, reason)` API is allowed.

## Evaluation

- `calculate_trade_outcome(position_id)`
- `get_strategy_metrics(strategy_version_id, config_snapshot_id?)`
- `compare_strategies(criteria_snapshot_id)`

## Jobs

- `lease_next_job(worker_type)`
- `complete_job(job_id, artifact_ref)`
- `fail_job(job_id, failure_reason)`
- `block_job(job_id, conflict_ref)`

## Memory

- `write_post_trade_review(position_id, review_payload)`
- `propose_memory_entry(payload)`
- `curate_memory_entry(memory_entry_id, action)`

