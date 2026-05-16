from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Migration:
    version: int
    name: str
    sql: str


IMMUTABLE_TABLES = [
    "raw_source_events",
    "audit_events",
    "config_snapshots",
    "risk_limit_snapshots",
    "strategy_config_snapshots",
    "promotion_criteria_snapshots",
    "acceptance_runs",
    "signals",
    "trade_theses",
    "risk_checks",
    "paper_orders",
    "paper_fills",
    "exit_decisions",
    "trade_outcomes",
]


def _append_only_triggers_for(tables: list[str]) -> str:
    parts: list[str] = []
    for table in tables:
        parts.append(
            f"""
CREATE TRIGGER IF NOT EXISTS prevent_update_{table}
BEFORE UPDATE ON {table}
BEGIN
  SELECT RAISE(ABORT, '{table} is append-only');
END;
CREATE TRIGGER IF NOT EXISTS prevent_delete_{table}
BEFORE DELETE ON {table}
BEGIN
  SELECT RAISE(ABORT, '{table} is append-only');
END;
"""
        )
    return "\n".join(parts)


def _append_only_triggers() -> str:
    return _append_only_triggers_for(IMMUTABLE_TABLES)


FOUNDATION_SCHEMA = f"""
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS raw_source_events (
  raw_source_event_id TEXT PRIMARY KEY,
  source_name TEXT NOT NULL,
  source_type TEXT NOT NULL,
  external_id TEXT,
  payload_json TEXT NOT NULL,
  observed_at TEXT NOT NULL,
  ingested_at TEXT NOT NULL,
  confidence TEXT DEFAULT 'unknown',
  quality_metadata_json TEXT NOT NULL DEFAULT '{{}}'
);

CREATE TABLE IF NOT EXISTS audit_events (
  audit_event_id TEXT PRIMARY KEY,
  actor TEXT NOT NULL,
  action TEXT NOT NULL,
  entity_type TEXT NOT NULL,
  entity_id TEXT NOT NULL,
  created_at TEXT NOT NULL,
  payload_json TEXT NOT NULL DEFAULT '{{}}',
  diff_json TEXT,
  metadata_json TEXT NOT NULL DEFAULT '{{}}',
  correlation_id TEXT
);

CREATE TABLE IF NOT EXISTS config_snapshots (
  config_snapshot_id TEXT PRIMARY KEY,
  created_at TEXT NOT NULL,
  source TEXT NOT NULL,
  content_hash TEXT NOT NULL UNIQUE,
  environment TEXT NOT NULL,
  app_version TEXT NOT NULL,
  settings_json TEXT NOT NULL,
  build_info_json TEXT NOT NULL DEFAULT '{{}}'
);

CREATE TABLE IF NOT EXISTS risk_limit_snapshots (
  risk_limit_snapshot_id TEXT PRIMARY KEY,
  config_snapshot_id TEXT,
  created_at TEXT NOT NULL,
  source TEXT NOT NULL,
  content_hash TEXT NOT NULL UNIQUE,
  limits_json TEXT NOT NULL,
  FOREIGN KEY(config_snapshot_id) REFERENCES config_snapshots(config_snapshot_id)
);

CREATE TABLE IF NOT EXISTS strategy_config_snapshots (
  strategy_config_snapshot_id TEXT PRIMARY KEY,
  config_snapshot_id TEXT,
  strategy_name TEXT NOT NULL,
  strategy_version_label TEXT NOT NULL,
  created_at TEXT NOT NULL,
  content_hash TEXT NOT NULL UNIQUE,
  weights_json TEXT NOT NULL DEFAULT '{{}}',
  thresholds_json TEXT NOT NULL DEFAULT '{{}}',
  signal_rules_json TEXT NOT NULL DEFAULT '{{}}',
  exit_rules_json TEXT NOT NULL DEFAULT '{{}}',
  no_trade_rules_json TEXT NOT NULL DEFAULT '{{}}',
  FOREIGN KEY(config_snapshot_id) REFERENCES config_snapshots(config_snapshot_id)
);

CREATE TABLE IF NOT EXISTS promotion_criteria_snapshots (
  promotion_criteria_snapshot_id TEXT PRIMARY KEY,
  config_snapshot_id TEXT,
  created_at TEXT NOT NULL,
  source TEXT NOT NULL,
  content_hash TEXT NOT NULL UNIQUE,
  criteria_json TEXT NOT NULL,
  FOREIGN KEY(config_snapshot_id) REFERENCES config_snapshots(config_snapshot_id)
);

CREATE TABLE IF NOT EXISTS acceptance_runs (
  acceptance_run_id TEXT PRIMARY KEY,
  config_snapshot_id TEXT NOT NULL,
  risk_limit_snapshot_id TEXT,
  promotion_criteria_snapshot_id TEXT,
  created_at TEXT NOT NULL,
  acceptance_window_started_at TEXT,
  acceptance_window_ended_at TEXT,
  completed_at TEXT,
  invariant_violations_json TEXT NOT NULL DEFAULT '[]',
  result TEXT NOT NULL DEFAULT 'pending',
  gap_report_json TEXT,
  FOREIGN KEY(config_snapshot_id) REFERENCES config_snapshots(config_snapshot_id),
  FOREIGN KEY(risk_limit_snapshot_id) REFERENCES risk_limit_snapshots(risk_limit_snapshot_id),
  FOREIGN KEY(promotion_criteria_snapshot_id) REFERENCES promotion_criteria_snapshots(promotion_criteria_snapshot_id)
);

CREATE TABLE IF NOT EXISTS strategy_versions (
  strategy_version_id TEXT PRIMARY KEY,
  strategy_config_snapshot_id TEXT NOT NULL,
  parent_strategy_version_id TEXT,
  mutation_proposal_id TEXT,
  rules_json TEXT NOT NULL DEFAULT '{{}}',
  params_json TEXT NOT NULL DEFAULT '{{}}',
  agents_json TEXT NOT NULL DEFAULT '[]',
  created_at TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'experimental',
  FOREIGN KEY(strategy_config_snapshot_id) REFERENCES strategy_config_snapshots(strategy_config_snapshot_id),
  FOREIGN KEY(parent_strategy_version_id) REFERENCES strategy_versions(strategy_version_id)
);

CREATE TABLE IF NOT EXISTS signals (
  signal_id TEXT PRIMARY KEY,
  created_at TEXT NOT NULL,
  data_as_of TEXT NOT NULL,
  token_id TEXT NOT NULL,
  strategy_version_id TEXT NOT NULL,
  strategy_config_snapshot_id TEXT NOT NULL,
  promotion_criteria_snapshot_id TEXT,
  source_refs_json TEXT NOT NULL DEFAULT '[]',
  confidence TEXT NOT NULL DEFAULT 'unknown',
  thesis_ref TEXT,
  invalidation_condition TEXT NOT NULL,
  expected_holding_time TEXT NOT NULL,
  estimated_risk_json TEXT NOT NULL DEFAULT '{{}}',
  estimated_slippage REAL,
  status TEXT NOT NULL DEFAULT 'candidate',
  FOREIGN KEY(strategy_version_id) REFERENCES strategy_versions(strategy_version_id),
  FOREIGN KEY(strategy_config_snapshot_id) REFERENCES strategy_config_snapshots(strategy_config_snapshot_id),
  FOREIGN KEY(promotion_criteria_snapshot_id) REFERENCES promotion_criteria_snapshots(promotion_criteria_snapshot_id)
);

CREATE TABLE IF NOT EXISTS trade_theses (
  thesis_id TEXT PRIMARY KEY,
  signal_id TEXT NOT NULL,
  entry_reason TEXT NOT NULL,
  exit_plan TEXT NOT NULL,
  expected_holding_time TEXT NOT NULL,
  proof_wrong TEXT NOT NULL,
  context_snapshot_id TEXT,
  created_at TEXT NOT NULL,
  FOREIGN KEY(signal_id) REFERENCES signals(signal_id)
);

CREATE TABLE IF NOT EXISTS risk_checks (
  risk_check_id TEXT PRIMARY KEY,
  check_scope TEXT NOT NULL CHECK(check_scope IN ('entry', 'exit', 'position_monitoring')),
  subject_type TEXT NOT NULL CHECK(subject_type IN ('signal', 'paper_order', 'paper_position', 'exit_decision')),
  subject_id TEXT NOT NULL,
  market_snapshot_id TEXT,
  risk_limit_snapshot_id TEXT NOT NULL,
  config_snapshot_id TEXT NOT NULL,
  data_as_of TEXT NOT NULL,
  passed INTEGER NOT NULL CHECK(passed IN (0, 1)),
  veto_reason TEXT,
  warnings_json TEXT NOT NULL DEFAULT '[]',
  created_at TEXT NOT NULL,
  created_by_service TEXT NOT NULL DEFAULT 'risk_service',
  FOREIGN KEY(risk_limit_snapshot_id) REFERENCES risk_limit_snapshots(risk_limit_snapshot_id),
  FOREIGN KEY(config_snapshot_id) REFERENCES config_snapshots(config_snapshot_id)
);

CREATE TABLE IF NOT EXISTS paper_orders (
  paper_order_id TEXT PRIMARY KEY,
  signal_id TEXT NOT NULL,
  risk_check_id TEXT NOT NULL,
  strategy_version_id TEXT NOT NULL,
  side TEXT NOT NULL CHECK(side IN ('buy', 'sell')),
  intended_size REAL NOT NULL,
  intended_price_ref TEXT,
  created_at TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'created',
  FOREIGN KEY(signal_id) REFERENCES signals(signal_id),
  FOREIGN KEY(risk_check_id) REFERENCES risk_checks(risk_check_id),
  FOREIGN KEY(strategy_version_id) REFERENCES strategy_versions(strategy_version_id)
);

CREATE TABLE IF NOT EXISTS paper_fills (
  paper_fill_id TEXT PRIMARY KEY,
  paper_order_id TEXT NOT NULL,
  fill_time TEXT NOT NULL,
  fill_price REAL,
  fees REAL NOT NULL DEFAULT 0,
  slippage REAL NOT NULL DEFAULT 0,
  latency_assumption TEXT NOT NULL,
  liquidity_constraint TEXT NOT NULL,
  failed_fill_reason TEXT,
  market_snapshot_id TEXT,
  FOREIGN KEY(paper_order_id) REFERENCES paper_orders(paper_order_id)
);

CREATE TABLE IF NOT EXISTS paper_positions (
  position_id TEXT PRIMARY KEY,
  token_id TEXT NOT NULL,
  strategy_version_id TEXT NOT NULL,
  entry_order_id TEXT NOT NULL,
  entry_fill_id TEXT NOT NULL,
  size REAL NOT NULL,
  cost_basis REAL NOT NULL,
  opened_at TEXT NOT NULL,
  closed_at TEXT,
  status TEXT NOT NULL DEFAULT 'open',
  FOREIGN KEY(strategy_version_id) REFERENCES strategy_versions(strategy_version_id),
  FOREIGN KEY(entry_order_id) REFERENCES paper_orders(paper_order_id),
  FOREIGN KEY(entry_fill_id) REFERENCES paper_fills(paper_fill_id)
);

CREATE TABLE IF NOT EXISTS exit_decisions (
  exit_decision_id TEXT PRIMARY KEY,
  position_id TEXT NOT NULL,
  created_at TEXT NOT NULL,
  data_as_of TEXT NOT NULL,
  market_snapshot_id TEXT,
  exit_reason TEXT NOT NULL,
  exit_trigger TEXT NOT NULL,
  expected_exit_logic TEXT NOT NULL,
  created_by TEXT NOT NULL,
  FOREIGN KEY(position_id) REFERENCES paper_positions(position_id)
);

CREATE TABLE IF NOT EXISTS trade_outcomes (
  outcome_id TEXT PRIMARY KEY,
  position_id TEXT NOT NULL,
  exit_decision_id TEXT NOT NULL,
  gross_pnl REAL NOT NULL,
  net_pnl REAL NOT NULL,
  fees REAL NOT NULL,
  slippage REAL NOT NULL,
  duration_seconds REAL NOT NULL,
  max_drawdown REAL NOT NULL,
  calculated_at TEXT NOT NULL,
  calculated_by_service TEXT NOT NULL DEFAULT 'evaluation_service',
  FOREIGN KEY(position_id) REFERENCES paper_positions(position_id),
  FOREIGN KEY(exit_decision_id) REFERENCES exit_decisions(exit_decision_id)
);

CREATE TABLE IF NOT EXISTS post_trade_reviews (
  post_trade_review_id TEXT PRIMARY KEY,
  outcome_id TEXT NOT NULL,
  position_id TEXT NOT NULL,
  reviewer TEXT NOT NULL,
  mistakes_json TEXT NOT NULL DEFAULT '[]',
  lessons_json TEXT NOT NULL DEFAULT '[]',
  hypothesis_update_json TEXT NOT NULL DEFAULT '{{}}',
  evidence_refs_json TEXT NOT NULL DEFAULT '[]',
  created_at TEXT NOT NULL,
  FOREIGN KEY(outcome_id) REFERENCES trade_outcomes(outcome_id),
  FOREIGN KEY(position_id) REFERENCES paper_positions(position_id)
);

CREATE TABLE IF NOT EXISTS memory_entries (
  memory_entry_id TEXT PRIMARY KEY,
  claim TEXT NOT NULL,
  evidence_grade TEXT NOT NULL,
  source_refs_json TEXT NOT NULL DEFAULT '[]',
  status TEXT NOT NULL DEFAULT 'proposed',
  expires_at TEXT,
  created_at TEXT NOT NULL,
  created_by TEXT NOT NULL,
  metadata_json TEXT NOT NULL DEFAULT '{{}}'
);

CREATE TABLE IF NOT EXISTS jobs (
  job_id TEXT PRIMARY KEY,
  job_type TEXT NOT NULL,
  worker_type TEXT,
  target_ref TEXT,
  status TEXT NOT NULL CHECK(status IN ('pending', 'running', 'completed', 'failed', 'blocked')),
  priority INTEGER NOT NULL DEFAULT 100,
  payload_json TEXT NOT NULL DEFAULT '{{}}',
  output_schema_json TEXT NOT NULL DEFAULT '{{}}',
  attempts INTEGER NOT NULL DEFAULT 0,
  max_attempts INTEGER NOT NULL DEFAULT 3,
  scheduled_at TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  last_error TEXT
);

CREATE TABLE IF NOT EXISTS worker_leases (
  worker_lease_id TEXT PRIMARY KEY,
  job_id TEXT NOT NULL,
  worker_id TEXT NOT NULL,
  lease_acquired_at TEXT NOT NULL,
  lease_expires_at TEXT NOT NULL,
  heartbeat_at TEXT NOT NULL,
  metadata_json TEXT NOT NULL DEFAULT '{{}}',
  FOREIGN KEY(job_id) REFERENCES jobs(job_id)
);

CREATE TABLE IF NOT EXISTS monitoring_sessions (
  monitoring_session_id TEXT PRIMARY KEY,
  session_type TEXT NOT NULL,
  subject_type TEXT NOT NULL,
  subject_id TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  priority INTEGER NOT NULL DEFAULT 100,
  strategy_version_id TEXT,
  started_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  stopped_at TEXT,
  stop_reason TEXT,
  metadata_json TEXT NOT NULL DEFAULT '{{}}',
  FOREIGN KEY(strategy_version_id) REFERENCES strategy_versions(strategy_version_id)
);

CREATE TABLE IF NOT EXISTS conflict_reviews (
  conflict_review_id TEXT PRIMARY KEY,
  subject_type TEXT NOT NULL,
  subject_id TEXT NOT NULL,
  conflicting_action TEXT NOT NULL,
  reason TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'open',
  resolution TEXT,
  audit_event_id TEXT,
  created_at TEXT NOT NULL,
  resolved_at TEXT,
  metadata_json TEXT NOT NULL DEFAULT '{{}}',
  FOREIGN KEY(audit_event_id) REFERENCES audit_events(audit_event_id)
);

CREATE INDEX IF NOT EXISTS idx_jobs_available ON jobs(status, priority, scheduled_at);
CREATE INDEX IF NOT EXISTS idx_worker_leases_job_expiry ON worker_leases(job_id, lease_expires_at);
CREATE INDEX IF NOT EXISTS idx_risk_checks_subject ON risk_checks(subject_type, subject_id, check_scope);
CREATE INDEX IF NOT EXISTS idx_paper_orders_signal ON paper_orders(signal_id);
CREATE INDEX IF NOT EXISTS idx_audit_events_entity ON audit_events(entity_type, entity_id, created_at);

{_append_only_triggers()}
"""


