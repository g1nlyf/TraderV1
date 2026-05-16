from __future__ import annotations

import json
from typing import Any

from walletscarper.stage2.clock import Clock, SystemClock, isoformat_utc
from walletscarper.stage2.config import Stage2Settings, load_stage2_settings
from walletscarper.stage2.db import Stage2Database
from walletscarper.stage2.domain import DomainRepository
from walletscarper.stage2.evaluation import DeterministicEvaluationService, OutcomeRejected
from walletscarper.stage2.memory import MemoryService
from walletscarper.stage2.orchestrator import HermesOrchestratorService
from walletscarper.stage2.paper_trading import PaperOrderRejected, Sprint3PaperTradingService
from walletscarper.stage2.reviews import PostTradeReviewService
from walletscarper.stage2.risk import DeterministicRiskService
from walletscarper.stage2.signals import SignalService
from walletscarper.stage2.token_intelligence import TokenIntelligenceService
from walletscarper.stage2.token_intelligence.session import ActiveTokenSessionService
from walletscarper.stage2.wallet_intelligence import WalletIntelligenceService


async def run_v2_tool(
    tool_name: str,
    payload: dict[str, Any] | None = None,
    *,
    settings: Stage2Settings | None = None,
    database: Stage2Database | None = None,
    clock: Clock | None = None,
) -> dict[str, Any]:
    resolved_payload = payload or {}
    resolved_settings = settings or load_stage2_settings()
    resolved_database = database or Stage2Database(resolved_settings, clock=clock)
    resolved_clock = clock or SystemClock()
    await resolved_database.migrate()
    token_service = TokenIntelligenceService(resolved_database, clock=resolved_clock)
    session_service = ActiveTokenSessionService(resolved_database, clock=resolved_clock)
    wallet_service = WalletIntelligenceService(resolved_database, clock=resolved_clock)
    domain = DomainRepository(resolved_database, clock=resolved_clock)
    orchestrator = HermesOrchestratorService(resolved_database, clock=resolved_clock)
    signal_service = SignalService(resolved_database, domain=domain, clock=resolved_clock)
    risk_service = DeterministicRiskService(resolved_database, domain=domain, clock=resolved_clock)
    paper_service = Sprint3PaperTradingService(resolved_database, domain=domain, clock=resolved_clock)
    evaluation_service = DeterministicEvaluationService(resolved_database, clock=resolved_clock)
    review_service = PostTradeReviewService(resolved_database, clock=resolved_clock)
    memory_service = MemoryService(resolved_database, clock=resolved_clock)

    if tool_name == "token.scan_universe":
        result = await token_service.scan_token_candidates_from_raw_events(limit=int(resolved_payload.get("limit") or 100))
        return _response(
            tool_name,
            data_as_of=isoformat_utc(resolved_clock.now()),
            quality_flags=result.get("quality_flags", []),
            confidence="medium",
            next_suggested_tools=["token.get_profile", "token.request_deep_parse"],
            result=result,
            raw_events_seen=result.get("raw_events_seen", 0),
            token_candidates_created=result.get("token_candidates_created", 0),
            profiles_created=result.get("profiles_created", 0),
            triage_decisions_created=result.get("triage_decisions_created", 0),
        )

    if tool_name == "token.get_profile":
        token_profile_id = resolved_payload.get("token_profile_id")
        token_mint = resolved_payload.get("token_mint")
        profile = await _get_token_profile(resolved_database, token_profile_id=token_profile_id, token_mint=token_mint)
        if not profile:
            return _response(
                tool_name,
                ok=False,
                blocked_reason="token profile not found",
                quality_flags=["missing_token_profile"],
                next_suggested_tools=["token.scan_universe"],
            )
        return _response(
            tool_name,
            artifact_id=profile.get("token_profile_id"),
            source_refs=_loads_list(profile.get("source_refs_json")),
            data_as_of=profile.get("latest_observed_at"),
            quality_flags=_loads_list(profile.get("quality_flags_json")),
            confidence=profile.get("confidence") or "unknown",
            next_suggested_tools=["token.request_deep_parse", "token.record_agent_decision"],
            profile=_token_profile_payload(profile),
        )

    if tool_name == "token.request_deep_parse":
        token_mint = str(resolved_payload.get("token_mint") or "")
        if not token_mint:
            return _response(tool_name, ok=False, blocked_reason="token_mint is required", quality_flags=["missing_token_mint"])
        corpus = await token_service.build_token_trade_corpus(
            token_mint=token_mint,
            pool_address=resolved_payload.get("pool_address"),
            window_start=resolved_payload.get("window_start"),
            window_end=resolved_payload.get("window_end"),
            created_by_service="hermes_token_request_deep_parse_tool",
        )
        return _response(
            tool_name,
            artifact_id=corpus["token_trade_corpus_id"],
            source_refs=corpus["raw_event_refs"],
            data_as_of=corpus.get("window_end") or isoformat_utc(resolved_clock.now()),
            quality_flags=corpus["quality_flags"],
            confidence=_confidence_from_sufficiency(corpus["data_sufficiency"]),
            next_suggested_tools=["wallet.extract_from_token", "token.record_agent_decision"],
            corpus=corpus,
        )

    if tool_name == "token.record_agent_decision":
        try:
            decision_id = await token_service.record_token_agent_decision(
                decision_type=str(resolved_payload.get("decision_type") or ""),
                created_by_agent=str(resolved_payload.get("created_by_agent") or "hermes"),
                token_profile_id=resolved_payload.get("token_profile_id"),
                token_mint=resolved_payload.get("token_mint"),
                pool_address=resolved_payload.get("pool_address"),
                reasons=list(resolved_payload.get("reasons") or []),
                uncertainties=list(resolved_payload.get("uncertainties") or []),
                requested_tool_calls=list(resolved_payload.get("requested_tool_calls") or []),
                evidence_refs=list(resolved_payload.get("evidence_refs") or []),
                confidence=str(resolved_payload.get("confidence") or "unknown"),
                expires_at=resolved_payload.get("expires_at"),
            )
        except ValueError as exc:
            return _response(tool_name, ok=False, blocked_reason=str(exc), quality_flags=["invalid_token_agent_decision"])

        # Session lifecycle: open on active_watch, close on downgrade/pass
        decision_type = str(resolved_payload.get("decision_type") or "")
        token_mint_for_session = resolved_payload.get("token_mint") or resolved_payload.get("token_profile_id")
        session_id: str | None = None
        sessions_closed: int = 0
        if token_mint_for_session:
            if decision_type == "active_watch":
                try:
                    session_id = await session_service.open_session(
                        token_mint=str(token_mint_for_session),
                        pool_address=resolved_payload.get("pool_address"),
                        trigger_ref=f"token_agent_decision:{decision_id}",
                        agent_owner=str(resolved_payload.get("created_by_agent") or "hermes"),
                    )
                    await session_service.record_agent_decision(session_id, decision_id)
                except Exception:
                    pass  # session lifecycle is best-effort
            elif decision_type in {"downgrade_token", "pass"}:
                try:
                    sessions_closed = await session_service.close_session_for_token(
                        str(token_mint_for_session),
                        reason=f"token_agent_decision:{decision_type}",
                    )
                except Exception:
                    pass

        extra: dict[str, Any] = {}
        if session_id:
            extra["active_token_session_id"] = session_id
        if sessions_closed:
            extra["sessions_closed"] = sessions_closed

        next_tools = (
            ["token.request_deep_parse", "wallet.extract_from_token"]
            if decision_type != "active_watch"
            else ["wallet.extract_from_token", "wallet.record_agent_review"]
        )
        return _response(
            tool_name,
            artifact_id=decision_id,
            source_refs=list(resolved_payload.get("evidence_refs") or []),
            data_as_of=isoformat_utc(resolved_clock.now()),
            quality_flags=[],
            confidence=str(resolved_payload.get("confidence") or "unknown"),
            next_suggested_tools=next_tools,
            **extra,
        )

    if tool_name == "wallet.extract_from_token":
        corpus_id = resolved_payload.get("token_trade_corpus_id")
        if not corpus_id:
            token_mint = str(resolved_payload.get("token_mint") or "")
            if not token_mint:
                return _response(
                    tool_name,
                    ok=False,
                    blocked_reason="token_trade_corpus_id or token_mint is required",
                    quality_flags=["missing_token_trade_corpus"],
                )
            corpus = await token_service.build_token_trade_corpus(
                token_mint=token_mint,
                pool_address=resolved_payload.get("pool_address"),
                window_start=resolved_payload.get("window_start"),
                window_end=resolved_payload.get("window_end"),
                created_by_service="hermes_wallet_extract_from_token_tool",
            )
            corpus_id = corpus["token_trade_corpus_id"]
        extracted = await token_service.extract_wallet_candidates_from_corpus(str(corpus_id))
        return _response(
            tool_name,
            artifact_id=str(corpus_id),
            source_refs=extracted.get("source_refs", []),
            data_as_of=isoformat_utc(resolved_clock.now()),
            quality_flags=extracted.get("quality_flags", []),
            confidence=_confidence_from_sufficiency(extracted.get("data_sufficiency")),
            next_suggested_tools=["wallet.profile_history", "wallet.record_agent_review"],
            wallet_candidates_extracted=extracted.get("wallet_count", 0),
            wallet_count=extracted.get("wallet_count", 0),
            extracted=extracted,
        )

    if tool_name == "wallet.calculate_token_outcomes":
        corpus_id = resolved_payload.get("token_trade_corpus_id")
        if not corpus_id:
            token_mint = str(resolved_payload.get("token_mint") or "")
            if not token_mint:
                return _response(
                    tool_name,
                    ok=False,
                    blocked_reason="token_trade_corpus_id or token_mint is required",
                    quality_flags=["missing_token_trade_corpus"],
                )
            corpus = await token_service.build_token_trade_corpus(
                token_mint=token_mint,
                pool_address=resolved_payload.get("pool_address"),
                window_start=resolved_payload.get("window_start"),
                window_end=resolved_payload.get("window_end"),
                created_by_service="hermes_wallet_calculate_token_outcomes_tool",
            )
            corpus_id = corpus["token_trade_corpus_id"]
        try:
            outcome_result = await wallet_service.calculate_wallet_token_outcomes(str(corpus_id))
        except ValueError as exc:
            return _response(tool_name, ok=False, blocked_reason=str(exc), quality_flags=["wallet_outcome_blocked"])
        eligible_wallets = [
            item["wallet"]
            for item in outcome_result.get("outcomes", [])
            if item.get("eligible_for_agent_review")
        ]
        return _response(
            tool_name,
            artifact_id=str(corpus_id),
            source_refs=outcome_result.get("wallet_token_outcome_ids", []),
            data_as_of=isoformat_utc(resolved_clock.now()),
            quality_flags=outcome_result.get("quality_flags", []),
            confidence=_confidence_from_sufficiency(outcome_result.get("data_sufficiency")),
            next_suggested_tools=["wallet.profile_history", "wallet.record_agent_review"],
            wallet_outcomes_created=len(outcome_result.get("wallet_token_outcome_ids", [])),
            eligible_wallets_for_review=eligible_wallets,
            eligible_wallet_count=len(eligible_wallets),
            outcomes=outcome_result,
        )

    if tool_name == "wallet.profile_history":
        wallet = str(resolved_payload.get("wallet") or "")
        if not wallet:
            return _response(tool_name, ok=False, blocked_reason="wallet is required", quality_flags=["missing_wallet"])
        profile = await wallet_service.profile_wallet_history_v2(wallet)
        return _response(
            tool_name,
            artifact_id=profile.get("metrics_snapshot_id"),
            source_refs=profile.get("source_refs", []),
            data_as_of=isoformat_utc(resolved_clock.now()),
            quality_flags=profile.get("quality_flags", []),
            confidence=_confidence_from_sufficiency(profile.get("data_sufficiency")),
            next_suggested_tools=["wallet.record_agent_review", "wallet.get_metrics"],
            profile=profile,
        )

    if tool_name == "wallet.get_metrics":
        wallet = str(resolved_payload.get("wallet") or "")
        if not wallet:
            return _response(tool_name, ok=False, blocked_reason="wallet is required", quality_flags=["missing_wallet"])
        metric = await _latest_wallet_metric(resolved_database, wallet)
        if not metric:
            return _response(
                tool_name,
                ok=False,
                blocked_reason="wallet metrics not found",
                quality_flags=["missing_wallet_metrics"],
                next_suggested_tools=["wallet.profile_history"],
            )
        return _response(
            tool_name,
            artifact_id=metric.get("wallet_metric_snapshot_id"),
            source_refs=_loads_list(metric.get("source_refs_json")),
            data_as_of=metric.get("calculated_at"),
            quality_flags=_loads_list(metric.get("quality_flags_json")),
            confidence=metric.get("confidence") or "unknown",
            next_suggested_tools=["wallet.record_agent_review"],
            metrics=_wallet_metric_payload(metric),
        )

    if tool_name == "wallet.record_agent_review":
        try:
            review_id = await wallet_service.record_agent_wallet_review(
                wallet=str(resolved_payload.get("wallet") or ""),
                decision=str(resolved_payload.get("decision") or ""),
                created_by_agent=str(resolved_payload.get("created_by_agent") or "hermes"),
                metrics_snapshot_id=resolved_payload.get("metrics_snapshot_id"),
                agent_rating=_optional_float(resolved_payload.get("agent_rating")),
                copyability_rating=_optional_float(resolved_payload.get("copyability_rating")),
                pnl_quality=str(resolved_payload.get("pnl_quality") or "unknown"),
                winrate_quality=str(resolved_payload.get("winrate_quality") or "unknown"),
                behavior_profile=dict(resolved_payload.get("behavior_profile") or {}),
                why_yes=list(resolved_payload.get("why_yes") or []),
                why_no=list(resolved_payload.get("why_no") or []),
                demotion_triggers=list(resolved_payload.get("demotion_triggers") or []),
                data_sufficiency=str(resolved_payload.get("data_sufficiency") or "insufficient"),
                observed_behavior=dict(resolved_payload.get("observed_behavior") or {}),
                inferred_behavior=dict(resolved_payload.get("inferred_behavior") or {}),
                unknowns=list(resolved_payload.get("unknowns") or []),
                evidence_refs=list(resolved_payload.get("evidence_refs") or []),
            )
        except ValueError as exc:
            return _response(tool_name, ok=False, blocked_reason=str(exc), quality_flags=["invalid_agent_wallet_review"])
        return _response(
            tool_name,
            artifact_id=review_id,
            source_refs=list(resolved_payload.get("evidence_refs") or []),
            data_as_of=isoformat_utc(resolved_clock.now()),
            quality_flags=[],
            confidence="medium",
            next_suggested_tools=["wallet.list_elite"],
        )

    if tool_name == "wallet.list_elite":
        limit = max(1, min(int(resolved_payload.get("limit") or 20), 100))
        rows = await _latest_elite_reviews(resolved_database, limit=limit)
        return _response(
            tool_name,
            source_refs=[row["agent_wallet_review_id"] for row in rows],
            data_as_of=isoformat_utc(resolved_clock.now()),
            quality_flags=[] if rows else ["no_elite_wallets_recorded"],
            confidence="medium" if rows else "unknown",
            next_suggested_tools=["wallet.profile_history", "wallet.record_agent_review"],
            wallets=[_wallet_review_payload(row) for row in rows],
        )

    if tool_name == "wallet.record_signal_event":
        try:
            event_id = await orchestrator.record_tracked_wallet_signal_event(
                wallet=str(resolved_payload.get("wallet") or ""),
                token_mint=str(resolved_payload.get("token_mint") or ""),
                pool_address=resolved_payload.get("pool_address"),
                side=str(resolved_payload.get("side") or ""),
                observed_at=resolved_payload.get("observed_at"),
                source_name=str(resolved_payload.get("source_name") or "hermes_tool"),
                source_refs=list(resolved_payload.get("source_refs") or []),
                latency_metadata=dict(resolved_payload.get("latency_metadata") or {}),
                cluster_refs=list(resolved_payload.get("cluster_refs") or []),
                correlation_refs=list(resolved_payload.get("correlation_refs") or []),
                input_mode=str(resolved_payload.get("input_mode") or "fixture"),
                data_sufficiency=resolved_payload.get("data_sufficiency"),
                quality_flags=list(resolved_payload.get("quality_flags") or []),
            )
        except ValueError as exc:
            return _response(tool_name, ok=False, blocked_reason=str(exc), quality_flags=["invalid_tracked_wallet_signal_event"])
        event = await resolved_database.fetchone(
            "SELECT * FROM tracked_wallet_signal_events WHERE tracked_wallet_signal_event_id = ?",
            (event_id,),
        )
        return _response(
            tool_name,
            artifact_id=event_id,
            source_refs=_loads_list((event or {}).get("source_refs_json")),
            data_as_of=(event or {}).get("observed_at") or isoformat_utc(resolved_clock.now()),
            quality_flags=_loads_list((event or {}).get("quality_flags_json")),
            confidence=_confidence_from_sufficiency((event or {}).get("data_sufficiency")),
            next_suggested_tools=["agent.record_trading_decision"],
            tracked_wallet_signal_event=event,
        )

    if tool_name == "agent.record_trading_decision":
        try:
            decision_id = await orchestrator.record_agent_trading_decision(
                decision_type=str(resolved_payload.get("decision_type") or ""),
                pre_action_reasoning=str(resolved_payload.get("pre_action_reasoning") or ""),
                created_by_agent=str(resolved_payload.get("created_by_agent") or "hermes"),
                active_token_session_id=resolved_payload.get("active_token_session_id"),
                token_refs=list(resolved_payload.get("token_refs") or []),
                wallet_refs=list(resolved_payload.get("wallet_refs") or []),
                market_snapshot_refs=list(resolved_payload.get("market_snapshot_refs") or []),
                source_quality_summary=dict(resolved_payload.get("source_quality_summary") or {}),
                uncertainties=list(resolved_payload.get("uncertainties") or []),
                evidence_refs=list(resolved_payload.get("evidence_refs") or []),
                data_as_of=resolved_payload.get("data_as_of"),
                linked_signal_id=resolved_payload.get("linked_signal_id"),
                linked_no_trade_signal_id=resolved_payload.get("linked_no_trade_signal_id"),
                linked_exit_decision_id=resolved_payload.get("linked_exit_decision_id"),
                linked_outcome_id=resolved_payload.get("linked_outcome_id"),
                linked_tracked_wallet_signal_event_id=resolved_payload.get("linked_tracked_wallet_signal_event_id"),
                quality_flags=list(resolved_payload.get("quality_flags") or []),
            )
        except ValueError as exc:
            return _response(tool_name, ok=False, blocked_reason=str(exc), quality_flags=["invalid_agent_trading_decision"])
        row = await resolved_database.fetchone("SELECT * FROM agent_trading_decisions WHERE agent_trading_decision_id = ?", (decision_id,))
        return _response(
            tool_name,
            artifact_id=decision_id,
            source_refs=_loads_list((row or {}).get("evidence_refs_json")),
            data_as_of=(row or {}).get("data_as_of"),
            quality_flags=_loads_list((row or {}).get("quality_flags_json")),
            confidence=_confidence_from_sufficiency("partial"),
            next_suggested_tools=_next_tools_for_agent_decision((row or {}).get("decision_type")),
            agent_trading_decision=row,
        )

    if tool_name == "signal.create":
        decision_id = str(resolved_payload.get("agent_trading_decision_id") or "")
        if not decision_id:
            return _response(tool_name, ok=False, blocked_reason="agent_trading_decision_id is required", quality_flags=["missing_agent_trading_decision"])
        decision = await _get_agent_decision(resolved_database, decision_id)
        if not decision:
            return _response(tool_name, ok=False, blocked_reason="AgentTradingDecision not found", quality_flags=["missing_agent_trading_decision"])
        try:
            source_refs = _unique(
                list(resolved_payload.get("source_refs") or [])
                + _loads_list(decision.get("evidence_refs_json"))
                + [f"agent_trading_decision:{decision_id}"]
            )
            signal_id = await signal_service.create_signal({**resolved_payload, "source_refs": source_refs})
            thesis_id = None
            thesis_payload = resolved_payload.get("thesis")
            if isinstance(thesis_payload, dict):
                thesis_id = await signal_service.create_trade_thesis(signal_id, thesis_payload)
            await orchestrator.link_decision_artifact(
                agent_trading_decision_id=decision_id,
                artifact_type="signal",
                artifact_id=signal_id,
                relationship="hermes_decision_created_signal",
                evidence_refs=[f"agent_trading_decision:{decision_id}", *source_refs],
            )
        except ValueError as exc:
            return _response(tool_name, ok=False, blocked_reason=str(exc), quality_flags=["signal_create_blocked"])
        return _response(
            tool_name,
            artifact_id=signal_id,
            source_refs=source_refs,
            data_as_of=resolved_payload.get("data_as_of") or decision.get("data_as_of"),
            quality_flags=[],
            confidence=str(resolved_payload.get("confidence") or "unknown"),
            next_suggested_tools=["risk.check_entry"],
            signal_id=signal_id,
            trade_thesis_id=thesis_id,
        )

    if tool_name == "signal.create_no_trade":
        decision_id = str(resolved_payload.get("agent_trading_decision_id") or "")
        if not decision_id:
            return _response(tool_name, ok=False, blocked_reason="agent_trading_decision_id is required", quality_flags=["missing_agent_trading_decision"])
        decision = await _get_agent_decision(resolved_database, decision_id)
        if not decision:
            return _response(tool_name, ok=False, blocked_reason="AgentTradingDecision not found", quality_flags=["missing_agent_trading_decision"])
        try:
            source_refs = _unique(
                list(resolved_payload.get("source_refs") or [])
                + _loads_list(decision.get("evidence_refs_json"))
                + [f"agent_trading_decision:{decision_id}"]
            )
            no_trade_id = await signal_service.create_no_trade_signal({**resolved_payload, "source_refs": source_refs})
            await orchestrator.link_decision_artifact(
                agent_trading_decision_id=decision_id,
                artifact_type="no_trade_signal",
                artifact_id=no_trade_id,
                relationship="hermes_decision_created_no_trade",
                evidence_refs=[f"agent_trading_decision:{decision_id}", *source_refs],
            )
        except ValueError as exc:
            return _response(tool_name, ok=False, blocked_reason=str(exc), quality_flags=["no_trade_create_blocked"])
        return _response(
            tool_name,
            artifact_id=no_trade_id,
            source_refs=source_refs,
            data_as_of=resolved_payload.get("data_as_of") or decision.get("data_as_of"),
            quality_flags=[],
            confidence=str(resolved_payload.get("confidence") or "unknown"),
            next_suggested_tools=["agent.record_trading_decision"],
            no_trade_signal_id=no_trade_id,
        )

    if tool_name == "risk.check_entry":
        try:
            risk_id = await risk_service.run_entry_risk_check(
                signal_id=str(resolved_payload.get("signal_id") or ""),
                market_snapshot_id=resolved_payload.get("market_snapshot_id"),
                risk_limit_snapshot_id=str(resolved_payload.get("risk_limit_snapshot_id") or ""),
                config_snapshot_id=str(resolved_payload.get("config_snapshot_id") or ""),
            )
        except ValueError as exc:
            return _response(tool_name, ok=False, blocked_reason=str(exc), quality_flags=["entry_risk_blocked"])
        risk = await domain.get_risk_check(risk_id)
        passed = bool(risk and int(risk["passed"]) == 1)
        return _response(
            tool_name,
            artifact_id=risk_id,
            source_refs=[str(resolved_payload.get("signal_id") or ""), str(resolved_payload.get("market_snapshot_id") or "")],
            data_as_of=(risk or {}).get("data_as_of"),
            quality_flags=[] if passed else ["entry_risk_vetoed"],
            confidence="high",
            blocked_reason=None if passed else (risk or {}).get("veto_reason"),
            next_suggested_tools=["paper.create_order"] if passed else ["signal.create_no_trade", "agent.record_trading_decision"],
            risk_check=risk,
        )

    if tool_name == "paper.create_order":
        try:
            order_id = await paper_service.create_paper_order(
                signal_id=str(resolved_payload.get("signal_id") or ""),
                risk_check_id=str(resolved_payload.get("risk_check_id") or ""),
                intended_size=_optional_float(resolved_payload.get("intended_size")),
                intended_price_ref=resolved_payload.get("intended_price_ref"),
            )
        except (PaperOrderRejected, ValueError) as exc:
            return _response(tool_name, ok=False, blocked_reason=str(exc), quality_flags=["paper_order_blocked"])
        decision_id = resolved_payload.get("agent_trading_decision_id")
        if decision_id:
            await orchestrator.link_decision_artifact(
                agent_trading_decision_id=str(decision_id),
                artifact_type="paper_order",
                artifact_id=order_id,
                relationship="risk_passed_order_created",
                evidence_refs=[f"risk_check:{resolved_payload.get('risk_check_id')}"],
            )
        return _response(
            tool_name,
            artifact_id=order_id,
            source_refs=[str(resolved_payload.get("signal_id") or ""), str(resolved_payload.get("risk_check_id") or "")],
            data_as_of=isoformat_utc(resolved_clock.now()),
            quality_flags=[],
            confidence="high",
            next_suggested_tools=["paper.simulate_fill"],
        )

    if tool_name == "paper.simulate_fill":
        try:
            fill_id = await paper_service.simulate_entry_fill(
                paper_order_id=str(resolved_payload.get("paper_order_id") or ""),
                market_snapshot_id=str(resolved_payload.get("market_snapshot_id") or ""),
            )
            fill = await resolved_database.fetchone("SELECT * FROM paper_fills WHERE paper_fill_id = ?", (fill_id,))
            position_id = None
            if fill and not fill.get("failed_fill_reason"):
                position_id = await paper_service.open_position_from_fill(paper_fill_id=fill_id)
        except (PaperOrderRejected, ValueError) as exc:
            return _response(tool_name, ok=False, blocked_reason=str(exc), quality_flags=["paper_fill_blocked"])
        decision_id = resolved_payload.get("agent_trading_decision_id")
        if decision_id:
            await orchestrator.link_decision_artifact(
                agent_trading_decision_id=str(decision_id),
                artifact_type="paper_fill",
                artifact_id=fill_id,
                relationship="entry_fill_simulated",
                evidence_refs=[f"paper_order:{resolved_payload.get('paper_order_id')}"],
            )
            if position_id:
                await orchestrator.link_decision_artifact(
                    agent_trading_decision_id=str(decision_id),
                    artifact_type="paper_position",
                    artifact_id=position_id,
                    relationship="entry_fill_opened_position",
                    evidence_refs=[f"paper_fill:{fill_id}"],
                )
        fill = await resolved_database.fetchone("SELECT * FROM paper_fills WHERE paper_fill_id = ?", (fill_id,))
        return _response(
            tool_name,
            artifact_id=fill_id,
            source_refs=[str(resolved_payload.get("paper_order_id") or ""), str(resolved_payload.get("market_snapshot_id") or "")],
            data_as_of=(fill or {}).get("fill_time"),
            quality_flags=["failed_fill"] if fill and fill.get("failed_fill_reason") else [],
            confidence="high" if fill and not fill.get("failed_fill_reason") else "low",
            blocked_reason=(fill or {}).get("failed_fill_reason"),
            next_suggested_tools=["paper.create_exit_decision"] if position_id else ["risk.check_entry"],
            paper_fill=fill,
            paper_position_id=position_id,
        )

    if tool_name == "paper.create_exit_decision":
        try:
            exit_id = await paper_service.create_exit_decision(
                position_id=str(resolved_payload.get("position_id") or ""),
                payload={
                    "market_snapshot_id": resolved_payload.get("market_snapshot_id"),
                    "data_as_of": resolved_payload.get("data_as_of"),
                    "exit_reason": resolved_payload.get("exit_reason"),
                    "exit_trigger": resolved_payload.get("exit_trigger"),
                    "expected_exit_logic": resolved_payload.get("expected_exit_logic"),
                    "created_by": resolved_payload.get("created_by") or "hermes",
                },
            )
        except (PaperOrderRejected, ValueError) as exc:
            return _response(tool_name, ok=False, blocked_reason=str(exc), quality_flags=["exit_decision_blocked"])
        decision_id = resolved_payload.get("agent_trading_decision_id")
        if decision_id:
            await orchestrator.link_decision_artifact(
                agent_trading_decision_id=str(decision_id),
                artifact_type="exit_decision",
                artifact_id=exit_id,
                relationship="hermes_exit_decision_recorded",
                evidence_refs=[f"paper_position:{resolved_payload.get('position_id')}"],
            )
        return _response(
            tool_name,
            artifact_id=exit_id,
            source_refs=[str(resolved_payload.get("position_id") or ""), str(resolved_payload.get("market_snapshot_id") or "")],
            data_as_of=resolved_payload.get("data_as_of") or isoformat_utc(resolved_clock.now()),
            quality_flags=[],
            confidence="medium",
            next_suggested_tools=["risk.check_exit"],
        )

    if tool_name == "risk.check_exit":
        try:
            risk_id = await risk_service.run_exit_risk_check(
                exit_decision_id=str(resolved_payload.get("exit_decision_id") or ""),
                market_snapshot_id=resolved_payload.get("market_snapshot_id"),
                risk_limit_snapshot_id=str(resolved_payload.get("risk_limit_snapshot_id") or ""),
                config_snapshot_id=str(resolved_payload.get("config_snapshot_id") or ""),
            )
        except ValueError as exc:
            return _response(tool_name, ok=False, blocked_reason=str(exc), quality_flags=["exit_risk_blocked"])
        risk = await domain.get_risk_check(risk_id)
        passed = bool(risk and int(risk["passed"]) == 1)
        return _response(
            tool_name,
            artifact_id=risk_id,
            source_refs=[str(resolved_payload.get("exit_decision_id") or ""), str(resolved_payload.get("market_snapshot_id") or "")],
            data_as_of=(risk or {}).get("data_as_of"),
            quality_flags=[] if passed else ["exit_risk_vetoed"],
            confidence="high",
            blocked_reason=None if passed else (risk or {}).get("veto_reason"),
            next_suggested_tools=["paper.execute_exit"] if passed else ["agent.record_trading_decision"],
            risk_check=risk,
        )

    if tool_name == "paper.execute_exit":
        try:
            fill_id = await paper_service.execute_paper_exit(
                exit_decision_id=str(resolved_payload.get("exit_decision_id") or ""),
                risk_check_id=str(resolved_payload.get("risk_check_id") or ""),
            )
            fill = await resolved_database.fetchone("SELECT * FROM paper_fills WHERE paper_fill_id = ?", (fill_id,))
            exit_decision = await resolved_database.fetchone(
                "SELECT * FROM exit_decisions WHERE exit_decision_id = ?",
                (str(resolved_payload.get("exit_decision_id") or ""),),
            )
            outcome_id = None
            if fill and not fill.get("failed_fill_reason") and exit_decision:
                outcome_id = await evaluation_service.calculate_trade_outcome(position_id=str(exit_decision["position_id"]))
        except (PaperOrderRejected, OutcomeRejected, ValueError) as exc:
            return _response(tool_name, ok=False, blocked_reason=str(exc), quality_flags=["exit_execution_blocked"])
        decision_id = resolved_payload.get("agent_trading_decision_id")
        if decision_id:
            await orchestrator.link_decision_artifact(
                agent_trading_decision_id=str(decision_id),
                artifact_type="paper_fill",
                artifact_id=fill_id,
                relationship="exit_fill_simulated",
                evidence_refs=[f"exit_decision:{resolved_payload.get('exit_decision_id')}", f"risk_check:{resolved_payload.get('risk_check_id')}"],
            )
            if outcome_id:
                await orchestrator.link_decision_artifact(
                    agent_trading_decision_id=str(decision_id),
                    artifact_type="trade_outcome",
                    artifact_id=outcome_id,
                    relationship="deterministic_outcome_calculated",
                    evidence_refs=[f"paper_fill:{fill_id}"],
                )
        return _response(
            tool_name,
            artifact_id=fill_id,
            source_refs=[str(resolved_payload.get("exit_decision_id") or ""), str(resolved_payload.get("risk_check_id") or "")],
            data_as_of=(fill or {}).get("fill_time") if (fill := await resolved_database.fetchone("SELECT * FROM paper_fills WHERE paper_fill_id = ?", (fill_id,))) else None,
            quality_flags=["failed_exit_fill"] if fill and fill.get("failed_fill_reason") else [],
            confidence="high" if outcome_id else "low",
            blocked_reason=(fill or {}).get("failed_fill_reason") if fill else None,
            next_suggested_tools=["review.create_post_trade", "metrics.wallet_report"] if outcome_id else ["risk.check_exit"],
            exit_fill_id=fill_id,
            trade_outcome_id=outcome_id,
        )

    if tool_name == "review.create_post_trade":
        try:
            review_id = await review_service.create_post_trade_review(
                outcome_id=str(resolved_payload.get("outcome_id") or ""),
                reviewer=str(resolved_payload.get("reviewer") or "hermes"),
                thesis_expected=dict(resolved_payload.get("thesis_expected") or {}),
                actual_result=dict(resolved_payload.get("actual_result") or {}),
                source_quality_issues=list(resolved_payload.get("source_quality_issues") or []),
                exit_matched_plan=resolved_payload.get("exit_matched_plan"),
                lessons=list(resolved_payload.get("lessons") or []),
                proposed_mutation_refs=list(resolved_payload.get("proposed_mutation_refs") or []),
                memory_proposal_refs=list(resolved_payload.get("memory_proposal_refs") or []),
                evidence_refs=list(resolved_payload.get("evidence_refs") or []),
                hindsight_claims=list(resolved_payload.get("hindsight_claims") or []),
            )
        except ValueError as exc:
            return _response(tool_name, ok=False, blocked_reason=str(exc), quality_flags=["post_trade_review_blocked"])
        decision_id = resolved_payload.get("agent_trading_decision_id")
        if decision_id:
            await orchestrator.link_decision_artifact(
                agent_trading_decision_id=str(decision_id),
                artifact_type="post_trade_review",
                artifact_id=review_id,
                relationship="post_trade_review_created",
                evidence_refs=[f"trade_outcome:{resolved_payload.get('outcome_id')}"],
            )
        return _response(
            tool_name,
            artifact_id=review_id,
            source_refs=[str(resolved_payload.get("outcome_id") or ""), *list(resolved_payload.get("evidence_refs") or [])],
            data_as_of=isoformat_utc(resolved_clock.now()),
            quality_flags=[],
            confidence="medium",
            next_suggested_tools=["memory.propose"],
        )

    if tool_name == "memory.propose":
        try:
            proposal_id = await memory_service.propose_memory(
                claim=str(resolved_payload.get("claim") or ""),
                memory_type=str(resolved_payload.get("memory_type") or "lesson"),
                evidence_refs=list(resolved_payload.get("evidence_refs") or []),
                review_refs=list(resolved_payload.get("review_refs") or []),
                strategy_refs=list(resolved_payload.get("strategy_refs") or []),
                confidence=str(resolved_payload.get("confidence") or "unknown"),
                validity_scope=dict(resolved_payload.get("validity_scope") or {}),
                created_by=str(resolved_payload.get("created_by") or "hermes"),
            )
        except ValueError as exc:
            return _response(tool_name, ok=False, blocked_reason=str(exc), quality_flags=["memory_proposal_blocked"])
        decision_id = resolved_payload.get("agent_trading_decision_id")
        if decision_id:
            await orchestrator.link_decision_artifact(
                agent_trading_decision_id=str(decision_id),
                artifact_type="memory_proposal",
                artifact_id=proposal_id,
                relationship="memory_proposal_created",
                evidence_refs=list(resolved_payload.get("evidence_refs") or []) + list(resolved_payload.get("review_refs") or []),
            )
        return _response(
            tool_name,
            artifact_id=proposal_id,
            source_refs=list(resolved_payload.get("evidence_refs") or []) + list(resolved_payload.get("review_refs") or []),
            data_as_of=isoformat_utc(resolved_clock.now()),
            quality_flags=[],
            confidence=str(resolved_payload.get("confidence") or "unknown"),
            next_suggested_tools=["metrics.wallet_report"],
        )

    if tool_name == "metrics.wallet_report":
        try:
            report = await orchestrator.create_wallet_contribution_report(
                wallet=str(resolved_payload.get("wallet") or ""),
                strategy_version_id=resolved_payload.get("strategy_version_id"),
                window_start=resolved_payload.get("window_start"),
                window_end=resolved_payload.get("window_end"),
            )
        except ValueError as exc:
            return _response(tool_name, ok=False, blocked_reason=str(exc), quality_flags=["wallet_report_blocked"])
        decision_id = resolved_payload.get("agent_trading_decision_id")
        if decision_id:
            await orchestrator.link_decision_artifact(
                agent_trading_decision_id=str(decision_id),
                artifact_type="wallet_contribution_report",
                artifact_id=report["wallet_contribution_report_id"],
                relationship="wallet_contribution_report_created",
                evidence_refs=report.get("evidence_refs", []),
            )
        return _response(
            tool_name,
            artifact_id=report["wallet_contribution_report_id"],
            source_refs=report.get("evidence_refs", []),
            data_as_of=isoformat_utc(resolved_clock.now()),
            quality_flags=report.get("quality_flags", []),
            confidence=_confidence_from_sufficiency(report.get("data_sufficiency")),
            blocked_reason="insufficient forward evidence" if report.get("data_sufficiency") == "insufficient" else None,
            next_suggested_tools=["review.create_post_trade"] if report.get("data_sufficiency") == "insufficient" else [],
            wallet_report=report,
        )

    return _response(tool_name, ok=False, blocked_reason=f"unknown V2 Hermes tool: {tool_name}", quality_flags=["unknown_tool"])


