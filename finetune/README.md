# Fine-Tuning Infrastructure — TraderV1 Signal Reviewer

## Зачем

Сейчас Hermes (generic free 20B LLM через CLI) принимает решения по торговым сигналам.

Проблемы:
- 5-30 секунд на решение (CLI subprocess + model warmup)
- Нестабильный JSON → парсинг падает → решение теряется
- Нет доменных знаний о Solana memecoins
- Free модель — низкое качество reasoning

Цель: заменить вызов `hermes.exe -z prompt` на прямой вызов **fine-tuned GPT-4o mini**:
- 200-500ms latency
- Гарантированный формат tool calls
- Домен baked-in
- ~$0.0002/решение vs проблемы с rate limits

---

## Как работает fine-tuning (просто)

```
Обычная модель:               Fine-tuned модель:
видит сигнал → думает         знает что такое tracked_wallet_signal_event
"используй инструменты"  →    ВСЕГДА вызывает правильную цепочку tool calls
любой формат →                строго наш JSON schema
нет торговых знаний →         знает Solana, мемкоины, copyable wallets
```

Fine-tuning = дообучение pre-trained модели на **твоих примерах**.

Каждый пример выглядит так:
```
user: "Review signal: wallet ABC bought token XYZ..."
→ assistant calls wallet_profile_history(wallet="ABC")
→ tool returns {win_rate: 0.6, trade_count: 12, ...}
→ assistant calls token_get_profile(token_mint="XYZ")  
→ tool returns {liquidity_usd: 45000, quality_flags: [], ...}
→ assistant calls agent_record_trading_decision(decision_type="signal", reasoning="...")
```

Модель учится воспроизводить **эту последовательность** для любого нового сигнала.

---

## Этапы

```
ЭТАП 1: Сбор данных (можно начать СЕЙЧАС)
  script 01: извлечь реальные события из stage2 DB (16 decisions уже есть)
  script 02: прогнать через teacher model (Claude Sonnet) → получить ideal sequences
  script 03: сгенерировать synthetic examples (целевой объём: 300-500 total)

ЭТАП 2: Подготовка датасета (1-2 дня)
  script 04: соединить все источники → validate → JSONL формат
  Нужно: ~200 обучающих примеров minimum, лучше 400+

ЭТАП 3: Fine-tuning (1-2 часа работы + несколько часов обучения)
  script 05: загрузить JSONL в OpenAI → запустить training job
  Стоимость: ~$1-5 за весь training run

ЭТАП 4: Интеграция (1 день)
  inference/signal_reviewer.py: drop-in замена AutonomousSignalReviewer
  Гейт: A/B тест — сравнить качество решений с текущим Hermes

ЭТАП 5: Continuous improvement (ongoing)
  По мере накопления реальных paper trades → outcome labels
  Каждые 50 новых outcomes → retraining run
  Через 200 trades: модель учится на своих собственных ошибках
```

---

## Файловая структура

```
finetune/
├── README.md                        ← этот файл
├── requirements.txt
├── .env.example                     ← переменные окружения
├── config/
│   ├── tools.json                   ← OpenAI function schemas для teacher + flash модели
│   └── training_config.yaml        ← hyperparams, model choice, thresholds
├── prompts/
│   └── teacher_system.md           ← системный промпт для teacher модели (GPT-4o/Claude Sonnet)
├── data/
│   ├── raw/                         ← JSON из stage2 DB (01_extract_from_db.py)
│   ├── sessions/                    ← полные диалоги teacher модели (teacher_service.py)
│   └── training/
│       ├── bootstrap.jsonl          ← FORMAT примеры (03_generate_bootstrap.py)
│       ├── train.jsonl              ← финальный train set (06_export_dataset.py)
│       └── val.jsonl               ← validation set
├── tools/
│   ├── db_context.py               ← read-only запросы к stage2 DB
│   └── review_context.py           ← CLI для просмотра контекста сигналов
├── scripts/
│   ├── 01_extract_from_db.py       ← извлечь существующие данные из DB
│   ├── 03_generate_bootstrap.py    ← 100 FORMAT примеров (без стратегии)
│   ├── teacher_service.py          ← ГЛАВНЫЙ: teacher model рецензирует сигналы
│   ├── 05_label_outcomes.py        ← P&L outcomes → quality labels для sessions
│   ├── 06_export_dataset.py        ← labeled sessions → JSONL для fine-tuning
│   ├── 07_train.py                 ← submit training job в OpenAI
│   └── 08_continuous_retrain.py   ← автоматический retrain loop
└── inference/
    └── signal_reviewer.py          ← drop-in замена AutonomousSignalReviewer
```

