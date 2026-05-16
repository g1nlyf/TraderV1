from __future__ import annotations

from typing import Any

from walletscarper.stage2.clock import Clock, SystemClock, isoformat_utc
from walletscarper.stage2.db import Stage2Database
from walletscarper.stage2.db.json import dumps_json
from walletscarper.stage2.ids import new_id


class BrowserExtractionRepository:
    def __init__(self, database: Stage2Database, clock: Clock | None = None):
        self.database = database
        self.clock = clock or SystemClock()

    async def record_success(
        self,
        *,
        source_url: str,
        parser_name: str,
        parser_version: str,
        extracted_fields: dict[str, Any],
        confidence_score: float,
        source_name: str | None = None,
        raw_source_event_id: str | None = None,
        raw_html_ref: str | None = None,
        screenshot_ref: str | None = None,
        snapshot_ref: str | None = None,
        quality_flags: list[str] | None = None,
    ) -> str:
        flags = _unique(["browser_non_canonical", *(quality_flags or [])])
        return await self._insert(
            source_url=source_url,
            parser_name=parser_name,
            parser_version=parser_version,
            status="success",
            extracted_fields=extracted_fields,
            confidence_score=min(max(confidence_score, 0), 1),
            degradation_reason=None,
            source_name=source_name,
            raw_source_event_id=raw_source_event_id,
            raw_html_ref=raw_html_ref,
            screenshot_ref=screenshot_ref,
            snapshot_ref=snapshot_ref,
            quality_flags=flags,
        )

    async def record_failure(
        self,
        *,
        source_url: str,
        parser_name: str,
        parser_version: str,
        degradation_reason: str,
        source_name: str | None = None,
        raw_source_event_id: str | None = None,
        raw_html_ref: str | None = None,
        screenshot_ref: str | None = None,
        snapshot_ref: str | None = None,
        quality_flags: list[str] | None = None,
    ) -> str:
        flags = _unique(["browser_non_canonical", "browser_extraction_failed", "parser_failed", *(quality_flags or [])])
        return await self._insert(
            source_url=source_url,
            parser_name=parser_name,
            parser_version=parser_version,
            status="failed",
            extracted_fields={},
            confidence_score=0,
            degradation_reason=degradation_reason,
            source_name=source_name,
            raw_source_event_id=raw_source_event_id,
            raw_html_ref=raw_html_ref,
            screenshot_ref=screenshot_ref,
            snapshot_ref=snapshot_ref,
            quality_flags=flags,
        )

    async def _insert(
        self,
        *,
        source_url: str,
        parser_name: str,
        parser_version: str,
        status: str,
        extracted_fields: dict[str, Any],
        confidence_score: float,
        degradation_reason: str | None,
        source_name: str | None,
        raw_source_event_id: str | None,
        raw_html_ref: str | None,
        screenshot_ref: str | None,
        snapshot_ref: str | None,
        quality_flags: list[str],
    ) -> str:
        extraction_id = new_id("browser_extraction")
        now = isoformat_utc(self.clock.now())
        await self.database.execute(
            """
            INSERT INTO browser_extractions(
              browser_extraction_id, source_url, source_name, raw_source_event_id,
              extracted_at, parser_name, parser_version, status, raw_html_ref,
              screenshot_ref, snapshot_ref, extracted_fields_json, confidence_score,
              degradation_reason, quality_flags_json, eligible_for_high_confidence_evaluation,
              created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?)
            """,
            (
                extraction_id,
                source_url,
                source_name,
                raw_source_event_id,
                now,
                parser_name,
                parser_version,
                status,
                raw_html_ref,
                screenshot_ref,
                snapshot_ref,
                dumps_json(extracted_fields),
                confidence_score,
                degradation_reason,
                dumps_json(quality_flags),
                now,
            ),
        )
        return extraction_id


def _unique(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result