EVIDENCE_IMMUTABLE_TABLES = [
    "source_health_snapshots",
    "token_candidates",
    "market_snapshots",
    "normalized_evidence_refs",
]


SOURCE_EVIDENCE_SCHEMA = f"""
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS data_sources (
  data_source_id TEXT PRIMARY KEY,
  source_name TEXT NOT NULL UNIQUE,
  source_type TEXT NOT NULL,
  adapter_name TEXT NOT NULL,
  reliability_tier TEXT NOT NULL DEFAULT 'unknown',
  interface_kind TEXT NOT NULL CHECK(interface_kind IN ('api', 'rpc', 'browser', 'stream', 'fixture', 'legacy_mapped')),
  allowed_for_high_confidence_evaluation INTEGER NOT NULL CHECK(allowed_for_high_confidence_evaluation IN (0, 1)),
  status TEXT NOT NULL DEFAULT 'unknown',
  notes TEXT,
  metadata_json TEXT NOT NULL DEFAULT '{{}}',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS source_health_snapshots (
  source_health_snapshot_id TEXT PRIMARY KEY,
  data_source_id TEXT,
  source_name TEXT NOT NULL,
  observed_at TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('healthy', 'degraded', 'unavailable', 'unknown')),
  latency_ms REAL,
  error_rate REAL,
  rate_limit_state_json TEXT NOT NULL DEFAULT '{{}}',
  last_successful_event_at TEXT,
  degradation_reason TEXT,
  confidence_impact TEXT NOT NULL DEFAULT 'unknown',
  metadata_json TEXT NOT NULL DEFAULT '{{}}',
  FOREIGN KEY(data_source_id) REFERENCES data_sources(data_source_id)
);

CREATE TABLE IF NOT EXISTS ingestion_runs (
  ingestion_run_id TEXT PRIMARY KEY,
  data_source_id TEXT,
  source_name TEXT NOT NULL,
  adapter_name TEXT NOT NULL,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  status TEXT NOT NULL CHECK(status IN ('running', 'completed', 'failed', 'degraded', 'aborted')),
  events_seen INTEGER NOT NULL DEFAULT 0,
  events_written INTEGER NOT NULL DEFAULT 0,
  events_rejected INTEGER NOT NULL DEFAULT 0,
  quality_summary_json TEXT NOT NULL DEFAULT '{{}}',
  error_summary_json TEXT NOT NULL DEFAULT '{{}}',
  correlation_id TEXT,
  metadata_json TEXT NOT NULL DEFAULT '{{}}',
  FOREIGN KEY(data_source_id) REFERENCES data_sources(data_source_id)
);

CREATE TABLE IF NOT EXISTS token_candidates (
  token_candidate_id TEXT PRIMARY KEY,
  token_mint TEXT,
  chain TEXT,
  ecosystem TEXT,
  symbol TEXT,
  name TEXT,
  discovered_at TEXT NOT NULL,
  data_source_id TEXT,
  source_names_json TEXT NOT NULL DEFAULT '[]',
  raw_event_refs_json TEXT NOT NULL DEFAULT '[]',
  confidence TEXT NOT NULL DEFAULT 'unknown',
  quality_flags_json TEXT NOT NULL DEFAULT '[]',
  candidate_status TEXT NOT NULL CHECK(candidate_status IN ('discovered', 'triage_pending', 'watching', 'archived', 'rejected')),
  rejection_reason TEXT,
  eligible_for_high_confidence_evaluation INTEGER NOT NULL CHECK(eligible_for_high_confidence_evaluation IN (0, 1)),
  created_at TEXT NOT NULL,
  FOREIGN KEY(data_source_id) REFERENCES data_sources(data_source_id)
);

CREATE TABLE IF NOT EXISTS market_snapshots (
  market_snapshot_id TEXT PRIMARY KEY,
  token_candidate_id TEXT,
  token_mint TEXT,
  pool_address TEXT,
  chain TEXT,
  observed_at TEXT NOT NULL,
  data_source_id TEXT,
  source_name TEXT NOT NULL,
  raw_source_event_id TEXT NOT NULL,
  price_usd REAL,
  liquidity_usd REAL,
  volume_5m REAL,
  volume_1h REAL,
  volume_6h REAL,
  volume_24h REAL,
  market_cap REAL,
  fdv REAL,
  txns_5m INTEGER,
  txns_1h INTEGER,
  holder_count INTEGER,
  confidence TEXT NOT NULL DEFAULT 'unknown',
  quality_flags_json TEXT NOT NULL DEFAULT '[]',
  eligible_for_high_confidence_evaluation INTEGER NOT NULL CHECK(eligible_for_high_confidence_evaluation IN (0, 1)),
  created_at TEXT NOT NULL,
  FOREIGN KEY(token_candidate_id) REFERENCES token_candidates(token_candidate_id),
  FOREIGN KEY(data_source_id) REFERENCES data_sources(data_source_id),
  FOREIGN KEY(raw_source_event_id) REFERENCES raw_source_events(raw_source_event_id)
);

CREATE TABLE IF NOT EXISTS normalized_evidence_refs (
  normalized_evidence_ref_id TEXT PRIMARY KEY,
  raw_source_event_id TEXT NOT NULL,
  normalized_type TEXT NOT NULL,
  normalized_id TEXT NOT NULL,
  created_at TEXT NOT NULL,
  metadata_json TEXT NOT NULL DEFAULT '{{}}',
  FOREIGN KEY(raw_source_event_id) REFERENCES raw_source_events(raw_source_event_id)
);

CREATE INDEX IF NOT EXISTS idx_data_sources_name ON data_sources(source_name);
CREATE INDEX IF NOT EXISTS idx_source_health_source_time ON source_health_snapshots(source_name, observed_at);
CREATE INDEX IF NOT EXISTS idx_ingestion_runs_source_status ON ingestion_runs(source_name, status, started_at);
CREATE INDEX IF NOT EXISTS idx_token_candidates_mint ON token_candidates(token_mint);
CREATE INDEX IF NOT EXISTS idx_market_snapshots_token_time ON market_snapshots(token_mint, observed_at);
CREATE INDEX IF NOT EXISTS idx_market_snapshots_raw_event ON market_snapshots(raw_source_event_id);
CREATE INDEX IF NOT EXISTS idx_normalized_evidence_raw ON normalized_evidence_refs(raw_source_event_id);

{_append_only_triggers_for(EVIDENCE_IMMUTABLE_TABLES)}
"""


