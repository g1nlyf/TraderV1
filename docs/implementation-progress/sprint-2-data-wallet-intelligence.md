# Sprint 2 - Data, Token Discovery And Wallet Intelligence

## Status

Sprint 2 is implemented and validated. It remains an evidence layer, not a trading layer.

The implementation covers the Sprint 2 almanac scope: source registry, source health/degradation, ingestion runs, source-linked raw event normalization, browser extraction records, token candidates, token profiles, configurable token triage decisions, reconstructed wallet trades, historical wallet metrics marked as candidate evidence only, wallet profiles, wallet clusters, and evidence-quality propagation.

At the time Sprint 2 was completed, Sprint 3 had not started. Current Sprint 3 status is tracked separately in `sprint-3-signal-risk-paper.md`. Sprint 2 itself does not create `Signal`, `TradeThesis`, authoritative `RiskCheck`, `PaperOrder`, `PaperFill`, `PaperPosition`, `TradeOutcome`, strategy metrics, live execution paths, private-key handling, signing, swap adapters, or DEX transaction execution.

The first Sprint 2 slice created a Stage 2 raw ingestion boundary for already-obtained legacy/source payloads. It did not call live legacy adapters, mutate legacy tables, create Stage 2 signals, run risk checks, create paper orders, create fills, calculate P&L, rank tokens, or score wallets.

Step 2 created normalized evidence records from Stage 2 `RawSourceEvent` rows. Later Sprint 2 completion work added the remaining token/wallet evidence layer. These records are source evidence only; they are not trade signals, risk approvals, paper ledger entries, strategy metrics, or performance proof.

## Sprint 2 Completion Implementation

### Implemented

- Source health automation helper for success, stale-data degradation, failures, rate-limit/error metadata, last successful event time, and downstream quality flags.
- Browser extraction records with success/failure status, URL, parser/version, extraction timestamp, raw/screenshot/snapshot refs, extracted fields, confidence score, degradation reason, quality flags, and fail-closed behavior.
- `TokenProfile` derivation from `TokenCandidate`, `MarketSnapshot`, and source-linked evidence refs.
- Token discovery pipeline over unprocessed Stage 2 `RawSourceEvent` rows.
- Configurable/versioned token triage priors and append-only triage decisions.
- `WalletTrade` reconstruction from observed, timestamped, source-linked raw events.
- Historical wallet metrics from reconstructed `WalletTrade` rows only, marked candidate evidence only.
- `WalletProfile` creation from wallet metric snapshots with non-permanent labels and evidence-quality/degradation fields.
- `WalletCluster` evidence records with relation type, wallets, token, source refs, confidence, and flags.
- Evidence-quality propagation from degraded/unavailable/stale sources, missing timestamps, missing prices, incomplete wallet trade fields, weak Bitquery timestamp provenance, and browser-only records.

### Additional Files Created Or Modified For Completion

- `WalletScarper/walletscarper/stage2/browser/**`
- `WalletScarper/walletscarper/stage2/token_intelligence/**`
- `WalletScarper/walletscarper/stage2/wallet_intelligence/**`
- `WalletScarper/walletscarper/stage2/sources/health.py`
- `WalletScarper/walletscarper/stage2/sources/repository.py`
- `WalletScarper/walletscarper/stage2/sources/__init__.py`
- `WalletScarper/walletscarper/stage2/evidence/normalizer.py`
- `WalletScarper/walletscarper/stage2/db/migrations.py`
- `WalletScarper/tests/test_stage2_sprint2_completion.py`

### Additional Tables Added For Completion

- `browser_extractions`
- `token_profiles`
- `token_triage_configs`
- `token_triage_decisions`
- `wallet_trades`
- `wallet_metric_snapshots`
- `wallet_profiles`
- `wallet_clusters`

These evidence tables are append-only. `data_sources` remains an upsertable registry record and `ingestion_runs` remains updateable for operational run completion.

### How The Completed Sprint 2 Pieces Work

