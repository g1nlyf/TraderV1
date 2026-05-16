# 16. Acceptance Criteria

## System-level criteria

The system is correctly built when:

- decisions are logged before trades;
- no hindsight entry or exit is possible;
- paper ledger is deterministic and append-only;
- costs include fees, slippage, latency, failed fills and liquidity constraints;
- LLM and deterministic modules are clearly separated;
- Hermes role is explicit and bounded;
- wallet signals are validated by forward performance;
- strategy versions are comparable;
- metrics dashboard works;
- rejected trades are logged;
- missed opportunities are logged when observable;
- post-trade review updates curated memory;
- no real-money live execution path is enabled in this release;
- system can run continuously across the configured acceptance window;
- final acceptance requires a configured continuous paper/shadow run window with no critical invariant violations;
- system can explain why it entered, exited, skipped or rejected a trade;
- system can monitor multiple tokens and open paper positions without losing exit/risk priority.

## Hermes acceptance

Hermes integration is acceptable when:

- Hermes can call project tools;
- Hermes cannot mutate ledger directly;
- Hermes cannot calculate canonical P&L;
- Hermes cannot bypass risk;
- Hermes memory stores curated learnings, not raw accounting truth;
- Hermes workflows are reproducible through tools or jobs.

## Paper trading acceptance

Paper trading is acceptable when:

- every paper order links to a signal;
- every signal links to pre-trade thesis;
- every fill includes fees/slippage/latency assumptions;
- failed fills are represented;
- exits are decided before outcome;
- outcomes are calculated by deterministic engine;
- trade history cannot be rewritten by LLM;
- paper mode and future live mode share signal, risk, monitoring and audit workflow.

## Parallel monitoring acceptance

Parallel monitoring is acceptable when:

- jobs are durable;
- workers use leases/timeouts;
- per-token sessions have explicit state;
- max parallel investigations are enforced;
- open paper positions have priority over new research;
- memory scope is session-local unless curated;
- conflicts are blocked and logged;
- no agent can overwrite another session without ownership.

## Wallet intelligence acceptance

Wallet Intelligence is acceptable when:

- wallet metrics are cost-adjusted;
- evidence quality is recorded;
- wallet classes include uncertainty;
- clusters/copy-traders/farm wallets can be flagged;
- wallet inclusion/exclusion is explainable;
- wallet contribution to net expectancy is measured;
- degraded wallets can be demoted.

## Strategy search acceptance

Strategy search is acceptable when:

- every strategy has a version;
- every experiment has budget and criteria;
- strategies compete against baselines;
- kill/promotion/demotion criteria exist;
- kill/promotion/demotion criteria are versioned config snapshots;
- out-of-sample paper performance is tracked;
- qualitative review cannot override quantitative failure;
- every material strategy mutation creates a new StrategyVersion;
- agents cannot mutate P&L, ledger, costs or risk controls.

## Ready for next autonomy stage

The system can move beyond the final Stage 2 release only when:

- positive net expectancy after costs is demonstrated;
- cumulative net paper P&L after costs is positive;
- drawdown is acceptable;
- performance is not concentrated in one token/wallet/regime;
- execution assumptions are conservative;
- risk engine and audit logs are stable.