def _response(
    tool_name: str,
    *,
    ok: bool = True,
    artifact_id: str | None = None,
    job_id: str | None = None,
    source_refs: list[Any] | None = None,
    data_as_of: Any = None,
    quality_flags: list[Any] | None = None,
    confidence: str = "unknown",
    blocked_reason: str | None = None,
    next_suggested_tools: list[str] | None = None,
    **extra: Any,
) -> dict[str, Any]:
    return {
        "tool": tool_name,
        "ok": ok,
        "artifact_id": artifact_id,
        "job_id": job_id,
        "source_refs": [str(ref) for ref in (source_refs or []) if ref],
        "data_as_of": data_as_of,
        "quality_flags": [str(flag) for flag in (quality_flags or []) if flag],
        "confidence": confidence,
        "blocked_reason": blocked_reason,
        "next_suggested_tools": next_suggested_tools or [],
        **extra,
    }


async def _get_token_profile(
    database: Stage2Database,
    *,
    token_profile_id: Any = None,
    token_mint: Any = None,
) -> dict[str, Any] | None:
    if token_profile_id:
        return await database.fetchone("SELECT * FROM token_profiles WHERE token_profile_id = ?", (str(token_profile_id),))
    if token_mint:
        return await database.fetchone(
            """
            SELECT *
            FROM token_profiles
            WHERE token_mint = ?
            ORDER BY latest_observed_at DESC, created_at DESC
            LIMIT 1
            """,
            (str(token_mint),),
        )
    return None


