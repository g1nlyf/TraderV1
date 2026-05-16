"""Stage 2 ingestion bridges.

Two bridges, both lazy-init and best-effort (errors logged and swallowed so
the legacy pipeline is never broken by Stage 2 problems):

- Stage2IngestBridge: TokenCandidate objects → Stage 2 raw_source_events
  (token discovery path; normalizer handles idempotency)

- Stage2WalletSignalBridge: tracked wallet transactions → Stage 2
  tracked_wallet_signal_events (wallet signal path; Hermes consumes these)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from walletscarper.models import TokenCandidate

log = logging.getLogger(__name__)

_SOURCE_MAPPERS: dict[str, str] = {
    "dexscreener": "map_dexscreener_payload",
    "geckoterminal": "map_geckoterminal_payload",
    "dexpaprika": "map_dexpaprika_payload",
}


class Stage2IngestBridge:
    """Best-effort bridge: writes discovered token candidates into Stage 2 raw_source_events.

    Lazy-initializes Stage2Database on first use.  All errors are caught and
    logged so the legacy pipeline is never disrupted by Stage 2 failures.
    """

    def __init__(self) -> None:
        self._database: Any = None
        self._raw_log: Any = None
        self._available: bool | None = None  # None = not yet tested

    async def ingest_token_candidates(self, candidates: list[TokenCandidate]) -> int:
        """Write candidates to Stage 2 raw_source_events.

        Returns number of events successfully written.
        """
        if not candidates:
            return 0
        if not await self._ensure_ready():
            return 0

        written = 0
        for candidate in candidates:
            try:
                written += await self._ingest_one(candidate)
            except Exception:
                log.debug("stage2_bridge: skipped candidate %s", candidate.pool_address, exc_info=True)
        if written:
            log.info("stage2_bridge: wrote %d raw_source_events to Stage 2", written)
        return written

    async def _ingest_one(self, candidate: TokenCandidate) -> int:
        from walletscarper.stage2.legacy_ingestion import write_raw_source_event
        from walletscarper.stage2.legacy_ingestion.mappers import (
            map_dexscreener_payload,
            map_geckoterminal_payload,
            map_dexpaprika_payload,
        )

        source = (candidate.source or "").lower()
        raw = candidate.raw
        if not isinstance(raw, dict) or not raw:
            return 0

        if source == "dexscreener":
            draft = map_dexscreener_payload(raw)
        elif source == "geckoterminal":
            draft = map_geckoterminal_payload(raw)
        elif source == "dexpaprika":
            draft = map_dexpaprika_payload(raw)
        else:
            # Unknown source: use dexscreener mapper as fallback for dict payloads
            draft = map_dexscreener_payload(raw)

        # Override external_id if mapper couldn't extract it — pool_address is always known
        if draft.external_id is None and candidate.pool_address:
            from walletscarper.stage2.legacy_ingestion.models import RawSourceEventDraft
            draft = RawSourceEventDraft(
                source_name=draft.source_name,
                source_type=draft.source_type,
                external_id=candidate.pool_address,
                observed_at=draft.observed_at,
                payload=draft.payload,
                provenance={**draft.provenance, "pool_address_fallback_external_id": True},
                confidence=draft.confidence if draft.confidence != "unknown" else candidate.confidence,
                extraction_method=draft.extraction_method,
                quality_flags=[f for f in draft.quality_flags if f != "missing_external_id"],
                raw_adapter_name=draft.raw_adapter_name,
            )

        await write_raw_source_event(draft, self._raw_log)
        return 1

    async def _ensure_ready(self) -> bool:
        if self._available is False:
            return False
        if self._available is True:
            return True

        try:
            from walletscarper.stage2.config import load_stage2_settings
            from walletscarper.stage2.db import Stage2Database
            from walletscarper.stage2.events import RawSourceEventLog

            stage2_settings = load_stage2_settings()
            database = Stage2Database(stage2_settings)
            await database.migrate()
            self._database = database
            self._raw_log = RawSourceEventLog(database)
            self._available = True
            log.info("stage2_bridge: Stage 2 database ready at %s", stage2_settings.database_path)
            return True
        except Exception:
            self._available = False
            log.warning("stage2_bridge: Stage 2 unavailable — token candidates will not be written to Stage 2", exc_info=True)
            return False


class Stage2WalletSignalBridge:
    """Best-effort bridge: writes tracked wallet signal events into Stage 2.

    Called from LiveMonitor whenever a tracked wallet executes a new buy or sell.
    Lazy-initializes Stage2Database on first use.  All errors are caught and
    logged so the legacy pipeline is never disrupted by Stage 2 failures.
    """

    def __init__(self) -> None:
        self._orchestrator: Any = None
        self._available: bool | None = None  # None = not yet tested

    async def emit_wallet_signal(
        self,
        wallet: str,
        token_mint: str,
        side: str,
        *,
        pool_address: str | None = None,
        signature: str | None = None,
        block_time: str | None = None,
        source: str | None = None,
    ) -> str | None:
        """Emit a tracked wallet signal event to Stage 2.

        Returns Stage 2 event_id on success, None on failure or unavailability.
        Side must be 'buy' or 'sell'.
        """
        if side not in {"buy", "sell"}:
            log.debug("stage2_signal_bridge: skipped unsupported side=%s for wallet %s", side, wallet)
            return None
        if not await self._ensure_ready():
            return None
        try:
            source_refs = [f"signature:{signature}"] if signature else []
            event_id = await self._orchestrator.record_tracked_wallet_signal_event(
                wallet=wallet,
                token_mint=token_mint,
                side=side,
                pool_address=pool_address,
                observed_at=block_time,
                source_name=source or "live_monitor",
                source_refs=source_refs,
                input_mode="real_source",
                data_sufficiency="partial",
            )
            log.info(
                "stage2_signal_bridge: emitted %s signal wallet=%s token=%s event=%s",
                side,
                wallet[:8],
                token_mint[:8],
                event_id,
            )
            return event_id
        except Exception:
            log.debug("stage2_signal_bridge: failed to emit signal for wallet %s", wallet, exc_info=True)
            return None

    async def _ensure_ready(self) -> bool:
        if self._available is False:
            return False
        if self._available is True:
            return True

        try:
            from walletscarper.stage2.config import load_stage2_settings
            from walletscarper.stage2.db import Stage2Database
            from walletscarper.stage2.orchestrator.service import HermesOrchestratorService

            stage2_settings = load_stage2_settings()
            database = Stage2Database(stage2_settings)
            await database.migrate()
            self._orchestrator = HermesOrchestratorService(database)
            self._available = True
            log.info("stage2_signal_bridge: Stage 2 database ready for wallet signals")
            return True
        except Exception:
            self._available = False
            log.warning("stage2_signal_bridge: Stage 2 unavailable — wallet signals will not be written to Stage 2", exc_info=True)
            return False
