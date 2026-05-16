# 06. Data Model

This is a logical data model. The implementation may use SQLite/Postgres/etc., but entities and audit boundaries should remain.

## Entity table

| Entity | Purpose | Key fields | Created by | Used by | Why important for evaluation |
|---|---|---|---|---|---|
| TokenCandidate | Newly discovered token/pool candidate | id, mint, pool, source, discovered_at, source_confidence | Token Discovery | Triage | Defines opportunity universe |
| TokenProfile | Normalized token state | mint, age, market_cap, liquidity, holders, volume, tx_count, top_holder_concentration | Data/Triage | Signals, risk, metrics | Enables bucket analysis |
| WalletProfile | Current wallet intelligence profile | wallet, class, score, evidence_quality, degradation_status | Wallet Intelligence | Signals, dashboard | Tracks wallet edge |
| WalletTrade | Reconstructed wallet trade | wallet, token, side, amount, price, timestamp, source, fees_estimate | Wallet Intelligence | Wallet metrics | Basis for wallet P&L |
| WalletCluster | Related/coordinated wallet group | cluster_id, wallets, relation_type, evidence | Wallet Intelligence | Risk/signals | Prevents fake edge |
| Signal | Structured trade signal | id, timestamp, source, strategy_version_id, strategy_config_snapshot_id, promotion_criteria_snapshot_id if experiment-related, confidence, thesis, invalidation | Signal Generator | Risk, paper | Pre-trade decision record |
| TradeThesis | Human/LLM-readable reasoning before trade | signal_id, entry_reason, exit_plan, expected_holding_time, proof_wrong | Hypothesis Agent | Review | No hindsight and interpretability |
| PaperOrder | Intended virtual order | order_id, signal_id, risk_check_id, side, size, order_time, intended_price, status | Paper Trading Engine from approved Signal + passed RiskCheck; requested by Paper Trading Agent / Hermes tool | Paper engine | Records intent before fill |
| PaperFill | Simulated execution result | fill_id, order_id, fill_time, fill_price, slippage, fees, failed_fill_reason | Paper Engine | P&L | Execution realism |
| PaperPosition | Open/closed paper position state | position_id, token, size, cost_basis, opened_at, closed_at, status | Paper Engine | Monitoring | Exposure and lifecycle |
| ExitDecision | Pre-result exit decision | exit_decision_id, position_id, timestamp, reason, trigger, expected_exit_logic, data_as_of, market_snapshot_id | Agent/Risk | Paper engine | Prevents hindsight exits |
| TradeOutcome | Final trade result | position_id, gross_pnl, net_pnl, fees, slippage, duration, drawdown | Evaluation Engine | Metrics, review | Core performance truth |
| Hypothesis | Testable claim | hypothesis_id, statement, assumptions, scope, status | Hypothesis Agent | Experiments | Research unit |
| Experiment | Bounded test of hypothesis | experiment_id, hypothesis_id, budget, start/end, criteria, status | Supervisor | Strategy search | Controls p-hacking |
| StrategyVersion | Versioned strategy definition | version_id, strategy_config_snapshot_id, parent_version_id, mutation_proposal_id, rules, params, agents, created_at, status | Strategy Search | Signals, metrics | Comparable performance |
| AgentDecision | Auditable agent decision | agent, timestamp, inputs_ref, output, reason, confidence | Hermes/tools | Audit/review | Accountability |
| RiskCheck | Risk engine result | check_id, check_scope: entry/exit/position_monitoring, subject_type, subject_id, market_snapshot_id, risk_limit_snapshot_id, config_snapshot_id, data_as_of, pass, veto_reason | Risk Engine | Paper/live future | Safety and reproducibility |
| PostTradeReview | Structured review after outcome | position_id, mistakes, lessons, hypothesis_update | Review Agent | Memory, strategy | Learning loop |
| MemoryEntry | Curated knowledge item | id, claim, evidence_grade, source_refs, status, expires_at | Memory Curator | Hermes | Prevents stale knowledge |
| DataSource | Source metadata | source, type, latency, reliability, rate_limit, status | Ingestion | All layers | Data trust |
| MarketSnapshot | Timestamped market state | token, timestamp, price, liquidity, volume, spread, route_quality | Data Ingestion | Paper/risk | No-future-data execution |
| ContextSnapshot | Research context at decision time | signal_id, wallet_context, social_context, market_regime, raw_refs | Research agents | Review | Reconstructs what was known |
| Job | Durable unit of work for workers/agents | job_id, type, target_ref, priority, status, attempts, timeout, output_schema | Supervisor / queue | Workers | Enables bounded parallelism |
| MonitoringSession | Per-token/position/cluster session state | session_id, type, target_ref, state, owner, strategy_version, started_at, stop_reason | Queue/session service | Agents, dashboard | Prevents linear or chaotic monitoring |
| WorkerLease | Temporary ownership of a job/session | lease_id, job_id, worker_id, expires_at, heartbeat_at | Queue service | Workers | Prevents conflicting writes |
| ConflictReview | Blocked conflict between agents/actions | conflict_id, refs, conflict_type, proposed_actions, resolution, resolver | Supervisor/rules | Agents, audit | Prevents silent overwrite |
| StrategyMutationProposal | Proposed change to strategy | proposal_id, parent_version, mutation_type, fields_changed, hypothesis, budget | Hypothesis agent | Strategy search | Makes self-improvement auditable |
| BrowserExtraction | Browser-derived research artifact | extraction_id, url, timestamp, raw_ref, screenshot_ref, confidence, parser_version | Browser adapter | Research agents | Keeps browser facts non-canonical |
| ConfigSnapshot | Versioned system configuration | config_id, created_at, source, hash, settings_ref | Config service | All services | Reproduces decisions |
| RiskLimitSnapshot | Versioned risk limits | risk_config_id, max_exposure, max_drawdown, liquidity_veto, slippage_limit, stale_data_limit | Risk service/config | RiskCheck | Explains pass/veto |
| StrategyConfigSnapshot | Versioned strategy config | strategy_config_id, strategy_version, weights, thresholds, signal_rules, exit_rules | Strategy service | Signals, experiments | Reproduces strategy behavior |
| PromotionCriteriaSnapshot | Versioned promotion/demotion/kill criteria | criteria_id, min_trades, min_expectancy, drawdown_limit, confidence_rules, baseline_refs | Strategy search service | Strategy decisions | Prevents narrative promotion |
| AcceptanceRun | Final configured continuous run | run_id, config_snapshot_id, start/end, acceptance_window, invariant_violations, result | Operator/test harness | Final acceptance | Proves continuous operation |

