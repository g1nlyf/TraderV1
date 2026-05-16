# 13. Risk Management And Live Readiness

## Principle

Risk engine is sovereign. It can veto every trade, every strategy and every promotion. LLM cannot override risk.

## Stage-based risk model

| Stage | Mode | Allowed actions | Forbidden actions | Required controls | Promotion criteria |
|---|---|---|---|---|---|
| 0 | Research-only | Data collection, wallet/token analysis | Signals/trades | Data logs, source confidence | Reliable ingestion |
| 1 | Signal-only | Timestamped trade ideas | Automatic paper orders | Signal logs, no-hindsight policy | Signal schema quality |
| 2 | Autonomous paper trading | Create/manage/close paper trades | Real money | Paper ledger, risk checks, costs | Positive paper metrics after costs |
| 3 | Shadow trading | Live quote shadow simulation | Real transactions | Execution simulation, failed tx model | Execution realism evidence |
| 4 | Human-confirmed live | Propose trades for confirmation | Autonomous live | Manual approval, strict logs | Small-scope live validation |
| 5 | Limited autonomous live | Execute within hard limits | Unlimited exposure | Emergency stop, private key isolation | Long robust performance |
| 6 | Higher autonomy | Expanded limits | Unbounded autonomy | Independent audits, risk governance | Proven robustness |

## Parameterized limits

Do not invent capital-specific numbers until capital is known. Limits must be configurable:

- max daily loss;
- max strategy drawdown;
- max position size;
- max token exposure;
- max wallet-signal exposure;
- max open positions;
- max slippage;
- max failed-fill rate;
- min liquidity;
- max stale-data age;
- max strategy allocation;
- max exposure by token bucket.

## Risk vetoes

Hard veto examples:

- insufficient liquidity;
- stale market snapshot;
- unknown fill price;
- failed risk check;
- drawdown limit reached;
- source degraded;
- token rug risk above threshold;
- slippage estimate too high;
- wallet cluster suspected manipulation;
- strategy under demotion/kill status.

## Emergency stop

Required for later stages and useful even in paper:

- stop new orders;
- stop exits only if doing so is safer in paper/live context;
- pause specific strategy;
- pause specific source;
- pause specific wallet cluster;
- alert operator;
- write audit event.

## Future live execution extension spec

This is a future extension spec, not a module to implement in this release. Do not create live execution module, private-key path, swap adapter, signer or DEX transaction code in this release.

If a future release reaches live readiness, live execution must be separate from Hermes:

- deterministic execution engine;
- risk engine before execution;
- exchange/DEX adapter;
- transaction simulation;
- slippage control;
- failed transaction handling;
- private key isolation;
- no direct LLM access to private keys;
- emergency stop;
- audit logs;
- manual override;
- live readiness gates.

## Live readiness gates

Before any live stage:

- paper expectancy positive after costs;
- cumulative net paper P&L positive;
- drawdown acceptable;
- strategy robust across buckets;
- execution simulation conservative;
- risk engine tested;
- audit logs complete;
- manual override tested;
- private key isolation designed;
- legal/compliance reviewed if applicable.

## Final Stage 2 delivery rule

Real-money live trading is not part of the final Stage 2 paper trading delivery. It remains a separate future extension behind live readiness gates. Stage 3-compatible shadow design is required, but full Stage 3 completion is conditional on data quality.
