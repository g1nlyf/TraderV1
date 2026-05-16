from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

import aiosqlite

from walletscarper.config import settings
from walletscarper.models import utc_now


SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS tokens (
  mint TEXT PRIMARY KEY,
  symbol TEXT,
  name TEXT,
  first_seen_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL,
  source TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pools (
  pool_address TEXT PRIMARY KEY,
  token_mint TEXT NOT NULL,
  quote_mint TEXT,
  dex_id TEXT,
  created_at TEXT,
  first_seen_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS token_snapshots (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  token_mint TEXT NOT NULL,
  pool_address TEXT,
  captured_at TEXT NOT NULL,
  price_usd REAL,
  liquidity_usd REAL,
  volume_5m REAL,
  volume_1h REAL,
  volume_6h REAL,
  volume_24h REAL,
  txns_5m INTEGER,
  txns_1h INTEGER,
  buys_1h INTEGER,
  sells_1h INTEGER,
  fdv REAL,
  market_cap REAL,
  signal_score REAL,
  priority TEXT,
  source TEXT NOT NULL,
  source_confidence TEXT DEFAULT 'unknown'
);

CREATE TABLE IF NOT EXISTS pool_transactions (
  signature TEXT PRIMARY KEY,
  pool_address TEXT NOT NULL,
  token_mint TEXT NOT NULL,
  wallet TEXT,
  side TEXT,
  token_amount REAL,
  quote_amount REAL,
  price_usd REAL,
  block_time TEXT,
  source TEXT NOT NULL,
  source_confidence TEXT DEFAULT 'unknown',
  completeness TEXT DEFAULT 'unknown',
  raw_json TEXT
);

CREATE TABLE IF NOT EXISTS raw_trades (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  signature TEXT NOT NULL,
  wallet TEXT,
  token_mint TEXT NOT NULL,
  pool_address TEXT,
  dex_id TEXT,
  side TEXT,
  token_amount REAL,
  quote_amount REAL,
  price_usd REAL,
  block_time TEXT,
  slot INTEGER,
  source TEXT NOT NULL,
  source_confidence TEXT DEFAULT 'unknown',
  ingestion_run_id TEXT,
  raw_json TEXT,
  UNIQUE(signature, wallet, token_mint, side, source)
);

CREATE TABLE IF NOT EXISTS ingestion_runs (
  id TEXT PRIMARY KEY,
  source TEXT NOT NULL,
  mode TEXT NOT NULL,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  status TEXT NOT NULL,
  trades_ingested INTEGER DEFAULT 0,
  tokens_seen INTEGER DEFAULT 0,
  wallets_seen INTEGER DEFAULT 0,
  error_message TEXT
);

CREATE TABLE IF NOT EXISTS backfill_queue (
  pool_address TEXT PRIMARY KEY,
  token_mint TEXT NOT NULL,
  priority REAL NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'pending',
  attempts INTEGER NOT NULL DEFAULT 0,
  last_attempt_at TEXT,
  next_attempt_at TEXT,
  last_error TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS wallet_token_pnl (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  wallet TEXT NOT NULL,
  token_mint TEXT NOT NULL,
  calculated_at TEXT NOT NULL,
  realized_pnl_quote REAL,
  realized_pnl_usd REAL,
  unrealized_pnl_quote REAL,
  roi REAL,
  buys_count INTEGER,
  sells_count INTEGER,
  first_buy_at TEXT,
  last_sell_at TEXT,
  holding_time_minutes REAL,
  method TEXT NOT NULL,
  UNIQUE(wallet, token_mint, method)
);

CREATE TABLE IF NOT EXISTS wallet_scores (
  wallet TEXT PRIMARY KEY,
  calculated_at TEXT NOT NULL,
  total_trades INTEGER,
  unique_tokens INTEGER,
  realized_pnl_usd REAL,
  winrate REAL,
  median_roi REAL,
  median_holding_minutes REAL,
  fast_trade_pct REAL,
  consistency_score REAL,
  copyability_score REAL,
  risk_penalty REAL,
  bot_score REAL DEFAULT 0,
  human_score REAL DEFAULT 0,
  sample_score REAL DEFAULT 0,
  median_buy_usd REAL DEFAULT 0,
  total_volume_usd REAL DEFAULT 0,
  one_token_pnl_share REAL DEFAULT 0,
  tx_per_token_median REAL DEFAULT 0,
  reason_json TEXT,
  confidence TEXT DEFAULT 'unknown',
  decision_band TEXT
);

CREATE TABLE IF NOT EXISTS tracked_wallets (
  wallet TEXT PRIMARY KEY,
  status TEXT NOT NULL,
  added_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  source_token_mint TEXT,
  source_pool_address TEXT,
  copyability_score REAL,
  confidence TEXT,
  last_seen_signature TEXT,
  last_checked_at TEXT,
  stale_reason TEXT
);

CREATE TABLE IF NOT EXISTS wallet_leaderboard (
  wallet TEXT PRIMARY KEY,
  rank INTEGER NOT NULL,
  previous_rank INTEGER,
  calculated_at TEXT NOT NULL,
  composite_score REAL NOT NULL,
  copyability_score REAL,
  forward_score REAL,
  confidence TEXT,
  status TEXT NOT NULL,
  reason_json TEXT
);

CREATE TABLE IF NOT EXISTS wallet_rank_history (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  wallet TEXT NOT NULL,
  rank INTEGER NOT NULL,
  composite_score REAL NOT NULL,
  captured_at TEXT NOT NULL,
  reason_json TEXT
);

CREATE TABLE IF NOT EXISTS telegram_chat_settings (
  chat_id TEXT PRIMARY KEY,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  digest_enabled INTEGER NOT NULL DEFAULT 1,
  digest_interval_minutes INTEGER NOT NULL DEFAULT 60,
  live_alerts_enabled INTEGER NOT NULL DEFAULT 0,
  daily_reminder_enabled INTEGER NOT NULL DEFAULT 1,
  language TEXT NOT NULL DEFAULT 'ru'
);

CREATE TABLE IF NOT EXISTS signal_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  wallet TEXT NOT NULL,
  signature TEXT NOT NULL,
  token_mint TEXT,
  side TEXT,
  block_time TEXT,
  detected_at TEXT NOT NULL,
  detection_lag_seconds REAL,
  source TEXT NOT NULL,
  token_risk_status TEXT,
  paper_trade_created INTEGER NOT NULL DEFAULT 0,
  raw_json TEXT,
  UNIQUE(wallet, signature)
);

CREATE TABLE IF NOT EXISTS paper_trades (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  signal_id INTEGER NOT NULL,
  wallet TEXT NOT NULL,
  token_mint TEXT NOT NULL,
  created_at TEXT NOT NULL,
  simulated_entry_at TEXT NOT NULL,
  entry_price_usd REAL,
  entry_slippage_bps REAL,
  fee_bps REAL,
  exit_strategy TEXT NOT NULL,
  simulated_exit_at TEXT,
  exit_price_usd REAL,
  realized_pnl_usd REAL,
  roi REAL,
  status TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS notification_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  notification_type TEXT NOT NULL,
  created_at TEXT NOT NULL,
  sent_at TEXT,
  status TEXT NOT NULL,
  error_message TEXT,
  payload_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS run_summaries (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_type TEXT NOT NULL,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  status TEXT NOT NULL,
  tokens_checked INTEGER DEFAULT 0,
  tokens_deep_analyzed INTEGER DEFAULT 0,
  wallet_candidates_found INTEGER DEFAULT 0,
  tracked_wallets_added INTEGER DEFAULT 0,
  errors_count INTEGER DEFAULT 0,
  summary_json TEXT
);

CREATE TABLE IF NOT EXISTS llm_wallet_reports (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  wallet TEXT NOT NULL,
  created_at TEXT NOT NULL,
  model TEXT NOT NULL,
  recommendation TEXT NOT NULL,
  confidence TEXT NOT NULL,
  summary TEXT NOT NULL,
  flags_json TEXT NOT NULL,
  raw_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS api_cache (
  cache_key TEXT PRIMARY KEY,
  source TEXT NOT NULL,
  created_at TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  status_code INTEGER,
  payload TEXT
);

CREATE TABLE IF NOT EXISTS api_budget (
  source TEXT PRIMARY KEY,
  window_start TEXT NOT NULL,
  requests_used INTEGER NOT NULL,
  requests_limit INTEGER,
  last_429_at TEXT
);

CREATE TABLE IF NOT EXISTS source_health (
  source TEXT PRIMARY KEY,
  status TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  last_success_at TEXT,
  last_error_at TEXT,
  last_error_message TEXT,
  cooldown_until TEXT,
  confidence TEXT DEFAULT 'unknown'
);

CREATE INDEX IF NOT EXISTS idx_token_snapshots_token_time ON token_snapshots(token_mint, captured_at);
CREATE INDEX IF NOT EXISTS idx_pool_transactions_pool_time ON pool_transactions(pool_address, block_time);
CREATE INDEX IF NOT EXISTS idx_pool_transactions_wallet ON pool_transactions(wallet);
CREATE INDEX IF NOT EXISTS idx_raw_trades_token_time ON raw_trades(token_mint, block_time);
CREATE INDEX IF NOT EXISTS idx_raw_trades_wallet ON raw_trades(wallet);
CREATE INDEX IF NOT EXISTS idx_raw_trades_source ON raw_trades(source, block_time);
CREATE INDEX IF NOT EXISTS idx_backfill_queue_status ON backfill_queue(status, priority);
CREATE INDEX IF NOT EXISTS idx_wallet_token_pnl_wallet ON wallet_token_pnl(wallet);
CREATE INDEX IF NOT EXISTS idx_tracked_wallets_status ON tracked_wallets(status);
CREATE INDEX IF NOT EXISTS idx_wallet_leaderboard_rank ON wallet_leaderboard(rank);
CREATE INDEX IF NOT EXISTS idx_signal_log_wallet_time ON signal_log(wallet, detected_at);
CREATE INDEX IF NOT EXISTS idx_paper_trades_wallet ON paper_trades(wallet);
"""


class Database:
    def __init__(self, path: Path | None = None):
        self.path = path or settings.database_path

    async def connect(self) -> aiosqlite.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = await aiosqlite.connect(self.path)
        await conn.execute("PRAGMA busy_timeout=5000")
        conn.row_factory = aiosqlite.Row
        return conn

    async def init(self) -> None:
        conn = await self.connect()
        try:
            await conn.executescript(SCHEMA)
            await conn.commit()
        finally:
            await conn.close()

    async def execute(self, sql: str, params: Iterable[Any] = ()) -> None:
        conn = await self.connect()
        try:
            await conn.execute(sql, tuple(params))
            await conn.commit()
        finally:
            await conn.close()

    async def fetchall(self, sql: str, params: Iterable[Any] = ()) -> list[dict[str, Any]]:
        conn = await self.connect()
        try:
            cur = await conn.execute(sql, tuple(params))
            rows = await cur.fetchall()
            return [dict(row) for row in rows]
        finally:
            await conn.close()

    async def fetchone(self, sql: str, params: Iterable[Any] = ()) -> dict[str, Any] | None:
        rows = await self.fetchall(sql, params)
        return rows[0] if rows else None

    async def insert_notification(self, notification_type: str, payload: dict[str, Any], status: str, error: str | None = None) -> None:
        await self.execute(
            """
            INSERT INTO notification_log(notification_type, created_at, sent_at, status, error_message, payload_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (notification_type, utc_now(), utc_now() if status == "sent" else None, status, error, json.dumps(payload, ensure_ascii=False)),
        )


db = Database()
