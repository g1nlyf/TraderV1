"""Stage 2 scanner service.

Scheduled jobs that run V2 intelligence tools on a recurring basis:

- run_token_scan(): normalize new raw_source_events → token_candidates/profiles
  (wraps token.scan_universe; run after every discovery cycle)

- run_wallet_extraction(): build trade corpora and extract wallet candidates
  for recently discovered tokens that have not yet been processed
  (wraps wallet.extract_from_token; run every few hours)

Design: lazy init, best-effort — all errors logged and swallowed so the
legacy scheduler is never disrupted by Stage 2 failures.
"""

from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger(__name__)


class Stage2ScannerService:
    """Best-effort Stage 2 intelligence scanner for use by WalletScarperScheduler.

    Lazy-initializes Stage2Database on first use.
    """

    def __init__(self) -> None:
        self._database: Any = None
        self._available: bool | None = None  # None = not yet tested

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run_token_scan(self, limit: int = 100) -> dict[str, Any]:
        """Normalize up to `limit` un-processed raw_source_events into token candidates.

        Returns the tool response dict (token_candidates_created, profiles_created, etc.)
        or an empty dict on failure.
        """
        if not await self._ensure_ready():
            return {}
        try:
            from walletscarper.stage2.hermes_integration.v2_tools import run_v2_tool
            result = await run_v2_tool("token.scan_universe", {"limit": limit}, database=self._database)
            summary = result.get("result") if isinstance(result.get("result"), dict) else result
            created = int(summary.get("token_candidates_created", 0) or 0)
            profiles = int(summary.get("profiles_created", 0) or 0)
            log.info("stage2_scanner: token_scan done — candidates=%s profiles=%s", created, profiles)
            return result
        except Exception:
            log.warning("stage2_scanner: run_token_scan failed", exc_info=True)
            return {}

    async def run_legacy_token_sync(self, limit: int = 50) -> dict[str, Any]:
        """Ingest legacy DB tokens (that have no Stage2 raw_source_event) into Stage2.

        This unblocks wallet extraction for the 744k+ transactions already in the
        legacy pool_transactions table for tokens discovered before the Stage2 bridge
        was wired.

        Returns a summary dict with tokens_synced and events_written.
        """
        if not await self._ensure_ready():
            return {}
        try:
            from walletscarper.db import db as legacy_db
            from walletscarper.stage2.legacy_ingestion.models import RawSourceEventDraft
            from walletscarper.stage2.legacy_ingestion.writer import write_raw_source_event
            from walletscarper.stage2.events import RawSourceEventLog
            from datetime import timezone
            import datetime as _dt

            raw_log = RawSourceEventLog(self._database)

            # Get legacy tokens+pools that have no matching Stage2 raw_source_event by external_id
            legacy_tokens = await legacy_db.fetchall(
                """
                SELECT t.mint, t.symbol, t.name, t.source, t.last_seen_at,
                       p.pool_address, p.dex_id, p.quote_mint,
                       (SELECT COUNT(*) FROM pool_transactions pt WHERE pt.token_mint = t.mint) AS tx_count
                FROM tokens t
                LEFT JOIN pools p ON p.token_mint = t.mint
                GROUP BY t.mint
                ORDER BY tx_count DESC
                LIMIT ?
                """,
                (limit,),
            )

            if not legacy_tokens:
                return {"tokens_synced": 0, "events_written": 0}

            # Get existing Stage2 external_ids to avoid duplication
            existing_rows = await self._database.fetchall(
                "SELECT external_id FROM raw_source_events WHERE source_name = 'legacy_tokens_db'"
            )
            existing_ids: set[str] = {str(r["external_id"]) for r in existing_rows if r.get("external_id")}

            events_written = 0
            tokens_synced = 0
            for row in legacy_tokens:
                pool_addr = str(row.get("pool_address") or "")
                token_mint = str(row["mint"])
                external_id = pool_addr or token_mint
                if external_id in existing_ids:
                    continue

                try:
                    observed_raw = row.get("last_seen_at")
                    if observed_raw:
                        try:
                            observed_at = _dt.datetime.fromisoformat(str(observed_raw).replace("Z", "+00:00"))
                            if observed_at.tzinfo is None:
                                observed_at = observed_at.replace(tzinfo=timezone.utc)
                        except ValueError:
                            observed_at = _dt.datetime.now(timezone.utc)
                    else:
                        observed_at = _dt.datetime.now(timezone.utc)

                    draft = RawSourceEventDraft(
                        source_name="legacy_tokens_db",
                        source_type="token_discovery",
                        external_id=external_id,
                        observed_at=observed_at,
                        payload={
                            "token_mint": token_mint,
                            "pool_address": pool_addr,
                            "symbol": str(row.get("symbol") or ""),
                            "name": str(row.get("name") or ""),
                            "dex_id": str(row.get("dex_id") or ""),
                            "quote_mint": str(row.get("quote_mint") or ""),
                            "source": str(row.get("source") or "legacy"),
                            "tx_count": int(row.get("tx_count") or 0),
                        },
                        provenance={"origin": "legacy_tokens_db_sync", "token_mint": token_mint},
                        confidence="medium",
                        extraction_method="legacy_db_direct_read",
                        quality_flags=["legacy_adapter_source"],
                        raw_adapter_name="LegacyTokensDbAdapter",
                    )
                    await write_raw_source_event(draft, raw_log)
                    existing_ids.add(external_id)
                    events_written += 1
                    tokens_synced += 1
                    log.debug("stage2_scanner: synced legacy token %s (%s)", token_mint[:8], row.get("symbol", ""))
                except Exception:
                    log.debug("stage2_scanner: failed to sync legacy token %s", token_mint, exc_info=True)

            log.info("stage2_scanner: legacy_token_sync done — tokens=%d events=%d", tokens_synced, events_written)
            return {"tokens_synced": tokens_synced, "events_written": events_written}
        except Exception:
            log.warning("stage2_scanner: run_legacy_token_sync failed", exc_info=True)
            return {}

    async def run_wallet_extraction_backfill(self, max_tokens: int = 50) -> dict[str, Any]:
        """Extract wallets for ALL unprocessed token profiles regardless of age.

        This complements run_wallet_extraction (which only processes recent profiles)
        by ensuring legacy-synced and older profiles also get wallet extraction.
        """
        if not await self._ensure_ready():
            return {}
        try:
            # Use a very large lookback (10 years) to catch all unprocessed profiles
            return await self.run_wallet_extraction(max_tokens=max_tokens, lookback_hours=87_600)
        except Exception:
            log.warning("stage2_scanner: run_wallet_extraction_backfill failed", exc_info=True)
            return {}

    async def run_hermes_signal_review(self, max_signals: int = 5) -> dict[str, Any]:
        """Review pending real-source wallet signals via Hermes LLM.

        Calls HermesSignalReviewService which polls unreviewed tracked_wallet_signal_events,
        calls OpenRouter with the Hermes system prompt, and records AgentTradingDecision.
        """
        if not await self._ensure_ready():
            return {}
        try:
            from walletscarper.stage2.hermes_review.service import HermesSignalReviewService

            service = HermesSignalReviewService(self._database)
            result = await service.review_pending_signals(max_signals=max_signals)
            return result
        except Exception:
            log.warning("stage2_scanner: run_hermes_signal_review failed", exc_info=True)
            return {}

    async def run_wallet_extraction(self, max_tokens: int = 20, lookback_hours: int = 6) -> dict[str, Any]:
        """Extract wallet candidates from recently discovered tokens.

        Finds token_candidates created in the last `lookback_hours` that do not
        yet have a trade corpus, then calls wallet.extract_from_token for each.

        Returns a summary dict with tokens_processed and wallets_extracted.
        """
        if not await self._ensure_ready():
            return {}
        try:
            targets = await self._pending_extraction_targets(max_tokens, lookback_hours)
            if not targets:
                log.debug("stage2_scanner: wallet_extraction — no pending tokens")
                return {
                    "tokens_processed": 0,
                    "wallets_extracted": 0,
                    "wallet_outcomes_calculated": 0,
                    "eligible_wallets_for_review": 0,
                    "wallet_profiles_created": 0,
                }

            from walletscarper.stage2.hermes_integration.v2_tools import run_v2_tool
            total_wallets = 0
            total_outcomes = 0
            total_eligible = 0
            profiles_created = 0
            processed = 0
            for target in targets:
                token_mint = str(target["token_mint"])
                pool_address = target.get("pool_address")
                try:
                    result = await run_v2_tool(
                        "wallet.extract_from_token",
                        {"token_mint": token_mint, "pool_address": pool_address},
                        database=self._database,
                    )
                    extracted_payload = result.get("extracted") if isinstance(result.get("extracted"), dict) else {}
                    extracted = int(result.get("wallet_candidates_extracted") or extracted_payload.get("wallet_count") or 0)
                    total_wallets += extracted
                    corpus_id = result.get("artifact_id")
                    if corpus_id:
                        outcome_result = await run_v2_tool(
                            "wallet.calculate_token_outcomes",
                            {"token_trade_corpus_id": corpus_id},
                            database=self._database,
                        )
                        outcomes = outcome_result.get("outcomes") if isinstance(outcome_result.get("outcomes"), dict) else {}
                        total_outcomes += int(outcome_result.get("wallet_outcomes_created") or len(outcomes.get("wallet_token_outcome_ids") or []))
                        eligible_wallets = list(outcome_result.get("eligible_wallets_for_review") or [])
                        total_eligible += len(eligible_wallets)
                        for wallet in eligible_wallets[:10]:
                            await run_v2_tool("wallet.profile_history", {"wallet": wallet}, database=self._database)
                            profiles_created += 1
                    processed += 1
                    log.debug("stage2_scanner: extracted %d wallet candidates from %s", extracted, token_mint[:8])
                except Exception:
                    log.debug("stage2_scanner: wallet.extract_from_token failed for %s", token_mint, exc_info=True)

            log.info(
                "stage2_scanner: wallet_extraction done — tokens=%d wallets=%d",
                processed,
                total_wallets,
            )
            return {
                "tokens_processed": processed,
                "wallets_extracted": total_wallets,
                "wallet_outcomes_calculated": total_outcomes,
                "eligible_wallets_for_review": total_eligible,
                "wallet_profiles_created": profiles_created,
            }
        except Exception:
            log.warning("stage2_scanner: run_wallet_extraction failed", exc_info=True)
            return {}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _pending_extraction_targets(self, limit: int, lookback_hours: int) -> list[dict[str, str | None]]:
        """Return distinct token/pool targets that still need a usable trade corpus."""
        rows = await self._database.fetchall(
            """
            SELECT tp.token_mint, tp.pool_address, MAX(tp.created_at) AS latest_created_at
            FROM token_profiles tp
            WHERE tp.token_mint IS NOT NULL
              AND tp.created_at >= datetime('now', ? || ' hours')
              AND NOT EXISTS (
                SELECT 1
                FROM token_trade_corpora ttc
                WHERE ttc.token_mint = tp.token_mint
                  AND COALESCE(ttc.pool_address, '') = COALESCE(tp.pool_address, '')
                  AND ttc.trade_count > 0
              )
            GROUP BY tp.token_mint, tp.pool_address
            ORDER BY latest_created_at DESC
            LIMIT ?
            """,
            (f"-{lookback_hours}", limit),
        )
        return [{"token_mint": str(row["token_mint"]), "pool_address": row.get("pool_address")} for row in rows]

    async def _ensure_ready(self) -> bool:
        if self._available is False:
            return False
        if self._available is True:
            return True

        try:
            from walletscarper.stage2.config import load_stage2_settings
            from walletscarper.stage2.db import Stage2Database

            stage2_settings = load_stage2_settings()
            database = Stage2Database(stage2_settings)
            await database.migrate()
            self._database = database
            self._available = True
            log.info("stage2_scanner: Stage 2 database ready")
            return True
        except Exception:
            self._available = False
            log.warning("stage2_scanner: Stage 2 unavailable — scanner jobs will be skipped", exc_info=True)
            return False