`SourceHealthService` appends source-health snapshots and updates the source registry status. Stale successes become degraded rather than normal healthy evidence. Failures create degraded or unavailable source state. `EvidenceNormalizer` reads latest source health and adds downstream quality flags such as `source_degraded`, `source_unavailable`, and `stale_source_data`.

`BrowserExtractionRepository` records browser extractions as non-canonical research artifacts. Failures write empty extracted fields, `parser_failed`, and a degradation reason. Browser records are never high-confidence evaluation evidence.

`TokenIntelligenceService` can scan unprocessed raw source events, normalize them, create token profiles, create a versioned triage config, and create triage decisions. Triage decisions use configurable bucket priors and are evidence classifications only.

`WalletIntelligenceService` reconstructs wallet trades only from observed raw event payloads and linked market snapshots. Missing wallet, side, amount, price, or timestamp quality lowers confidence. Historical metric snapshots are deterministic estimates from reconstructed trades only and are marked `candidate_evidence_only=1`. Wallet profiles and clusters are evidence records, not strategy proof.

### Sprint 2 Acceptance Criteria Satisfied

- Source registry exists and is usable.
- Source health/degradation automation exists.
- Ingestion runs are tracked.
- `RawSourceEvent` normalization remains source-linked and confidence-aware.
- Browser extraction records exist and fail closed.
- `TokenCandidate` exists and is populated from evidence.
- `TokenProfile` exists and is derived from timestamped source-linked evidence.
- Token triage exists with configurable bucket priors.
- Wallet trades are reconstructed from observed data.
- `WalletProfile` exists.
- `WalletCluster` exists.
- Historical wallet metrics are computed only as candidate evidence.
- Token and wallet evidence carries confidence, provenance/source refs, and quality flags.
- Browser-derived data remains non-canonical.
- Legacy `paper_trades`, legacy FIFO PnL, and legacy wallet scores remain excluded from Stage 2 truth.
- Tests validate stale data, browser failure, confidence degradation, token profile derivation, triage, wallet reconstruction, wallet metrics, wallet profiles, clusters, and non-creation of trading records.
- No trading decisions or paper ledger records are created by Sprint 2 pipelines.
- No live execution, private-key, signer, swap adapter, or DEX transaction path was added.

### Sprint 2 Acceptance Criteria Not Satisfied

No Sprint 2 almanac acceptance criteria remain intentionally open in the implemented Stage 2 evidence layer.

Important limitation: Sprint 2 uses restored legacy collectors and Stage 2 raw-event mapping boundaries as source input. Stage 2 does not yet own live network collection jobs that call external APIs directly. This is acceptable for the current architecture boundary because legacy collectors remain non-authoritative and Stage 2 source-of-truth starts at `RawSourceEvent`.

### Intentionally Deferred To Sprint 3 Or Later

- Signal generation.
- Strategy logic.
- Risk decisions beyond Sprint 1 guard boundaries.
- Paper order workflow beyond Sprint 1 guard skeleton.
- Paper fills, positions, exits, canonical P&L, and strategy metrics.
- Strategy promotion/demotion/kill decisions.
- Treating wallet historical profitability as strategy success.
- Live/shadow execution behavior.
- Private key handling, signing, swap adapters, or DEX transaction construction.

### Sprint 2 Final Validation

Validation run on 2026-05-14:

- `.\.venv\Scripts\python.exe -m pytest`: passed, 32 tests.
- `.\.venv\Scripts\python.exe -m compileall walletscarper`: passed.
- `.\.venv\Scripts\python.exe -m walletscarper stage2-migrate`: passed and applied migrations 1-3 to `data\stage2_foundation.sqlite3`.
- `.\.venv\Scripts\python.exe -m walletscarper project-health-check`: passed on rerun after migration completion; `database_connectivity: ok`, `migration_status: current`, applied migrations 1-3.
- Dangerous-term `rg` scan: completed. Matches are documentation prohibitions, read-only market-data naming, or read-only parsed RPC metadata. No dangerous live execution path was found.

