# 12. Evaluation Metrics

## Primary metrics

The two primary metrics are:

- **positive net expectancy / trade**;
- **positive cumulative net P&L after costs**.

These metrics must be calculated after:

- fees;
- slippage;
- latency;
- failed fills;
- liquidity constraints;
- price impact;
- route quality limitations;
- drawdown.

## Secondary metrics

- win rate;
- profit factor;
- average win / average loss;
- payoff ratio;
- max drawdown;
- Sharpe / Sortino, if applicable;
- exposure time;
- position duration distribution;
- slippage-adjusted returns;
- signal calibration;
- false positive rate;
- false negative rate;
- opportunity cost;
- wallet signal contribution;
- strategy version comparison;
- regime robustness.

## Required breakdowns

Performance must be segmented by:

- token type;
- liquidity bucket;
- holder bucket;
- market cap bucket;
- token age bucket;
- volume bucket;
- time of day;
- market regime;
- wallet class;
- strategy version;
- signal type;
- confidence bucket.

## Operational metrics for parallel mode

Parallel agents are useful only if they improve throughput without degrading decision quality.

Track:

- queued jobs by type;
- job age;
- lease timeouts;
- retry count;
- conflict count;
- average token monitoring duration;
- open paper positions monitored on time;
- missed exit checks;
- browser extraction failure rate;
- agent artifact rejection rate;
- cost per accepted signal;
- cost per completed paper trade.

If parallelism increases cost, latency or conflicts without improving expectancy, reduce worker counts.

## Win rate warning

Положительный win rate без positive expectancy не считается успехом.

Examples:

- 70% win rate with tiny wins and large losses can be negative expectancy.
- 35% win rate with large average wins and controlled losses can be positive expectancy.

Therefore win rate must always be interpreted with payoff ratio, average win/loss, drawdown and net P&L.

## Strategy leaderboard

Strategy leaderboard should include:

- strategy version;
- number of trades;
- net expectancy;
- cumulative net P&L;
- max drawdown;
- profit factor;
- average duration;
- liquidity bucket performance;
- holder bucket performance;
- wallet signal contribution;
- confidence calibration;
- status: experimental / probation / active / demoted / killed.

## Signal quality

Track:

- confidence bucket calibration;
- signal-to-trade conversion;
- rejected signal outcome when observable;
- no-trade decision quality;
- exit timing quality;
- signal decay over time.

## Wallet contribution

For wallet-derived signals, measure:

- performance with wallet signal;
- performance without wallet signal;
- performance by wallet class;
- wallet-specific expectancy;
- degradation after wallet popularity;
- cluster risk penalty impact.

## Evaluation authority

Evaluation Engine is the source of truth. LLM may summarize or interpret metrics, but cannot create canonical metrics.

## Positive expectancy connection

Metrics must expose whether the system is actually improving after costs. If a metric does not affect strategy selection, risk control or expectancy, it should be treated as secondary or removed from the primary dashboard.
