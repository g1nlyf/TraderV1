# DATA LEDGER — every dataset, its span, and its leakage risk

> "Source confidence" = how much I trust the values. "Leakage risk" = can this be used as a *feature*
> at event time without seeing the future? Updated 2026-06-06.

## On-chain trade data (the wallet-alpha substrate)

### `raw_trades` — walletscarper.sqlite3 — **PRIMARY**
- **847,269 rows.** Cols: id, signature, wallet, token_mint, pool_address, dex_id, side, token_amount, quote_amount, price_usd, block_time, slot, source, source_confidence, ingestion_run_id, raw_json.
- **Time: 843,323 on 2026-05-14 (10:00–15:31 UTC, 5.5h); 3,946 on 2026-05-16.** Effectively a 5.5-hour snapshot.
- 120,418 distinct wallets · 12,318 tokens · 15,519 pools. side: buy 463,760 / sell 383,509.
- Source: bitquery_corecast 98.9%, dexpaprika 1.0%, geckoterminal <0.01%. source_confidence: **all "medium"**.
- DEX mix: pump 35%, amm_v3 (Orca) 29%, whirlpool 22%, raydium_amm 7.5%, raydium_cp 6%.
- **Quality flags:** `price_usd` is 99% NULL (8,543 / 847k > 0). **Use price_sol = quote_amount / token_amount** (quote_amount present 99.998%). `block_time` is mixed format (ISO + a few unix-epoch strings) — normalize on read.
- **Source confidence: MEDIUM-HIGH** for the fills themselves (real on-chain swaps). **Leakage risk: LOW if used point-in-time** (block_time is the true event clock). The trap is computing wallet/token aggregates over the *whole* table and using them as pre-event features.

### `pool_transactions` — walletscarper.sqlite3
- 745,566 rows. Same shape as raw_trades minus id/dex_id/slot, plus `completeness`. Overlapping/legacy adapter of the same swaps. Use raw_trades as canonical; pool_transactions only to backfill missing pools.

### `wallet_tapes.json` — finetune/data/ — **secondary (long-horizon, biased)**
- 12,128 swap events, **86 wallets**, **2025-07-14 → 2026-06-01 (321 days)**. Helius-reconstructed (getSignatures + Enhanced Tx). Fields: ts, signature, wallet, token_mint, side, sol_amount, token_amount, price_sol.
- **Source confidence: HIGH** (real fills). **Leakage risk: HIGH as currently used** — the 86 wallets are the *leaderboard* wallets, selected because they were profitable over this same span → survivorship. Usable point-in-time per wallet (trades before t) but the *universe* is biased.

## Wallet aggregates (LABEL-ONLY — never features)

### `wallet_token_pnl` — walletscarper.sqlite3
- 76,175 rows. wallet × token realized/unrealized PnL, roi, buys/sells count, holding_time.
- **`first_buy_at`, `last_sell_at` are ALL NULL.** `calculated_at` is a single batch (2026-05-16T13:15:04Z).
- **Leakage risk: FATAL as feature.** Full-lifecycle realized outcome, no timestamps → cannot be placed in time, encodes the future. Use only as a sanity cross-check on labels.

### `wallet_scores` — walletscarper.sqlite3 (108 rows)
- winrate, median_roi, bot_score, human_score, copyability_score, **decision_band**, etc. Single `calculated_at` batch over all history. **Leakage risk: FATAL as feature** (look-ahead skill label).

### `wallet_leaderboard` — two versions, both look-ahead
- DB table: 69 rows (rank, composite_score, copyability_score, forward_score, reason_json).
- JSON `wallet_leaderboard.json`: **641 rows** (wallet, realized_pnl_sol, win_rate, payoff_ratio, score, …). Newer/wider.
- **Leakage risk: FATAL as feature** + survivorship (defines the biased 86-wallet copy universe).

### `tracked_wallets` (130) / `wallet_rank_history` (1,079)
- The discovery roster + rank time series. Useful for *which wallets were known when* — `added_at` IS a point-in-time field (when a wallet entered tracking). Potential honest feature: "wallet was already tracked before t."

## Forward-price / label sources (calendar-spanning but tiny coverage)

### `token_price_paths` — stage2_foundation.sqlite3
- 48,107 rows. token_mint, pool_address, observed_at, price_usd. **2026-04-04 → 2026-05-31 (8 weeks).** 250 tokens.
- **Overlap with raw_trades tokens: 13.** → multi-day labels available for only 13 raw_trades tokens.

### `token_ohlcv` — stage2 (19,641 rows, 332 tokens, unix ts) · overlap with raw_trades: **9**
### Union (price_paths ∪ ohlcv) ∩ raw_trades = **16 tokens** → **multi-day forward labels are not viable for the cross-section.**

### `wallet_token_outcomes` — stage2 (1,422 rows)
- roi_estimate non-null only **50**; roi_bucket non-null **1**. **Effectively empty of labels.** Do not rely on.

## CEX market-structure data (the C-002 / carry substrate)
- `finetune/data/funding_cache/` — 50 USDT perps, Binance+Bybit funding + spot/perp 8h klines, ~730d (2,190 periods). Drives C-002. **Confidence HIGH, leakage LOW** (train/test temporal split enforced in funding_harvest).
- `finetune/data/intraday_1m/` — 1m perp+spot, 10 names, 180d. Drives leverage_sim. HIGH/LOW.
- BLOCKED (not cached): OI history, L2/orderbook, options/IV, OKX funding, SPX/macro, on-chain TVL. These gate ~30 generated hypotheses (see DEAD_TRACKS §blocked).

## Forward collector (live, running)
- `finetune/pipeline/forward_collector.py` + cron → `finetune/data/forward_collector_state.jsonl` (updated 2026-06-06 18:40). Accumulates forward outcomes for H-040/H-024/H-042 to grow n past the gate. **This is the unblock path for sub-gate sleeves.**

## Wallet firehose collector (NEW, Sprint 6 — the persistence unblock)
- `hypothesis_lab/wallet_alpha/firehose_collector.py` → `hypothesis_lab/wallet_alpha/_data/firehose.sqlite3` (gitignored). **FREE, keyless** GeckoTerminal (new+trending pools → per-pool trades). Schema aligned to raw_trades (wallet, token, side, quote/base, block_ts, provenance). UNIQUE(sig,token,side,wallet) dedup. **Confidence MEDIUM (real fills), leakage LOW** (block_ts is event time). **This is what makes cross-day wallet persistence (H-163) testable** — run daily, target ≥14 days. Runbook: `wallet_alpha/FIREHOSE_RUNBOOK.md`.
- Future-optional (free, not yet wired into this table): Bitquery Corecast gRPC (`WalletScarper/.../bitquery_corecast.py`, higher throughput), Helius free DAS (`helius_das.py`, per-wallet backfill). Document quota before relying.

## Bottom line for Sprint 5
- **Feature substrate:** raw_trades, point-in-time (block_time < t), price_sol = quote/token.
- **Label:** intraday forward VWAP return from raw_trades itself, H ∈ {30m, 60m}. Multi-day = unavailable.
- **Forbidden as features:** wallet_token_pnl, wallet_scores, wallet_leaderboard, GMGN score, any `calculated_at`-batch aggregate.