async def _latest_wallet_metric(database: Stage2Database, wallet: str) -> dict[str, Any] | None:
    return await database.fetchone(
        """
        SELECT *
        FROM wallet_metric_snapshots
        WHERE wallet = ?
        ORDER BY calculated_at DESC, created_at DESC
        LIMIT 1
        """,
        (wallet,),
    )


async def _latest_elite_reviews(database: Stage2Database, *, limit: int) -> list[dict[str, Any]]:
    return await database.fetchall(
        """
        SELECT r.*
        FROM agent_wallet_reviews r
        JOIN (
          SELECT wallet, MAX(created_at) AS max_created_at
          FROM agent_wallet_reviews
          GROUP BY wallet
        ) latest ON latest.wallet = r.wallet AND latest.max_created_at = r.created_at
        WHERE r.decision IN ('elite', 'probation')
        ORDER BY COALESCE(r.agent_rating, 0) DESC, r.created_at DESC
        LIMIT ?
        """,
        (limit,),
    )


async def _get_agent_decision(database: Stage2Database, agent_trading_decision_id: str) -> dict[str, Any] | None:
    return await database.fetchone(
        "SELECT * FROM agent_trading_decisions WHERE agent_trading_decision_id = ?",
        (agent_trading_decision_id,),
    )


def _next_tools_for_agent_decision(decision_type: Any) -> list[str]:
    if decision_type == "signal":
        return ["signal.create", "risk.check_entry"]
    if decision_type == "no_trade":
        return ["signal.create_no_trade"]
    if decision_type == "exit":
        return ["paper.create_exit_decision", "risk.check_exit"]
    if decision_type in {"wait", "downgrade_wallet", "downgrade_token"}:
        return ["metrics.wallet_report", "agent.record_trading_decision"]
    return []


