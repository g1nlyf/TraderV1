# H-003 — Holder-Flow Signal: Does Early Wallet Accumulation Predict Price?

**Status:** proposed
**Priority:** P1
**Asset universe:** Solana memecoins (Helius on-chain)
**Created:** 2026-06-04

## Statement
For Solana memecoin launches, early wallet accumulation patterns (number of distinct early buyers, early buy SOL volume, overlap with tracked smart wallets) predict forward price return at 24h horizon better than random. This is the highest-potential hypothesis in the queue (#74).

## Rationale ("million dollar idea")
Smart money leaves footprints on-chain. When 3 wallets with 70%+ historical win rates buy a token in its first hour, that's a signal no price chart shows yet. This is information asymmetry you can only get from on-chain data — and most retail traders can't parse Helius RPC responses. The edge: be the person who knows BEFORE the chart shows anything. Forward collector (H-18) is already running and collecting exactly this data.

## Data required
- `WalletScarper/data/stage2_foundation.sqlite3` — wallet_token_outcomes, wallet_metric_snapshots
- `finetune/data/forward_collector_state.jsonl` — H-18 forward collection state
- `finetune/pipeline/forward_collector.py` — active data collection script
- GeckoTerminal OHLCV for forward returns (already in DB: token_ohlcv)
- Helius API key (in WalletScarper/.env: HELIUS_API_KEY)

## Test method
1. Join `wallet_token_outcomes` with `token_ohlcv` on token address — get wallet behavior + realized return
2. Features per token-launch: distinct_early_buyers, overlap_with_scored_wallets, early_buy_sol_total, buyer_concentration (HHI), max_single_buyer_sol
3. Outcome: forward return at 24h (triple-barrier: +50% take, -30% stop, time=24h)
4. Temporal holdout: train on older launches, test on recent (H-18 forward collection)
5. Permutation null: compare high-overlap (scored wallets) vs random same-size token set

## Parameters
- Window: first 1h / first 3h / first 6h after launch
- Overlap threshold: ≥1, ≥2, ≥3 scored wallets present
- Scored wallet win-rate filter: >60%, >70%, >80%
- Horizon: 24h, 48h, 72h

## Results
```
Current forward_collector state:
- 60 pools discovered, 19 launches snapshotted
- Early buyers per token: 0-47
- Overlap with tracked/scored wallets: 0 (as of 2026-06-04)

[To be filled as more data accumulates]
```

## Verdict
[ ] PASS  [ ] FAIL  [ ] INCONCLUSIVE — PENDING DATA

## Refinement path
**If overlap is always zero (not enough tracked wallets):**
→ Expand wallet tracking: run WalletScarper discovery for 30 days
→ Alternative: use on-chain wallet age as proxy for "smart" (old wallet = experienced)

**If early buyer count predicts (without needing specific wallets):**
→ Simpler signal: tokens with many distinct early buyers in first hour
→ Combine with H-001 fix: enter on drawdown ONLY when early buyer signal is present
