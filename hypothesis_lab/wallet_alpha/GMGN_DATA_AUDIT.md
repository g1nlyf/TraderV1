# GMGN Data Audit (Sprint 9 cont., 2026-06-06) — PRIMARY source before Bitquery

Audited the GMGN integration (`WalletScarper/.../gmgn_enrichment.py` + `gmgn-cli`) and probed live. **Verdict:
GMGN is a usable PRIMARY point-in-time event source** via `gmgn-cli track`, superior to Bitquery/Corecast for
this program because it is pre-filtered to the smart-money population we study, timestamped per trade, keyed,
and live now (key configured in `hypothesis_lab/.env`). Corecast stays a FALLBACK raw-firehose path.

## What GMGN exposes (gmgn-cli, key present, live-probed)
| command | returns | usable as |
|---------|---------|-----------|
| `track smartmoney --raw` | **raw per-trade records** (tx_hash, maker, base_address, side, amounts, price, **timestamp**) | **POINT-IN-TIME EVENTS** (primary) |
| `track follow-wallet --raw` | same shape, for tracked wallets | point-in-time events (our wallet set) |
| `track kol --raw` | same shape, KOL trades | point-in-time events (KOL subset) |
| `token traders` | top traders of a token | discovery-only (selection lens) |
| `token holders / info / security / pool` | holders, price, security, LP | enrichment snapshot |
| `market` | market data | enrichment snapshot |
| `portfolio stats --period 7d` | trailing PnL/winrate/pnl-distribution | **FORBIDDEN as feature** (full-history aggregate) |

## Field classification (the `track smartmoney` record)
Live sample: `{transaction_hash, maker, base_amount, quote_amount, token_amount, buy_cost_usd, amount_usd,
price, price_usd, timestamp, side, is_open_or_close, base_address, balance, base_token{symbol,total_supply,
launchpad}, maker_info{tags,...}}`

| field | class | rationale |
|-------|-------|-----------|
| `timestamp` | **point-in-time** | unix event time of the trade — the as_of anchor |
| `transaction_hash` | point-in-time (dedup key) | unique per fill |
| `maker` | point-in-time (wallet id) | the acting wallet |
| `base_address` | point-in-time (token id) | the token |
| `side` | point-in-time | buy/sell at event time |
| `base_amount`/`quote_amount`/`token_amount` | point-in-time | sizes at event time |
| `price`/`price_usd`/`amount_usd` | point-in-time | execution price at event time |
| `is_open_or_close` | point-in-time | position open/close flag at event time |
| `base_token.{symbol,total_supply,launchpad}` | **enrichment-only snapshot** | metadata at fetch; store, don't use as predictive feature |
| `maker_info.tags` (`smart_degen`, `axiom`, …) | **enrichment-only snapshot** | GMGN's CURRENT classification = lookahead if applied to a past decision |
| feed membership ("this is a smart-money trade") | **discovery-only** | use to FIND wallets/tokens; not a per-decision feature (selection bias, not lookahead) |
| `portfolio stats` (realized_profit, winrate, pnl_distribution, token_num) | **FORBIDDEN lookahead** | trailing full-history aggregate = leaderboard class (same as wallet_scores) |

## Volume (live-probed) — the unblock
- One `smartmoney --limit 200` poll: **100 records, 95 new, 26 wallets, 27 tokens, 508s span** (~8.5 min of
  smart-money flow). ≈ **0.20 trades/s ≈ 17K smart-money trades/day** if looped — vs GeckoTerminal free ~0.5
  sell-clusters/day. est sell-clusters/day jumped 0.5 → 8.4 after 2 polls; continuous loop reaches the 100/day
  gate easily across the smart-money population (which is exactly the population H-162/H-171 study).
- Records are timestamped ~today (2026-06) = a **different calendar day** than the May-14 raw_trades →
  cross-day accumulation has started with the first poll.

## Provenance + storage
- All rows written to `_data/firehose.sqlite3` (same schema), `source="gmgn:smartmoney"`, full raw response in
  `raw_json` (tags + token meta preserved as enrichment), `ingested_at` set, dedup `UNIQUE(signature,token_mint,
  side,wallet)`. Resume-safe. `gmgn_adapter.py --selftest` proves map+dedup+schema (no network).

## Decision
- **GMGN smartmoney = PRIMARY collector** (`gmgn_adapter.py --loop`). High-signal, point-in-time, live.
- **follow-wallet/kol** = secondary point-in-time feeds (our wallet set + KOLs).
- **token holders/security/pool/info** = enrichment snapshots (store with fetched_at; never retroactive feature).
- **portfolio stats + tags + smart-money membership** = NOT predictive features (forbidden/enrichment/discovery).
- **Corecast** = fallback only (full raw firehose if we need beyond smart money). `corecast_adapter.py` stands by.
- Limitation: GMGN smartmoney is a CURATED feed (smart-money only) → great for wallet-quality studies, but for
  token-lifecycle base rates over ALL tokens we still want the broad firehose (Corecast) eventually. Documented.
