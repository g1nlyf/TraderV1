# WalletScarper Final Free v1

Бесплатная 24/7 система поиска и ранжирования Solana wallets.

## Быстрый запуск

1. `install.bat`
2. Заполнить `.env` по `.env.example`
3. `run.bat`
4. Отдельно, для dashboard: `run_web.bat`

Dashboard: `http://127.0.0.1:8787`

## Основные команды

- `python -m walletscarper smoke-test`
- `python -m walletscarper run-once --notify`
- `python -m walletscarper backfill --limit 20`
- `python -m walletscarper bitquery-stream --seconds 30`
- `python -m walletscarper run`
- `python -m walletscarper web`