MIGRATIONS = [
    Migration(1, "stage2_foundation_schema", FOUNDATION_SCHEMA),
    Migration(2, "stage2_source_registry_and_evidence_schema", SOURCE_EVIDENCE_SCHEMA),
]


SPRINT2_COMPLETION_IMMUTABLE_TABLES = [
    "browser_extractions",
    "token_profiles",
    "token_triage_configs",
    "token_triage_decisions",
    "wallet_trades",
    "wallet_metric_snapshots",
    "wallet_profiles",
    "wallet_clusters",
]


SPRINT2_COMPLETION_SCHEMA = f"""
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS browser_extractions (
  browser_extraction_id TEXT PRIMARY KEY,
  source_url TEXT NOT NULL,
  source_name TEXT,
  raw_source_event_id TEXT,
  extracted_at TEXT NOT NULL,
  parser_name TEXT NOT NULL,
  parser_version TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('success', 'failed')),
  raw_html_ref TEXT,
  screenshot_ref TEXT,
  snapshot_ref TEXT,
  extracted_fields_json TEXT NOT NULL DEFAULT '{{}}',
  confidence_score REAL NOT NULL DEFAULT 0,
  degradation_reason TEXT,
  quality_flags_json TEXT NOT NULL DEFAULT '[]',
  eligible_for_high_confidence_evaluation INTEGER NOT NULL DEFAULT 0 CHECK(eligible_for_high_confidence_evaluation IN (0, 1)),
  created_at TEXT NOT NULL,
  FOREIGN KEY(raw_source_event_id) REFERENCES raw_source_events(raw_source_event_id)
);

CREATE TABLE IF NOT EXISTS token_profiles (
  token_profile_id TEXT PRIMARY KEY,
  token_candidate_id TEXT,
  token_mint TEXT,
  pool_address TEXT,
  chain TEXT,
  ecosystem TEXT,
  symbol TEXT,
  name TEXT,
  discovered_at TEXT,
  latest_observed_at TEXT NOT NULL,
  age_seconds REAL,
  market_cap REAL,
  fdv REAL,
  liquidity_usd REAL,
  volume_24h REAL,
  txns_1h INTEGER,
  holder_count INTEGER,
  top_holder_concentration REAL,
  source_refs_json TEXT NOT NULL DEFAULT '[]',
  evidence_quality TEXT NOT NULL DEFAULT 'unknown',
  confidence TEXT NOT NULL DEFAULT 'unknown',
  quality_flags_json TEXT NOT NULL DEFAULT '[]',
  degradation_status TEXT NOT NULL DEFAULT 'unknown',
  eligible_for_high_confidence_evaluation INTEGER NOT NULL DEFAULT 0 CHECK(eligible_for_high_confidence_evaluation IN (0, 1)),
  created_at TEXT NOT NULL,
  FOREIGN KEY(token_candidate_id) REFERENCES token_candidates(token_candidate_id)
);

CREATE TABLE IF NOT EXISTS token_triage_configs (
  token_triage_config_id TEXT PRIMARY KEY,
  version_label TEXT NOT NULL,
  content_hash TEXT NOT NULL UNIQUE,
  bucket_priors_json TEXT NOT NULL,
  notes TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS token_triage_decisions (
  token_triage_decision_id TEXT PRIMARY KEY,
  token_profile_id TEXT NOT NULL,
  token_candidate_id TEXT,
  token_triage_config_id TEXT NOT NULL,
  decision_status TEXT NOT NULL CHECK(decision_status IN ('discovered', 'triage_pending', 'watching', 'archived', 'rejected')),
  reasons_json TEXT NOT NULL DEFAULT '[]',
  bucket_assignments_json TEXT NOT NULL DEFAULT '{{}}',
  no_trade_reason TEXT,
  confidence TEXT NOT NULL DEFAULT 'unknown',
  quality_flags_json TEXT NOT NULL DEFAULT '[]',
  created_at TEXT NOT NULL,
  FOREIGN KEY(token_profile_id) REFERENCES token_profiles(token_profile_id),
  FOREIGN KEY(token_candidate_id) REFERENCES token_candidates(token_candidate_id),
  FOREIGN KEY(token_triage_config_id) REFERENCES token_triage_configs(token_triage_config_id)
);

CREATE TABLE IF NOT EXISTS wallet_trades (
  wallet_trade_id TEXT PRIMARY KEY,
  wallet TEXT,
  token_mint TEXT,
  pool_address TEXT,
  side TEXT CHECK(side IN ('buy', 'sell') OR side IS NULL),
  token_amount REAL,
  quote_amount REAL,
  price_usd REAL,
  observed_at TEXT NOT NULL,
  source_name TEXT NOT NULL,
  raw_source_event_id TEXT NOT NULL,
  market_snapshot_id TEXT,
  fees_estimate REAL,
  confidence TEXT NOT NULL DEFAULT 'unknown',
  quality_flags_json TEXT NOT NULL DEFAULT '[]',
  reconstruction_method TEXT NOT NULL,
  eligible_for_high_confidence_evaluation INTEGER NOT NULL DEFAULT 0 CHECK(eligible_for_high_confidence_evaluation IN (0, 1)),
  created_at TEXT NOT NULL,
  FOREIGN KEY(raw_source_event_id) REFERENCES raw_source_events(raw_source_event_id),
  FOREIGN KEY(market_snapshot_id) REFERENCES market_snapshots(market_snapshot_id)
);

CREATE TABLE IF NOT EXISTS wallet_metric_snapshots (
  wallet_metric_snapshot_id TEXT PRIMARY KEY,
  wallet TEXT NOT NULL,
  calculated_at TEXT NOT NULL,
  trade_count INTEGER NOT NULL DEFAULT 0,
  closed_trade_count INTEGER NOT NULL DEFAULT 0,
  realized_pnl_estimate REAL,
  unrealized_inventory_json TEXT NOT NULL DEFAULT '{{}}',
  net_pnl_estimate REAL,
  win_rate_estimate REAL,
  expectancy_estimate REAL,
  payoff_ratio REAL,
  average_win REAL,
  average_loss REAL,
  holding_time_summary_json TEXT NOT NULL DEFAULT '{{}}',
  position_sizing_summary_json TEXT NOT NULL DEFAULT '{{}}',
  sample_size INTEGER NOT NULL DEFAULT 0,
  recency_seconds REAL,
  evidence_quality TEXT NOT NULL DEFAULT 'unknown',
  confidence TEXT NOT NULL DEFAULT 'unknown',
  quality_flags_json TEXT NOT NULL DEFAULT '[]',
  source_refs_json TEXT NOT NULL DEFAULT '[]',
  candidate_evidence_only INTEGER NOT NULL DEFAULT 1 CHECK(candidate_evidence_only IN (0, 1)),
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS wallet_profiles (
  wallet_profile_id TEXT PRIMARY KEY,
  wallet TEXT NOT NULL,
  metrics_snapshot_id TEXT,
  label TEXT NOT NULL,
  label_confidence TEXT NOT NULL DEFAULT 'unknown',
  candidate_score REAL,
  evidence_quality TEXT NOT NULL DEFAULT 'unknown',
  degradation_status TEXT NOT NULL DEFAULT 'unknown',
  sample_size INTEGER NOT NULL DEFAULT 0,
  recency_seconds REAL,
  source_refs_json TEXT NOT NULL DEFAULT '[]',
  explanation_json TEXT NOT NULL DEFAULT '{{}}',
  included_reasons_json TEXT NOT NULL DEFAULT '[]',
  excluded_reasons_json TEXT NOT NULL DEFAULT '[]',
  last_updated_at TEXT NOT NULL,
  candidate_evidence_only INTEGER NOT NULL DEFAULT 1 CHECK(candidate_evidence_only IN (0, 1)),
  created_at TEXT NOT NULL,
  FOREIGN KEY(metrics_snapshot_id) REFERENCES wallet_metric_snapshots(wallet_metric_snapshot_id)
);

CREATE TABLE IF NOT EXISTS wallet_clusters (
  wallet_cluster_id TEXT PRIMARY KEY,
  relation_type TEXT NOT NULL,
  wallets_json TEXT NOT NULL DEFAULT '[]',
  token_mint TEXT,
  evidence_refs_json TEXT NOT NULL DEFAULT '[]',
  confidence TEXT NOT NULL DEFAULT 'unknown',
  quality_flags_json TEXT NOT NULL DEFAULT '[]',
  flags_json TEXT NOT NULL DEFAULT '[]',
  created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_browser_extractions_url_time ON browser_extractions(source_url, extracted_at);
CREATE INDEX IF NOT EXISTS idx_token_profiles_mint_time ON token_profiles(token_mint, latest_observed_at);
CREATE INDEX IF NOT EXISTS idx_token_triage_decisions_profile ON token_triage_decisions(token_profile_id, created_at);
CREATE INDEX IF NOT EXISTS idx_wallet_trades_wallet_time ON wallet_trades(wallet, observed_at);
CREATE INDEX IF NOT EXISTS idx_wallet_trades_raw_event ON wallet_trades(raw_source_event_id);
CREATE INDEX IF NOT EXISTS idx_wallet_metric_snapshots_wallet_time ON wallet_metric_snapshots(wallet, calculated_at);
CREATE INDEX IF NOT EXISTS idx_wallet_profiles_wallet_time ON wallet_profiles(wallet, last_updated_at);
CREATE INDEX IF NOT EXISTS idx_wallet_clusters_token ON wallet_clusters(token_mint);

{_append_only_triggers_for(SPRINT2_COMPLETION_IMMUTABLE_TABLES)}
"""