## Implemented In Step 1

- Added `walletscarper.stage2.legacy_ingestion`.
- Added `RawSourceEventDraft`, a mapper-side draft model for raw source event ingestion.
- Added pure mapping functions for DexScreener, GeckoTerminal, DexPaprika, Bitquery CoreCast `RawTrade`, and read-only Solana RPC transaction payloads.
- Added `write_raw_source_event()`, which appends through the existing Stage 2 `RawSourceEventLog`.
- Stored provenance, extraction method, adapter name, and quality flags inside `raw_source_events.quality_metadata_json`.
- Preserved raw payloads in `raw_source_events.payload_json`.
- Added timestamp parsing for visible source fields only.
- Added `missing_observed_at` quality flag when no source timestamp is present.
- Added tests proving ingestion writes only raw source events and does not create Stage 2 trading ledger records.

## Files Created Or Modified

- `WalletScarper/walletscarper/stage2/legacy_ingestion/__init__.py`
- `WalletScarper/walletscarper/stage2/legacy_ingestion/models.py`
- `WalletScarper/walletscarper/stage2/legacy_ingestion/mappers.py`
- `WalletScarper/walletscarper/stage2/legacy_ingestion/writer.py`
- `WalletScarper/tests/test_stage2_legacy_ingestion.py`
- `WalletScarper/walletscarper/stage2/sources/__init__.py`
- `WalletScarper/walletscarper/stage2/sources/models.py`
- `WalletScarper/walletscarper/stage2/sources/repository.py`
- `WalletScarper/walletscarper/stage2/evidence/__init__.py`
- `WalletScarper/walletscarper/stage2/evidence/models.py`
- `WalletScarper/walletscarper/stage2/evidence/normalizer.py`
- `WalletScarper/tests/test_stage2_source_evidence.py`
- `WalletScarper/tests/test_stage2_foundation.py`
- `WalletScarper/walletscarper/stage2/db/migrations.py`
- `docs/implementation-progress/README.md`
- `docs/implementation-progress/sprint-2-data-wallet-intelligence.md`

## How The Ingestion Boundary Works

The new mappers accept raw dict payloads or legacy objects with a `raw` dict. They do not instantiate legacy adapters, perform network calls, write to the legacy SQLite database, or call legacy paper-trade, signal, score, FIFO, or dashboard modules.

Each mapper returns `RawSourceEventDraft` with:

- `source_name`;
- `source_type`;
- `external_id`, if visible;
- `observed_at`, if a visible source timestamp can be parsed;
- original `payload`;
- `provenance`;
- `confidence`;
- `extraction_method`;
- `quality_flags`;
- `raw_adapter_name`.

`write_raw_source_event()` calls `RawSourceEventLog.append()`. The existing Stage 2 source log sets `ingested_at` and writes the append-only `raw_source_events` row. If `observed_at` is missing, the source log stores ingestion time as the row timestamp while the metadata flags `missing_observed_at`; no mapper invents source timestamp precision.

## RawSourceEvent Mapping Fields

| Source | `source_name` | `source_type` | External ID Policy | Timestamp Fields Checked | Default Confidence |
|---|---|---|---|---|---|
| DexScreener | `dexscreener` | `market_profile` | `pairAddress`, `url`, `baseToken.address`, `tokenAddress` | `pairCreatedAt`, `pair_created_at`, `created_at` | `medium` unless supplied |
| GeckoTerminal | `geckoterminal` | `market_pool` | `id`, `attributes.address`, `attributes.tx_hash`, `attributes.txHash` | `attributes.pool_created_at`, `attributes.block_timestamp`, `attributes.timestamp`, `attributes.created_at`, top-level fallbacks | `medium` unless supplied |
| DexPaprika | `dexpaprika` | `pool_transaction` | `tx_hash`, `txHash`, `transaction_hash`, `signature`, `hash`, `id` | `block_time`, `timestamp`, `created_at`, including `attributes.*` | `medium` unless supplied |
| Bitquery CoreCast | `bitquery_corecast` | `corecast_trade` | `RawTrade.signature` or raw `signature` | `block_time`, `timestamp`, `created_at` | legacy `RawTrade.confidence` or `medium` |
| Solana RPC | `solana_rpc` | `rpc_transaction` | mapper `signature` argument | `blockTime`, `block_time`, `timestamp`, `created_at` | `medium` unless supplied |

