# DATA AUDIT REPORT — Sprint 5 (PHASE 1)

Generated 2026-06-06 from `walletscarper.sqlite3` (1.6 GB) and `stage2_foundation.sqlite3` (189 MB).
Method: full-scan row counts, parsed time ranges, distinct-entity counts, null/quality probes.
Reproduce: `py hypothesis_lab/wallet_alpha/profile_dbs.py`.

## Executive summary
1. The "847K tape" (`raw_trades`) is a **5.5-hour firehose snapshot** (2026-05-14 10:00–15:31 UTC, 843,323
   rows) + 3,946 stragglers on 05-16. Cross-section is huge (120,418 wallets × 12,318 tokens); calendar
   span is ~zero. **This is the single most important fact in the project right now.**
2. **Every wallet "skill" table is look-ahead** (`wallet_scores`, `wallet_leaderboard`, `wallet_token_pnl`)
   — single `calculated_at` batch, and `wallet_token_pnl` has **NULL** entry/exit timestamps. They are
   label/diagnostic only, never features.
3. **Multi-day forward labels are unavailable** for the cross-section: calendar price sources
   (`token_price_paths` 250 tok, `token_ohlcv` 332 tok) overlap raw_trades on **16 tokens**.
4. Therefore Sprint 5 is scoped to **intraday cross-sectional** wallet alpha with self-derived forward
   VWAP labels. Persistence is explicitly out of reach until multi-day capture exists.

## LEGACY DB — walletscarper.sqlite3 (22 tables)

| Table | Rows | Time field | Span | Distinct | Source conf | Leakage as feature |
|-------|------|-----------|------|----------|-------------|--------------------|
| raw_trades | 847,269 | block_time | **2026-05-14 5.5h** (+05-16 tail) | 120,418 w / 12,318 tok / 15,519 pool | medium (real fills) | **LOW** if block_time<t enforced |
| pool_transactions | 745,566 | block_time | same window | — | medium | LOW (legacy dup of raw_trades) |
| wallet_token_pnl | 76,175 | first_buy/last_sell **NULL**; calculated_at single | — | — | n/a | **FATAL** (full-lifecycle, no ts) |
| wallet_scores | 108 | calculated_at single | — | — | n/a | **FATAL** (look-ahead skill) |
| wallet_leaderboard | 69 | calculated_at single | — | — | n/a | **FATAL** + survivorship |
| tracked_wallets | 130 | added_at | point-in-time ✓ | — | — | OK ("known before t") |
| wallet_rank_history | 1,079 | — | — | — | — | use with care |
| wallet_scores band | — | decision_band ∈ scores | — | — | — | label |
| tokens | 37 | first_seen_at | — | — | — | OK (token age) |
| token_snapshots | 103 | — | — | — | — | context |
| signal_log | 841 | detected_at, block_time | window | — | — | OK (detection lag is real) |
| paper_trades | 841 | created_at | — | — | — | outcome of old paper loop |
| api_cache 63 / pools 42 / ingestion_runs 191 / run_summaries 8 / source_health 7 / llm_wallet_reports 2 | small | — | — | — | — | infra |

Key distributions (raw_trades):
- Trades/wallet: median **1**, max 36,103 (bots). Wallets with ≥20 trades: 3,550; ≥50: 1,482; ≥100: 568.
- Tokens by distinct wallets: ≥5: **4,447**; ≥10: 2,558; ≥20: 1,396. → ample cluster-event candidates.
- side: buy 463,760 / sell 383,509. DEX: pump 35% / Orca(amm_v3+whirlpool) 51% / Raydium 13.5%.
- `price_usd` > 0: only **8,543** → derive **price_sol = quote_amount / token_amount** (present 99.998%).
- `block_time` mixed ISO + few unix-epoch strings → normalize on read.

## STAGE2 DB — stage2_foundation.sqlite3 (77 tables, mostly operational)

| Table | Rows | Use | Note |
|-------|------|-----|------|
| token_price_paths | 48,107 | **forward label (multi-day)** | 250 tok, 2026-04-04→05-31; ∩ raw_trades = **13** |
| token_ohlcv | 19,641 | forward label (bars) | 332 tok, unix ts; ∩ raw_trades = **9** |
| token_price_paths ∪ ohlcv ∩ raw_trades | **16** | — | multi-day labels not viable for cross-section |
| wallet_token_outcomes | 1,422 | intended labels | roi_estimate non-null **50**, roi_bucket **1** → effectively empty |
| wallet_metric_snapshots | 758 | wallet metrics | calculated_at → look-ahead as feature |
| token_candidates | 127 / token_profiles 87 / token_triage_decisions 87 | discovery context | small |
| tracked_wallet_signal_events | 15 | live signals | too few to test |
| agent_trading_decisions 16 / signals 16 / trade_outcomes 9 / paper_* ~25 | agent loop | operational, tiny |
| (remaining ~55 tables) | <60 each | infra/acceptance/worker | not research data |

## Leakage rules adopted for Sprint 5 (binding)
1. Features may read raw_trades rows with **block_time < event_t** only.
2. Wallet "skill" is recomputed point-in-time from pre-t **completed round-trips** (buy then sell, both < t).
   Never from wallet_scores/leaderboard/wallet_token_pnl/GMGN.
3. Labels = forward price_sol VWAP over (t, t+H], H ∈ {30m, 60m}, from raw_trades itself. Cost 0.018 RT.
4. Split = temporal (by event_t). Report train/test wallet & token overlap to expose cross-fold leakage.
5. Baselines mandatory: token-only, naive-copy (equal-weight all clusters), random/permutation.

## What this audit changes
- Kills any near-term "wallet alpha is real" claim that rests on the leaderboard (survivorship).
- Reframes the deliverable from "find persistent wallet alpha" to "is there *intraday* cross-sectional
  wallet-consensus structure, tested honestly?" + "what data do we need for persistence?" (answer: multi-day capture).
