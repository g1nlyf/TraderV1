# 00. Project Definition

## Working name

**Hermes Solana Memecoin Research Lab**

## Short definition

Мы строим Hermes-based AI-agent trading research and real-market paper-trading system для Solana memecoins. Это не обычный trading bot: система не просто исполняет фиксированный набор правил, а формулирует, тестирует и отбирает торговые гипотезы. Hermes Agent является главным агентным, orchestration, research, memory и workflow layer. Hermes не является exchange engine, risk engine, paper trading ledger, database или источником истины по P&L.

Центральная стадия - realistic paper trading в реальном рынке с timestamped decisions, fees, slippage, latency, failed fills, liquidity constraints, price impact и drawdown accounting. Успех определяется не высоким win rate и не "умным" поведением LLM, а устойчивыми positive net expectancy / trade и positive cumulative net paper-trading P&L after costs.

## Executive summary

Solana memecoins дают широкий opportunity set, но одновременно создают экстремальный шум: манипуляции, short-lived liquidity, coordinated wallets, fake volume, copy-trader cascades, rugs и social noise. Простая LLM-система в такой среде будет легко объяснять случайность как закономерность. Поэтому архитектура должна быть evidence-first и paper-before-live.

Решение: Hermes координирует исследовательские агенты, wallet intelligence, token triage, hypothesis generation, post-trade reviews и memory curation. Отдельные deterministic modules отвечают за ingestion, normalization, immutable paper ledger, fills, fees, slippage, latency, risk, P&L, evaluation и dashboards.

Главная метрика: **positive net expectancy / trade** и **positive cumulative net P&L after costs**. Win rate полезен, но вторичен.

Эта версия проекта не строится как урезанный прототип. Release target: **Stage 2 autonomous real-market paper trading system with Stage 3-compatible shadow execution design**. Stage 3 shadow mode may be partially implemented where feasible, but full Stage 3 is not required unless live quote quality, latency data and execution simulation quality are sufficient. Live trading реальными деньгами остается будущей gated extension, а не частью этой финальной paper/shadow реализации.

## Main goal

Система должна быть построена так, чтобы искать, тестировать и отбирать только те гипотезы и стратегии, которые демонстрируют положительную net expectancy на realistic paper trading.

Цель включает:

- positive net expectancy / trade;
- positive cumulative net paper-trading P&L after costs;
- controlled max drawdown;
- acceptable profit factor;
- healthy average win / average loss;
- payoff ratio that compensates for losses;
- win rate as a secondary metric;
- regime robustness;
- performance stability across token groups;
- signal quality;
- execution realism.

Нельзя формулировать цель как "система будет прибыльной". Правильная формулировка: система должна искать и отбирать гипотезы, которые демонстрируют positive net expectancy на реалистичном paper trading.

## What the system must not do

Система не должна:

- торговать реальными деньгами в Stage 2 paper/shadow-compatible реализации;
- считать LLM источником истины;
- подгонять результаты задним числом;
- оптимизироваться только под win rate;
- верить "умным кошелькам" без forward validation;
- принимать пользовательские гипотезы как доказанные правила;
- принимать решения без логирования причины до сделки;
- использовать будущие данные;
- считать paper trading успешным без fees, slippage, latency and failed fills;
- позволять LLM редактировать историю сделок;
- превращаться в хаотичную multi-agent систему без метрик;
- превращать Hermes в trading engine, risk engine или P&L calculator.

## Core principles

- **Evidence-first:** каждое правило проходит через данные.
- **Paper-before-live:** live trading запрещен до доказательной paper-фазы.
- **No hindsight:** entry, exit and reasoning фиксируются до результата.
- **Deterministic accounting:** P&L, fees, slippage, latency, fills, win rate, drawdown and expectancy считает код.
- **Every trade is an experiment:** каждая paper trade связана с hypothesis и strategy version.
- **Every hypothesis must compete:** гипотезы сравниваются с baselines and no-trade baseline.
- **LLM proposes, deterministic systems verify.**
- **Risk engine is sovereign:** risk veto сильнее любого агента.
- **Memory must be curated:** память не должна слепо накапливаться.
- **No signal is trusted until it improves net expectancy.**

## Autonomy stages

| Stage | Mode | Meaning |
|---|---|---|
| 0 | Research-only mode | Система собирает данные, анализирует токены и кошельки, но не создает сделки. |
| 1 | Signal-only mode | Система формирует торговые идеи, но не исполняет даже paper trades автоматически. |
| 2 | Autonomous real-market paper trading | Основной текущий этап. Система самостоятельно создает, ведет и закрывает виртуальные сделки. |
| 3 | Shadow trading with live quotes | Система работает как live, но без реальных транзакций, с максимально реалистичной execution simulation. |
| 4 | Human-confirmed live trading | Система предлагает сделки, человек подтверждает. |
| 5 | Limited autonomous live trading | Система может исполнять сделки только в строгих параметризованных лимитах. |
| 6 | Higher autonomy | Только после доказанной устойчивости, строгой валидации и risk gates. |

Текущий проектный фокус: **Stage 2**, спроектированный так, чтобы его signal/risk/monitoring/audit workflow был совместим с будущим Stage 3 shadow mode.
