# 15. Implementation Guidance For IDE / Coding Agent

## Build order

Follow the five-sprint delivery plan in [14-final-system-delivery.md](14-final-system-delivery.md). Do not create a separate reduced product path.

1. Foundation, environment and source of truth.
2. Data, token discovery and wallet intelligence.
3. Integrated signal, risk and paper trading workflow.
4. Parallel monitoring, strategy search and memory.
5. Hardening, shadow mode and final acceptance.

Within each sprint, implement the smallest vertical slice that proves the sprint's integration gate. A slice is allowed as a construction check, not as a separate product version.

## Do first

Start with source-of-truth systems:

- database;
- raw event log;
- normalized snapshots;
- paper ledger;
- deterministic metrics.

Do not start with many agents. Agents without reliable measurement will amplify noise.

## Hermes integration pattern

Preferred:

```text
Hermes -> MCP/API tool -> deterministic service -> database/ledger -> structured response -> Hermes summary
```

Avoid:

```text
Hermes -> direct database mutation
Hermes -> manual P&L calculation
Hermes -> risk override
Hermes -> private key access
```

## Required internal services

- Data Ingestion Service.
- Token Discovery/Triage Service.
- Wallet Intelligence Service.
- Signal Service.
- Risk Service.
- Paper Trading Service.
- Evaluation Service.
- Job Queue / Monitoring Session Service.
- Experiment Registry.
- Memory Curator.
- Dashboard/Monitoring.

## Suggested first API/tool contracts

- `scan_token_candidates()`;
- `get_token_profile(mint)`;
- `profile_wallet(wallet)`;
- `create_signal(payload)`;
- `run_entry_risk_check(signal_id, market_snapshot_id, risk_limit_snapshot_id, config_snapshot_id)`;
- `create_paper_order(signal_id, risk_check_id)`;
- `create_exit_decision(position_id, payload)`;
- `run_exit_risk_check(exit_decision_id, market_snapshot_id, risk_limit_snapshot_id, config_snapshot_id)`;
- `execute_paper_exit(exit_decision_id, risk_check_id)`;
- `get_strategy_metrics(strategy_version)`;
- `register_experiment(payload)`;
- `write_post_trade_review(position_id, review)`;
- `create_monitoring_session(type, target_ref)`;
- `lease_next_job(worker_type)`;
- `complete_job(job_id, artifact_ref)`;
- `block_job(job_id, reason)`.

## Job queue rules

- Jobs are durable DB rows.
- Workers acquire leases with TTL.
- Expired leases return to queue.
- Every job has an output schema.
- Every job has a max retry count.
- Jobs reference data by ids, not by copying large context.
- Open paper position jobs outrank new discovery jobs.
- Conflicts create `conflict_review`, not silent overwrites.

## Data rules

- Store raw events before derived metrics.
- Keep timestamps explicit.
- Store source confidence.
- Store data_as_of separately from created_at.
- Use correction records instead of silent edits.
- Version strategies and filters.

## Paper order and exit rules

- `create_paper_order(signal_id, risk_check_id)` must reject unless `risk_check_id` belongs to the same signal, has `check_scope = entry`, passed under the current relevant config snapshots, and references a valid market snapshot.
- Exit must be two-step: create `ExitDecision` before simulated exit fill, then run deterministic exit risk check, then execute paper exit.
- `execute_paper_exit(exit_decision_id, risk_check_id)` must reject unless `risk_check_id` has `check_scope = exit` or `position_monitoring`, passed or explicitly authorizes a risk-stop exit, and references the same position/context.
- No API may close a paper position from free-text `reason` alone.

## Testing guidance

Use the narrowest meaningful verification:

- schema tests;
- deterministic P&L unit tests;
- risk check unit tests;
- paper ledger append-only tests;
- no-hindsight workflow tests;
- source adapter smoke tests;
- dashboard smoke test.

## Existing WalletScarper module

Before integrating:

- audit current data model;
- audit source assumptions;
- document transaction parser output;
- add confidence/completeness metadata;
- isolate adapters from strategy logic;
- ensure paper trading logic is not the same as live execution;
- avoid treating existing wallet scores as final truth.