MIGRATIONS.append(Migration(3, "stage2_data_wallet_intelligence_completion_schema", SPRINT2_COMPLETION_SCHEMA))


SPRINT3_WORKFLOW_IMMUTABLE_TABLES = [
    "no_trade_signals",
    "trade_thesis_details",
    "paper_position_events",
    "rejected_trade_logs",
    "missed_opportunity_logs",
    "paper_positions",
]


SPRINT3_SIGNAL_RISK_PAPER_SCHEMA = f"""
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS no_trade_signals (
  no_trade_signal_id TEXT PRIMARY KEY,
  created_at TEXT NOT NULL,
  data_as_of TEXT NOT NULL,
  token_id TEXT,
  token_profile_id TEXT,
  strategy_version_id TEXT NOT NULL,
  strategy_config_snapshot_id TEXT NOT NULL,
  promotion_criteria_snapshot_id TEXT,
  reason TEXT NOT NULL,
  source_refs_json TEXT NOT NULL DEFAULT '[]',
  confidence TEXT NOT NULL DEFAULT 'unknown',
  quality_flags_json TEXT NOT NULL DEFAULT '[]',
  observe_later INTEGER NOT NULL DEFAULT 0 CHECK(observe_later IN (0, 1)),
  status TEXT NOT NULL DEFAULT 'logged',
  FOREIGN KEY(token_profile_id) REFERENCES token_profiles(token_profile_id),
  FOREIGN KEY(strategy_version_id) REFERENCES strategy_versions(strategy_version_id),
  FOREIGN KEY(strategy_config_snapshot_id) REFERENCES strategy_config_snapshots(strategy_config_snapshot_id),
  FOREIGN KEY(promotion_criteria_snapshot_id) REFERENCES promotion_criteria_snapshots(promotion_criteria_snapshot_id)
);

CREATE TABLE IF NOT EXISTS trade_thesis_details (
  trade_thesis_detail_id TEXT PRIMARY KEY,
  thesis_id TEXT NOT NULL UNIQUE,
  signal_id TEXT NOT NULL,
  why_token TEXT NOT NULL,
  why_now TEXT NOT NULL,
  evidence_refs_json TEXT NOT NULL DEFAULT '[]',
  planned_exit_logic TEXT NOT NULL,
  invalidation_condition TEXT NOT NULL,
  wrong_condition TEXT NOT NULL,
  uncopyable_risk TEXT NOT NULL,
  strategy_version_id TEXT NOT NULL,
  created_at TEXT NOT NULL,
  FOREIGN KEY(thesis_id) REFERENCES trade_theses(thesis_id),
  FOREIGN KEY(signal_id) REFERENCES signals(signal_id),
  FOREIGN KEY(strategy_version_id) REFERENCES strategy_versions(strategy_version_id)
);

CREATE TABLE IF NOT EXISTS paper_position_events (
  paper_position_event_id TEXT PRIMARY KEY,
  position_id TEXT NOT NULL,
  event_type TEXT NOT NULL,
  created_at TEXT NOT NULL,
  market_snapshot_id TEXT,
  risk_check_id TEXT,
  payload_json TEXT NOT NULL DEFAULT '{{}}',
  FOREIGN KEY(position_id) REFERENCES paper_positions(position_id),
  FOREIGN KEY(risk_check_id) REFERENCES risk_checks(risk_check_id),
  FOREIGN KEY(market_snapshot_id) REFERENCES market_snapshots(market_snapshot_id)
);

CREATE TABLE IF NOT EXISTS rejected_trade_logs (
  rejected_trade_log_id TEXT PRIMARY KEY,
  subject_type TEXT NOT NULL,
  subject_id TEXT,
  stage TEXT NOT NULL,
  reason TEXT NOT NULL,
  source_refs_json TEXT NOT NULL DEFAULT '[]',
  metadata_json TEXT NOT NULL DEFAULT '{{}}',
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS missed_opportunity_logs (
  missed_opportunity_log_id TEXT PRIMARY KEY,
  token_id TEXT,
  token_profile_id TEXT,
  reason TEXT NOT NULL,
  source_refs_json TEXT NOT NULL DEFAULT '[]',
  observed_at TEXT NOT NULL,
  created_at TEXT NOT NULL,
  metadata_json TEXT NOT NULL DEFAULT '{{}}',
  FOREIGN KEY(token_profile_id) REFERENCES token_profiles(token_profile_id)
);

CREATE INDEX IF NOT EXISTS idx_no_trade_signals_strategy_time ON no_trade_signals(strategy_version_id, created_at);
CREATE INDEX IF NOT EXISTS idx_trade_thesis_details_signal ON trade_thesis_details(signal_id);
CREATE INDEX IF NOT EXISTS idx_position_events_position_time ON paper_position_events(position_id, created_at);
CREATE INDEX IF NOT EXISTS idx_rejected_trade_logs_subject ON rejected_trade_logs(subject_type, subject_id, created_at);
CREATE INDEX IF NOT EXISTS idx_missed_opportunity_logs_token ON missed_opportunity_logs(token_id, observed_at);

CREATE TRIGGER IF NOT EXISTS prevent_non_evaluation_trade_outcome_insert
BEFORE INSERT ON trade_outcomes
WHEN NEW.calculated_by_service != 'evaluation_service'
BEGIN
  SELECT RAISE(ABORT, 'trade_outcomes can only be created by evaluation_service');
END;

{_append_only_triggers_for(SPRINT3_WORKFLOW_IMMUTABLE_TABLES)}
"""


MIGRATIONS.append(Migration(4, "stage2_signal_risk_paper_workflow_schema", SPRINT3_SIGNAL_RISK_PAPER_SCHEMA))


SPRINT3_FILL_SIZE_SCHEMA = """
PRAGMA foreign_keys=ON;

ALTER TABLE paper_fills ADD COLUMN filled_size REAL;
"""


MIGRATIONS.append(Migration(5, "stage2_paper_fill_size_schema", SPRINT3_FILL_SIZE_SCHEMA))


SPRINT4_IMMUTABLE_TABLES = [
    "worker_artifacts",
    "parallelism_configs",
    "strategy_metric_snapshots",
    "strategy_decisions",
    "post_trade_review_details",
    "memory_curation_events",
]


