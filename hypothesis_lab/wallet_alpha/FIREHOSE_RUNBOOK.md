# FIREHOSE RUNBOOK — durable free wallet-trade collector

The engine of the persistence flywheel. Captures free, wallet-attributed Solana DEX trades day after day so
H-162 persistence becomes testable (the binding constraint per CANONICAL_STATE).

## What it is
`firehose_collector.py` polls GeckoTerminal's **free, keyless** endpoints:
- `GET /networks/solana/new_pools` + `/trending_pools` → candidate pools
- `GET /networks/solana/pools/{pool}/trades` → recent trades, each with `tx_from_address` (**wallet**),
  `tx_hash` (dedup), `block_timestamp`, `kind` (buy/sell), both leg amounts.

Stdlib only (urllib). No API key, no paid source, no new dependency.

## Where data goes
`hypothesis_lab/wallet_alpha/_data/firehose.sqlite3` (gitignored — machine-local, regrows by collecting).
- `firehose_trades`: signature, wallet, token_mint, pool_address, dex, side, base_amount, quote_amount,
  quote_mint, price_quote (=quote/base = SOL-per-token for SOL pools), price_usd, block_time, block_ts,
  source, ingested_at, raw_json. **UNIQUE(signature, token_mint, side, wallet)** → idempotent re-runs.
- `firehose_runs`: per-tick health (pools_polled, trades_seen, trades_new, http_ok/fail, rate_limited).

Point-in-time guarantee: `block_ts` is the on-chain event time; `ingested_at` is capture time. Builders
must filter `block_ts < event_t` (never `ingested_at`).

## Run
```
REM Windows
hypothesis_lab\wallet_alpha\run_firehose.bat dry     :: dry-run, no writes
hypothesis_lab\wallet_alpha\run_firehose.bat once    :: single tick
hypothesis_lab\wallet_alpha\run_firehose.bat         :: loop every 15 min

REM direct
py hypothesis_lab\wallet_alpha\firehose_collector.py --once --max-pools 40 --pages 2
py hypothesis_lab\wallet_alpha\firehose_collector.py --loop --interval 900 --max-pools 40 --pages 2
```

## Free-tier budget
GeckoTerminal free ≈ 30 req/min. Each tick ≈ (2×pages) list calls + max_pools trade calls, paced at 2.2s.
Default (pages=2, max_pools=40) ≈ 44 calls/tick ≈ ~100s wall, well under limits with backoff. 429s are
caught and backed off; a tick that hits limits just collects fewer pools (no corruption).

## Smoke / verification
```
py hypothesis_lab\wallet_alpha\test_firehose_smoke.py     :: parse + dedup (no network) — must print ALL PASS
py hypothesis_lab\wallet_alpha\firehose_collector.py --dry-run --max-pools 3   :: live fetch, no writes
```
Verified 2026-06-06: dry-run parsed 286 trades/3 pools clean; live tick wrote 392 trades / 34 wallets;
backoff handled 3 rate-limits without data loss; smoke ALL PASS.

## Scheduling for real persistence (the actual goal)
Run the loop continuously, OR a Windows Task Scheduler job every 15 min calling `run_firehose.bat once`.
**Collection target: ≥ 14 distinct calendar days** (≥30 ideal) before H-163 multi-day persistence can
separate cross-sectional skill from regime. Track progress: `firehose_runs` row count + `block_ts` span.

```sql
-- progress check
SELECT COUNT(*) trades, COUNT(DISTINCT wallet) wallets, COUNT(DISTINCT token_mint) tokens,
       (MAX(block_ts)-MIN(block_ts))/86400.0 span_days FROM firehose_trades;
SELECT date(block_ts,'unixepoch') d, COUNT(*) FROM firehose_trades GROUP BY d ORDER BY d;
```

## Integration with the dataset builder
`build_events.py` reads raw_trades (May-14 history). Once `firehose.sqlite3` has ≥1 new day, point its
loader at the union (raw_trades ∪ firehose_trades) to build multi-day datasets. Schema is aligned
(token_mint, wallet, side, quote/base amounts, block_ts) so the union is a straight concat.

## Future optional (NOT current — paid)
Bitquery Corecast gRPC stream (`WalletScarper/walletscarper/sources/bitquery_corecast.py`) is a far higher
-throughput firehose and is already wired; the Ory token is configured. If/when a heavier capture is wanted
and the token's free quota allows, run that streamer into the same `firehose_trades` schema. Helius free
tier (`sources/helius_das.py`) can backfill per-wallet tapes. Both are free-tier; document quota before relying.
