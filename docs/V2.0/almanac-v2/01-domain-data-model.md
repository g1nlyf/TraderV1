# V2 Domain Data Model

## Current Foundation To Reuse

The current Stage 2 schema already includes strong foundations:

- `raw_source_events`, `data_sources`, `source_health_snapshots`, `market_snapshots`;
- `token_candidates`, `token_profiles`, `token_triage_decisions`;
- `wallet_trades`, `wallet_metric_snapshots`, `wallet_profiles`, `wallet_clusters`;
- `signals`, `no_trade_signals`, `trade_theses`;
- `risk_checks`, `paper_orders`, `paper_fills`, `paper_positions`, `exit_decisions`, `trade_outcomes`;
- `jobs`, `worker_leases`, `monitoring_sessions`;
- `strategy_versions`, `strategy_experiments`, `strategy_metric_snapshots`, `strategy_decisions`;
- `memory_entries`, `memory_proposals`, `memory_curation_events`;
- `quote_observations`, `source_latency_samples`, `route_quality_evidence`, `fill_quote_comparisons`.

V2.0 should extend these rather than replace them.

## New Or Strengthened Objects

### TokenAgentDecision

Records the Token Selection Agent's attention decision.

Required fields:

- `token_agent_decision_id`;
- `token_profile_id` or `token_mint`;
- `decision_type`: `reject`, `passive_watch`, `deep_parse`, `active_watch`, `archive`;
- `reasons_json`;
- `uncertainties_json`;
- `requested_tool_calls_json`;
- `evidence_refs_json`;
- `confidence`;
- `created_at`;
- `expires_at`;
- `created_by_agent`.

### TokenTradeCorpus

Represents the best available parsed transaction set for a token/pool.

Required fields:

- `token_trade_corpus_id`;
- `token_mint`;
- `pool_address`;
- `window_start`;
- `window_end`;
- `source_names_json`;
- `trade_count`;
- `wallet_count`;
- `coverage_estimate`;
- `quality_flags_json`;
- `raw_event_refs_json`;
- `created_at`.

### WalletTokenOutcome

Stores token-specific wallet performance before broader wallet profiling.

Required fields:

- `wallet_token_outcome_id`;
- `wallet`;
- `token_mint`;
- `pool_address`;
- `buy_count`;
- `sell_count`;
- `realized_pnl_estimate`;
- `roi_estimate`;
- `notional_usd`;
- `entry_time`;
- `exit_time`;
- `holding_seconds`;
- `source_refs_json`;
- `quality_flags_json`;
- `eligible_for_agent_review`;

### AgentWalletReview

Stores the Wallet Intelligence Agent's decision.

Required fields:

- `agent_wallet_review_id`;
- `wallet`;
- `metrics_snapshot_id`;
- `decision`: `elite`, `probation`, `watch`, `reject`, `archive`;
- `agent_rating`;
- `copyability_rating`;
- `pnl_quality`;
- `winrate_quality`;
- `behavior_profile_json`;
- `why_yes_json`;
- `why_no_json`;
- `demotion_triggers_json`;
- `data_sufficiency`: `sufficient`, `partial`, `insufficient`;
- `observed_behavior_json`;
- `inferred_behavior_json`;
- `unknowns_json`;
- `evidence_refs_json`;
- `created_at`;
- `created_by_agent`.

### WalletForwardContribution

Measures whether tracked wallet signals helped future paper/shadow outcomes.

Required fields:

- `wallet_forward_contribution_id`;
- `wallet`;
- `strategy_version_id`;
- `window_start`;
- `window_end`;
- `signal_count`;
- `paper_trade_count`;
- `net_pnl`;
- `expectancy`;
- `win_rate`;
- `max_drawdown`;
- `quality_flags_json`;
- `calculated_by_service`;
- `calculated_at`.

### ActiveTokenSession

Represents the high-frequency Hermes market loop.

Required fields:

- `active_token_session_id`;
- `token_mint`;
- `pool_address`;
- `started_at`;
- `ended_at`;
- `status`: `active`, `paused`, `closed`, `degraded`;
- `trigger_ref`;
- `agent_owner`;
- `market_data_cadence_seconds`;
- `agent_review_cadence_seconds`;
- `cadence_policy_json`;
- `cadence_degradation_reason`;
- `source_capacity_state_json`;
- `last_market_snapshot_id`;
- `last_agent_decision_id`;
- `quality_flags_json`.

### AgentTradingDecision

Captures Hermes's contextual trading decision.

Required fields:

- `agent_trading_decision_id`;
- `active_token_session_id`;
- `decision_type`: `signal`, `no_trade`, `wait`, `exit`, `downgrade_wallet`, `downgrade_token`;
- `pre_action_reasoning`;
- `evidence_refs_json`;
- `wallet_refs_json`;
- `token_refs_json`;
- `market_snapshot_refs_json`;
- `source_quality_summary_json`;
- `uncertainties_json`;
- `created_at`;
- `data_as_of`;
- `linked_signal_id`;
- `linked_no_trade_signal_id`;
- `created_by_agent`.

## Data Flow Rules

1. Raw source data is stored first.
2. Normalized token/trade/wallet artifacts reference raw evidence.
3. Deterministic wallet metrics are calculated before agent wallet review.
4. Agent wallet review writes rating and reasons, not canonical P&L.
5. Active token sessions reference token and wallet evidence.
6. Hermes trading decisions reference all evidence used at decision time.
7. Signals and no-trades are derived from Hermes decisions.
8. Risk, paper/shadow, fills and outcomes remain deterministic.