SPRINT4_PARALLEL_STRATEGY_MEMORY_SCHEMA = f"""
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS worker_registry (
  worker_id TEXT PRIMARY KEY,
  worker_type TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'registered',
  registered_at TEXT NOT NULL,
  last_heartbeat_at TEXT,
  max_concurrent_leases INTEGER NOT NULL DEFAULT 1,
  metadata_json TEXT NOT NULL DEFAULT '{{}}'
);

CREATE TABLE IF NOT EXISTS monitoring_session_transitions (
  monitoring_session_transition_id TEXT PRIMARY KEY,
  monitoring_session_id TEXT NOT NULL,
  previous_state TEXT NOT NULL,
  new_state TEXT NOT NULL,
  reason TEXT NOT NULL,
  actor TEXT NOT NULL,
  created_at TEXT NOT NULL,
  related_job_id TEXT,
  audit_event_id TEXT,
  metadata_json TEXT NOT NULL DEFAULT '{{}}',
  FOREIGN KEY(monitoring_session_id) REFERENCES monitoring_sessions(monitoring_session_id),
  FOREIGN KEY(related_job_id) REFERENCES jobs(job_id),
  FOREIGN KEY(audit_event_id) REFERENCES audit_events(audit_event_id)
);

CREATE TABLE IF NOT EXISTS worker_artifacts (
  worker_artifact_id TEXT PRIMARY KEY,
  job_id TEXT,
  worker_id TEXT NOT NULL,
  artifact_type TEXT NOT NULL,
  artifact_ref TEXT,
  payload_json TEXT NOT NULL DEFAULT '{{}}',
  authoritative INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  FOREIGN KEY(job_id) REFERENCES jobs(job_id),
  FOREIGN KEY(worker_id) REFERENCES worker_registry(worker_id)
);

CREATE TABLE IF NOT EXISTS parallelism_configs (
  parallelism_config_id TEXT PRIMARY KEY,
  version_label TEXT NOT NULL,
  content_hash TEXT NOT NULL UNIQUE,
  limits_json TEXT NOT NULL,
  source TEXT NOT NULL,
  notes TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS strategy_mutation_proposals (
  strategy_mutation_proposal_id TEXT PRIMARY KEY,
  parent_strategy_version_id TEXT NOT NULL,
  proposed_strategy_version_id TEXT,
  mutation_type TEXT NOT NULL,
  hypothesis TEXT NOT NULL,
  changed_assumptions_json TEXT NOT NULL DEFAULT '{{}}',
  expected_effect TEXT NOT NULL,
  target_buckets_json TEXT NOT NULL DEFAULT '{{}}',
  proposed_budget_json TEXT NOT NULL DEFAULT '{{}}',
  kill_criteria_ref TEXT,
  promotion_criteria_snapshot_id TEXT NOT NULL,
  source_refs_json TEXT NOT NULL DEFAULT '[]',
  review_refs_json TEXT NOT NULL DEFAULT '[]',
  created_by TEXT NOT NULL,
  created_at TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'proposed',
  FOREIGN KEY(parent_strategy_version_id) REFERENCES strategy_versions(strategy_version_id),
  FOREIGN KEY(proposed_strategy_version_id) REFERENCES strategy_versions(strategy_version_id),
  FOREIGN KEY(promotion_criteria_snapshot_id) REFERENCES promotion_criteria_snapshots(promotion_criteria_snapshot_id)
);

CREATE TABLE IF NOT EXISTS strategy_experiments (
  strategy_experiment_id TEXT PRIMARY KEY,
  strategy_version_id TEXT NOT NULL,
  parent_strategy_version_id TEXT,
  mutation_proposal_id TEXT,
  strategy_config_snapshot_id TEXT NOT NULL,
  promotion_criteria_snapshot_id TEXT NOT NULL,
  budget_json TEXT NOT NULL,
  stop_conditions_json TEXT NOT NULL DEFAULT '{{}}',
  target_buckets_json TEXT NOT NULL DEFAULT '{{}}',
  baseline_refs_json TEXT NOT NULL DEFAULT '[]',
  no_trade_baseline_refs_json TEXT NOT NULL DEFAULT '[]',
  status TEXT NOT NULL DEFAULT 'planned',
  started_at TEXT,
  ended_at TEXT,
  created_at TEXT NOT NULL,
  audit_refs_json TEXT NOT NULL DEFAULT '[]',
  FOREIGN KEY(strategy_version_id) REFERENCES strategy_versions(strategy_version_id),
  FOREIGN KEY(parent_strategy_version_id) REFERENCES strategy_versions(strategy_version_id),
  FOREIGN KEY(mutation_proposal_id) REFERENCES strategy_mutation_proposals(strategy_mutation_proposal_id),
  FOREIGN KEY(strategy_config_snapshot_id) REFERENCES strategy_config_snapshots(strategy_config_snapshot_id),
  FOREIGN KEY(promotion_criteria_snapshot_id) REFERENCES promotion_criteria_snapshots(promotion_criteria_snapshot_id)
);

CREATE TABLE IF NOT EXISTS strategy_metric_snapshots (
  strategy_metric_snapshot_id TEXT PRIMARY KEY,
  strategy_version_id TEXT NOT NULL,
  promotion_criteria_snapshot_id TEXT,
  calculated_at TEXT NOT NULL,
  closed_trade_count INTEGER NOT NULL DEFAULT 0,
  open_position_count INTEGER NOT NULL DEFAULT 0,
  rejected_count INTEGER NOT NULL DEFAULT 0,
  no_trade_count INTEGER NOT NULL DEFAULT 0,
  failed_fill_count INTEGER NOT NULL DEFAULT 0,
  gross_pnl REAL NOT NULL DEFAULT 0,
  net_pnl REAL NOT NULL DEFAULT 0,
  expectancy REAL,
  win_rate REAL,
  profit_factor REAL,
  average_win REAL,
  average_loss REAL,
  max_drawdown REAL,
  degraded_outcome_count INTEGER NOT NULL DEFAULT 0,
  sample_size_warning TEXT,
  concentration_warning TEXT,
  quality_flags_json TEXT NOT NULL DEFAULT '[]',
  metrics_json TEXT NOT NULL DEFAULT '{{}}',
  FOREIGN KEY(strategy_version_id) REFERENCES strategy_versions(strategy_version_id),
  FOREIGN KEY(promotion_criteria_snapshot_id) REFERENCES promotion_criteria_snapshots(promotion_criteria_snapshot_id)
);

CREATE TABLE IF NOT EXISTS strategy_decisions (
  strategy_decision_id TEXT PRIMARY KEY,
  strategy_version_id TEXT NOT NULL,
  decision_type TEXT NOT NULL CHECK(decision_type IN ('promote', 'demote', 'kill', 'keep_testing', 'insufficient_data')),
  promotion_criteria_snapshot_id TEXT NOT NULL,
  metrics_snapshot_id TEXT NOT NULL,
  reason TEXT NOT NULL,
  failed_criteria_json TEXT NOT NULL DEFAULT '[]',
  passed_criteria_json TEXT NOT NULL DEFAULT '[]',
  created_by_service TEXT NOT NULL,
  created_at TEXT NOT NULL,
  audit_refs_json TEXT NOT NULL DEFAULT '[]',
  FOREIGN KEY(strategy_version_id) REFERENCES strategy_versions(strategy_version_id),
  FOREIGN KEY(promotion_criteria_snapshot_id) REFERENCES promotion_criteria_snapshots(promotion_criteria_snapshot_id),
  FOREIGN KEY(metrics_snapshot_id) REFERENCES strategy_metric_snapshots(strategy_metric_snapshot_id)
);

CREATE TABLE IF NOT EXISTS post_trade_review_details (
  post_trade_review_detail_id TEXT PRIMARY KEY,
  post_trade_review_id TEXT NOT NULL UNIQUE,
  position_id TEXT NOT NULL,
  strategy_version_id TEXT NOT NULL,
  signal_id TEXT NOT NULL,
  thesis_id TEXT NOT NULL,
  outcome_id TEXT NOT NULL,
  thesis_expected_json TEXT NOT NULL DEFAULT '{{}}',
  actual_result_json TEXT NOT NULL DEFAULT '{{}}',
  cost_impact_json TEXT NOT NULL DEFAULT '{{}}',
  risk_summary_json TEXT NOT NULL DEFAULT '{{}}',
  fill_quality_json TEXT NOT NULL DEFAULT '{{}}',
  source_quality_issues_json TEXT NOT NULL DEFAULT '[]',
  exit_matched_plan INTEGER,
  bias_flags_json TEXT NOT NULL DEFAULT '[]',
  lessons_json TEXT NOT NULL DEFAULT '[]',
  proposed_mutation_refs_json TEXT NOT NULL DEFAULT '[]',
  memory_proposal_refs_json TEXT NOT NULL DEFAULT '[]',
  hindsight_flags_json TEXT NOT NULL DEFAULT '[]',
  created_by TEXT NOT NULL,
  created_at TEXT NOT NULL,
  FOREIGN KEY(post_trade_review_id) REFERENCES post_trade_reviews(post_trade_review_id),
  FOREIGN KEY(position_id) REFERENCES paper_positions(position_id),
  FOREIGN KEY(strategy_version_id) REFERENCES strategy_versions(strategy_version_id),
  FOREIGN KEY(signal_id) REFERENCES signals(signal_id),
  FOREIGN KEY(thesis_id) REFERENCES trade_theses(thesis_id),
  FOREIGN KEY(outcome_id) REFERENCES trade_outcomes(outcome_id)
);

CREATE TABLE IF NOT EXISTS memory_proposals (
  memory_proposal_id TEXT PRIMARY KEY,
  claim TEXT NOT NULL,
  memory_type TEXT NOT NULL CHECK(memory_type IN ('fact', 'hypothesis', 'lesson', 'warning', 'obsolete_conclusion')),
  evidence_refs_json TEXT NOT NULL DEFAULT '[]',
  review_refs_json TEXT NOT NULL DEFAULT '[]',
  strategy_refs_json TEXT NOT NULL DEFAULT '[]',
  confidence TEXT NOT NULL DEFAULT 'unknown',
  validity_scope_json TEXT NOT NULL DEFAULT '{{}}',
  created_at TEXT NOT NULL,
  created_by TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'proposed' CHECK(status IN ('proposed', 'accepted', 'rejected', 'archived', 'superseded')),
  curated_memory_entry_id TEXT,
  FOREIGN KEY(curated_memory_entry_id) REFERENCES memory_entries(memory_entry_id)
);

CREATE TABLE IF NOT EXISTS memory_curation_events (
  memory_curation_event_id TEXT PRIMARY KEY,
  memory_proposal_id TEXT NOT NULL,
  memory_entry_id TEXT,
  action TEXT NOT NULL CHECK(action IN ('accept', 'reject', 'archive', 'supersede')),
  curator TEXT NOT NULL,
  reason TEXT NOT NULL,
  created_at TEXT NOT NULL,
  supersedes_memory_entry_id TEXT,
  metadata_json TEXT NOT NULL DEFAULT '{{}}',
  FOREIGN KEY(memory_proposal_id) REFERENCES memory_proposals(memory_proposal_id),
  FOREIGN KEY(memory_entry_id) REFERENCES memory_entries(memory_entry_id),
  FOREIGN KEY(supersedes_memory_entry_id) REFERENCES memory_entries(memory_entry_id)
);

CREATE INDEX IF NOT EXISTS idx_worker_registry_type_status ON worker_registry(worker_type, status);
CREATE INDEX IF NOT EXISTS idx_monitoring_transitions_session_time ON monitoring_session_transitions(monitoring_session_id, created_at);
CREATE INDEX IF NOT EXISTS idx_worker_artifacts_job ON worker_artifacts(job_id, worker_id, created_at);
CREATE INDEX IF NOT EXISTS idx_strategy_mutations_parent ON strategy_mutation_proposals(parent_strategy_version_id, status, created_at);
CREATE INDEX IF NOT EXISTS idx_strategy_experiments_strategy ON strategy_experiments(strategy_version_id, status, created_at);
CREATE INDEX IF NOT EXISTS idx_strategy_metric_strategy_time ON strategy_metric_snapshots(strategy_version_id, calculated_at);
CREATE INDEX IF NOT EXISTS idx_strategy_decisions_strategy_time ON strategy_decisions(strategy_version_id, created_at);
CREATE INDEX IF NOT EXISTS idx_memory_proposals_status ON memory_proposals(status, created_at);

ALTER TABLE conflict_reviews ADD COLUMN resolver TEXT;
ALTER TABLE conflict_reviews ADD COLUMN involved_refs_json TEXT NOT NULL DEFAULT '[]';
ALTER TABLE conflict_reviews ADD COLUMN resolution_metadata_json TEXT NOT NULL DEFAULT '{{}}';

{_append_only_triggers_for(SPRINT4_IMMUTABLE_TABLES)}
"""


MIGRATIONS.append(Migration(6, "stage2_parallel_strategy_memory_schema", SPRINT4_PARALLEL_STRATEGY_MEMORY_SCHEMA))


SPRINT5_IMMUTABLE_TABLES = [
    "acceptance_run_events",
    "invariant_violations",
    "operational_health_snapshots",
    "shadow_mode_gap_reports",
    "final_acceptance_reports",
]