def _token_profile_payload(row: dict[str, Any]) -> dict[str, Any]:
    unknown_fields = [
        "route_quality",
        "spread",
        "volume_growth_windows",
        "transaction_growth_windows",
        "buy_sell_balance",
    ]
    return {
        "token_profile_id": row.get("token_profile_id"),
        "token_mint": row.get("token_mint"),
        "pool_address": row.get("pool_address"),
        "market_cap": row.get("market_cap"),
        "fdv": row.get("fdv"),
        "liquidity_usd": row.get("liquidity_usd"),
        "route_quality": None,
        "spread": None,
        "volume_24h": row.get("volume_24h"),
        "volume_growth_windows": {
            "24h": row.get("volume_24h"),
            "5m": None,
            "1h": None,
            "6h": None,
        },
        "txns_1h": row.get("txns_1h"),
        "transaction_growth_windows": {
            "1h": row.get("txns_1h"),
            "5m": None,
            "6h": None,
            "24h": None,
        },
        "buy_sell_balance": None,
        "holder_count": row.get("holder_count"),
        "top_holder_concentration": row.get("top_holder_concentration"),
        "tradeability_summary": {
            "evidence_quality": row.get("evidence_quality"),
            "degradation_status": row.get("degradation_status"),
            "eligible_for_high_confidence_evaluation": bool(row.get("eligible_for_high_confidence_evaluation")),
        },
        "source_freshness": row.get("latest_observed_at"),
        "source_quality": row.get("evidence_quality"),
        "data_sufficiency": "partial" if row.get("token_mint") else "insufficient",
        "unknown_fields": [field for field in unknown_fields if row.get(field) is None],
    }


