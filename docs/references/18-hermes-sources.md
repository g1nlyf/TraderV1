# 18. Hermes Sources And Confirmed Capabilities

This document records the official Hermes sources used for architecture assumptions. Re-check these before implementation because Hermes is actively evolving.

## Official sources

- Hermes docs: https://hermes-agent.nousresearch.com/docs/
- Hermes GitHub: https://github.com/NousResearch/hermes-agent
- Tools & Toolsets: https://hermes-agent.nousresearch.com/docs/user-guide/features/tools
- Persistent Memory: https://hermes-agent.nousresearch.com/docs/user-guide/features/memory/
- Skills System: https://hermes-agent.nousresearch.com/docs/user-guide/features/skills
- MCP Integration: https://hermes-agent.nousresearch.com/docs/user-guide/features/mcp
- Cron: https://hermes-agent.nousresearch.com/docs/user-guide/features/cron
- Subagent Delegation: https://hermes-agent.nousresearch.com/docs/user-guide/features/delegation
- Browser Automation: https://hermes-agent.nousresearch.com/docs/user-guide/features/browser
- Architecture: https://hermes-agent.nousresearch.com/docs/developer-guide/architecture/

## Confirmed useful Hermes capabilities

Confirmed by docs:

- tools and toolsets;
- terminal/file/browser/search-style tool use depending on configured toolsets;
- persistent bounded memory;
- skills/procedural memory;
- MCP servers through stdio or HTTP;
- cron jobs;
- subagent delegation;
- browser automation;
- session persistence;
- provider routing;
- plugins/hooks;
- API/server and IDE integration options.

## Not confirmed for this trading system

Недостаточно информации для подтверждения этих возможностей Hermes:

- built-in Solana trading;
- built-in GMGN integration;
- built-in paper trading ledger;
- built-in risk engine for trading;
- built-in P&L/expectancy calculator;
- built-in private key management for DEX trading;
- built-in exchange/DEX execution.

Architectural workaround:

- custom module;
- MCP tool;
- external deterministic service;
- separate trading/data layer;
- database;
- scheduler;
- API adapter;
- browser automation layer only where realistic and allowed.

## Design implication

Hermes is the right layer for orchestration, research, memory and tool use. It is not the right layer for accounting, risk, immutable history, execution or source-of-truth evaluation.

## Additional framework research

Checked sources:

- MetaGPT GitHub: https://github.com/FoundationAgents/MetaGPT
- MetaGPT MultiAgent 101: https://docs.deepwisdom.ai/main/en/guide/tutorials/multi_agent_101.html
- MetaGPT Agent Communication: https://docs.deepwisdom.ai/main/en/guide/in_depth_guides/agent_communication.html
- MetaGPT Memory: https://docs.deepwisdom.ai/main/en/guide/tutorials/use_memories.html
- Ruflo GitHub: https://github.com/ruvnet/ruflo
- agency-agents GitHub: https://github.com/msitarzewski/agency-agents
- CrewAI docs: https://docs.crewai.com/
- CrewAI Crews: https://docs.crewai.com/en/concepts/crews
- CrewAI Flows: https://docs.crewai.com/en/concepts/flows
- LangGraph overview: https://docs.langchain.com/oss/python/langgraph/overview
- LangChain multi-agent patterns: https://docs.langchain.com/oss/python/langchain/multi-agent/index
- LangGraph workflows/agents: https://docs.langchain.com/oss/python/langgraph/workflows-agents
- LangGraph subgraphs: https://docs.langchain.com/oss/python/langgraph/use-subgraphs
- AutoGen docs: https://microsoft.github.io/autogen/stable/
- A2A protocol GitHub: https://github.com/a2aproject/A2A
- A2A specification: https://a2a-protocol.org/latest/specification/

## Framework conclusion

- MetaGPT is useful as an SOP/role/action reference, but it is not the best core for the first final-system implementation of a real-time trading research system.
- Ruflo is too broad and swarm-oriented for the first final-system implementation. It is useful as a reference for governance, memory, workers and observability, not as the first runtime.
- agency-agents is a prompt/persona library, not orchestration infrastructure.
- CrewAI can be useful later for bounded research crews or review flows, but must not own trading state.
- LangGraph is the strongest optional candidate if this project later needs a formal stateful workflow runtime with durable execution, human-in-the-loop and graph control.
- AutoGen is useful for multi-agent research experiments, but conversational multi-agent loops are too risky for operational trading workflow unless heavily constrained.
- A2A is a future interoperability protocol for independent agent services, not a replacement for the system job queue.

The final system should be built with Hermes + custom deterministic services + database-backed job queue. Add an external framework only when the missing capability is specific and measured. Adding a framework is not progress by itself.