SPRINT5_HARDENING_ACCEPTANCE_SCHEMA = f"""
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS acceptance_run_executions (
  acceptance_run_execution_id TEXT PRIMARY KEY,
  acceptance_run_id TEXT NOT NULL,
  run_mode TEXT NOT NULL CHECK(run_mode IN ('fixture_replay', 'paper_live_data', 'shadow_gap_assessment')),
  status TEXT NOT NULL CHECK(status IN ('configured', 'running', 'passed', 'failed', 'partial', 'aborted', 'gap_report_required')),
  started_at TEXT,
  ended_at TEXT,
  configured_duration_seconds INTEGER NOT NULL DEFAULT 0,
  max_events INTEGER,
  max_jobs INTEGER,
  max_trades INTEGER,
  config_snapshot_id TEXT NOT NULL,
  risk_limit_snapshot_id TEXT,
  strategy_config_snapshot_id TEXT,
  promotion_criteria_snapshot_id TEXT,
  data_source_set_json TEXT NOT NULL DEFAULT '[]',
  invariant_violation_count INTEGER NOT NULL DEFAULT 0,
  critical_violation_count INTEGER NOT NULL DEFAULT 0,
  signals_count INTEGER NOT NULL DEFAULT 0,
  orders_count INTEGER NOT NULL DEFAULT 0,
  fills_count INTEGER NOT NULL DEFAULT 0,
  outcomes_count INTEGER NOT NULL DEFAULT 0,
  failed_fills INTEGER NOT NULL DEFAULT 0,
  risk_vetoes INTEGER NOT NULL DEFAULT 0,
  no_trade_decisions INTEGER NOT NULL DEFAULT 0,
  open_positions INTEGER NOT NULL DEFAULT 0,
  closed_positions INTEGER NOT NULL DEFAULT 0,
  worker_failures INTEGER NOT NULL DEFAULT 0,
  source_degradation_events INTEGER NOT NULL DEFAULT 0,
  final_net_pnl REAL,
  expectancy REAL,
  drawdown REAL,
  leaderboard_snapshot_ref TEXT,
  shadow_gap_report_ref TEXT,
  final_report_ref TEXT,
  metadata_json TEXT NOT NULL DEFAULT '{{}}',
  FOREIGN KEY(acceptance_run_id) REFERENCES acceptance_runs(acceptance_run_id),
  FOREIGN KEY(config_snapshot_id) REFERENCES config_snapshots(config_snapshot_id),
  FOREIGN KEY(risk_limit_snapshot_id) REFERENCES risk_limit_snapshots(risk_limit_snapshot_id),
  FOREIGN KEY(strategy_config_snapshot_id) REFERENCES strategy_config_snapshots(strategy_config_snapshot_id),
  FOREIGN KEY(promotion_criteria_snapshot_id) REFERENCES promotion_criteria_snapshots(promotion_criteria_snapshot_id),
  FOREIGN KEY(shadow_gap_report_ref) REFERENCES shadow_mode_gap_reports(shadow_mode_gap_report_id),
  FOREIGN KEY(final_report_ref) REFERENCES final_acceptance_reports(final_acceptance_report_id)
);

CREATE TABLE IF NOT EXISTS acceptance_run_events (
  acceptance_run_event_id TEXT PRIMARY KEY,
  acceptance_run_id TEXT NOT NULL,
  acceptance_run_execution_id TEXT,
  event_type TEXT NOT NULL,
  status TEXT,
  created_at TEXT NOT NULL,
  payload_json TEXT NOT NULL DEFAULT '{{}}',
  FOREIGN KEY(acceptance_run_id) REFERENCES acceptance_runs(acceptance_run_id),
  FOREIGN KEY(acceptance_run_execution_id) REFERENCES acceptance_run_executions(acceptance_run_execution_id)
);

CREATE TABLE IF NOT EXISTS invariant_violations (
  invariant_violation_id TEXT PRIMARY KEY,
  acceptance_run_id TEXT,
  invariant_name TEXT NOT NULL,
  severity TEXT NOT NULL CHECK(severity IN ('info', 'warning', 'critical')),
  entity_refs_json TEXT NOT NULL DEFAULT '[]',
  detected_at TEXT NOT NULL,
  description TEXT NOT NULL,
  remediation_hint TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'open',
  metadata_json TEXT NOT NULL DEFAULT '{{}}',
  FOREIGN KEY(acceptance_run_id) REFERENCES acceptance_runs(acceptance_run_id)
);

CREATE TABLE IF NOT EXISTS operational_health_snapshots (
  operational_health_snapshot_id TEXT PRIMARY KEY,
  acceptance_run_id TEXT,
  observed_at TEXT NOT NULL,
  source_health_summary_json TEXT NOT NULL DEFAULT '{{}}',
  stale_source_count INTEGER NOT NULL DEFAULT 0,
  degraded_source_count INTEGER NOT NULL DEFAULT 0,
  unavailable_source_count INTEGER NOT NULL DEFAULT 0,
  queue_depth INTEGER NOT NULL DEFAULT 0,
  active_leases INTEGER NOT NULL DEFAULT 0,
  expired_leases INTEGER NOT NULL DEFAULT 0,
  failed_jobs INTEGER NOT NULL DEFAULT 0,
  active_sessions INTEGER NOT NULL DEFAULT 0,
  blocked_sessions INTEGER NOT NULL DEFAULT 0,
  open_positions INTEGER NOT NULL DEFAULT 0,
  unmonitored_open_positions INTEGER NOT NULL DEFAULT 0,
  missed_exit_risk_checks INTEGER NOT NULL DEFAULT 0,
  failed_fills INTEGER NOT NULL DEFAULT 0,
  risk_vetoes INTEGER NOT NULL DEFAULT 0,
  net_pnl REAL NOT NULL DEFAULT 0,
  expectancy REAL,
  drawdown REAL NOT NULL DEFAULT 0,
  leaderboard_summary_json TEXT NOT NULL DEFAULT '[]',
  memory_review_summary_json TEXT NOT NULL DEFAULT '{{}}',
  critical_invariant_violations INTEGER NOT NULL DEFAULT 0,
  warnings_json TEXT NOT NULL DEFAULT '[]',
  FOREIGN KEY(acceptance_run_id) REFERENCES acceptance_runs(acceptance_run_id)
);

CREATE TABLE IF NOT EXISTS shadow_mode_gap_reports (
  shadow_mode_gap_report_id TEXT PRIMARY KEY,
  acceptance_run_id TEXT,
  assessed_at TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('shadow_ready', 'gap_report_required')),
  missing_capabilities_json TEXT NOT NULL DEFAULT '[]',
  required_evidence_json TEXT NOT NULL DEFAULT '{{}}',
  current_evidence_json TEXT NOT NULL DEFAULT '{{}}',
  risk_of_pretending_completion TEXT NOT NULL,
  affected_modules_json TEXT NOT NULL DEFAULT '[]',
  recommended_remediation_json TEXT NOT NULL DEFAULT '[]',
  blocks_stage2_release INTEGER NOT NULL DEFAULT 0,
  blocks_stage3_progression INTEGER NOT NULL DEFAULT 1,
  report_json TEXT NOT NULL DEFAULT '{{}}',
  FOREIGN KEY(acceptance_run_id) REFERENCES acceptance_runs(acceptance_run_id)
);

CREATE TABLE IF NOT EXISTS final_acceptance_reports (
  final_acceptance_report_id TEXT PRIMARY KEY,
  acceptance_run_id TEXT NOT NULL,
  generated_at TEXT NOT NULL,
  decision TEXT NOT NULL CHECK(decision IN ('accepted_stage2_release', 'accepted_with_gaps', 'rejected_blocked', 'requires_further_remediation')),
  run_mode TEXT NOT NULL,
  acceptance_run_result TEXT NOT NULL,
  invariant_summary_json TEXT NOT NULL DEFAULT '{{}}',
  operational_health_summary_json TEXT NOT NULL DEFAULT '{{}}',
  paper_trading_summary_json TEXT NOT NULL DEFAULT '{{}}',
  strategy_leaderboard_json TEXT NOT NULL DEFAULT '[]',
  strategy_decisions_json TEXT NOT NULL DEFAULT '[]',
  memory_review_summary_json TEXT NOT NULL DEFAULT '{{}}',
  source_degradation_summary_json TEXT NOT NULL DEFAULT '{{}}',
  shadow_status TEXT NOT NULL,
  shadow_gap_report_id TEXT,
  known_limitations_json TEXT NOT NULL DEFAULT '[]',
  validation_summary_json TEXT NOT NULL DEFAULT '{{}}',
  report_json TEXT NOT NULL DEFAULT '{{}}',
  FOREIGN KEY(acceptance_run_id) REFERENCES acceptance_runs(acceptance_run_id),
  FOREIGN KEY(shadow_gap_report_id) REFERENCES shadow_mode_gap_reports(shadow_mode_gap_report_id)
);

CREATE INDEX IF NOT EXISTS idx_acceptance_run_executions_run ON acceptance_run_executions(acceptance_run_id, status);
CREATE INDEX IF NOT EXISTS idx_acceptance_run_events_run_time ON acceptance_run_events(acceptance_run_id, created_at);
CREATE INDEX IF NOT EXISTS idx_invariant_violations_run_severity ON invariant_violations(acceptance_run_id, severity, detected_at);
CREATE INDEX IF NOT EXISTS idx_operational_health_run_time ON operational_health_snapshots(acceptance_run_id, observed_at);
CREATE INDEX IF NOT EXISTS idx_shadow_gap_run ON shadow_mode_gap_reports(acceptance_run_id, assessed_at);
CREATE INDEX IF NOT EXISTS idx_final_acceptance_run ON final_acceptance_reports(acceptance_run_id, generated_at);

{_append_only_triggers_for(SPRINT5_IMMUTABLE_TABLES)}
"""


MIGRATIONS.append(Migration(7, "stage2_hardening_shadow_acceptance_schema", SPRINT5_HARDENING_ACCEPTANCE_SCHEMA))


SHADOW_READINESS_IMMUTABLE_TABLES = [
    "quote_observations",
    "source_latency_samples",
    "route_quality_evidence",
    "fill_quote_comparisons",
    "live_data_acceptance_windows",
]


