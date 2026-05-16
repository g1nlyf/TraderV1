# Technical Pipeline

## Источники

Core:
- DexScreener - discovery свежих токенов и текущих метрик.
- GeckoTerminal - fallback discovery/trades.
- DexPaprika - pool transactions для выбранных pools.
- Bitquery CoreCast gRPC - high-throughput live ingestion, если токен доступен.
- Helius/public Solana RPC - точечные уточнения, не массовый historical indexer.

Optional:
- OpenRouter - объяснение уже посчитанных wallet metrics в JSON.

## Token Discovery

`DiscoveryService.run()`:

1. Берет latest profiles/boosts из DexScreener.
2. Берет `new_pools` из GeckoTerminal.
3. Дедуплицирует по pool address.
4. Считает `signal_score`.
5. Сохраняет tokens, pools и snapshots.

Минимальный фильтр:
- age >= 30 минут;
- age <= 48 часов;
- liquidity >= 5,000 USD;
- есть pool address.

Scoring токена:
- 30% volume 1h;
- 20% txns 1h;
- 15% liquidity;
- 15% buy/sell balance;
- 20% age score;
- penalty за FDV > 50M.

## Trade Collection

`TransactionService.collect_for_token()`:

1. Пробует DexPaprika pool transactions.
2. Если пусто - GeckoTerminal pool trades.
3. Нормализует signature, wallet, side, amounts, price, timestamp.
4. Ограниченно использует RPC, если wallet не найден.
5. Пишет сделки в `raw_trades` и `pool_transactions`.

## Bitquery Stream

`BitqueryCoreCastSource.stream_dex_trades()`:

- слушает Solana DEX trade stream циклами;
- нормализует native SOL quote в USD;
- отбрасывает quote-only swaps;
- пишет batch insert в SQLite;
- защищен lock от overlap.

## Wallet Scoring

`ScoringService.score_recent_swaps()`:

1. Читает `pool_transactions`.
2. Группирует по `(wallet, token_mint)`.
3. Считает token-level FIFO PnL.
4. Агрегирует результаты по wallet.
5. Вызывает `WalletQualityScorer`.
6. Пишет `wallet_scores`.
7. Promotes active/probation wallets в `tracked_wallets`.
8. Пересобирает `wallet_leaderboard`.

## Decision Bands

- `active`: score >= 80, bot score < 35, confidence medium/high.
- `probation`: score >= 70, bot score < 50.
- `watch`: score >= 55.
- `store`: сохранить, но не tracked.
- `rejected_bot`, `rejected_micro`, `rejected_one_token`: жесткий reject.
- `stale`: tracked wallet деградировал.

