# Free Data Sources

This page describes what can run without paid data-source keys. It does not claim that every source currently closes Stage 3 gaps.

## Policy

- Prefer no-key sources first.
- Respect public rate limits; on HTTP 429, degrade and stop.
- Do not infer unsupported endpoint behavior.
- Browser extraction is degraded fallback only.
- If freshness, timestamp, latency, route quality, or fill comparison evidence is missing, produce a gap report.

## Source Table

| Source | Endpoint pattern in code | Key required | Rate-limit assumption | Data available | Data not available / not proven | Confidence tier | Degrade / stop rule | Current support |
|---|---|---:|---|---|---|---|---|---|
| DexScreener | `https://api.dexscreener.com/token-profiles/latest/v1`, `https://api.dexscreener.com/token-boosts/latest/v1`, `https://api.dexscreener.com/latest/dex/tokens/{addresses}` | No | Public API; exact quota not encoded in repo | Token/pair profile, price, liquidity, volume, tx counts | Source quote timestamp for calibration wrapper | Medium for discovery/profile; gap-limited for shadow | Degrade on 429, missing pair, missing price, missing timestamp | Legacy discovery adapter exists; live calibration wrapper uses this source |
| GeckoTerminal | `https://api.geckoterminal.com/api/v2/networks/solana/new_pools`, `/tokens/{token}/pools`, `/pools/{pool}/trades` | No | Public API with low practical limits; exact quota not encoded | New pools, pool trades, token pool price/liquidity snapshots | Source quote timestamp not present in the wired token-pools response | Medium when API responds; timestamp-limited for shadow | Degrade on 429/no payload; keep freshness gaps open when timestamp is absent | Legacy adapter exists; live calibration wrapper uses token-pools endpoint |
| DexPaprika | `https://api.dexpaprika.com/networks/solana/tokens/{token}/pools`, `/pools/{pool}` | No in current code | Public/free tier assumed reachable; exact quota not encoded | Pool list, pool detail price, `price_time`, reserve USD, short-window volume/tx stats | May show wide cross-source spread during volatile markets; public limits not encoded | Medium when API responds; best current no-key timestamp evidence | Degrade on 429/no payload; keep route/fill gaps open when evidence is insufficient | Legacy adapter exists; live calibration wrapper uses token-pools plus pool detail |
| Public Solana RPC | `SOLANA_PUBLIC_RPC_URL=https://api.mainnet-beta.solana.com` | No | Strict public RPC limits | Read-only `getHealth`, `getTransaction` | DEX quote, route, reliable high-volume indexing | Low for broad calibration, medium for targeted transaction inspection | Use sparingly; degrade on rate limit or missing transaction | Read-only adapter exists |
| Browser extraction | Stage 2 table support for `browser_extractions` | No key, but browser tooling may be required | Source/layout dependent | Context snapshots and degraded research evidence | Canonical price/P&L, high-confidence promotion evidence | Low/degraded | Stop on layout change, missing fields, or no raw artifact | Schema exists; no default live browser extractor wired |
| Bitquery CoreCast | `corecast.bitquery.io:443`, `https://streaming.bitquery.io/graphql` | Yes | Credentialed streaming source | Streamed DEX trade feed | No-key operation | Optional keyed | Disabled when token missing | Adapter exists but disabled by default |
| Helius RPC | `HELIUS_RPC_URL` | Yes if selected | Account quota dependent | Read-only Solana RPC with better limits | No-key default | Optional keyed | Do not require by default | Config field exists |

## Current Calibration Reality

`stage2-calibration-window` supports:

- `--source dexscreener`
- `--source geckoterminal`
- `--source dexpaprika`
- `--source all_free`

`all_free` currently attempts DexScreener, GeckoTerminal, and DexPaprika. It is observation-only and records quote, latency, source health, and route-quality evidence. Source failures degrade source health and are reported in command output.

DexScreener and GeckoTerminal still lack source quote timestamps in the wired responses. DexPaprika pool detail can provide `price_time`; that is used as timestamp evidence when present. Wide cross-source spread or shallow route depth still keeps route-quality gaps open.

When a real token is selected:

```bat
scripts\run-calibration-window.bat TOKEN_MINT [POOL_ADDRESS]
```

Expected result today is often `gap_report_required`, not `shadow_ready`.
