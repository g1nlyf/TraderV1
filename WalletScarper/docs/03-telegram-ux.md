# Telegram UX

Главный режим Telegram - wallet intelligence, не поток транзакций.

Команды:

- `/start`, `/help` - помощь.
- `/flash_top`, `/top`, `/top10` - топ кошельков.
- `/tracked` - tracked wallets.
- `/digest` - текущий дайджест.
- `/status` - состояние системы и источников.
- `/settings` - настройки чата.
- `/interval 60` - интервал digest.
- `/tx_on`, `/tx_off` - отдельный режим live transaction alerts.

По умолчанию `live_alerts_enabled=0`. Это важно: бот нужен для развития списка сильных кошельков, а не для спама всеми покупками и продажами.

