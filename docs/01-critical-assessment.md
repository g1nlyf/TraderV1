# 01. Critical Assessment

Этот документ отделяет факты от гипотез. Все пользовательские идеи рассматриваются как seed hypotheses, пока система не проверит их через data, paper trading and evaluation.

## Confirmed facts

- Проект должен строиться вокруг Hermes Agent.
- OpenFlow / OpenCloth / OpenClaw исключаются из этой версии архитектуры.
- Уже существует модуль парсинга / анализа кошельков и транзакций в `WalletScarper`.
- Существующий модуль нужно рассматривать как existing data collector / adapter candidate, а не как финальный wallet intelligence layer.
- До live trading система должна работать в paper trading.
- LLM не должна быть источником истины по P&L, risk, fills или ledger.
- Hermes Agent официально документирует tools/toolsets, memory, skills, MCP, cron, browser automation, subagent delegation and session persistence.

## Hermes-related facts and limits

Hermes подтвержден как agent/orchestration/tool layer. Недостаточно информации для подтверждения trading-specific возможностей Hermes:

- Solana execution adapter;
- GMGN integration;
- paper trading ledger;
- deterministic risk engine;
- P&L calculator;
- private key management;
- exchange/DEX execution engine.

Для этих частей требуется custom module, MCP tool, API service, database, deterministic engine или отдельный trading/data layer.

## Strong hypotheses

- Solana memecoins подходят для research-first системы из-за богатого on-chain поведения.
- "Медленные" memecoins лучше подходят для агентного анализа, чем секундные pump/rug tokens.
- Wallet intelligence может быть сильным сигналом, если проверяется через net expectancy.
- Paper-first подход является обязательным.
- Желание избегать тысячи hardcoded filters правильно, если оно заменяется bounded strategy search.

## Weak or risky hypotheses

- Holder-count hypothesis: идея о 20-1000 holders может быть полезной, но это не правило.
- Smart-wallet following: даже сильный кошелек может быть lucky wallet, insider, manipulated wallet или signal that degrades after discovery.
- 5-60 minute holding-time intuition: разумный prior для не-секундных стратегий, но требует bucket testing.
- Multi-agent idea: больше агентов не значит лучше. Без metrics это увеличивает шум.
- Self-search idea: "агент сам найдет путь" опасно без objective function, budget, baselines, kill criteria and experiment registry.
- Ready-made swarm frameworks: могут ускорить прототип, но также могут скрыть state ownership, retries, memory scope and conflict resolution. Для trading research это опасно без deterministic queue and evaluation.

## Assumptions

- Система будет работать с real-market data в near-real-time.
- Во время строительства допустимы временные construction checks, но они не считаются продуктовой версией.
- Для финальной Stage 2 системы со Stage 3-compatible shadow design допустимы approximate execution models только если они явно логируются, консервативны и входят в acceptance criteria.
- Existing wallet parser можно использовать как сырой data adapter после audit.
- Источники можно подключать по очереди, но финальная система не считается готовой, пока data quality, confidence and degradation handling не интегрированы в общий workflow.

## Unknowns

- GMGN API/browser availability.
- Реальный формат текущего wallet parser.
- Solana RPC/indexer choice.
- Доступная latency и reliability.
- Liquidity and slippage model.
- Capital assumptions for future live stages.
- Legal/compliance constraints.

## Ideas to preserve

- Paper trading as central proof layer.
- Wallet behavior as a research signal.
- Self-search as bounded exploration.
- Hermes as orchestration/research/memory layer.
- No real-money live trading in the final Stage 2 release.

## Ideas to modify

- "Хороший кошелек" нужно определить не по красивой истории, а по contribution to forward net expectancy.
- Holder filters нужно оформить как experiment buckets.
- Fixed wallet rules нужно заменить на metrics, evidence quality and out-of-sample validation.
- Multi-agent architecture нужно запускать постепенно, начиная с минимального полезного набора.

## Ideas to reject or postpone

- Live trading in the final Stage 2 release.
- RL/fine-tuning before high-quality logs.
- Fully autonomous trading before risk gates.
- Unbounded self-search.
- Any strategy that cannot be evaluated deterministically.

## Critical conclusion

Самая сильная часть концепции - связка Hermes research/orchestration with deterministic evaluation. Самая опасная часть - ожидание, что LLM сможет "найти edge" без строгого paper ledger, metrics and research discipline. Реалистичный проект должен сначала построить measurement machine, а уже потом увеличивать агентность.

## Updated architecture warning

The project should not choose a multi-agent framework because "A2A communication is scary". It should reduce A2A complexity by using a database-backed job queue, clear task schemas, leases, session state and deterministic validation.

External frameworks are acceptable only when they reduce a specific implementation risk:

- LangGraph may help if workflow state and durable execution become too complex.
- CrewAI may help for bounded research/review flows.
- MetaGPT may inspire SOP-style role/action design.
- Ruflo may inspire governance/observability patterns.
- agency-agents may inspire specialist prompts.
- A2A protocol may help later when agents run as independent services.

None of these should replace the paper ledger, risk engine, P&L engine or Hermes project orchestration in the final Stage 2 system.