SHADOW_READINESS_GAP_CLOSURE_SCHEMA = f"""
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS quote_observations (
  quote_observation_id TEXT PRIMARY KEY,
  raw_source_event_id TEXT NOT NULL,
  market_snapshot_id TEXT NOT NULL,
  source_name TEXT NOT NULL,
  source_type TEXT NOT NULL DEFAULT 'quote_snapshot',
  token_mint TEXT,
  pool_address TEXT,
  chain TEXT,
  observed_at TEXT NOT NULL,
  ingested_at TEXT NOT NULL,
  latency_ms REAL,
  response_latency_ms REAL,
  quote_age_seconds REAL,
  price_usd REAL,
  liquidity_usd REAL,
  confidence TEXT NOT NULL DEFAULT 'unknown',
  quality_flags_json TEXT NOT NULL DEFAULT '[]',
  provenance_json TEXT NOT NULL DEFAULT '{{}}',
  eligible_for_shadow_comparison INTEGER NOT NULL CHECK(eligible_for_shadow_comparison IN (0, 1)),
  created_at TEXT NOT NULL,
  FOREIGN KEY(raw_source_event_id) REFERENCES raw_source_events(raw_source_event_id),
  FOREIGN KEY(market_snapshot_id) REFERENCES market_snapshots(market_snapshot_id)
);

CREATE TABLE IF NOT EXISTS source_latency_samples (
  source_latency_sample_id TEXT PRIMARY KEY,
  quote_observation_id TEXT,
  raw_source_event_id TEXT,
  source_name TEXT NOT NULL,
  observed_at TEXT,
  ingested_at TEXT NOT NULL,
  response_latency_ms REAL,
  event_lag_ms REAL,
  total_latency_ms REAL,
  confidence_impact TEXT NOT NULL DEFAULT 'unknown',
  quality_flags_json TEXT NOT NULL DEFAULT '[]',
  created_at TEXT NOT NULL,
  metadata_json TEXT NOT NULL DEFAULT '{{}}',
  FOREIGN KEY(quote_observation_id) REFERENCES quote_observations(quote_observation_id),
  FOREIGN KEY(raw_source_event_id) REFERENCES raw_source_events(raw_source_event_id)
);

CREATE TABLE IF NOT EXISTS route_quality_evidence (
  route_quality_evidence_id TEXT PRIMARY KEY,
  quote_observation_id TEXT NOT NULL,
  market_snapshot_id TEXT NOT NULL,
  token_mint TEXT,
  pool_address TEXT,
  observed_at TEXT NOT NULL,
  liquidity_usd REAL,
  route_depth_usd REAL,
  spread_bps REAL,
  independent_quote_count INTEGER NOT NULL DEFAULT 0,
  route_quality_score REAL,
  sufficient_for_shadow_comparison INTEGER NOT NULL CHECK(sufficient_for_shadow_comparison IN (0, 1)),
  insufficiency_reason TEXT,
  evidence_json TEXT NOT NULL DEFAULT '{{}}',
  created_at TEXT NOT NULL,
  FOREIGN KEY(quote_observation_id) REFERENCES quote_observations(quote_observation_id),
  FOREIGN KEY(market_snapshot_id) REFERENCES market_snapshots(market_snapshot_id)
);

CREATE TABLE IF NOT EXISTS fill_quote_comparisons (
  fill_quote_comparison_id TEXT PRIMARY KEY,
  paper_fill_id TEXT NOT NULL,
  paper_order_id TEXT NOT NULL,
  quote_observation_id TEXT,
  quote_market_snapshot_id TEXT,
  route_quality_evidence_id TEXT,
  compared_at TEXT NOT NULL,
  fill_time TEXT,
  quote_observed_at TEXT,
  fill_price REAL,
  quote_price REAL,
  absolute_difference REAL,
  difference_bps REAL,
  quote_age_seconds REAL,
  status TEXT NOT NULL CHECK(status IN ('passed', 'missing_quote', 'stale_quote', 'weak_route_quality', 'failed_fill', 'missing_fill_price')),
  quality_flags_json TEXT NOT NULL DEFAULT '[]',
  evidence_json TEXT NOT NULL DEFAULT '{{}}',
  FOREIGN KEY(paper_fill_id) REFERENCES paper_fills(paper_fill_id),
  FOREIGN KEY(paper_order_id) REFERENCES paper_orders(paper_order_id),
  FOREIGN KEY(quote_observation_id) REFERENCES quote_observations(quote_observation_id),
  FOREIGN KEY(quote_market_snapshot_id) REFERENCES market_snapshots(market_snapshot_id),
  FOREIGN KEY(route_quality_evidence_id) REFERENCES route_quality_evidence(route_quality_evidence_id)
);

CREATE TABLE IF NOT EXISTS live_data_acceptance_windows (
  live_data_acceptance_window_id TEXT PRIMARY KEY,
  configured_at TEXT NOT NULL,
  started_at TEXT NOT NULL,
  ended_at TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('passed', 'gap_report_required', 'failed')),
  source_names_json TEXT NOT NULL DEFAULT '[]',
  token_mints_json TEXT NOT NULL DEFAULT '[]',
  quotes_seen INTEGER NOT NULL DEFAULT 0,
  fresh_quote_count INTEGER NOT NULL DEFAULT 0,
  stale_quote_count INTEGER NOT NULL DEFAULT 0,
  latency_sample_count INTEGER NOT NULL DEFAULT 0,
  route_quality_sufficient_count INTEGER NOT NULL DEFAULT 0,
  fill_comparison_count INTEGER NOT NULL DEFAULT 0,
  gaps_json TEXT NOT NULL DEFAULT '[]',
  metrics_json TEXT NOT NULL DEFAULT '{{}}',
  created_by TEXT NOT NULL DEFAULT 'live_data_acceptance_window_service'
);

CREATE INDEX IF NOT EXISTS idx_quote_observations_token_time ON quote_observations(token_mint, observed_at);
CREATE INDEX IF NOT EXISTS idx_quote_observations_source_time ON quote_observations(source_name, observed_at);
CREATE INDEX IF NOT EXISTS idx_latency_samples_source_time ON source_latency_samples(source_name, observed_at);
CREATE INDEX IF NOT EXISTS idx_route_quality_quote ON route_quality_evidence(quote_observation_id, sufficient_for_shadow_comparison);
CREATE INDEX IF NOT EXISTS idx_fill_quote_comparison_fill ON fill_quote_comparisons(paper_fill_id, status);
CREATE INDEX IF NOT EXISTS idx_live_data_window_status ON live_data_acceptance_windows(status, ended_at);

{_append_only_triggers_for(SHADOW_READINESS_IMMUTABLE_TABLES)}
"""


MIGRATIONS.append(Migration(8, "stage2_shadow_readiness_gap_closure_schema", SHADOW_READINESS_GAP_CLOSURE_SCHEMA))


V2_SPRINT1_IMMUTABLE_TABLES = [
    "token_agent_decisions",
    "token_trade_corpora",
    "wallet_token_outcomes",
    "agent_wallet_reviews",
    "wallet_forward_contributions",
    "agent_trading_decisions",
]


V2_SPRINT1_AGENTIC_TOKEN_WALLET_FOUNDATION_SCHEMA = f"""
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS token_agent_decisions (
  token_agent_decision_id TEXT PRIMARY KEY,
  token_profile_id TEXT,
  token_mint TEXT,
  pool_address TEXT,
  decision_type TEXT NOT NULL CHECK(decision_type IN ('reject', 'passive_watch', 'deep_parse', 'active_watch', 'archive')),
  reasons_json TEXT NOT NULL DEFAULT '[]',
  uncertainties_json TEXT NOT NULL DEFAULT '[]',
  requested_tool_calls_json TEXT NOT NULL DEFAULT '[]',
  evidence_refs_json TEXT NOT NULL DEFAULT '[]',
  confidence TEXT NOT NULL DEFAULT 'unknown',
  expires_at TEXT,
  created_by_agent TEXT NOT NULL,
  created_at TEXT NOT NULL,
  FOREIGN KEY(token_profile_id) REFERENCES token_profiles(token_profile_id)
);

CREATE TABLE IF NOT EXISTS token_trade_corpora (
  token_trade_corpus_id TEXT PRIMARY KEY,
  token_mint TEXT NOT NULL,
  pool_address TEXT,
  window_start TEXT,
  window_end TEXT,
  source_names_json TEXT NOT NULL DEFAULT '[]',
  trade_count INTEGER NOT NULL DEFAULT 0,
  wallet_count INTEGER NOT NULL DEFAULT 0,
  coverage_estimate REAL NOT NULL DEFAULT 0,
  data_sufficiency TEXT NOT NULL DEFAULT 'insufficient' CHECK(data_sufficiency IN ('sufficient', 'partial', 'insufficient')),
  quality_flags_json TEXT NOT NULL DEFAULT '[]',
  raw_event_refs_json TEXT NOT NULL DEFAULT '[]',
  created_by_service TEXT NOT NULL DEFAULT 'token_trade_corpus_service',
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS wallet_token_outcomes (
  wallet_token_outcome_id TEXT PRIMARY KEY,
  token_trade_corpus_id TEXT,
  wallet TEXT NOT NULL,
  token_mint TEXT NOT NULL,
  pool_address TEXT,
  buy_count INTEGER NOT NULL DEFAULT 0,
  sell_count INTEGER NOT NULL DEFAULT 0,
  realized_pnl_estimate REAL,
  roi_estimate REAL,
  roi_bucket TEXT CHECK(roi_bucket IN ('20_50', '50_100', '100_200', '200_plus') OR roi_bucket IS NULL),
  notional_usd REAL,
  entry_time TEXT,
  exit_time TEXT,
  holding_seconds REAL,
  data_sufficiency TEXT NOT NULL DEFAULT 'insufficient' CHECK(data_sufficiency IN ('sufficient', 'partial', 'insufficient')),
  source_refs_json TEXT NOT NULL DEFAULT '[]',
  quality_flags_json TEXT NOT NULL DEFAULT '[]',
  eligible_for_agent_review INTEGER NOT NULL DEFAULT 0 CHECK(eligible_for_agent_review IN (0, 1)),
  calculated_by_service TEXT NOT NULL DEFAULT 'wallet_token_outcome_service',
  created_at TEXT NOT NULL,
  FOREIGN KEY(token_trade_corpus_id) REFERENCES token_trade_corpora(token_trade_corpus_id)
);

CREATE TABLE IF NOT EXISTS agent_wallet_reviews (
  agent_wallet_review_id TEXT PRIMARY KEY,
  wallet TEXT NOT NULL,
  metrics_snapshot_id TEXT,
  decision TEXT NOT NULL CHECK(decision IN ('elite', 'probation', 'watch', 'reject', 'archive')),
  agent_rating REAL,
  copyability_rating REAL,
  pnl_quality TEXT NOT NULL DEFAULT 'unknown',
  winrate_quality TEXT NOT NULL DEFAULT 'unknown',
  behavior_profile_json TEXT NOT NULL DEFAULT '{{}}',
  why_yes_json TEXT NOT NULL DEFAULT '[]',
  why_no_json TEXT NOT NULL DEFAULT '[]',
  demotion_triggers_json TEXT NOT NULL DEFAULT '[]',
  data_sufficiency TEXT NOT NULL CHECK(data_sufficiency IN ('sufficient', 'partial', 'insufficient')),
  observed_behavior_json TEXT NOT NULL DEFAULT '{{}}',
  inferred_behavior_json TEXT NOT NULL DEFAULT '{{}}',
  unknowns_json TEXT NOT NULL DEFAULT '[]',
  evidence_refs_json TEXT NOT NULL DEFAULT '[]',
  created_by_agent TEXT NOT NULL,
  created_at TEXT NOT NULL,
  FOREIGN KEY(metrics_snapshot_id) REFERENCES wallet_metric_snapshots(wallet_metric_snapshot_id)
);

CREATE TABLE IF NOT EXISTS wallet_forward_contributions (
  wallet_forward_contribution_id TEXT PRIMARY KEY,
  wallet TEXT NOT NULL,
  strategy_version_id TEXT,
  window_start TEXT,
  window_end TEXT,
  signal_count INTEGER NOT NULL DEFAULT 0,
  paper_trade_count INTEGER NOT NULL DEFAULT 0,
  net_pnl REAL,
  expectancy REAL,
  win_rate REAL,
  max_drawdown REAL,
  quality_flags_json TEXT NOT NULL DEFAULT '[]',
  calculated_by_service TEXT NOT NULL DEFAULT 'wallet_forward_contribution_service',
  calculated_at TEXT NOT NULL,
  FOREIGN KEY(strategy_version_id) REFERENCES strategy_versions(strategy_version_id)
);

CREATE TABLE IF NOT EXISTS active_token_sessions (
  active_token_session_id TEXT PRIMARY KEY,
  token_mint TEXT NOT NULL,
  pool_address TEXT,
  started_at TEXT NOT NULL,
  ended_at TEXT,
  status TEXT NOT NULL DEFAULT 'planned' CHECK(status IN ('planned', 'watching', 'paused', 'closed', 'blocked')),
  trigger_ref TEXT,
  agent_owner TEXT,
  market_data_cadence_seconds REAL,
  agent_review_cadence_seconds REAL,
  cadence_policy_json TEXT NOT NULL DEFAULT '{{}}',
  cadence_degradation_reason TEXT,
  source_capacity_state_json TEXT NOT NULL DEFAULT '{{}}',
  last_market_snapshot_id TEXT,
  last_agent_decision_id TEXT,
  quality_flags_json TEXT NOT NULL DEFAULT '[]',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY(last_market_snapshot_id) REFERENCES market_snapshots(market_snapshot_id)
);

CREATE TABLE IF NOT EXISTS agent_trading_decisions (
  agent_trading_decision_id TEXT PRIMARY KEY,
  active_token_session_id TEXT,
  decision_type TEXT NOT NULL CHECK(decision_type IN ('no_trade', 'paper_trade_candidate', 'continue_observing', 'exit_candidate', 'archive')),
  pre_action_reasoning TEXT NOT NULL,
  evidence_refs_json TEXT NOT NULL DEFAULT '[]',
  wallet_refs_json TEXT NOT NULL DEFAULT '[]',
  token_refs_json TEXT NOT NULL DEFAULT '[]',
  market_snapshot_refs_json TEXT NOT NULL DEFAULT '[]',
  source_quality_summary_json TEXT NOT NULL DEFAULT '{{}}',
  uncertainties_json TEXT NOT NULL DEFAULT '[]',
  data_as_of TEXT NOT NULL,
  linked_signal_id TEXT,
  linked_no_trade_signal_id TEXT,
  created_by_agent TEXT NOT NULL,
  created_at TEXT NOT NULL,
  FOREIGN KEY(active_token_session_id) REFERENCES active_token_sessions(active_token_session_id)
);

CREATE INDEX IF NOT EXISTS idx_token_agent_decisions_token_time ON token_agent_decisions(token_mint, created_at);
CREATE INDEX IF NOT EXISTS idx_token_agent_decisions_profile ON token_agent_decisions(token_profile_id, created_at);
CREATE INDEX IF NOT EXISTS idx_token_trade_corpora_token_time ON token_trade_corpora(token_mint, window_start, window_end);
CREATE INDEX IF NOT EXISTS idx_wallet_token_outcomes_corpus_wallet ON wallet_token_outcomes(token_trade_corpus_id, wallet);
CREATE INDEX IF NOT EXISTS idx_wallet_token_outcomes_wallet_token ON wallet_token_outcomes(wallet, token_mint, created_at);
CREATE INDEX IF NOT EXISTS idx_agent_wallet_reviews_wallet_time ON agent_wallet_reviews(wallet, created_at);
CREATE INDEX IF NOT EXISTS idx_agent_wallet_reviews_decision_time ON agent_wallet_reviews(decision, created_at);
CREATE INDEX IF NOT EXISTS idx_wallet_forward_contributions_wallet_time ON wallet_forward_contributions(wallet, calculated_at);
CREATE INDEX IF NOT EXISTS idx_active_token_sessions_status ON active_token_sessions(status, token_mint);
CREATE INDEX IF NOT EXISTS idx_agent_trading_decisions_session_time ON agent_trading_decisions(active_token_session_id, created_at);

{_append_only_triggers_for(V2_SPRINT1_IMMUTABLE_TABLES)}
"""


