# Current System Reality Audit

Generated for the Operational Launch, Hermes Runtime and Design Sprint.

## Summary

Stage 2 is launchable for local paper-mode inspection and fixture acceptance. It is not Stage 3 shadow-ready. The repo now has a local read-only dashboard, Windows launch scripts, Hermes checkout/config, and calibration wrappers. Real observation-only calibration still requires a selected live token/pool and enough public-source evidence to close shadow gaps.

## Truth Table

| Module | Status | Evidence | Operator truth |
|---|---|---|---|
| Stage 2 database/migrations | Exists and works | `WalletScarper/walletscarper/stage2/db/database.py`, migrations 1-8 in `migrations.py` | SQLite custom migrations, not Alembic. Append-only triggers exist for critical tables. |
| config/env loading | Exists and works | `WalletScarper/walletscarper/config.py`, `WalletScarper/walletscarper/stage2/config/settings.py`, `.env.example` | Stage 2 uses `STAGE2_` env prefix. OpenRouter/Hermes fields are documented; real keys stay in local `.env`. |
| source registry | Exists and works | `walletscarper/stage2/sources/repository.py` | Registry records source metadata and health. Defaults include DexScreener, GeckoTerminal, DexPaprika, Bitquery CoreCast, Solana RPC, Stage 2 quote observer. |
| quote observation | Exists and works | `QuoteObservationService` | Persists observation-only raw event, market snapshot, quote row and latency row. No trading artifacts are created. |
| latency tracking | Exists and works | `source_latency_samples`, operational health summary | Captures event lag, response latency, total latency. Real distribution is missing until live observation runs. |
| route-quality evidence | Exists and works | `RouteQualityService`, `route_quality_evidence` | Append-only evidence exists. A real sufficient route-quality model is still not proven. |
| fill-vs-quote comparison | Exists and works | `FillQuoteComparisonService`, tests | Comparisons do not rewrite fills or outcomes. Real passed comparisons are missing in the current validation baseline. |
| calibration run | Exists and wired for multiple no-key sources | `stage2-calibration-smoke`, `stage2-calibration-window` | Smoke uses a temp fixture DB. Live window wrapper supports DexScreener, GeckoTerminal, DexPaprika, and `all_free`; it fails closed when evidence is insufficient. |
| final acceptance | Exists and works | `stage2-final-acceptance --run-mode fixture_replay` | Fixture acceptance returns `accepted_with_gaps` when shadow evidence is missing. This is not a profitability claim. |
| dashboard/reporting | Exists and wired | `walletscarper/web/app.py`, `scripts/run-dashboard.bat` | Local read-only dashboard at `http://127.0.0.1:8787` shows Stage 2 and shadow status. |
| Hermes runtime | Exists and configured locally | `external/hermes-agent`, `~/.hermes/config.yaml` | Hermes v0.13.0 is installed in a local venv. Use `scripts/run-hermes.bat` so OpenRouter env is loaded. |
| Hermes model configuration | Exists and configured | `~/.hermes/config.yaml`, `WalletScarper/.env` | Provider: OpenRouter. Model: `openai/gpt-oss-20b:free`. Direct OpenRouter smoke passed; Hermes one-shot passed when env was loaded. |
| Hermes tool integration | Exists and wired into launch flow | `stage2/hermes_integration/tools.py`, `.hermes/plugins/traderv1_operator`, `scripts/run-hermes.bat` | Hermes can call read-only project tools for health and deterministic reports through the `traderv1_operator` toolset. No MCP server packaging yet. |
| Windows launch scripts | Exists and wired | `scripts/*.bat` | Scripts use `.venv`, fail clearly, do not print secrets, and do not enable live execution. |
| online/local web interface | Exists and wired | FastAPI app | Local only by default via `WEB_HOST=127.0.0.1`. No online hosted dashboard exists. |
| free data source adapters | Exists and partially Stage 2 quote-wired | `sources/dexscreener.py`, `geckoterminal.py`, `dexpaprika.py`, `solana_rpc.py`, `stage2-calibration-window` | Legacy adapters exist. The live calibration wrapper now writes quote evidence from DexScreener, GeckoTerminal, and DexPaprika; public Solana RPC remains read-only fallback only. |
| paid/optional data source adapters | Exists but credentials required | Bitquery, OpenRouter, optional Helius RPC | Bitquery requires token. OpenRouter requires key but can use free models. Helius requires key only if selected. |
| dangerous live execution paths | Not present | invariant scan and code review | No private key manager, signer, swap adapter, DEX transaction builder, or real order placement path was added. Legacy code has read-only transaction terminology. |

## Current Blockers

- No passed real Stage 2-owned live data acceptance window.
- DexScreener and GeckoTerminal wired responses still do not provide source quote timestamps.
- DexPaprika can provide `price_time`, but wide cross-source spread or shallow route depth can still block route-quality sufficiency.
- Fill-vs-quote comparisons need real paper fill context plus contemporaneous quote evidence.
- Hermes project tools are local plugin tools, not a packaged MCP server.
- Stage 3 remains `gap_report_required`.