---

## Что нужно для запуска

```
pip install openai anthropic aiosqlite pydantic pyyaml rich
```

Переменные окружения:
```
OPENAI_API_KEY=sk-...       # для fine-tuning и inference
ANTHROPIC_API_KEY=sk-...    # для teacher labeling (опционально, можно GPT-4o)
```

---

## Быстрый старт

```bash
# Шаг 1: извлечь реальные данные
python scripts/01_extract_from_db.py

# Шаг 2: прогнать через teacher (нужен ANTHROPIC_API_KEY или OPENAI_API_KEY)  
python scripts/02_teacher_label.py

# Шаг 3: сгенерировать synthetic
python scripts/03_generate_synthetic.py --count 300

# Шаг 4: собрать датасет
python scripts/04_build_dataset.py

# Шаг 5: запустить fine-tuning
python scripts/05_train.py --dry-run   # сначала проверить без отправки
python scripts/05_train.py             # реальный запуск

# Шаг 6: проверить качество
python scripts/06_evaluate.py --model ft:gpt-4o-mini:...:...
```

---

## Модель выбора

По умолчанию: **gpt-4o-mini** через OpenAI fine-tuning API.

Почему:
- Нативный tool use (function calling) с гарантированным JSON
- Fine-tuning API стабилен и прост
- ~$3/1M tokens training, ~$0.0003/decision inference
- 200K context window

Альтернативы (настраиваются в config/training_config.yaml):
- `gemini-flash-2.0` — дешевле, нужен Vertex AI
- `qwen-2.5-7b` — локально, zero inference cost, нужен GPU

---

## Формат training примера

```json
{
  "messages": [
    {"role": "system", "content": "You are a Solana memecoin signal reviewer..."},
    {"role": "user", "content": "AUTONOMOUS SIGNAL REVIEW\nSignal event: ..."},
    {"role": "assistant", "tool_calls": [{"function": {"name": "wallet_profile_history", "arguments": "{\"wallet\": \"ABC...\"}"}}]},
    {"role": "tool", "tool_call_id": "...", "content": "{\"ok\": true, \"profile\": {...}}"},
    {"role": "assistant", "tool_calls": [{"function": {"name": "token_get_profile", "arguments": "{\"token_mint\": \"XYZ...\"}"}}]},
    {"role": "tool", "tool_call_id": "...", "content": "{\"ok\": true, \"profile\": {...}}"},
    {"role": "assistant", "tool_calls": [{"function": {"name": "agent_record_trading_decision", "arguments": "{\"decision_type\": \"no_trade\", \"pre_action_reasoning\": \"...\"}"}}]},
    {"role": "tool", "tool_call_id": "...", "content": "{\"ok\": true, \"artifact_id\": \"...\"}"}
  ],
  "tools": [...]
}
```

---

## Ожидаемые метрики

После 300 примеров:
- Tool call schema compliance: >99% (vs ~70% текущего free 20B)
- Decision latency: 200-500ms (vs 5-30s)
- Decision rate (% сигналов с записанным решением): >95% (vs ~70%)

После 200+ реальных trades + retraining:
- Ожидаем улучшение signal/no_trade ratio (больше правильных signal, меньше ложных no_trade)