## Immutability policy

Immutable:

- raw source events;
- Signal;
- TradeThesis after order creation;
- PaperOrder;
- PaperFill;
- ExitDecision;
- TradeOutcome;
- RiskCheck.
- WorkerLease history;
- ConflictReview resolution;
- BrowserExtraction raw refs.
- ConfigSnapshot;
- RiskLimitSnapshot;
- StrategyConfigSnapshot;
- PromotionCriteriaSnapshot;
- AcceptanceRun result.

Mutable but versioned:

- WalletProfile;
- TokenProfile;
- Hypothesis;
- StrategyVersion status;
- MemoryEntry status.
- Job status.
- MonitoringSession state.
- StrategyMutationProposal status.

## Required timestamps

Every decision entity must include:

- created_at;
- data_as_of;
- source_timestamp when available;
- agent_or_service that created it;
- strategy_version if related to trading.
- relevant config snapshot references.

## Config snapshot rule

Every `RiskCheck`, `StrategyVersion` promotion/demotion/kill decision, `Experiment` and `AcceptanceRun` must reference the relevant config snapshot.

Minimum references:

- `RiskCheck` -> `RiskLimitSnapshot` and `ConfigSnapshot`;
- `Signal` -> `StrategyConfigSnapshot`;
- `Experiment` -> `StrategyConfigSnapshot` and `PromotionCriteriaSnapshot`;
- strategy promotion/demotion/kill decision -> `PromotionCriteriaSnapshot`;
- `AcceptanceRun` -> `ConfigSnapshot`, `RiskLimitSnapshot` and acceptance window parameters.

## Source of truth

- Ledger and outcomes are source of truth for performance.
- Database is source of truth for structured history.
- Hermes memory is curated operational memory, not accounting truth.
- LLM summaries are explanations, not canonical metrics.