## Legacy Source Adapter Audit

| Adapter | Input | Output | Endpoint Or Source Type | Timestamp Fields | Payload Shape | Confidence / Provenance Gaps | Rate Limit / Error Handling | Execution Classification |
|---|---|---|---|---|---|---|---|---|
| `DexScreenerSource` | No direct input to `discover()`; uses discovered token addresses from profiles and boosts | `TokenCandidate` with raw pair payload | Read-only HTTP: token profiles, token boosts, latest DEX token pairs | `pairCreatedAt` in milliseconds, mapped to `pair_created_at` | Pair dict with base/quote token, pair address, txns, volume, liquidity, price, FDV, market cap | Confidence hardcoded to `medium`; endpoint provenance not stored in legacy candidate except `source` and raw payload | Uses shared `HttpClient` cache/TTL; no source-specific structured degradation in the candidate | Read-only market/profile discovery |
| `GeckoTerminalSource` | Page count for discovery; pool address for trade lookup | `TokenCandidate` for new pools or raw trade dicts for pool trades | Read-only HTTP: Solana new pools and pool trades | `attributes.pool_created_at`; trade payloads may expose `block_timestamp`, `timestamp`, or `created_at` depending response | JSON:API-style dict with `id`, `attributes`, `relationships` | Confidence hardcoded to `medium`; rate-limit state not attached to candidate/trade payload | Uses shared `HttpClient` cache/TTL; no typed source health record on output | Read-only market/pool/trade data |
| `DexPaprikaSource` | Pool address and limit | Raw transaction dicts | Read-only HTTP: pool transactions endpoint, fallback pool swaps endpoint | Not normalized in source; downstream legacy code checks `block_time`, `timestamp`, `created_at` | List payload or dict containing `transactions`, `data`, or `swaps` | No explicit confidence/provenance in returned dicts | Uses shared `HttpClient` cache/TTL; returns empty list on missing supported payload keys | Read-only pool transaction data; `swaps` is market-data endpoint naming |
| `BitqueryCoreCastSource` | Stream duration and optional program address filters | Legacy `RawTrade`; legacy store writes `raw_trades`, `pool_transactions`, source health, ingestion runs | Read-only gRPC CoreCast DEX trade stream | Legacy `RawTrade.block_time` is set with local `utc_now()` in current code, not a proven chain timestamp | `RawTrade.raw` includes signature, slot, source, quote mint | Confidence hardcoded to `medium`; raw payload is partial; block time provenance is weak | Handles missing config/imports; catches gRPC errors; stores legacy source health | Read-only DEX trade stream; writes legacy collector tables when stream is called, but Stage 2 mappers do not call it |
| `SolanaRpcSource` | RPC method/params; signature for transaction lookup | Health boolean or parsed tuple of account metadata and block time | Read-only JSON-RPC: `getHealth`, `getTransaction` | `blockTime` from RPC result | Parsed transaction result; legacy method returns tuple, not full typed record | Parsed account `signer` flag has no confidence/provenance annotation | Uses shared `HttpClient`; returns empty tuple fields if result is not dict | Read-only RPC parsing. `signer` is transaction account metadata, not signing behavior |

## Legacy Paper Trades Audit

Legacy `paper_trades` are defined in `WalletScarper/walletscarper/db.py` and created by `LiveMonitor._paper_entry()` in `WalletScarper/walletscarper/services/live_monitor.py`.

Flow observed:

1. `LiveMonitor._scan_wallet()` reads recent `pool_transactions` for tracked wallets.
2. If a new buy is detected after `last_seen_signature`, `_log_signal()` inserts a legacy `signal_log` row.
3. `_paper_entry()` inserts into legacy `paper_trades` with `signal_id`, wallet, token mint, created time, simulated entry time, slippage bps, fee bps, exit strategy, and status.

Classification:

- Legacy `paper_trades` do not contain Stage 2 `TradeThesis`.
- They do not require deterministic Stage 2 `RiskCheck`.
- They do not create Stage 2 `PaperOrder` or `PaperFill`.
- They do not require pre-result Stage 2 `ExitDecision`.
- They do not create Stage 2 `TradeOutcome`.
- They store slippage/fee assumptions but do not model Stage 2 fees, slippage, latency, failed fills, and fills as immutable source-of-truth ledger records.
- They are linked to legacy `signal_log`, not Stage 2 `signals`.
- Legacy FIFO P&L exists in `ScoringService` over `pool_transactions` and writes `wallet_token_pnl` / `wallet_scores`; it is not Stage 2 evaluation truth.

Result: legacy `paper_trades`, FIFO P&L, and wallet scores are classified as legacy evidence only. They are not migrated into Stage 2 paper ledger tables in this step.

## Dangerous-Term Scan

Command run:

```powershell
rg -n -i "private_key|secret_key|seed phrase|signer|signTransaction|sendTransaction|VersionedTransaction|\bswap\b|\bswaps\b|jupiter|raydium|dex transaction|live trade|execute trade|order placement" WalletScarper\walletscarper docs\implementation-progress docs\implementation-almanac docs\research docs\architecture -g "*.py" -g "*.md"
```

| Finding Area | Terms | Classification | Notes |
|---|---|---|---|
| `docs/implementation-almanac/**`, `docs/architecture/**`, `docs/implementation-progress/sprint-1-foundation.md` | signer, swap, DEX transaction, private-key references | Harmless config/doc reference | These are architecture prohibitions and acceptance checklist items. |
| `WalletScarper/walletscarper/sources/dexpaprika.py` | `swaps` | Read-only market-data terminology | Used for the DexPaprika pool swaps endpoint and response key. No transaction execution. |
| `WalletScarper/walletscarper/services/backfill.py` | `swaps` | Historical/legacy naming only | Refers to normalized observed trades returned by transaction collection. |
| `WalletScarper/walletscarper/services/transactions.py` | `swap`, `swaps`, `store_swap`, `signer` | Read-only market-data terminology / read-only RPC parsed metadata | Normalizes observed pool transactions. `signer` is returned by read-only RPC transaction parsing. |
| `WalletScarper/walletscarper/sources/solana_rpc.py` | `signer` | Read-only RPC parsed metadata | Reads account-key `signer` flag from `getTransaction`; no signing operation. |
| `WalletScarper/walletscarper/services/scoring.py` | `swaps` | Historical/legacy naming only | Variable name for observed trade rows used in FIFO scoring. |
| Codebase scan | `private_key`, `secret_key`, `seed phrase`, `signTransaction`, `sendTransaction`, `VersionedTransaction`, `jupiter`, `raydium`, `live trade`, `execute trade`, `order placement` | No code matches in scanned paths | No dangerous live execution path was found by the scan. |

No secrets or environment values were printed or copied into this documentation.

## Tests Added

- `test_legacy_mappers_append_raw_source_events`
- `test_writer_preserves_payload_and_quality_metadata`
- `test_missing_observed_timestamp_adds_quality_flag`
- `test_solana_block_time_maps_to_utc_observed_timestamp`
- `test_legacy_ingestion_does_not_create_stage2_trading_records`
- `test_legacy_ingestion_code_contains_no_live_execution_path`

The tests verify that raw payloads are preserved, metadata is stored in `quality_metadata_json`, missing source timestamps are flagged, Solana `blockTime` is converted to UTC, and Stage 2 trading source-of-truth tables are not touched by ingestion.

