# 05. Agent Architecture

## Design rule

Agents are not authority. Agents propose, classify, prioritize and review. Deterministic systems verify, calculate and veto.

The final system should avoid excessive multi-agent complexity. Build the full system through controlled integration stages: start construction with the smallest useful worker set, then expand only when queue metrics, conflict rate and evaluation quality justify more parallelism.

The future architecture may run 10 or more worker agents, but only through a bounded job queue and isolated monitoring sessions. It must not become a free-form chat room where agents negotiate trades without deterministic state.

## Continuous operating loop

The end-to-end loop is:

```text
scan
  -> triage
  -> create/refresh token monitoring session
  -> profile wallets and wallet clusters
  -> generate signal or no-trade decision
  -> risk check
  -> paper order
  -> monitor paper position
  -> exit decision
  -> deterministic evaluation
  -> post-trade review
  -> update experiment registry
  -> curate memory
  -> reprioritize queue
```

This loop runs continuously. It must support many token sessions, but each session has explicit state, owner, timeout and stop criteria.

## Research agents vs trading operators

Separate these responsibilities:

- Research agents create hypotheses, context, wallet profiles and signal candidates.
- Trading operator agents manage paper order requests and paper position monitoring through deterministic services.
- Evaluation agents summarize outcomes but do not calculate canonical metrics.
- Memory agents curate lessons but do not rewrite ledger or strategy history.

No single "Supervisor" should directly do every task. Supervisor prioritizes, assigns and resolves conflicts.

## Core agents

| Agent | Goal | Inputs | Outputs | Can decide | Cannot decide | Writes | Tools needed | Usefulness metrics | Failure modes |
|---|---|---|---|---|---|---|---|---|---|
| Supervisor / Trading Research Director | Keep research loop disciplined | Metrics, experiments, backlog, alerts | Prioritized tasks, research plan | What to investigate next | P&L, fills, risk overrides | AgentDecision, Experiment updates | DB, metrics, scheduler | Better experiment throughput, fewer weak paths | Chasing noise, over-expanding scope |
| Token Discovery Agent | Find token candidates | On-chain/DEX/GMGN/source events | TokenCandidate | Send to triage | Open trades | TokenCandidate | Data adapters | Candidate coverage, duplicate rate | Too many low-quality candidates |
| Token Triage Agent | Decide which tokens deserve research | TokenProfile, liquidity, holders, volume | Triage decision | Analyze / skip / monitor | Enter trade | Triage logs | Token data, risk read | Bad-token rejection quality | Over-filtering real opportunities |
| Wallet Intelligence Agent | Evaluate wallet signal quality | Wallet trades, holdings, token history | WalletProfile, wallet score | Include/exclude wallet candidate | Trust wallet without forward validation | WalletProfile, WalletTrade | On-chain, DB, metrics | Wallet signal contribution to expectancy | Lucky-wallet bias, fake clusters |
| Hypothesis Generator Agent | Create testable strategies/signals | Token, wallet, context, past outcomes | Hypothesis, Signal, TradeThesis | Propose paper trade candidate | Execute, fill, calculate P&L | Hypothesis, Signal | DB, research, signal API | Calibration, testability, novelty | Vague hypotheses, narrative overfit |
| Paper Trading Agent | Operate paper workflow via engine | Signal, risk result, market snapshot | Paper order request, exit request | Request paper order/exit | Mutate ledger directly | AgentDecision | Paper API, risk API | Complete pre-trade logging | Missing context, late exits |
| Risk Guardian Agent | Request and explain deterministic risk checks | Signal, exposure, liquidity, market data | Risk check request, risk explanation, escalation | Request deterministic risk check, explain result, escalate unclear cases | Create authoritative RiskCheck manually, override configured risk rules | AgentDecision, risk explanation | Risk engine | Escalation quality, risk explanation usefulness | LLM-based risk decision, false confidence |
| Post-Trade Review Agent | Turn outcomes into lessons | TradeOutcome, signal, context | PostTradeReview | Suggest hypothesis updates | Rewrite metrics/history | Review entries | Metrics, DB | Useful revisions, bias control | Hindsight storytelling |
| Memory Curator Agent | Keep memory useful and evidence-tagged | Reviews, experiments, failed assumptions | MemoryEntry | Promote/archive knowledge | Replace raw ledger | Curated memory | DB, Hermes memory | Memory precision and freshness | Stale conclusions, memory bloat |

## Later agents

| Agent | Add when | Purpose |
|---|---|---|
| On-chain Behavior Analyst | Wallet and token behavior need deeper analysis | Detect clusters, coordinated behavior, copy-traders |
| Market Microstructure Agent | Execution realism becomes bottleneck | Analyze liquidity, route quality, spread, price impact |
| Social / Narrative Agent | Social sources become available and testable | Summarize X/news/community context |
| Strategy Comparison Agent | Multiple strategy versions exist | Compare strategy metrics, prepare promotion/demotion evidence, archive weak versions |
| Monitoring / Alerting Agent | System runs continuously | Summaries, degradation alerts, operator reports |

## Future parallel worker model

Future 10-agent mode should use workers, not permanent personalities with shared memory.

| Worker pool | Parallelism limit | Scope | Memory |
|---|---:|---|---|
| Token monitors | configurable, e.g. `MAX_TOKEN_SESSIONS` | One token/session per worker lease | Session-local + DB snapshots |
| Wallet cluster analysts | configurable | One wallet/cluster task | WalletProfile + evidence refs |
| Strategy experiment workers | configurable | One StrategyVersion experiment | Experiment registry |
| Paper position monitors | must cover all open positions | One open paper position | Ledger + market snapshots |
| Browser research workers | low limit | One source extraction task | Extraction log only |

The actual limits are configuration, not hardcoded architecture. Open paper positions and exit checks get priority over new research.

## Agent task isolation

Each task must include:

- task id;
- task type;
- strategy version if relevant;
- token/session id if relevant;
- input refs, not giant copied context;
- allowed tools;
- forbidden tools;
- timeout;
- output schema;
- confidence/evidence requirements;
- parent job id;
- retry count.

Agents return artifacts, not authority. Artifacts are validated before use.

## Agent permissions

Allowed:

- create hypotheses;
- summarize context;
- classify wallets/tokens with uncertainty;
- request deterministic calculations;
- request deterministic risk checks;
- create paper order requests through approved API;
- write reviews and memory proposals.

Forbidden:

- direct database edits outside allowed APIs;
- P&L calculation as source of truth;
- ledger mutation;
- risk override;
- creating authoritative RiskCheck manually;
- private key handling;
- changing past reasoning after outcome;
- promoting strategies without metrics.

## Conflict resolution

Conflicts are expected in parallel mode.

Rules:

- risk veto wins;
- ledger state wins;
- deterministic metrics win over narrative review;
- newer market snapshot wins only if timestamp is valid and source confidence is acceptable;
- conflicting strategy mutations become separate StrategyVersions;
- conflicting trade actions block into `conflict_review`;
- no worker can overwrite another worker's session state without lease ownership.

## Connection to positive expectancy

Each agent must justify its existence by measurable contribution:

- better candidate quality;
- fewer bad paper trades;
- better signal calibration;
- improved wallet ranking;
- better strategy selection;
- faster detection of degradation.

If an agent does not improve evaluation quality or net expectancy, it should be disabled, simplified or moved to experimental backlog.
