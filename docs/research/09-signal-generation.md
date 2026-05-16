# 09. Signal Generation

## Purpose

Signal generation converts wallet, token, market and social evidence into structured trade hypotheses. A signal is not a trade. A signal is an auditable proposal that must pass risk checks and paper execution rules.

## Signal types

- wallet-based signal;
- token momentum signal;
- liquidity expansion signal;
- holder-quality signal;
- narrative/social confirmation signal;
- market microstructure signal;
- exit-timing signal;
- risk/liquidity veto;
- no-trade signal;
- contrarian signal.

## Required signal contract

Every signal must include:

- timestamp;
- data_as_of;
- source;
- evidence;
- confidence;
- thesis;
- invalidation condition;
- expected holding time;
- estimated risk;
- estimated slippage;
- entry reason;
- exit reason;
- what would prove this signal wrong;
- strategy version;
- expected contribution to net expectancy;
- links to token, wallet and market snapshots.

## Trade thesis contract

`TradeThesis` should answer:

- Why this token?
- Why now?
- What evidence existed before entry?
- What is the expected holding window?
- What is the planned exit logic?
- What invalidates the thesis?
- What risk could make this trade uncopyable?
- Which strategy version produced this signal?

## No-trade signal

No-trade signals are first-class. They should be logged when:

- a token looks attractive but liquidity is too weak;
- wallet signal is suspicious;
- social activity is too manipulated;
- slippage estimate is too high;
- data is stale;
- risk budget is exhausted.

Avoiding bad trades can improve expectancy as much as finding winners.

## Signal calibration

Confidence must be calibrated against outcomes. If high-confidence signals do not outperform low-confidence signals after costs, the confidence model is not useful.

Track:

- confidence bucket performance;
- false positives;
- false negatives;
- missed opportunities;
- rejected trade outcomes when observable;
- no-trade signal quality.

## LLM boundaries

LLM may:

- synthesize evidence;
- phrase thesis;
- classify context;
- suggest invalidation;
- create candidate signals.

LLM may not:

- decide final fill;
- calculate final P&L;
- override risk;
- change signal after outcome;
- hide rejected evidence.

## Positive expectancy connection

Signals exist to create measurable experiments. If a signal type cannot be linked to improved net expectancy or better risk avoidance, it should be removed or demoted to research-only.