## Acceptance Criteria Satisfied

- Legacy source adapters were audited at the module level.
- Legacy `paper_trades` were audited and classified as non-Stage-2 ledger records.
- Dangerous terminology scan was run and classified.
- Stage 2 source ingestion boundary exists.
- Safe legacy/source payloads can be converted into `RawSourceEvent`.
- Raw payload, provenance, confidence, and timestamps are preserved or flagged.
- Tests prove the adapter writes raw source events without creating signals, risk checks, paper orders, fills, positions, or outcomes.
- Execution documentation records what is done and not done.
- No live execution, private-key, signer, swap adapter, DEX transaction, or order placement path was added.

## Historical Step 1 Carry-Forward Items

- Full Sprint 2 token discovery and wallet intelligence: completed later in Sprint 2.
- Source health/degradation records for Stage 2 `DataSource`: completed later in Sprint 2.
- `MarketSnapshot`, `TokenProfile`, `WalletProfile`, `WalletTrade`, `WalletCluster`, and `BrowserExtraction`: completed later in Sprint 2.
- Legacy adapters are not yet wrapped as Stage 2 jobs or durable ingestion tasks.
- Bitquery CoreCast mapper preserves the legacy raw payload, but the current legacy raw payload is partial and its `block_time` may be ingestion time.
- Legacy Solana RPC parser returns a tuple in one path; this step maps full read-only RPC payload dicts when already obtained.

## Intentionally Not Implemented In Step 1

- Wallet intelligence scoring.
- Token discovery ranking.
- Signal generation.
- Risk logic beyond Sprint 1 boundaries.
- Paper fills, positions, exits, or P&L.
- Legacy `paper_trades` migration into Stage 2.
- Legacy FIFO P&L as Stage 2 evaluation.
- Dashboard or Telegram changes.
- Browser automation.
- Live trading, private key handling, signing, swap adapters, DEX transaction construction, or order placement.

## Assumptions

- Step 1 should map already-obtained payloads first, not call live legacy adapters, because this gate is about safe source-boundary conversion.
- Existing `raw_source_events.quality_metadata_json` is sufficient for provenance, extraction method, adapter name, and quality flags; no migration was needed.
- Legacy objects with a `raw` dict can be mapped by preserving that `raw` dict as the source payload.
- If a source timestamp is absent, Stage 2 records the ingestion timestamp via `RawSourceEventLog` and flags `missing_observed_at`.

## Remaining Unaudited Or Risky Items

- End-to-end legacy dashboard/API flows were not audited beyond identifying that they are outside this boundary.
- Telegram UX and notification behavior were not audited for Stage 2 integration.
- Legacy OpenRouter/reporting behavior was not audited in this step.
- Source rate-limit and degradation behavior should be turned into Stage 2 source-health records in a later Sprint 2 step.
- Legacy Bitquery CoreCast raw payload completeness should be improved before it becomes a high-confidence evidence source.

## Step 1 Validation

Validation was run on 2026-05-14:

- `.\.venv\Scripts\python.exe -m pytest`: passed, 16 tests.
- `.\.venv\Scripts\python.exe -m compileall walletscarper`: passed.
- Dangerous-term `rg` scan: run during audit; classifications recorded above. Matches were documentation prohibitions, read-only market-data naming, or read-only parsed RPC metadata. No dangerous live execution path was found.

## Step 1 Carry Forward Status

- Stage 2 source registry/source health records: initial implementation completed in Step 2.
- Raw event normalization into token candidates and market snapshots with explicit source refs: initial implementation completed in Step 2.
- Keep legacy wallet scores and paper trades as evidence only until Stage 2 risk-gated workflows exist.
- Preserve the rule that no wallet intelligence result is strategy proof without forward paper-trading evaluation.

## Step 2 - Source Registry, Source Health, And Token/Market Evidence Normalization

### Implemented In Step 2

