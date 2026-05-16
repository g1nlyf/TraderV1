# 17. Unknowns, Assumptions And Pending Decisions

## Data sources

- GMGN API availability.
- GMGN browser access reliability.
- Solana RPC/indexer choice.
- Dex/market data provider choice.
- Social data source availability.
- Source latency.
- Rate limits.
- Data completeness.

## Existing module

- Current `WalletScarper` transaction parser format.
- Current data model completeness.
- Current paper trading assumptions.
- Current wallet scoring assumptions.
- Current source reliability and confidence metadata.

## Execution simulation

- Fee model.
- Slippage model.
- Liquidity model.
- Price impact model.
- Latency assumptions.
- Failed-fill probability.
- Route quality model.
- Stale-price rejection threshold.

## System design

- Database choice.
- Scheduler choice.
- Job queue implementation.
- Monitoring session state machine implementation.
- Whether LangGraph/CrewAI/AutoGen are needed later or custom queue is enough.
- Whether A2A protocol is needed for independent services.
- Deployment environment.
- Dashboard framework.
- Alerting channel.
- Human approval flow for future stages.
- Logging retention.
- Backups.

## Risk and capital

- Capital assumptions for future live stages.
- Max position size.
- Max daily loss.
- Max drawdown.
- Max open positions.
- Liquidity veto threshold.
- Rug/noise risk rules.

## Hermes-specific pending verification

- Installed Hermes version and feature availability.
- MCP setup path.
- Cron deployment mode.
- Browser automation availability.
- Subagent delegation limits.
- Kanban availability in installed version.
- Memory provider choice.

## Legal / compliance

- Jurisdiction.
- Tax treatment.
- Regulatory constraints.
- Terms of service for data sources.
- Restrictions on scraping or browser automation.
- Live trading compliance requirements if ever considered.

## Assumption policy

Unknowns must not block documentation, but they must block false certainty. Any unknown that affects expectancy or risk must be represented in configuration, evidence quality or experiment status.
