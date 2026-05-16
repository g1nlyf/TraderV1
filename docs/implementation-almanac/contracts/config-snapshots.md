# Config Snapshots

Config snapshots make decisions reproducible.

## Required snapshot types

### ConfigSnapshot

Global config:

- sources enabled;
- scan cadence;
- acceptance window;
- worker limits;
- feature flags;
- environment metadata.

### RiskLimitSnapshot

Risk config:

- max open positions;
- max token exposure;
- max strategy exposure;
- liquidity veto;
- slippage limit;
- stale data limit;
- max drawdown;
- risk stop rules.

### StrategyConfigSnapshot

Strategy config:

- strategy version id;
- signal weights;
- token bucket filters;
- wallet scoring weights;
- confidence thresholds;
- entry rules;
- exit rules;
- no-trade rules.

### PromotionCriteriaSnapshot

Strategy decision config:

- min forward paper trades;
- min net expectancy;
- min cumulative net P&L;
- max drawdown;
- baseline comparison rules;
- regime robustness requirements;
- confidence requirements.

### AcceptanceRun

Final run config:

- acceptance window;
- config snapshot ids;
- start/end timestamps;
- invariant violations;
- result;
- gap reports.

## Snapshot rule

No strategy decision is valid without the relevant config snapshot reference.