- Added migration `stage2_source_registry_and_evidence_schema`.
- Added `data_sources`.
- Added `source_health_snapshots`.
- Added `ingestion_runs`.
- Added `token_candidates`.
- Added `market_snapshots`.
- Added `normalized_evidence_refs`.
- Added `walletscarper.stage2.sources` models and repository.
- Added `walletscarper.stage2.evidence` models and normalizer.
- Added normalization from Stage 2 `RawSourceEvent` rows into token and market evidence where visible fields allow it.
- Added source defaults for DexScreener, GeckoTerminal, DexPaprika, Bitquery CoreCast, and Solana RPC.
- Added high-confidence eligibility guards so low-confidence, browser, missing-field, or weak-timestamp records are not marked eligible for high-confidence evaluation.
- Added tests for registry, health snapshots, ingestion runs, normalization, quality flags, weak Bitquery timestamp provenance, and non-creation of trading records.

### Tables Added

| Table | Purpose | Mutability |
|---|---|---|
| `data_sources` | Registry of known Stage 2 data sources, adapter names, interface kind, reliability tier, evaluation eligibility, status, notes, and metadata | Upsertable registry record |
| `source_health_snapshots` | Point-in-time source health/degradation observations | Append-only trigger |
| `ingestion_runs` | Durable ingestion run accounting for events seen, written, rejected, quality summary, and errors | Mutable run status/count record |
| `token_candidates` | Normalized evidence that a token/pool candidate was observed | Append-only trigger |
| `market_snapshots` | Normalized market/trade evidence linked to a raw source event | Append-only trigger |
| `normalized_evidence_refs` | Link table from normalized records back to `RawSourceEvent` | Append-only trigger |

### Source Registry Defaults

| Source | Interface Kind | Reliability Tier | High-Confidence Evaluation Eligible By Source | Notes |
|---|---|---|---|---|
| DexScreener | `api` | `structured_api` | Yes, only if record quality allows | Legacy-mapped structured HTTP market/profile payloads |
| GeckoTerminal | `api` | `structured_api` | Yes, only if record quality allows | Legacy-mapped structured HTTP pool/trade payloads |
| DexPaprika | `api` | `structured_api` | Yes, only if record quality allows | Legacy-mapped structured HTTP pool transaction payloads |
| Bitquery CoreCast | `stream` | `degraded_timestamp_provenance` | No | Current legacy `RawTrade.block_time` may be local ingestion time |
| Solana RPC | `rpc` | `structured_rpc` | Yes by source, but current Step 2 maps it as transaction evidence only | Read-only `getTransaction` payloads |

### Normalization Behavior By Source

| Source | Normalized Output | Fields Used | Raw-Only / Caveats |
|---|---|---|---|
| DexScreener | `TokenCandidate` and `MarketSnapshot` | `baseToken.address`, `baseToken.symbol`, `baseToken.name`, `pairAddress`, `chainId`, `priceUsd`, `liquidity.usd`, `volume`, `marketCap`, `fdv`, `txns` | Missing token, pool, price, chain, or timestamp produce quality flags |
| GeckoTerminal | `TokenCandidate` and `MarketSnapshot` | JSON:API `id`, `attributes`, `relationships.base_token`, price, reserve, volume, txns, FDV, market cap | Chain is parsed only when visible in the payload id or attributes |
| DexPaprika | `MarketSnapshot` evidence only | transaction/pool fields such as token, pool, price, volume if visible | Often transaction-shaped; missing token/pool/price remains flagged |
| Bitquery CoreCast | `MarketSnapshot` trade evidence only plus degraded source health snapshot | raw `token_mint`, `pool_address`, `price_usd` when present | Always flags `weak_timestamp_provenance`; not high-confidence evaluation evidence |
| Solana RPC | `normalized_evidence_refs` transaction evidence only | raw event ref, slot/signature metadata if visible | Does not create token or market records unless a later parser safely extracts them |

### Quality Flags And Timestamp Provenance

Step 2 preserves Step 1 raw event quality flags and adds normalization flags:

