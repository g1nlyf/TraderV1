# 02. Architecture Decisions Summary

## Decision summary

| Decision | Chosen approach | Why |
|---|---|---|
| Release target | Stage 2 paper trading with Stage 3-compatible shadow design | Avoids fake Stage 3 completion while preserving future compatibility |
| Orchestration | Hermes + tools/MCP/API | Keeps Hermes as research/orchestration layer |
| Workflow state | Database-backed job queue and monitoring sessions | Safer than free-form A2A chat |
| Risk authority | Deterministic Risk Engine | Prevents LLM risk hallucination |
| P&L authority | Deterministic Evaluation Engine | Prevents narrative metrics |
| Paper order authority | Paper Trading Engine after passed RiskCheck | Preserves audit boundary |
| Browser data | Context/low-confidence evidence only | Prevents browser-only P&L promotion |
| Wallet metrics | Candidate evidence only | Prevents historical wallet P&L from proving strategy success |
| Strategy evolution | Versioned StrategyVersion + config snapshots | Reproducibility |
| Live execution | Explicitly out of release runtime | Avoids accidental private-key/swap path |

## Framework policy

Default runtime:

```text
Hermes + deterministic services + DB job queue
```

Allowed only with measured bottleneck:

- LangGraph: if job/session workflow becomes too complex.
- CrewAI: bounded review/research flow only.
- A2A: independent services only.
- Ruflo/MetaGPT: reference only unless a concrete implementation gap is measured.

Adding a framework is not progress by itself.

