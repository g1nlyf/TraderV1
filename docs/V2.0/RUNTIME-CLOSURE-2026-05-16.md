# Runtime Closure Audit - 2026-05-16

## Scope

This note updates `AUDIT-2026-05-16.md` after direct runtime fixes and live-source smoke checks.

Obsidian Smart Connections was checked first. It had 179 notes indexed, but searches for `TraderV1`, `Hermes`, wallet/token/PnL terms, and Russian equivalents returned no relevant notes. The working baseline is therefore the local repo plus local SQLite state.

## Commands Run

- `python -m walletscarper smoke-test` - passed.
- `python -m walletscarper stage2-migrate` - passed, migrations 1-10 current.
- `python -m walletscarper project-health-check` - passed.
- `python -m pytest -q` - passed, 71 tests.
- `python -m walletscarper score` - completed in about 22 seconds on the current 744k+ transaction legacy DB.
- `python -m walletscarper run-once` - completed in about 123 seconds with status `ok`.
- `python -m walletscarper stage2-v2-tool token.scan_universe` - created 15 new candidates/profiles after `run-once`.
- `Stage2ScannerService.run_wallet_extraction(max_tokens=5, lookback_hours=24)` - processed 5 token/pool targets and created 866 wallet outcomes.
- `LiveMonitor.tick()` - added 6 real-source Stage 2 wallet signal events.

## What Changed In Runtime

The earlier audit correctly identified a real-data wiring gap, but the codebase has now moved past that baseline:

- `Pipeline.run_once()` writes discovered token candidates into Stage 2 through `Stage2IngestBridge`.
- `LiveMonitor` emits real tracked-wallet buy/sell events into Stage 2 through `Stage2WalletSignalBridge`.
- `stage2-run-daemon` and `Stage2ScannerService` exist for continuous Stage 2 scanning.
- Hermes plugin exposes write-safe V2 tools, not only read-only reports.

Additional fixes made in this closure pass:

- `token.scan_universe` no longer reprocesses raw events that already produced `raw_only` or `market_snapshot` refs.
- V2 tool responses now expose top-level counts for `token.scan_universe` and `wallet.extract_from_token`.
- Added `wallet.calculate_token_outcomes` tool for token-specific wallet ROI/PnL outcomes.
- `Stage2ScannerService` now uses token/pool targets, calculates wallet outcomes, and profiles eligible wallets.
- `wallet.profile_history` now falls back to legacy `pool_transactions` when Stage 2 `wallet_trades` are absent.
- Legacy wallet scoring now performs bulk writes and completes on the current DB instead of making `run-once` stall.
- Hermes plugin registration includes `wallet.calculate_token_outcomes`.

## Current Live Baseline

After the runtime smoke:

| Area | Observed state |
|---|---|
| Legacy tokens | 36+ |
| Legacy pools | 40+ |
| Legacy pool transactions | 744k+ |
| Legacy wallet scores | 22k+ wallets after optimized scoring |
| Stage 2 raw source events | 103 |
| Stage 2 token candidates | 86 |
| Stage 2 token profiles | 48 |
| Stage 2 trade corpora | 28 |
| Stage 2 wallet-token outcomes | 866 |
| Stage 2 tracked wallet signal events | 9 total, 7 real_source |

Latest `run-once` result:

```text
status: ok
tokens_checked: 15
tokens_deep_analyzed: 15
wallet_candidates_found: 22818
tracked_wallets_added: 2
errors_count: 0
```

Latest Stage 2 wallet extraction sample:

```text
tokens_processed: 5
wallets_extracted: 866
wallet_outcomes_calculated: 866
eligible_wallets_for_review: 0
wallet_profiles_created: 0
```

The zero eligible wallets in that sample is not a failure. It means no wallet in that 5-token slice met the current token-specific +20% ROI and quality gate.

## Pipeline Reality

The pipeline now works in the requested order:

1. Token discovery: DexScreener/GeckoTerminal -> legacy `tokens`, `pools`, `token_snapshots`.
2. Stage 2 token scan: legacy discovered candidates -> `raw_source_events` -> `token_candidates` -> `token_profiles` -> `token_triage_decisions`.
3. Token deep parse: selected token/pool -> `token_trade_corpora` from Stage 2 or legacy trade evidence.
4. Wallet extraction: token corpus -> wallet candidate list.
5. Token-specific wallet outcomes: corpus -> `wallet_token_outcomes`, including +20% ROI eligibility.
6. Wallet history profile: Stage 2 trades first, legacy `pool_transactions` fallback when needed.
7. Wallet signal intake: tracked-wallet buys/sells -> `tracked_wallet_signal_events` with `input_mode=real_source`.
8. Hermes orchestration: fixture-verified signal -> risk -> paper -> exit -> review -> memory path remains intact.

## Remaining Gaps

These are still real gaps before calling the whole product final:

- Hermes still needs a sustained autonomous session that repeatedly chooses tokens, rates wallets, and records `AgentWalletReview` decisions without manual prompting.
- Wallet review volume is still low; `agent_wallet_reviews` is not yet populated from the new real candidates.
- Stage 2 `wallet_trades` remains sparse; legacy fallback works, but high-confidence reconstruction should eventually write normalized Stage 2 wallet trades.
- Active token sessions exist, but adaptive market polling/candles are not yet a complete priority loop.
- Shadow readiness remains gap-blocked until real observation windows, quote freshness, route quality, and fill-vs-quote comparisons are accumulated.
- Forward learning is structurally present, but meaningful promotion/demotion requires more real paper outcomes linked to real wallet signals.

## Updated Verdict

The project is no longer just a fixture-ready Stage 2 shell. It now has a working real-source token -> wallet -> signal pipeline and safe Hermes tool surface.

It is still not a fully autonomous profitable trading system. The next implementation pass should focus on autonomous Hermes review loops and adaptive market/session runtime, not another rewrite of the data foundation.