MIGRATIONS.append(Migration(9, "v2_sprint1_agentic_token_wallet_foundation_schema", V2_SPRINT1_AGENTIC_TOKEN_WALLET_FOUNDATION_SCHEMA))


V2_SPRINT2_IMMUTABLE_TABLES = [
    "tracked_wallet_signal_events",
    "agent_trading_decision_artifact_links",
    "wallet_contribution_reports",
]


V2_SPRINT2_HERMES_ORCHESTRATOR_SCHEMA = f"""
PRAGMA foreign_keys=ON;

DROP TRIGGER IF EXISTS prevent_update_agent_trading_decisions;
DROP TRIGGER IF EXISTS prevent_delete_agent_trading_decisions;

ALTER TABLE agent_trading_decisions RENAME TO agent_trading_decisions_sprint1_legacy;

CREATE TABLE IF NOT EXISTS agent_trading_decisions (
  agent_trading_decision_id TEXT PRIMARY KEY,
  active_token_session_id TEXT,
  decision_type TEXT NOT NULL CHECK(decision_type IN ('signal', 'no_trade', 'wait', 'exit', 'downgrade_wallet', 'downgrade_token')),
  pre_action_reasoning TEXT NOT NULL,
  evidence_refs_json TEXT NOT NULL DEFAULT '[]',
  wallet_refs_json TEXT NOT NULL DEFAULT '[]',
  token_refs_json TEXT NOT NULL DEFAULT '[]',
  market_snapshot_refs_json TEXT NOT NULL DEFAULT '[]',
  source_quality_summary_json TEXT NOT NULL DEFAULT '{{}}',
  uncertainties_json TEXT NOT NULL DEFAULT '[]',
  data_as_of TEXT NOT NULL,
  linked_signal_id TEXT,
  linked_no_trade_signal_id TEXT,
  linked_exit_decision_id TEXT,
  linked_outcome_id TEXT,
  linked_tracked_wallet_signal_event_id TEXT,
  quality_flags_json TEXT NOT NULL DEFAULT '[]',
  created_by_agent TEXT NOT NULL,
  created_at TEXT NOT NULL,
  FOREIGN KEY(active_token_session_id) REFERENCES active_token_sessions(active_token_session_id)
);

INSERT INTO agent_trading_decisions(
  agent_trading_decision_id, active_token_session_id, decision_type, pre_action_reasoning,
  evidence_refs_json, wallet_refs_json, token_refs_json, market_snapshot_refs_json,
  source_quality_summary_json, uncertainties_json, data_as_of, linked_signal_id,
  linked_no_trade_signal_id, created_by_agent, created_at
)
SELECT
  agent_trading_decision_id,
  active_token_session_id,
  CASE decision_type
    WHEN 'paper_trade_candidate' THEN 'signal'
    WHEN 'continue_observing' THEN 'wait'
    WHEN 'exit_candidate' THEN 'exit'
    WHEN 'archive' THEN 'wait'
    ELSE decision_type
  END,
  pre_action_reasoning,
  evidence_refs_json,
  wallet_refs_json,
  token_refs_json,
  market_snapshot_refs_json,
  source_quality_summary_json,
  uncertainties_json,
  data_as_of,
  linked_signal_id,
  linked_no_trade_signal_id,
  created_by_agent,
  created_at
FROM agent_trading_decisions_sprint1_legacy;

CREATE TABLE IF NOT EXISTS tracked_wallet_signal_events (
  tracked_wallet_signal_event_id TEXT PRIMARY KEY,
  wallet TEXT NOT NULL,
  token_mint TEXT NOT NULL,
  pool_address TEXT,
  side TEXT NOT NULL CHECK(side IN ('buy', 'sell')),
  observed_at TEXT NOT NULL,
  source_name TEXT NOT NULL,
  source_refs_json TEXT NOT NULL DEFAULT '[]',
  latency_metadata_json TEXT NOT NULL DEFAULT '{{}}',
  cluster_refs_json TEXT NOT NULL DEFAULT '[]',
  correlation_refs_json TEXT NOT NULL DEFAULT '[]',
  input_mode TEXT NOT NULL CHECK(input_mode IN ('real_source', 'fixture', 'smoke')),
  data_sufficiency TEXT NOT NULL CHECK(data_sufficiency IN ('sufficient', 'partial', 'insufficient')),
  quality_flags_json TEXT NOT NULL DEFAULT '[]',
  created_by_service TEXT NOT NULL DEFAULT 'tracked_wallet_signal_intake_service',
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS agent_trading_decision_artifact_links (
  agent_trading_decision_artifact_link_id TEXT PRIMARY KEY,
  agent_trading_decision_id TEXT NOT NULL,
  artifact_type TEXT NOT NULL CHECK(artifact_type IN (
    'tracked_wallet_signal_event', 'signal', 'no_trade_signal', 'wait_decision',
    'downgrade_wallet', 'downgrade_token', 'exit_decision', 'paper_order',
    'paper_fill', 'paper_position', 'trade_outcome', 'post_trade_review',
    'memory_proposal', 'wallet_contribution_report', 'token_agent_decision',
    'agent_wallet_review'
  )),
  artifact_id TEXT NOT NULL,
  relationship TEXT NOT NULL,
  evidence_refs_json TEXT NOT NULL DEFAULT '[]',
  created_at TEXT NOT NULL,
  FOREIGN KEY(agent_trading_decision_id) REFERENCES agent_trading_decisions(agent_trading_decision_id)
);

CREATE TABLE IF NOT EXISTS wallet_contribution_reports (
  wallet_contribution_report_id TEXT PRIMARY KEY,
  wallet TEXT NOT NULL,
  strategy_version_id TEXT,
  window_start TEXT,
  window_end TEXT,
  source_signal_count INTEGER NOT NULL DEFAULT 0,
  linked_outcome_count INTEGER NOT NULL DEFAULT 0,
  net_pnl REAL,
  expectancy REAL,
  win_rate REAL,
  max_drawdown REAL,
  data_sufficiency TEXT NOT NULL CHECK(data_sufficiency IN ('sufficient', 'partial', 'insufficient')),
  quality_flags_json TEXT NOT NULL DEFAULT '[]',
  evidence_refs_json TEXT NOT NULL DEFAULT '[]',
  report_json TEXT NOT NULL DEFAULT '{{}}',
  created_by_service TEXT NOT NULL DEFAULT 'v2_wallet_contribution_report_service',
  created_at TEXT NOT NULL,
  FOREIGN KEY(strategy_version_id) REFERENCES strategy_versions(strategy_version_id)
);

CREATE INDEX IF NOT EXISTS idx_tracked_wallet_signal_wallet_time ON tracked_wallet_signal_events(wallet, observed_at);
CREATE INDEX IF NOT EXISTS idx_tracked_wallet_signal_token_time ON tracked_wallet_signal_events(token_mint, observed_at);
CREATE INDEX IF NOT EXISTS idx_agent_trading_decisions_type_time ON agent_trading_decisions(decision_type, created_at);
CREATE INDEX IF NOT EXISTS idx_agent_decision_links_decision ON agent_trading_decision_artifact_links(agent_trading_decision_id, artifact_type);
CREATE INDEX IF NOT EXISTS idx_agent_decision_links_artifact ON agent_trading_decision_artifact_links(artifact_type, artifact_id);
CREATE INDEX IF NOT EXISTS idx_wallet_contribution_reports_wallet_time ON wallet_contribution_reports(wallet, created_at);

{_append_only_triggers_for(V2_SPRINT2_IMMUTABLE_TABLES + ["agent_trading_decisions"])}
"""


MIGRATIONS.append(Migration(10, "v2_sprint2_hermes_orchestrator_paper_shadow_schema", V2_SPRINT2_HERMES_ORCHESTRATOR_SCHEMA))
