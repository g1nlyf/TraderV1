from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "local"
    config_version: str = "final-free-v1"
    database_path: Path = Path("data/walletscarper.sqlite3")
    log_level: str = "INFO"
    log_json: bool = False

    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    openrouter_api_key: str = ""
    openrouter_enabled: bool = False
    openrouter_model: str = "openai/gpt-oss-20b:free"

    hermes_enabled: bool = False
    hermes_provider: str = "openrouter"
    hermes_model: str = "openai/gpt-oss-20b:free"
    hermes_base_url: str = "https://openrouter.ai/api/v1"
    hermes_api_key: str = ""
    hermes_confidence_threshold: str = "high"
    hermes_signal_strength_threshold: str = "moderate"
    hermes_max_decisions_per_hour: int = 50
    hermes_llm_timeout_seconds: float = 15.0

    bitquery_api_token: str = ""
    bitquery_enabled: bool = False
    bitquery_grpc_address: str = "corecast.bitquery.io:443"
    bitquery_graphql_url: str = "https://streaming.bitquery.io/graphql"
    bitquery_stream_seconds: int = 55
    bitquery_stream_interval_seconds: int = 70

    helius_api_key: str = ""
    helius_rpc_url: str = ""
    solana_public_rpc_url: str = "https://api.mainnet-beta.solana.com"
    sol_usd_estimate: float = 160.0
    wallet_trade_poll_signatures: int = 50
    token_validation_enabled: bool = True

    discovery_interval_minutes: int = 60
    live_monitor_interval_seconds: int = 30
    live_monitor_max_wallets_per_tick: int = 100
    digest_interval_minutes: int = 60
    daily_wallet_tracker_hour_utc: int = 0

    web_host: str = "127.0.0.1"
    web_port: int = 8787

    min_pair_age_minutes: int = 120
    max_pair_age_minutes: int = 2880
    min_liquidity_usd: float = 20_000
    min_volume_1h_usd: float = 5_000
    min_volume_6h_usd: float = 15_000
    min_txns_1h: int = 50
    min_buys_1h: int = 20
    min_sells_1h: int = 10
    max_fdv_usd: float = 50_000_000
    max_discovery_profiles: int = 200
    max_deep_tokens_per_run: int = 20
    max_transactions_per_pool: int = 100
    max_rpc_transactions_per_pool: int = 3
    max_wallet_history_signatures: int = 150
    backfill_workers: int = 8
    backfill_token_limit: int = 80

    active_tracked_wallet_score: float = 80
    probation_tracked_wallet_score: float = 70
    stale_tracked_wallet_score: float = 60
    min_wallet_token_roi: float = 0.20
    min_wallet_realized_profit_usd: float = 20
    min_median_holding_minutes: float = 5
    max_median_holding_minutes: float = 120
    wallet_candidate_one_token_profit_concentration_penalty_threshold: float = 0.60

    paper_entry_delay_seconds: int = 60
    paper_slippage_bps: float = 150
    paper_fee_bps: float = 40
    paper_portfolio_usd: float = 1000.0
    paper_max_position_pct: float = 0.02

    circuit_breaker_enabled: bool = True
    circuit_breaker_max_consecutive_losses: int = 3

    def ensure_dirs(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        Path("logs").mkdir(exist_ok=True)
        Path("tmp").mkdir(exist_ok=True)

    @property
    def rpc_url(self) -> str:
        return self.helius_rpc_url or self.solana_public_rpc_url

    @property
    def telegram_configured(self) -> bool:
        return bool(self.telegram_bot_token)

    @property
    def openrouter_configured(self) -> bool:
        return bool(self.openrouter_enabled and self.openrouter_api_key)

    @property
    def bitquery_configured(self) -> bool:
        return bool(self.bitquery_enabled and self.bitquery_api_token)

    @property
    def helius_configured(self) -> bool:
        return bool(self.helius_api_key)

    @property
    def helius_das_url(self) -> str:
        if self.helius_rpc_url:
            return self.helius_rpc_url
        if self.helius_api_key:
            return f"https://mainnet.helius-rpc.com/?api-key={self.helius_api_key}"
        return ""


settings = Settings()

Confidence = Literal["high", "medium", "low", "unknown"]