def _wallet_metric_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "wallet_metric_snapshot_id": row.get("wallet_metric_snapshot_id"),
        "wallet": row.get("wallet"),
        "trade_count": row.get("trade_count"),
        "closed_trade_count": row.get("closed_trade_count"),
        "realized_pnl_estimate": row.get("realized_pnl_estimate"),
        "net_pnl_estimate": row.get("net_pnl_estimate"),
        "win_rate_estimate": row.get("win_rate_estimate"),
        "expectancy_estimate": row.get("expectancy_estimate"),
        "payoff_ratio": row.get("payoff_ratio"),
        "average_win": row.get("average_win"),
        "average_loss": row.get("average_loss"),
        "holding_time_summary": _loads_dict(row.get("holding_time_summary_json")),
        "position_sizing_summary": _loads_dict(row.get("position_sizing_summary_json")),
        "sample_size": row.get("sample_size"),
        "source_quality": row.get("evidence_quality"),
        "candidate_evidence_only": bool(row.get("candidate_evidence_only")),
    }


def _wallet_review_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "agent_wallet_review_id": row.get("agent_wallet_review_id"),
        "wallet": row.get("wallet"),
        "decision": row.get("decision"),
        "agent_rating": row.get("agent_rating"),
        "copyability_rating": row.get("copyability_rating"),
        "pnl_quality": row.get("pnl_quality"),
        "winrate_quality": row.get("winrate_quality"),
        "data_sufficiency": row.get("data_sufficiency"),
        "why_yes": _loads_list(row.get("why_yes_json")),
        "why_no": _loads_list(row.get("why_no_json")),
        "unknowns": _loads_list(row.get("unknowns_json")),
        "demotion_triggers": _loads_list(row.get("demotion_triggers_json")),
        "created_at": row.get("created_at"),
        "created_by_agent": row.get("created_by_agent"),
    }


def _loads_list(raw: Any) -> list[Any]:
    if not raw:
        return []
    parsed = json.loads(raw) if isinstance(raw, str) else raw
    return parsed if isinstance(parsed, list) else []


def _loads_dict(raw: Any) -> dict[str, Any]:
    if not raw:
        return {}
    parsed = json.loads(raw) if isinstance(raw, str) else raw
    return parsed if isinstance(parsed, dict) else {}


def _unique(values: list[Any]) -> list[str]:
    result: list[str] = []
    for value in values:
        text = str(value)
        if text and text not in result:
            result.append(text)
    return result


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _confidence_from_sufficiency(data_sufficiency: Any) -> str:
    if data_sufficiency == "sufficient":
        return "medium"
    if data_sufficiency == "partial":
        return "low"
    return "unknown"
