---
type: research
date: 2026-06-04
tags:
  - research
  - trader
  - experiments-ledger
ai-first: true
status: tested
---
## For future Claude
Part of the [[index|TraderV1 experiment ledger]]. This note records the data assets used to produce the measurements in [[hypotheses-register]]: source, access method, fields, sizes, and time windows. Facts only.

# Datasets

## Binance spot klines
- **Access.** `api.binance.com` / `data-api.binance.vision`, `/api/v3/klines`, free, no key. 1000 bars/request, paginated by startTime.
- **Used in.** H-10, H-11, H-12; SOL hedge for H-15; spot leg for H-13 basis-aware.
- **Coverage.** Hourly; window ~730 days; 17,520 bars/symbol; universes of 44 and 115 USDT pairs (top by 24h `quoteVolume`).
- **Cache.** `finetune/data/majors_cache/*.npz`.

## Binance USDⓈ-M futures (funding + perp klines)
- **Access.** `fapi.binance.com`: `/fapi/v1/fundingRate`, `/fapi/v1/klines` (8h), `/fapi/v1/ticker/24hr`. Free.
- **Used in.** H-13, H-14.
- **Coverage.** 8h funding, ~730 days, 2,190 periods; 46 assets discovered, 40 with Bybit overlap.
- **Cache.** `finetune/data/funding_cache/*.npz`.

## Bybit funding history
- **Access.** `api.bybit.com/v5/market/funding/history`, `category=linear`, 200/request. Free.
- **Used in.** H-13 (cross-venue spread).

## GeckoTerminal (Solana DEX OHLCV + pools)
- **Access.** `api.geckoterminal.com/api/v2`, network `solana`; `trending_pools`, `new_pools`, `pools`, `pools/{addr}`, `pools/{addr}/ohlcv/hour`. Free, rate-limited (~2.2s/call observed; 429 backoff).
- **Used in.** H-15 (13 tokens, ~57d hourly), H-16 (pool OHLCV+volume+reserve, 12 usable pools), H-18 (forward launch discovery + outcome price).

## WalletScarper Stage-2 DB (`stage2_foundation.sqlite3`, 189.2 MB)
- **Tables referenced (row counts as of 2026-06-04):** `token_ohlcv` 19,641 rows / 332 distinct tokens (open, high, low, close, volume, pool_address, ts); `token_price_paths` 48,107 rows / 250 tokens; `wallet_token_outcomes` 1,422 rows / 13 real tokens / 1,330 wallets (`roi_bucket` populated in 1 row); `wallet_metric_snapshots` 758 rows / 116 wallets (483 rows with non-null `win_rate_estimate`, 21 distinct wallets); `market_snapshots` 216; `token_profiles` 87; `wallet_trades` 7; `agent_trading_decisions` 16; `trade_outcomes` 9.
- **Used in.** H-16 (survivorship IL), H-17 (token sample), H-18 (outcomes + tracked/scored wallet sets).
- **Observed property.** Token sets of `wallet_token_outcomes` and `token_ohlcv` have empty intersection.

## Helius (Solana RPC + Enhanced Transactions)
- **Access.** `HELIUS_RPC_URL` (getSignaturesForAddress) + `api-mainnet.helius-rpc.com/v0/transactions` (Enhanced parse). Keys in `WalletScarper/.env` and process env (`HELIUS_API_KEY`, `HELIUS_RPC_URL`).
- **Used in.** H-18 (early-buyer reconstruction; forward-collector snapshots).
- **Client.** `finetune/pipeline/helius_client.py` (getSignatures, parse, _extract_swap, wallet_swaps).

## Labeled feature holdout (H-03)
- **File.** `finetune/data/training/holdout_mom3_eval.jsonl`, 1,360 rows with features (`drawdown_from_high`, `range_pct`, `buy_pressure_6`) and `token_outcome_is_winner`.
- **Note.** Sibling training/holdout files (`train_mom3`, `holdout_mom2`, etc.) present but use a different label schema; not parsed with the same key.
