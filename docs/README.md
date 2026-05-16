# Hermes Solana Memecoin Research Lab Documentation

Эта папка описывает целевую архитектуру **Hermes-based AI-agent trading research and real-market paper-trading system** для Solana memecoins.

Документация является логическим проектным контуром для IDE / AI coding agent. Она не обещает прибыль, не задает "магические" торговые правила и не превращает LLM в источник истины. Главный фильтр каждого решения:

> Помогает ли это прийти к positive net expectancy / positive paper-trading P&L after costs?

Если нет, решение должно быть изменено, удалено или оформлено как экспериментальная гипотеза.

## Что строится

Система ищет, тестирует и отбирает торговые гипотезы для Solana memecoins через реалистичный paper trading. Hermes Agent используется как research, orchestration, memory и workflow layer. Все, что касается P&L, risk, ledger, fills, fees, slippage, latency, failed fills и evaluation, выполняется отдельными deterministic modules.

Текущий проект `WalletScarper` рассматривается как existing data collector / adapter candidate. Его нельзя автоматически считать финальной архитектурой: перед интеграцией нужен audit, нормализация данных, проверка источников и отделение wallet intelligence от сухого scraping/scoring.

## Delivery model

Документация больше не описывает урезанную промежуточную версию. Release target: Stage 2 autonomous real-market paper trading system with Stage 3-compatible shadow execution design. Stage 3 shadow mode может быть частично реализован там, где качество данных позволяет, но нельзя закрывать Stage 3 фиктивной галочкой. Временные частичные запуски допустимы только как construction checks; они не считаются продуктовой версией и не должны подменять финальный end-to-end workflow.

## Reading order

1. [00-project-definition.md](00-project-definition.md)
2. [01-critical-assessment.md](01-critical-assessment.md)
3. [02-target-market-and-principles.md](02-target-market-and-principles.md)
4. [architecture/03-system-architecture.md](architecture/03-system-architecture.md)
5. [architecture/04-hermes-system-design.md](architecture/04-hermes-system-design.md)
6. [architecture/05-agent-architecture.md](architecture/05-agent-architecture.md)
7. [architecture/06-data-model.md](architecture/06-data-model.md)
8. [research/07-wallet-intelligence.md](research/07-wallet-intelligence.md)
9. [research/08-token-discovery-and-market-context.md](research/08-token-discovery-and-market-context.md)
10. [research/09-signal-generation.md](research/09-signal-generation.md)
11. [research/10-strategy-search-and-self-improvement.md](research/10-strategy-search-and-self-improvement.md)
12. [trading/11-paper-trading-framework.md](trading/11-paper-trading-framework.md)
13. [trading/12-evaluation-metrics.md](trading/12-evaluation-metrics.md)
14. [trading/13-risk-management-and-live-readiness.md](trading/13-risk-management-and-live-readiness.md)
15. [delivery/14-final-system-delivery.md](delivery/14-final-system-delivery.md)
16. [delivery/15-implementation-guide.md](delivery/15-implementation-guide.md)
17. [delivery/16-acceptance-criteria.md](delivery/16-acceptance-criteria.md)
18. [delivery/17-unknowns.md](delivery/17-unknowns.md)
19. [references/18-hermes-sources.md](references/18-hermes-sources.md)

## Implementation almanac

For step-by-step implementation, use [implementation-almanac/README.md](implementation-almanac/README.md). The almanac is the coding-agent execution manual: five sprint plans, contracts, runbooks, checklists and ADRs. When the almanac is fully implemented and its acceptance gates pass, the system should be complete for this release.

## Directory map

```text
docs/
  README.md
  00-project-definition.md
  01-critical-assessment.md
  02-target-market-and-principles.md
  architecture/
    03-system-architecture.md
    04-hermes-system-design.md
    05-agent-architecture.md
    06-data-model.md
  research/
    07-wallet-intelligence.md
    08-token-discovery-and-market-context.md
    09-signal-generation.md
    10-strategy-search-and-self-improvement.md
  trading/
    11-paper-trading-framework.md
    12-evaluation-metrics.md
    13-risk-management-and-live-readiness.md
  delivery/
    14-final-system-delivery.md
    15-implementation-guide.md
    16-acceptance-criteria.md
    17-unknowns.md
  references/
    18-hermes-sources.md
  implementation-almanac/
    README.md
    00-master-build-map.md
    01-system-invariants.md
    02-architecture-decisions.md
    contracts/
    sprints/
    checklists/
    runbooks/
    decisions/
```

Всего содержательных документов в reading order: 19. Всего markdown-файлов вместе с этим README: 20. Документы нужно воспринимать вместе.

## Non-negotiable invariants

- No real-money live trading in the final Stage 2 system.
- No private keys in LLM context.
- No hindsight entries or exits.
- No perfect fills.
- No paper success without fees, slippage, latency, failed fills and liquidity constraints.
- No LLM-calculated P&L as source of truth.
- No wallet signal trusted before it improves net expectancy on new paper trades.
- No strategy promotion without deterministic metrics.
- Risk engine can veto every trade.
