from __future__ import annotations

from typing import Any

from walletscarper.stage2.clock import Clock, SystemClock, isoformat_utc
from walletscarper.stage2.db import Stage2Database
from walletscarper.stage2.db.json import dumps_json
from walletscarper.stage2.ids import new_id
from walletscarper.stage2.parallelism import parse_json_list, parse_json_object


class PostTradeReviewService:
    """Append-only post-trade review workflow built on deterministic outcomes."""

    def __init__(self, database: Stage2Database, *, clock: Clock | None = None):
        self.database = database
        self.clock = clock or SystemClock()

    async def create_post_trade_review(
        self,
        *,
        outcome_id: str,
        reviewer: str = "post_trade_review_service",
        thesis_expected: dict[str, Any] | None = None,
        actual_result: dict[str, Any] | None = None,
        source_quality_issues: list[str] | None = None,
        exit_matched_plan: bool | None = None,
        lessons: list[str] | None = None,
        proposed_mutation_refs: list[str] | None = None,
        memory_proposal_refs: list[str] | None = None,
        evidence_refs: list[str] | None = None,
        hindsight_claims: list[str] | None = None,
    ) -> str:
        context = await self._review_context(outcome_id)
        outcome = context["outcome"]
        position = context["position"]
        signal = context["signal"]
        thesis = context["thesis"]
        thesis_detail = context.get("thesis_detail") or {}
        bias_flags = self._bias_flags(hindsight_claims or [], evidence_refs or [])
        review_id = new_id("post_trade_review")
        await self.database.execute(
            """
            INSERT INTO post_trade_reviews(
              post_trade_review_id, outcome_id, position_id, reviewer,
              mistakes_json, lessons_json, hypothesis_update_json, evidence_refs_json,
              created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                review_id,
                outcome_id,
                position["position_id"],
                reviewer,
                dumps_json(bias_flags),
                dumps_json(lessons or []),
                dumps_json({"proposed_mutation_refs": proposed_mutation_refs or []}),
                dumps_json(evidence_refs or []),
                isoformat_utc(self.clock.now()),
            ),
        )
        await self.database.execute(
            """
            INSERT INTO post_trade_review_details(
              post_trade_review_detail_id, post_trade_review_id, position_id,
              strategy_version_id, signal_id, thesis_id, outcome_id,
              thesis_expected_json, actual_result_json, cost_impact_json,
              risk_summary_json, fill_quality_json, source_quality_issues_json,
              exit_matched_plan, bias_flags_json, lessons_json,
              proposed_mutation_refs_json, memory_proposal_refs_json,
              hindsight_flags_json, created_by, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                new_id("post_trade_review_detail"),
                review_id,
                position["position_id"],
                position["strategy_version_id"],
                signal["signal_id"],
                thesis["thesis_id"],
                outcome_id,
                dumps_json(thesis_expected or self._thesis_expected(thesis, thesis_detail)),
                dumps_json(actual_result or self._actual_result(outcome)),
                dumps_json(self._cost_impact(outcome)),
                dumps_json(await self._risk_summary(signal["signal_id"], position["position_id"])),
                dumps_json(await self._fill_quality(position["position_id"])),
                dumps_json(source_quality_issues or []),
                None if exit_matched_plan is None else (1 if exit_matched_plan else 0),
                dumps_json(bias_flags),
                dumps_json(lessons or []),
                dumps_json(proposed_mutation_refs or []),
                dumps_json(memory_proposal_refs or []),
                dumps_json(bias_flags),
                reviewer,
                isoformat_utc(self.clock.now()),
            ),
        )
        return review_id

    async def propose_memory_from_review(
        self,
        review_id: str,
        *,
        claim: str,
        memory_type: str = "lesson",
        confidence: str = "medium",
        created_by: str = "post_trade_review_service",
    ) -> str:
        review = await self.database.fetchone(
            "SELECT * FROM post_trade_review_details WHERE post_trade_review_id = ?",
            (review_id,),
        )
        if not review:
            raise ValueError(f"PostTradeReview detail not found: {review_id}")
        from walletscarper.stage2.memory import MemoryService

        memory_service = MemoryService(self.database, clock=self.clock)
        return await memory_service.propose_memory(
            claim=claim,
            memory_type=memory_type,
            evidence_refs=parse_json_list(review["source_quality_issues_json"]),
            review_refs=[review_id],
            strategy_refs=[str(review["strategy_version_id"])],
            confidence=confidence,
            validity_scope={"strategy_version_id": review["strategy_version_id"]},
            created_by=created_by,
        )

    async def _review_context(self, outcome_id: str) -> dict[str, Any]:
        outcome = await self.database.fetchone("SELECT * FROM trade_outcomes WHERE outcome_id = ?", (outcome_id,))
        if not outcome:
            raise ValueError(f"TradeOutcome not found: {outcome_id}")
        position = await self.database.fetchone("SELECT * FROM paper_positions WHERE position_id = ?", (outcome["position_id"],))
        if not position:
            raise ValueError("TradeOutcome references missing PaperPosition.")
        order = await self.database.fetchone("SELECT * FROM paper_orders WHERE paper_order_id = ?", (position["entry_order_id"],))
        if not order:
            raise ValueError("PaperPosition references missing entry PaperOrder.")
        signal = await self.database.fetchone("SELECT * FROM signals WHERE signal_id = ?", (order["signal_id"],))
        if not signal:
            raise ValueError("PaperOrder references missing Signal.")
        thesis = await self.database.fetchone("SELECT * FROM trade_theses WHERE signal_id = ?", (signal["signal_id"],))
        if not thesis:
            raise ValueError("Signal has no TradeThesis.")
        thesis_detail = await self.database.fetchone(
            "SELECT * FROM trade_thesis_details WHERE thesis_id = ?",
            (thesis["thesis_id"],),
        )
        return {"outcome": outcome, "position": position, "order": order, "signal": signal, "thesis": thesis, "thesis_detail": thesis_detail}

    def _thesis_expected(self, thesis: dict[str, Any], thesis_detail: dict[str, Any]) -> dict[str, Any]:
        return {
            "entry_reason": thesis.get("entry_reason"),
            "exit_plan": thesis.get("exit_plan"),
            "expected_holding_time": thesis.get("expected_holding_time"),
            "proof_wrong": thesis.get("proof_wrong"),
            "why_token": thesis_detail.get("why_token"),
            "why_now": thesis_detail.get("why_now"),
        }

    def _actual_result(self, outcome: dict[str, Any]) -> dict[str, Any]:
        return {
            "gross_pnl": outcome["gross_pnl"],
            "net_pnl": outcome["net_pnl"],
            "duration_seconds": outcome["duration_seconds"],
            "max_drawdown": outcome["max_drawdown"],
        }

    def _cost_impact(self, outcome: dict[str, Any]) -> dict[str, Any]:
        return {"fees": outcome["fees"], "slippage": outcome["slippage"]}

    async def _risk_summary(self, signal_id: str, position_id: str) -> dict[str, Any]:
        rows = await self.database.fetchall(
            """
            SELECT check_scope, passed, veto_reason, warnings_json
            FROM risk_checks
            WHERE (subject_type = 'signal' AND subject_id = ?)
               OR (subject_type = 'paper_position' AND subject_id = ?)
               OR (subject_type = 'exit_decision' AND subject_id IN (
                    SELECT exit_decision_id FROM exit_decisions WHERE position_id = ?
               ))
            ORDER BY created_at ASC
            """,
            (signal_id, position_id, position_id),
        )
        return {"checks": [dict(row) for row in rows]}

    async def _fill_quality(self, position_id: str) -> dict[str, Any]:
        rows = await self.database.fetchall(
            """
            SELECT pf.paper_fill_id, pf.fill_price, pf.fees, pf.slippage,
                   pf.latency_assumption, pf.liquidity_constraint, pf.failed_fill_reason
            FROM paper_fills pf
            JOIN paper_orders po ON po.paper_order_id = pf.paper_order_id
            JOIN paper_positions pp ON pp.position_id = ?
            JOIN paper_orders entry_po ON entry_po.paper_order_id = pp.entry_order_id
            WHERE pp.entry_fill_id = pf.paper_fill_id
               OR (po.signal_id = entry_po.signal_id AND po.side = 'sell')
            ORDER BY pf.fill_time ASC
            """,
            (position_id,),
        )
        return {"fills": [dict(row) for row in rows]}

    def _bias_flags(self, hindsight_claims: list[str], evidence_refs: list[str]) -> list[str]:
        flags: list[str] = []
        if hindsight_claims:
            flags.append("review_contains_post_outcome_claims")
        if hindsight_claims and not evidence_refs:
            flags.append("unsupported_hindsight_storytelling")
        return flags
