# 10. Strategy Search And Self-Improvement

## Correct framing

The correct concept is **Bounded Intelligent Strategy Search**.

Incorrect framing: "LLM agents will eventually find the winning strategy."

Correct framing: agents propose structured hypotheses under a fixed objective function, deterministic systems test them, and only strategies with evidence survive.

## Strategy search components

- objective function;
- search budget;
- hypothesis backlog;
- hypothesis priority;
- expected value of information;
- experiment registry;
- research stop-loss;
- strategy comparison / leaderboard v1;
- no-trade baseline;
- benchmark strategies;
- statistical confidence;
- qualitative review after quantitative filtering;
- kill criteria;
- promotion criteria;
- demotion criteria.

## Strategy Proposal & Mutation Policy

Agents may propose strategy mutations only inside explicit experiment boundaries.

Allowed mutations:

- change wallet scoring weights;
- add or remove signal combinations;
- create new no-trade filters;
- change confidence calibration rules;
- propose new holder/liquidity/age buckets;
- adjust expected holding-time hypothesis;
- change wallet ranking hypothesis;
- propose exit logic variants;
- propose risk-filter candidates for deterministic review;
- create a new StrategyVersion with documented assumptions.

Forbidden mutations:

- changing P&L calculation;
- changing immutable ledger behavior;
- disabling fees, slippage, latency or failed-fill handling;
- disabling risk engine;
- rewriting historical signals or outcomes;
- declaring a strategy successful without metrics;
- changing live execution constraints;
- giving itself private key access;
- silently changing active strategy config.

Every material change creates a new `StrategyVersion`.

Material changes include:

- new entry logic;
- new exit logic;
- changed scoring weights;
- changed risk/no-trade filter;
- changed wallet inclusion criteria;
- changed token bucket policy;
- changed confidence threshold;
- changed data source requirements.

Non-material changes:

- wording of explanations;
- dashboard labels;
- review summary style.

## Creativity limits

Each experiment must define:

- hypothesis;
- mutation from parent version;
- budget in number of paper trades or time;
- target token/wallet buckets;
- kill criteria;
- promotion criteria;
- metrics to compare;
- baseline.

Agents cannot launch unlimited experiments. The Supervisor allocates research budget by expected value of information and current system capacity.

Promotion, demotion and kill thresholds must be stored as versioned configuration. The exact config snapshot used for each decision must be auditable. LLM review cannot replace explicit thresholds.

## Objective function

Primary:

- maximize positive net expectancy / trade;
- maximize cumulative net P&L after costs;
- control drawdown.

Secondary:

- improve signal calibration;
- improve robustness across regimes;
- reduce bad trades;
- improve execution realism;
- improve research efficiency.

## Experiment directions

- wallet-following strategies;
- early-holder quality strategies;
- liquidity expansion strategies;
- narrative + wallet confirmation strategies;
- exit timing strategies;
- no-trade filters;
- rug/noise avoidance strategies;
- token lifecycle strategies;
- cluster-following strategies;
- contrarian strategies.

## Promotion criteria

A strategy version may be promoted only if:

- it has enough forward paper trades;
- net expectancy is positive after costs;
- cumulative net P&L is positive after costs;
- drawdown is within configured limits;
- performance is not concentrated in one token or one wallet;
- it beats no-trade and benchmark baselines;
- execution assumptions are realistic;
- no major bias issue is detected.

"Enough", "acceptable" and "within limits" must resolve to values in `PromotionCriteriaSnapshot`, not agent judgment.

## Demotion and kill criteria

Demote or kill when:

- negative net expectancy persists;
- drawdown exceeds limit;
- performance collapses out-of-sample;
- signal confidence is uncalibrated;
- edge depends on one wallet;
- edge disappears after wallet popularity;
- fills are unrealistic;
- data quality is insufficient.

## Self-improvement loop

1. Observe market.
2. Generate hypothesis.
3. Test through paper trading.
4. Record reasoning before trade.
5. Calculate result deterministically.
6. Perform post-trade review.
7. Update memory.
8. Update strategy score.
9. Promote/demote hypothesis.
10. Create improved strategy version.
11. Test again on new data.

## Bias protections

Required protections:

- p-hacking control;
- overfitting checks;
- survivorship bias checks;
- look-ahead bias prevention;
- confirmation bias review;
- correlation/causation separation;
- lucky wallet problem tracking;
- single-token overfitting prevention;
- regime change detection.

## Required artifacts

- strategy versioning;
- experiment registry;
- holdout periods;
- out-of-sample validation;
- regime segmentation;
- rejected hypothesis archive;
- failed assumption log.

## Positive expectancy connection

Self-search is valuable only if it increases probability of finding robust positive expectancy. If exploration becomes random or unbounded, it should be stopped.
