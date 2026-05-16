from __future__ import annotations

from walletscarper.stage2.events import RawSourceEventLog
from walletscarper.stage2.legacy_ingestion.models import RawSourceEventDraft


async def write_raw_source_event(draft: RawSourceEventDraft, raw_log: RawSourceEventLog) -> str:
    return await raw_log.append(
        source_name=draft.source_name,
        source_type=draft.source_type,
        external_id=draft.external_id,
        observed_at=draft.observed_at,
        payload=draft.payload,
        confidence=draft.confidence,
        quality_metadata=draft.quality_metadata(),
    )