- `missing_observed_at`;
- `invalid_observed_at`;
- `missing_token_mint`;
- `missing_pool_address`;
- `missing_price_usd`;
- `missing_chain`;
- `low_source_confidence`;
- `legacy_bitquery_block_time_may_be_ingested_at`;
- `weak_timestamp_provenance`;
- `unsupported_source_for_normalization`.

Records are not eligible for high-confidence evaluation when the source is disallowed, the source is browser-only, confidence is below medium, or disqualifying quality flags are present. This eligibility flag is not a trading signal and does not prove strategy performance.

### Acceptance Criteria Satisfied In Step 2

- Stage 2 `DataSource` registry exists.
- `SourceHealthSnapshot` exists.
- `IngestionRun` exists.
- `TokenCandidate` evidence model exists.
- `MarketSnapshot` evidence model exists.
- Normalized evidence links back to `RawSourceEvent`.
- Normalization preserves source confidence and quality flags.
- Missing fields are flagged, not invented.
- Weak Bitquery timestamp provenance is flagged and records a degraded health snapshot.
- Normalization does not create signals, trade theses, risk checks, paper orders, paper fills, paper positions, or trade outcomes.
- Low-confidence or weak records are not marked as high-confidence evaluation evidence.
- Existing Sprint 1 and Sprint 2 Step 1 tests still pass.

### Historical Step 2 Carry-Forward Status

- Full token discovery pipeline from Stage 2 raw events: completed later in Sprint 2.
- Token triage as evidence classification: completed later in Sprint 2. Triage as strategy input remains deferred to Sprint 3+.
- Wallet profile, wallet trade reconstruction, wallet cluster, and wallet evidence scoring: completed later in Sprint 2 as candidate evidence only.
- Historical wallet metrics as Stage 2 truth: intentionally not implemented. Historical wallet metrics are candidate evidence only.
- Source-health automation from real adapter failures: helper service completed later in Sprint 2; direct live adapter integration remains outside Stage 2 source-of-truth.
- Browser extraction records: completed later in Sprint 2.
- Paper trading behavior, fills, P&L, strategy metrics, or strategy promotion: intentionally deferred.
- Legacy `paper_trades`, FIFO PnL, or wallet score migration: intentionally excluded.

### What Remains Raw-Only

- Solana RPC transaction payloads are linked as transaction evidence only.
- Bitquery CoreCast raw payloads remain weak unless the legacy raw payload carries complete token, pool, price, and chain timestamp provenance.
- Legacy dashboard, Telegram, OpenRouter/reporting, wallet scores, and paper-trade behavior remain outside Stage 2 source-of-truth.

### Step 2 Assumptions

- Existing `raw_source_events` is the only acceptable input boundary for normalization.
- `data_sources` may be upserted because source metadata can be corrected; health snapshots and normalized evidence are append-only.
- A record-level `eligible_for_high_confidence_evaluation` flag is useful as a data-quality gate, not as trading proof.
- DexScreener, GeckoTerminal, and DexPaprika structured API payloads can be eligible only when required fields and timestamps are present.
- Bitquery CoreCast remains source-degraded until chain timestamp provenance is improved.

### Step 2 Carry Forward

- Source-health automation helper for errors/rate-limit/stale states: completed later in Sprint 2.
- `TokenProfile`, `WalletTrade`, `WalletProfile`, `WalletCluster`, and browser extraction records: completed later in Sprint 2.
- Deterministic triage without creating signals or strategy proof: completed later in Sprint 2.
- Improve Bitquery CoreCast raw payload completeness before using it for high-confidence evaluation evidence.

### Step 2 Validation

Validation was run on 2026-05-14:

- `.\.venv\Scripts\python.exe -m pytest`: passed, 23 tests.
- `.\.venv\Scripts\python.exe -m compileall walletscarper`: passed.
- Dangerous-term `rg` scan: run after documentation update. Matches remain documentation prohibitions, read-only market-data naming, or read-only parsed RPC metadata. No dangerous live execution path was found.
