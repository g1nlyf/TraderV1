# 04. Hermes-Based System Design

## Hermes role

Hermes Agent is the primary agentic layer:

- persistent research/orchestration agent;
- coordinator of subagents;
- project context layer;
- skills/procedural memory layer;
- tool-using agent;
- interface to custom tools, MCP servers and APIs;
- runner of research jobs, analysis jobs and review loops;
- optional browser/web research controller where applicable.

Hermes must not be:

- trading engine;
- exchange adapter;
- risk engine;
- P&L calculator;
- paper trading ledger;
- database;
- backtesting engine;
- private key manager;
- sole source of truth.

## Capability matrix

| Capability | Status | Source / reason | Use in this system | Workaround if not confirmed | Risk of relying on it |
|---|---|---|---|---|---|
| Tool registry/toolsets | Confirmed | Hermes docs describe built-in tool registry and toolsets | Call project tools and MCP services | Direct API service calls | Low |
| Persistent memory | Confirmed | Hermes docs describe MEMORY.md and USER.md | Store compact curated project memory | Project DB and memory curator | Medium: bounded size |
| Skills system | Confirmed | Hermes docs describe skill files and agent-created skills | Store procedural research workflows | Repo docs and prompts | Medium |
| MCP integration | Confirmed | Hermes docs describe stdio/HTTP MCP servers | Expose Solana, DB, paper, metrics tools | REST API adapters | Low |
| Cron scheduling | Confirmed | Hermes docs describe cron jobs | Scheduled scans and reviews | External scheduler | Medium |
| Subagent delegation | Confirmed | Hermes docs describe delegate_task | Parallel bounded research | Worker queue / job service | Medium |
| Browser automation | Confirmed | Hermes docs describe browser modes | Browser research when API unavailable | API scraper / external service | Medium-high |
| Session persistence/search | Confirmed | Hermes architecture docs describe session DB and search | Recall conversations | Project DB | Medium |
| Kanban multi-agent board | Confirmed in docs but should be verified in installed version before use | Hermes docs/search result describe durable task board | Later durable multi-agent workflows | External job queue | Medium |
| Solana trading adapter | Not confirmed | Hermes docs do not provide this as trading capability | Not used directly | Custom module / MCP tool | High |
| GMGN API support | Unknown | External availability not established | Optional source | Browser automation / API adapter | High |
| Paper trading ledger | Not confirmed | Hermes docs do not define a trading ledger | Must be separate | Custom deterministic engine | Critical |
| Risk engine | Not confirmed | Hermes docs do not define trading risk logic | Must be separate | Custom deterministic service | Critical |
| P&L calculator | Not confirmed | Hermes docs do not define trading accounting | Must be separate | Evaluation engine | Critical |
| Private key management | Not confirmed | Not part of the final Stage 2 paper trading system | Excluded | Future isolated vault | Critical |

For every unconfirmed trading capability: **Недостаточно информации для подтверждения этой возможности Hermes.**

## Hermes operating pattern

Hermes should interact with the system through safe tools:

```text
Hermes -> MCP/API tool -> deterministic service -> database/ledger -> deterministic response -> Hermes summary
```

Allowed examples:

- create analysis job;
- request token triage;
- ask paper engine to create paper order from approved signal;
- request evaluation report;
- write post-trade review;
- update curated memory entry.

Forbidden examples:

- direct ledger mutation by LLM;
- direct P&L calculation by LLM;
- private key access;
- bypassing risk check;
- rewriting signal reason after trade outcome.

## Custom tools required

At minimum:

- `token_discovery.scan`;
- `token_triage.evaluate`;
- `wallet_intelligence.profile`;
- `signal.create_candidate`;
- `risk.check_signal`;
- `paper.create_order`;
- `paper.close_position`;
- `metrics.strategy_report`;
- `experiments.register`;
- `memory.curate_entry`.

These can be exposed through MCP, internal HTTP APIs or CLI tools. MCP is preferred if Hermes will call them directly.

## Multi-agent framework decision

Hermes remains the main agentic/orchestration/research layer. Additional frameworks may be evaluated only as implementation aids for bounded workflows, not as replacements for Hermes and not as trading truth.

Adding a framework does not count as progress unless it reduces a specific measured system bottleneck.

