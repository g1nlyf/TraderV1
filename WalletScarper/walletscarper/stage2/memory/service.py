from __future__ import annotations

from datetime import datetime
from typing import Any

from walletscarper.stage2.clock import Clock, SystemClock, isoformat_utc
from walletscarper.stage2.db import Stage2Database
from walletscarper.stage2.db.json import dumps_json
from walletscarper.stage2.ids import new_id
from walletscarper.stage2.parallelism import parse_json_list


MEMORY_TYPES = {"fact", "hypothesis", "lesson", "warning", "obsolete_conclusion"}
CURATION_ACTIONS = {"accept", "reject", "archive", "supersede"}


class MemoryService:
    """Memory proposal and curation workflow.

    Memory entries are curated interpretation/evidence. This service never
    mutates ledger, risk, fills, outcomes, or strategy history.
    """

    def __init__(self, database: Stage2Database, *, clock: Clock | None = None):
        self.database = database
        self.clock = clock or SystemClock()

    async def propose_memory(
        self,
        *,
        claim: str,
        memory_type: str,
        evidence_refs: list[str],
        review_refs: list[str] | None = None,
        strategy_refs: list[str] | None = None,
        confidence: str = "unknown",
        validity_scope: dict[str, Any] | None = None,
        created_by: str = "memory_service",
    ) -> str:
        if memory_type not in MEMORY_TYPES:
            raise ValueError(f"Unsupported memory type: {memory_type}")
        if not evidence_refs and not review_refs and not strategy_refs:
            raise ValueError("MemoryProposal requires at least one evidence, review, or strategy reference.")
        proposal_id = new_id("memory_proposal")
        await self.database.execute(
            """
            INSERT INTO memory_proposals(
              memory_proposal_id, claim, memory_type, evidence_refs_json,
              review_refs_json, strategy_refs_json, confidence, validity_scope_json,
              created_at, created_by, status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'proposed')
            """,
            (
                proposal_id,
                claim,
                memory_type,
                dumps_json(evidence_refs),
                dumps_json(review_refs or []),
                dumps_json(strategy_refs or []),
                confidence,
                dumps_json(validity_scope or {}),
                isoformat_utc(self.clock.now()),
                created_by,
            ),
        )
        return proposal_id

    async def curate_memory(
        self,
        *,
        memory_proposal_id: str,
        action: str,
        curator: str,
        reason: str,
        expires_at: datetime | None = None,
        supersedes_memory_entry_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        if action not in CURATION_ACTIONS:
            raise ValueError(f"Unsupported curation action: {action}")
        proposal = await self.database.fetchone(
            "SELECT * FROM memory_proposals WHERE memory_proposal_id = ?",
            (memory_proposal_id,),
        )
        if not proposal:
            raise ValueError(f"MemoryProposal not found: {memory_proposal_id}")
        memory_entry_id: str | None = None
        if action in {"accept", "supersede"}:
            memory_entry_id = new_id("memory_entry")
            source_refs = parse_json_list(proposal["evidence_refs_json"]) + parse_json_list(proposal["review_refs_json"])
            await self.database.execute(
                """
                INSERT INTO memory_entries(
                  memory_entry_id, claim, evidence_grade, source_refs_json, status,
                  expires_at, created_at, created_by, metadata_json
                )
                VALUES (?, ?, ?, ?, 'accepted', ?, ?, ?, ?)
                """,
                (
                    memory_entry_id,
                    proposal["claim"],
                    proposal["confidence"],
                    dumps_json(source_refs),
                    isoformat_utc(expires_at) if expires_at else None,
                    isoformat_utc(self.clock.now()),
                    curator,
                    dumps_json(
                        {
                            "memory_proposal_id": memory_proposal_id,
                            "memory_type": proposal["memory_type"],
                            "validity_scope": proposal["validity_scope_json"],
                            "strategy_refs": parse_json_list(proposal["strategy_refs_json"]),
                        }
                    ),
                ),
            )
            if action == "supersede" and supersedes_memory_entry_id:
                await self.database.execute(
                    "UPDATE memory_entries SET status = 'superseded' WHERE memory_entry_id = ?",
                    (supersedes_memory_entry_id,),
                )
        elif action in {"reject", "archive"}:
            new_status = "rejected" if action == "reject" else "archived"
            await self.database.execute(
                "UPDATE memory_proposals SET status = ? WHERE memory_proposal_id = ?",
                (new_status, memory_proposal_id),
            )
        if action in {"accept", "supersede"}:
            await self.database.execute(
                "UPDATE memory_proposals SET status = ?, curated_memory_entry_id = ? WHERE memory_proposal_id = ?",
                ("accepted" if action == "accept" else "superseded", memory_entry_id, memory_proposal_id),
            )
        curation_id = new_id("memory_curation_event")
        await self.database.execute(
            """
            INSERT INTO memory_curation_events(
              memory_curation_event_id, memory_proposal_id, memory_entry_id,
              action, curator, reason, created_at, supersedes_memory_entry_id,
              metadata_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                curation_id,
                memory_proposal_id,
                memory_entry_id,
                action,
                curator,
                reason,
                isoformat_utc(self.clock.now()),
                supersedes_memory_entry_id,
                dumps_json(metadata or {}),
            ),
        )
        return curation_id

