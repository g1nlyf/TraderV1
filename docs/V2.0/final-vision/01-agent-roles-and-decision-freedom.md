# Agent Roles And Decision Freedom

## Design Rule

Agents are not calculators and scripts are not traders.

Agents receive many structured outputs and decide what matters together. Deterministic services can block actions, calculate facts and enforce invariants, but they should not encode the full trading decision as a fixed formula.

## Agent 1: Token Selection Agent

Mission: maintain the best current universe of tradeable tokens.

Primary inputs:

- token profile snapshots;
- market cap, FDV, liquidity, route depth and spread;
- holder count, holder concentration and growth;
- transaction velocity and buy/sell composition;
- volume growth over short and medium windows;
- token age and lifecycle stage;
- source health and timestamp quality;
- availability of token trade history;
- whether profitable wallet candidates can be extracted;
- historical outcomes for similar token buckets.

Allowed decisions:

- reject token;
- archive token;
- keep in passive watchlist;
- request deeper trade/wallet parsing;
- promote token to active observation;
- ask Hermes to consider a token session;
- downgrade token when liquidity, evidence or behavior degrades.

Forbidden:

- direct paper/live entry;
- direct P&L calculation;
- hardcoded "metric equals trade" authority.

Decision artifact:

```text
TokenAgentDecision
  token_ref
  decision_type: reject | passive_watch | deep_parse | active_watch | archive
  reasons
  uncertainties
  requested_tools
  evidence_refs
  confidence
  expires_at
```

## Agent 2: Wallet Intelligence Agent

Mission: build and maintain a competitive database of the best wallets.

Candidate sources:

- wallets that traded selected tokens;
- wallets that exited selected tokens above ROI/notional thresholds;
- wallets repeatedly present before strong moves;
- wallets linked to profitable clusters;
- wallets that already improved forward paper/shadow outcomes;
- wallets demoted earlier but worth retesting under a new market regime.

Deterministic prefilter outputs:

- token-specific ROI;
- realized P&L estimate;
- total recent P&L estimate;
- win rate estimate;
- closed trade count;
- sample size;
- average win and average loss;
- payoff ratio;
- holding time distribution;
- position sizing;
- one-token P&L concentration;
- bot/manipulation flags;
- data quality and source refs.

Agent responsibilities:

- decide whether the wallet is worth tracking;
- assign a rating and tier;
- write "why yes" and "why no" reasons;
- define what evidence would demote the wallet;
- build a behavioral profile of the person/actor behind the wallet;
- keep wallets competing by forward contribution, not only historical beauty.

Wallet rating should include:

| Field | Meaning |
|---|---|
| `agent_rating` | Agent's overall trust score for using this wallet as a signal source |
| `copyability_rating` | Whether the system can realistically follow the wallet with delay/slippage |
| `pnl_quality` | Strength of P&L after sample, concentration and cost adjustment |
| `winrate_quality` | Whether win rate supports repeatability rather than luck |
| `behavior_profile` | Human, bot-like, insider-like, farm-like, whale-like, early hunter, fast scalper, etc. |
| `decision` | include, probation, watch, reject, archive |
| `demotion_triggers` | Concrete conditions that should reduce trust |

## Agent 3: Hermes Trading Orchestrator

Mission: make paper/shadow trading decisions from combined evidence.

Inputs:

- wallet signal events;
- Token Selection Agent decisions;
- Wallet Intelligence Agent ratings;
- second-level market snapshots/candles;
- current liquidity and route quality;
- active paper positions;
- recent tracked-wallet exits;
- source health;
- source rate limits and current cadence degradation state;
- prior outcomes and curated memory;
- browser/API research artifacts;
- strategy experiment status.

Allowed decisions:

- create `Signal`;
- create `NoTradeSignal`;
- request risk check;
- request paper/shadow entry after passed risk;
- request active monitoring;
- request exit decision before simulated exit;
- downgrade a token or wallet;
- lower observation cadence when source health degrades;
- ask for deeper research;
- pause when source quality is unsafe.

Forbidden:

- direct ledger mutation;
- direct canonical P&L calculation;
- risk override;
- private key access;
- live transaction execution in V2.0;
- rewriting earlier reasoning after outcome is known.

## Decision Freedom Boundary

Hermes and specialist agents must have freedom to synthesize evidence, but all freedom is bounded by:

- typed input and output schemas;
- immutable evidence refs;
- pre-action reasoning;
- deterministic risk veto;
- append-only paper/shadow ledger;
- post-action evaluation;
- strategy and wallet competition.

This preserves the core concept: the agent decides, but the system can audit and measure whether those decisions are good.

## Interaction Model

```text
Agent asks for evidence -> script/tool returns structured artifact -> agent decides next action
Agent proposes trade thesis -> risk engine verifies -> paper engine simulates -> evaluation engine scores
Agent writes review -> memory curator accepts/rejects -> future agent decisions reference curated memory
```

No agent should consume unbounded raw context when a typed artifact can be referenced instead.