| Framework / repo | What it is | Useful for this project | Risk / mismatch | Decision |
|---|---|---|---|---|
| MetaGPT | Role/action/team/SOP multi-agent framework, originally shaped around software-company workflows | Useful mental model for roles, actions, message subscriptions and SOPs | Not trading-specific; can become another orchestration layer competing with Hermes; Python/runtime constraints must be checked | Do not adopt as final-system core. Borrow SOP ideas only. |
| Ruflo | Claude Code-oriented swarm/orchestration platform with many plugins, memory, federation and MCP surface | Interesting reference for swarm governance, background workers, federation, cost/observability ideas | Too broad, Claude-centric, high integration surface, promotes swarm complexity before measurement | Do not adopt as final-system core. Revisit only for tooling inspiration. |
| agency-agents | Collection of specialized agent prompt/persona files | Useful inspiration for role definitions and review personas | Not an orchestration framework; no queue, ledger, risk or trading runtime | Use as prompt reference only, not architecture. |
| CrewAI | Agents, crews and flows with state, event-driven workflows, guardrails and observability integrations | Could prototype bounded research crews or non-critical post-trade review workflows | Higher-level abstraction may hide state/control; must not own ledger/risk | Optional later experiment for research workflows only. |
| LangGraph | Low-level stateful graph runtime for long-running workflows, persistence, human-in-the-loop and parallel graph nodes | Strong candidate if custom workflow runtime becomes too complex | Adds new framework beside Hermes; requires careful state model | Best optional candidate for deterministic-ish workflow orchestration later, not required for the first final-system implementation. |
| AutoGen | Conversational single/multi-agent framework and event-driven Core for scalable multi-agent systems | Useful for research experiments and distributed agent patterns | Conversational loops can be hard to constrain for trading operations | Experimental only, not operational core for this release. |
| A2A Protocol | Open protocol for interoperable agent-to-agent communication across frameworks/runtimes | Useful if future agents run as independent services or across frameworks | Overkill for one local system; not a queue, risk engine or ledger | Future boundary protocol, not the first internal bus. |

Final-system implementation recommendation:

```text
Hermes + deterministic services + database + job queue + per-token sessions
```

Do not start with MetaGPT/Ruflo/CrewAI/AutoGen as the core runtime. The first hard problem is not agent chatter. The first hard problem is reliable state, no-hindsight paper trading, realistic fills, metrics and risk.

No fake framework progress:

- LangGraph may be added only if custom job/session workflow becomes a real bottleneck.
- CrewAI may be added only for bounded review/research flows with strict schemas.
- A2A may be added only if agents are actually split into independent services.
- Ruflo and MetaGPT remain references unless a concrete measured implementation gap justifies a runtime experiment.
- A framework cannot own ledger, risk, P&L, fills, private keys or source-of-truth state.

## A2A policy

Agent-to-agent communication inside the final system should not be free-form chat. It should be structured job handoff:

- input schema;
- output schema;
- state owner;
- timeout;
- retry policy;
- evidence references;
- confidence;
- allowed actions;
- forbidden actions;
- deterministic validation step.

A2A protocol may be introduced later only when agents are deployed as independent services that need protocol-level interoperability. For local bounded workers, a job queue plus database state is simpler and safer.

## Browser Research Adapter Policy

Browser-derived data is less reliable than API/indexer data. It can support research but must not become source of truth for P&L.

Rules:

- every browser-derived fact needs source URL and extraction timestamp;
- store raw HTML, screenshot, accessibility snapshot or extraction log where practical;
- assign extraction confidence;
- mark source layout/version if possible;
- browser-only prices must not be used for strategy promotion or canonical high-confidence P&L;
- if no better price source exists, the trade may be logged only as low-confidence, research-only or shadow-gap evidence, with explicit data quality limitation;
- if layout changes, adapter must degrade/fail closed instead of silently producing wrong data;
- browser research may create `ContextSnapshot`, not immutable trade outcome;
- browser automation must respect source terms and rate limits.

Browser research is appropriate for GMGN-like inspection, social context and semi-automated research flows. It is not appropriate as the only source of execution or accounting truth.

## Source links

Detailed source list is in [../references/18-hermes-sources.md](../references/18-hermes-sources.md).
