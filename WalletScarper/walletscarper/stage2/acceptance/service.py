from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from walletscarper.stage2.clock import Clock, FixedClock, SystemClock, isoformat_utc
from walletscarper.stage2.config import Stage2Settings
from walletscarper.stage2.config_snapshots import ConfigSnapshotRepository
from walletscarper.stage2.db import Stage2Database
from walletscarper.stage2.db.json import dumps_json
from walletscarper.stage2.domain import DomainRepository
from walletscarper.stage2.evaluation import DeterministicEvaluationService
from walletscarper.stage2.events import RawSourceEventLog
from walletscarper.stage2.evidence import EvidenceNormalizer
from walletscarper.stage2.ids import new_id
from walletscarper.stage2.legacy_ingestion import map_dexpaprika_payload, map_dexscreener_payload, write_raw_source_event
from walletscarper.stage2.memory import MemoryService
from walletscarper.stage2.monitoring import MonitoringService
from walletscarper.stage2.paper_trading import Sprint3PaperTradingService
from walletscarper.stage2.reports import Sprint4ReportService
from walletscarper.stage2.reviews import PostTradeReviewService
from walletscarper.stage2.risk import DeterministicRiskService
from walletscarper.stage2.shadow_readiness import LiveDataAcceptanceWindowService
from walletscarper.stage2.signals import SignalService
from walletscarper.stage2.sources import SourceHealthService
from walletscarper.stage2.strategy import StrategyResearchService
from walletscarper.stage2.token_intelligence import TokenIntelligenceService
from walletscarper.stage2.wallet_intelligence import WalletIntelligenceService
from walletscarper.stage2.workers import WorkerPoolService


def _loads(raw: str | None, default: Any) -> Any:
    if not raw:
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return default


def _now(clock: Clock | None) -> datetime:
    return (clock or SystemClock()).now().astimezone(timezone.utc)


def _as_float(value: Any, default: float = 0.0) -> float:
    if value in {None, ""}:
        return default
    return float(value)


@dataclass(frozen=True)
class InvariantFinding:
    invariant_name: str
    severity: str
    description: str
    remediation_hint: str
    entity_refs: dict[str, Any]


class InvariantChecker:
    """Final acceptance invariant checks.

    The checker is intentionally conservative. It records append-only violation
    rows and does not repair or rewrite source-of-truth state.
    """

    def __init__(self, database: Stage2Database, *, clock: Clock | None = None):
        self.database = database
        self.clock = clock or SystemClock()

    async def run_all(
        self,
        *,
        acceptance_run_id: str | None = None,
        package_root: Path | None = None,
        record: bool = True,
    ) -> dict[str, Any]:
        package_root = package_root or Path(__file__).resolve().parents[2]
        findings: list[InvariantFinding] = []
        findings.extend(self._scan_runtime_source(package_root))
        findings.extend(self._scan_hermes_boundary(package_root))
        findings.extend(await self._risk_authority())
        findings.extend(await self._outcome_authority())
        findings.extend(await self._signal_risk_order_sequence())
        findings.extend(await self._fill_and_exit_sequence())
        findings.extend(await self._evidence_boundaries())
        findings.extend(await self._strategy_boundaries())
        findings.extend(await self._worker_and_session_boundaries())
        findings.extend(await self._conflict_memory_boundaries())

        ids: list[str] = []
        if record:
            for finding in findings:
                ids.append(await self.record_violation(acceptance_run_id=acceptance_run_id, finding=finding))

        critical = sum(1 for finding in findings if finding.severity == "critical")
        warning = sum(1 for finding in findings if finding.severity == "warning")
        return {
            "status": "failed" if critical else "passed",
            "finding_count": len(findings),
            "critical_count": critical,
            "warning_count": warning,
            "recorded_ids": ids,
            "findings": [
                {
                    "invariant_name": finding.invariant_name,
                    "severity": finding.severity,
                    "description": finding.description,
                    "entity_refs": finding.entity_refs,
                }
                for finding in findings
            ],
        }

    async def record_violation(self, *, acceptance_run_id: str | None, finding: InvariantFinding) -> str:
        violation_id = new_id("invariant_violation")
        await self.database.execute(
            """
            INSERT INTO invariant_violations(
              invariant_violation_id, acceptance_run_id, invariant_name, severity,
              entity_refs_json, detected_at, description, remediation_hint, status,
              metadata_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'open', ?)
            """,
            (
                violation_id,
                acceptance_run_id,
                finding.invariant_name,
                finding.severity,
                dumps_json(finding.entity_refs),
                isoformat_utc(self.clock.now()),
                finding.description,
                finding.remediation_hint,
                dumps_json({}),
            ),
        )
        return violation_id

    def _scan_runtime_source(self, package_root: Path) -> list[InvariantFinding]:
        terms = [
            "_".join(["private", "key"]),
            "_".join(["secret", "key"]),
            "seed" + " phrase",
            "sign" + "Transaction",
            "send" + "Transaction",
            "Versioned" + "Transaction",
            ("swa" + "p") + " adapter",
            "dex" + " transaction",
            "jup" + "iter",
            "ray" + "dium",
        ]
        ignored = {"__pycache__", ".pytest_cache"}
        findings: list[InvariantFinding] = []
        for path in package_root.rglob("*.py"):
            if any(part in ignored for part in path.parts):
                continue
            text = path.read_text(encoding="utf-8", errors="ignore").lower()
            matched = [term for term in terms if term.lower() in text]
            if matched:
                findings.append(
                    InvariantFinding(
                        "no_live_or_credential_material_path",
                        "critical",
                        f"Runtime source contains prohibited terminology in {path.name}.",
                        "Remove or quarantine the path before release acceptance.",
                        {"file": str(path), "matched_terms": matched},
                    )
                )
        return findings

    def _scan_hermes_boundary(self, package_root: Path) -> list[InvariantFinding]:
        hermes_dir = package_root / "stage2" / "hermes_integration"
        if not hermes_dir.exists():
            return []
        findings: list[InvariantFinding] = []
        for path in hermes_dir.rglob("*.py"):
            text = path.read_text(encoding="utf-8", errors="ignore")
            matched = [term for term in ("INSERT ", "UPDATE ", "DELETE ", ".execute(") if term in text]
            if matched:
                findings.append(
                    InvariantFinding(
                        "hermes_boundary_is_read_only",
                        "critical",
                        "Hermes integration contains direct database mutation surface.",
                        "Expose only typed deterministic service boundaries to Hermes.",
                        {"file": str(path), "matched_terms": matched},
                    )
                )
        return findings

    async def _risk_authority(self) -> list[InvariantFinding]:
        rows = await self.database.fetchall(
            "SELECT risk_check_id, created_by_service FROM risk_checks WHERE created_by_service != 'risk_service'"
        )
        return [
            InvariantFinding(
                "authoritative_risk_checks_are_deterministic",
                "critical",
                "RiskCheck was not created by the deterministic risk service.",
                "Recreate risk state through Risk Service only.",
                dict(row),
            )
            for row in rows
        ]

    async def _outcome_authority(self) -> list[InvariantFinding]:
        rows = await self.database.fetchall(
            "SELECT outcome_id, calculated_by_service FROM trade_outcomes WHERE calculated_by_service != 'evaluation_service'"
        )
        return [
            InvariantFinding(
                "canonical_pnl_is_deterministic",
                "critical",
                "TradeOutcome was not calculated by the deterministic evaluation service.",
                "Recompute canonical outcome through Evaluation Service only.",
                dict(row),
            )
            for row in rows
        ]

    async def _signal_risk_order_sequence(self) -> list[InvariantFinding]:
        findings: list[InvariantFinding] = []
        bad_entry_risk = await self.database.fetchall(
            """
            SELECT r.risk_check_id, r.subject_id
            FROM risk_checks r
            LEFT JOIN signals s ON s.signal_id = r.subject_id
            WHERE r.check_scope = 'entry'
              AND r.subject_type = 'signal'
              AND (s.signal_id IS NULL OR s.created_at > r.created_at)
            """
        )
        for row in bad_entry_risk:
            findings.append(
                InvariantFinding(
                    "signal_exists_before_entry_risk",
                    "critical",
                    "Entry risk check has missing or later-created Signal.",
                    "Reject no-hindsight risk checks.",
                    dict(row),
                )
            )

        orders = await self.database.fetchall(
            """
            SELECT o.*, r.check_scope, r.subject_type, r.subject_id, r.passed,
                   r.created_by_service, r.created_at AS risk_created_at,
                   t.thesis_id, t.created_at AS thesis_created_at
            FROM paper_orders o
            LEFT JOIN risk_checks r ON r.risk_check_id = o.risk_check_id
            LEFT JOIN trade_theses t ON t.signal_id = o.signal_id
            """
        )
        for row in orders:
            refs = {"paper_order_id": row["paper_order_id"], "signal_id": row["signal_id"], "risk_check_id": row["risk_check_id"]}
            if not row["thesis_id"] or row["thesis_created_at"] > row["created_at"]:
                findings.append(
                    InvariantFinding(
                        "trade_thesis_exists_before_paper_order",
                        "critical",
                        "PaperOrder does not have a prior TradeThesis.",
                        "Require thesis before paper order.",
                        refs,
                    )
                )
            if row["side"] == "buy":
                risk_bad = (
                    row["check_scope"] != "entry"
                    or row["subject_type"] != "signal"
                    or row["subject_id"] != row["signal_id"]
                    or int(row["passed"] or 0) != 1
                    or row["created_by_service"] != "risk_service"
                    or row["risk_created_at"] > row["created_at"]
                )
                if risk_bad:
                    findings.append(
                        InvariantFinding(
                            "entry_risk_passes_before_paper_order",
                            "critical",
                            "Buy PaperOrder is not backed by prior passed authoritative entry risk.",
                            "Create orders only through guarded Paper Trading Service.",
                            refs,
                        )
                    )
        return findings

    async def _fill_and_exit_sequence(self) -> list[InvariantFinding]:
        findings: list[InvariantFinding] = []
        missing_fill_costs = await self.database.fetchall(
            """
            SELECT paper_fill_id, paper_order_id
            FROM paper_fills
            WHERE failed_fill_reason IS NULL
              AND (fees IS NULL OR slippage IS NULL OR latency_assumption IS NULL OR liquidity_constraint IS NULL)
            """
        )
        for row in missing_fill_costs:
            findings.append(
                InvariantFinding(
                    "paper_fills_include_cost_latency_liquidity",
                    "critical",
                    "Successful PaperFill lacks fee, slippage, latency, or liquidity metadata.",
                    "Use conservative fill simulation.",
                    dict(row),
                )
            )
        if not await self.database.fetchone("SELECT paper_fill_id FROM paper_fills WHERE failed_fill_reason IS NOT NULL LIMIT 1"):
            findings.append(
                InvariantFinding(
                    "failed_fills_are_visible",
                    "warning",
                    "No failed fill is present in this database.",
                    "Acceptance replay should include explicit failed fill evidence.",
                    {},
                )
            )

        exit_rows = await self.database.fetchall(
            """
            SELECT pf.paper_fill_id, pf.fill_time, po.paper_order_id, rc.risk_check_id,
                   rc.check_scope, rc.subject_id, rc.passed, ed.exit_decision_id,
                   ed.created_at AS exit_created_at
            FROM paper_fills pf
            JOIN paper_orders po ON po.paper_order_id = pf.paper_order_id
            LEFT JOIN risk_checks rc ON rc.risk_check_id = po.risk_check_id
            LEFT JOIN exit_decisions ed ON ed.exit_decision_id = rc.subject_id
            WHERE po.side = 'sell'
            """
        )
        for row in exit_rows:
            bad = (
                row["check_scope"] != "exit"
                or int(row["passed"] or 0) != 1
                or not row["exit_decision_id"]
                or row["exit_created_at"] > row["fill_time"]
            )
            if bad:
                findings.append(
                    InvariantFinding(
                        "exit_decision_and_exit_risk_before_exit_fill",
                        "critical",
                        "Exit fill is not backed by prior ExitDecision and passed exit risk.",
                        "Execute paper exits only through the guarded exit service.",
                        dict(row),
                    )
                )
        return findings

    async def _evidence_boundaries(self) -> list[InvariantFinding]:
        findings: list[InvariantFinding] = []
        missing_raw = await self.database.fetchall(
            """
            SELECT normalized_evidence_ref_id, raw_source_event_id
            FROM normalized_evidence_refs
            WHERE raw_source_event_id NOT IN (SELECT raw_source_event_id FROM raw_source_events)
            """
        )
        for row in missing_raw:
            findings.append(
                InvariantFinding(
                    "raw_events_precede_derived_evidence",
                    "critical",
                    "Normalized evidence references a missing RawSourceEvent.",
                    "Rebuild derived evidence from append-only raw events.",
                    dict(row),
                )
            )
        browser_rows = await self.database.fetchall(
            "SELECT browser_extraction_id FROM browser_extractions WHERE eligible_for_high_confidence_evaluation != 0"
        )
        for row in browser_rows:
            findings.append(
                InvariantFinding(
                    "browser_data_is_non_canonical",
                    "critical",
                    "Browser extraction is marked high-confidence evaluation eligible.",
                    "Keep browser data contextual unless independently verified.",
                    dict(row),
                )
            )
        wallet_metrics = await self.database.fetchall(
            "SELECT wallet_metric_snapshot_id FROM wallet_metric_snapshots WHERE candidate_evidence_only != 1"
        )
        for row in wallet_metrics:
            findings.append(
                InvariantFinding(
                    "wallet_metrics_are_candidate_evidence_only",
                    "critical",
                    "Wallet metric snapshot is not marked candidate-evidence-only.",
                    "Do not use historical wallet profitability as strategy proof.",
                    dict(row),
                )
            )
        return findings

    async def _strategy_boundaries(self) -> list[InvariantFinding]:
        findings: list[InvariantFinding] = []
        missing_strategy_config = await self.database.fetchall(
            "SELECT strategy_version_id FROM strategy_versions WHERE strategy_config_snapshot_id IS NULL"
        )
        for row in missing_strategy_config:
            findings.append(
                InvariantFinding(
                    "strategy_version_references_config_snapshot",
                    "critical",
                    "StrategyVersion lacks immutable config snapshot reference.",
                    "Create StrategyVersions with StrategyConfigSnapshot linkage.",
                    dict(row),
                )
            )
        bad_decisions = await self.database.fetchall(
            """
            SELECT strategy_decision_id, decision_type
            FROM strategy_decisions
            WHERE promotion_criteria_snapshot_id IS NULL
               OR metrics_snapshot_id IS NULL
               OR (decision_type = 'promote' AND metrics_snapshot_id IS NULL)
            """
        )
        for row in bad_decisions:
            findings.append(
                InvariantFinding(
                    "strategy_decisions_require_metrics_and_criteria",
                    "critical",
                    "Strategy decision lacks deterministic metrics or versioned criteria.",
                    "Fail closed until metrics and criteria snapshot exist.",
                    dict(row),
                )
            )
        return findings

    async def _worker_and_session_boundaries(self) -> list[InvariantFinding]:
        findings: list[InvariantFinding] = []
        now_iso = isoformat_utc(self.clock.now())
        expired = await self.database.fetchall(
            """
            SELECT wl.worker_lease_id, wl.job_id
            FROM worker_leases wl
            JOIN jobs j ON j.job_id = wl.job_id
            WHERE j.status = 'running' AND wl.lease_expires_at <= ?
            """,
            (now_iso,),
        )
        for row in expired:
            findings.append(
                InvariantFinding(
                    "worker_leases_expire_safely",
                    "warning",
                    "Expired running worker lease is visible.",
                    "Run worker lease expiry recovery before long acceptance windows.",
                    dict(row),
                )
            )
        duplicate_sessions = await self.database.fetchall(
            """
            SELECT subject_type, subject_id, COUNT(*) AS count
            FROM monitoring_sessions
            WHERE status IN ('queued', 'active', 'waiting')
            GROUP BY subject_type, subject_id
            HAVING count > 1
            """
        )
        for row in duplicate_sessions:
            findings.append(
                InvariantFinding(
                    "max_parallel_sessions_are_enforced",
                    "critical",
                    "Duplicate active monitoring sessions target the same subject.",
                    "Route duplicates into conflict review.",
                    dict(row),
                )
            )
        unmonitored = await self.database.fetchall(
            """
            SELECT pp.position_id
            FROM paper_positions pp
            LEFT JOIN trade_outcomes tout ON tout.position_id = pp.position_id
            LEFT JOIN monitoring_sessions ms
              ON ms.subject_type = 'paper_position'
             AND ms.subject_id = pp.position_id
             AND ms.status IN ('queued', 'active', 'waiting', 'blocked')
            WHERE tout.outcome_id IS NULL
              AND ms.monitoring_session_id IS NULL
            """
        )
        for row in unmonitored:
            findings.append(
                InvariantFinding(
                    "open_positions_outrank_discovery",
                    "critical",
                    "Open paper position is not monitored.",
                    "Restore paper-position monitoring before new discovery.",
                    dict(row),
                )
            )
        return findings

    async def _conflict_memory_boundaries(self) -> list[InvariantFinding]:
        findings: list[InvariantFinding] = []
        rewrite_conflicts = await self.database.fetchall(
            """
            SELECT conflict_review_id
            FROM conflict_reviews
            WHERE status = 'resolved'
              AND resolution LIKE '%rewrite%'
            """
        )
        for row in rewrite_conflicts:
            findings.append(
                InvariantFinding(
                    "conflicts_do_not_rewrite_history",
                    "critical",
                    "Conflict review resolution appears to rewrite history.",
                    "Resolve by append-only correction or supersession.",
                    dict(row),
                )
            )
        triggers = {row["name"] for row in await self.database.fetchall("SELECT name FROM sqlite_master WHERE type = 'trigger'")}
        for table in ("signals", "trade_theses", "risk_checks", "paper_orders", "paper_fills", "exit_decisions", "trade_outcomes"):
            if f"prevent_update_{table}" not in triggers:
                findings.append(
                    InvariantFinding(
                        "critical_records_are_append_only",
                        "critical",
                        f"Append-only trigger missing for {table}.",
                        "Add immutable protection before release acceptance.",
                        {"table": table},
                    )
                )
        return findings


class OperationalHealthService:
    def __init__(self, database: Stage2Database, *, clock: Clock | None = None):
        self.database = database
        self.clock = clock or SystemClock()

    async def current_summary(self, *, acceptance_run_id: str | None = None) -> dict[str, Any]:
        now = self.clock.now()
        stale_cutoff = isoformat_utc(now - timedelta(minutes=15))
        latest_sources = await self.database.fetchall(
            """
            SELECT sh.*
            FROM source_health_snapshots sh
            JOIN (
              SELECT source_name, MAX(observed_at) AS observed_at
              FROM source_health_snapshots
              GROUP BY source_name
            ) latest ON latest.source_name = sh.source_name AND latest.observed_at = sh.observed_at
            """
        )
        queue_depth = (await self.database.fetchone("SELECT COUNT(*) AS count FROM jobs WHERE status = 'pending'"))["count"]
        queue_metrics = await WorkerPoolService(self.database, clock=self.clock).queue_metrics()
        failed_jobs = (await self.database.fetchone("SELECT COUNT(*) AS count FROM jobs WHERE status = 'failed'"))["count"]
        active_sessions = (await self.database.fetchone("SELECT COUNT(*) AS count FROM monitoring_sessions WHERE status = 'active'"))["count"]
        blocked_sessions = (await self.database.fetchone("SELECT COUNT(*) AS count FROM monitoring_sessions WHERE status = 'blocked'"))["count"]
        open_positions = (
            await self.database.fetchone(
                """
                SELECT COUNT(*) AS count
                FROM paper_positions pp
                LEFT JOIN trade_outcomes tout ON tout.position_id = pp.position_id
                WHERE tout.outcome_id IS NULL
                """
            )
        )["count"]
        unmonitored = (
            await self.database.fetchone(
                """
                SELECT COUNT(*) AS count
                FROM paper_positions pp
                LEFT JOIN trade_outcomes tout ON tout.position_id = pp.position_id
                LEFT JOIN monitoring_sessions ms
                  ON ms.subject_type = 'paper_position'
                 AND ms.subject_id = pp.position_id
                 AND ms.status IN ('queued', 'active', 'waiting', 'blocked')
                WHERE tout.outcome_id IS NULL
                  AND ms.monitoring_session_id IS NULL
                """
            )
        )["count"]
        missed_exit_risk = (
            await self.database.fetchone(
                """
                SELECT COUNT(*) AS count
                FROM exit_decisions ed
                LEFT JOIN risk_checks rc
                  ON rc.subject_type = 'exit_decision'
                 AND rc.subject_id = ed.exit_decision_id
                 AND rc.check_scope = 'exit'
                WHERE rc.risk_check_id IS NULL
                """
            )
        )["count"]
        failed_fills = (await self.database.fetchone("SELECT COUNT(*) AS count FROM paper_fills WHERE failed_fill_reason IS NOT NULL"))[
            "count"
        ]
        risk_vetoes = (await self.database.fetchone("SELECT COUNT(*) AS count FROM risk_checks WHERE passed = 0"))["count"]
        outcomes = await self.database.fetchall("SELECT net_pnl FROM trade_outcomes ORDER BY calculated_at")
        net_values = [_as_float(row["net_pnl"]) for row in outcomes]
        net_pnl = sum(net_values)
        expectancy = net_pnl / len(net_values) if net_values else None
        drawdown = self._drawdown(net_values)
        sprint4 = await Sprint4ReportService(self.database, clock=self.clock).snapshot()
        latency_summary = await self._latency_summary()
        shadow_readiness = await self._shadow_readiness_summary()
        critical = (
            await self.database.fetchone(
                """
                SELECT COUNT(*) AS count
                FROM invariant_violations
                WHERE severity = 'critical'
                  AND (? IS NULL OR acceptance_run_id = ?)
                """,
                (acceptance_run_id, acceptance_run_id),
            )
        )["count"]
        memory_review = {
            "post_trade_reviews": (await self.database.fetchone("SELECT COUNT(*) AS count FROM post_trade_reviews"))["count"],
            "memory_proposals": (await self.database.fetchone("SELECT COUNT(*) AS count FROM memory_proposals"))["count"],
            "memory_entries": (await self.database.fetchone("SELECT COUNT(*) AS count FROM memory_entries"))["count"],
        }
        warnings: list[str] = []
        degraded = sum(1 for row in latest_sources if row["status"] == "degraded")
        unavailable = sum(1 for row in latest_sources if row["status"] == "unavailable")
        stale = sum(1 for row in latest_sources if row.get("last_successful_event_at") and row["last_successful_event_at"] < stale_cutoff)
        if degraded or unavailable:
            warnings.append("source_degradation_present")
        if unmonitored:
            warnings.append("unmonitored_open_positions")
        if int(queue_metrics.get("expired_leases") or 0):
            warnings.append("expired_leases_present")
        if critical:
            warnings.append("critical_invariant_violations_present")
        return {
            "observed_at": isoformat_utc(now),
            "source_health_summary": [dict(row) for row in latest_sources],
            "stale_source_count": stale,
            "degraded_source_count": degraded,
            "unavailable_source_count": unavailable,
            "queue_depth": queue_depth,
            "active_leases": int(queue_metrics.get("active_leases") or 0),
            "expired_leases": int(queue_metrics.get("expired_leases") or 0),
            "failed_jobs": failed_jobs,
            "active_sessions": active_sessions,
            "blocked_sessions": blocked_sessions,
            "open_positions": open_positions,
            "unmonitored_open_positions": unmonitored,
            "missed_exit_risk_checks": missed_exit_risk,
            "failed_fills": failed_fills,
            "risk_vetoes": risk_vetoes,
            "net_pnl": net_pnl,
            "expectancy": expectancy,
            "drawdown": drawdown,
            "leaderboard_summary": sprint4.get("latest_leaderboard_v1", []),
            "latency_summary": latency_summary,
            "shadow_readiness_summary": shadow_readiness,
            "memory_review_summary": memory_review,
            "critical_invariant_violations": critical,
            "warnings": warnings,
        }

    async def capture_snapshot(self, *, acceptance_run_id: str | None = None) -> dict[str, Any]:
        summary = await self.current_summary(acceptance_run_id=acceptance_run_id)
        snapshot_id = new_id("operational_health")
        await self.database.execute(
            """
            INSERT INTO operational_health_snapshots(
              operational_health_snapshot_id, acceptance_run_id, observed_at,
              source_health_summary_json, stale_source_count, degraded_source_count,
              unavailable_source_count, queue_depth, active_leases, expired_leases,
              failed_jobs, active_sessions, blocked_sessions, open_positions,
              unmonitored_open_positions, missed_exit_risk_checks, failed_fills,
              risk_vetoes, net_pnl, expectancy, drawdown, leaderboard_summary_json,
              memory_review_summary_json, critical_invariant_violations, warnings_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                snapshot_id,
                acceptance_run_id,
                summary["observed_at"],
                dumps_json(summary["source_health_summary"]),
                summary["stale_source_count"],
                summary["degraded_source_count"],
                summary["unavailable_source_count"],
                summary["queue_depth"],
                summary["active_leases"],
                summary["expired_leases"],
                summary["failed_jobs"],
                summary["active_sessions"],
                summary["blocked_sessions"],
                summary["open_positions"],
                summary["unmonitored_open_positions"],
                summary["missed_exit_risk_checks"],
                summary["failed_fills"],
                summary["risk_vetoes"],
                summary["net_pnl"],
                summary["expectancy"],
                summary["drawdown"],
                dumps_json(summary["leaderboard_summary"]),
                dumps_json(summary["memory_review_summary"]),
                summary["critical_invariant_violations"],
                dumps_json(summary["warnings"]),
            ),
        )
        return {"operational_health_snapshot_id": snapshot_id, **summary}

    async def _latency_summary(self) -> dict[str, Any]:
        rows = await self.database.fetchall(
            """
            SELECT source_name,
                   COUNT(*) AS sample_count,
                   AVG(total_latency_ms) AS avg_total_latency_ms,
                   MAX(total_latency_ms) AS max_total_latency_ms,
                   AVG(response_latency_ms) AS avg_response_latency_ms
            FROM source_latency_samples
            GROUP BY source_name
            ORDER BY source_name
            """
        )
        return {"sources": [dict(row) for row in rows]}

    async def _shadow_readiness_summary(self) -> dict[str, Any]:
        counts = await self.database.table_counts(
            [
                "quote_observations",
                "source_latency_samples",
                "route_quality_evidence",
                "fill_quote_comparisons",
                "live_data_acceptance_windows",
            ]
        )
        passed_windows = await self.database.fetchone(
            "SELECT COUNT(*) AS count FROM live_data_acceptance_windows WHERE status = 'passed'"
        )
        passed_comparisons = await self.database.fetchone(
            "SELECT COUNT(*) AS count FROM fill_quote_comparisons WHERE status = 'passed'"
        )
        sufficient_routes = await self.database.fetchone(
            "SELECT COUNT(*) AS count FROM route_quality_evidence WHERE sufficient_for_shadow_comparison = 1"
        )
        return {
            **counts,
            "passed_live_data_windows": int((passed_windows or {}).get("count") or 0),
            "passed_fill_quote_comparisons": int((passed_comparisons or {}).get("count") or 0),
            "sufficient_route_quality_evidence": int((sufficient_routes or {}).get("count") or 0),
        }

    @staticmethod
    def _drawdown(values: Iterable[float]) -> float:
        equity = 0.0
        peak = 0.0
        drawdown = 0.0
        for value in values:
            equity += value
            peak = max(peak, equity)
            drawdown = max(drawdown, peak - equity)
        return drawdown


class ShadowModeAssessmentService:
    def __init__(self, database: Stage2Database, *, clock: Clock | None = None):
        self.database = database
        self.clock = clock or SystemClock()

    async def assess(self, *, acceptance_run_id: str | None = None) -> dict[str, Any]:
        gaps = await self._gaps()
        status = "gap_report_required" if gaps else "shadow_ready"
        gap_report_id = None
        if gaps:
            gap_report_id = new_id("shadow_gap")
            report = {
                "missing_capabilities": gaps,
                "blocks_stage2_release": False,
                "blocks_stage3_progression": True,
            }
            await self.database.execute(
                """
                INSERT INTO shadow_mode_gap_reports(
                  shadow_mode_gap_report_id, acceptance_run_id, assessed_at, status,
                  missing_capabilities_json, required_evidence_json, current_evidence_json,
                  risk_of_pretending_completion, affected_modules_json,
                  recommended_remediation_json, blocks_stage2_release,
                  blocks_stage3_progression, report_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 1, ?)
                """,
                (
                    gap_report_id,
                    acceptance_run_id,
                    isoformat_utc(self.clock.now()),
                    status,
                    dumps_json([gap["missing_capability"] for gap in gaps]),
                    dumps_json({gap["missing_capability"]: gap["required_evidence"] for gap in gaps}),
                    dumps_json({gap["missing_capability"]: gap["current_evidence"] for gap in gaps}),
                    "Shadow readiness would be overstated without quote freshness, latency, route-quality, and fill-comparison evidence.",
                    dumps_json(sorted({module for gap in gaps for module in gap["affected_modules"]})),
                    dumps_json({gap["missing_capability"]: gap["recommended_remediation"] for gap in gaps}),
                    dumps_json(report),
                ),
            )
        return {
            "status": status,
            "shadow_gap_report_id": gap_report_id,
            "gaps": gaps,
            "blocks_stage2_release": False,
            "blocks_stage3_progression": bool(gaps),
        }

    async def _gaps(self) -> list[dict[str, Any]]:
        gaps: list[dict[str, Any]] = []
        fresh_cutoff = isoformat_utc(self.clock.now() - timedelta(minutes=5))
        fresh_quotes = (
            await self.database.fetchone(
                """
                SELECT COUNT(*) AS count
                FROM quote_observations qo
                JOIN market_snapshots ms ON ms.market_snapshot_id = qo.market_snapshot_id
                WHERE qo.observed_at >= ?
                  AND qo.eligible_for_shadow_comparison = 1
                  AND ms.eligible_for_high_confidence_evaluation = 1
                  AND qo.price_usd IS NOT NULL
                """,
                (fresh_cutoff,),
            )
        )["count"]
        if not fresh_quotes:
            gaps.append(
                self._gap(
                    "fresh_high_confidence_quote_stream",
                    "Recent high-confidence market snapshots with source timestamps and prices.",
                    "No eligible fresh market snapshot is available.",
                    ["sources", "evidence", "paper_trading"],
                    "Add verified quote collection with timestamp and confidence provenance.",
                )
            )
        latency = (
            await self.database.fetchone(
                "SELECT COUNT(*) AS count FROM source_latency_samples WHERE total_latency_ms IS NOT NULL"
            )
        )["count"]
        if not latency:
            gaps.append(
                self._gap(
                    "source_latency_distribution",
                    "Latency measurements for every source used in paper fill assumptions.",
                    "No source latency samples are recorded.",
                    ["sources", "operational_health"],
                    "Persist source latency samples and include them in fill quality reports.",
                )
            )
        route_quality = (
            await self.database.fetchone(
                """
                SELECT COUNT(*) AS count
                FROM route_quality_evidence
                WHERE sufficient_for_shadow_comparison = 1
                """
            )
        )["count"]
        if not route_quality:
            gaps.append(
                self._gap(
                    "route_quality_model",
                    "Evidence that paper fills can be compared with plausible current quotes and route assumptions.",
                    "No sufficient route-quality evidence exists.",
                    ["paper_trading", "evaluation", "reports"],
                    "Add quote/fill comparison artifacts before Stage 3 shadow readiness is claimed.",
                )
            )
        comparison_count = (
            await self.database.fetchone(
                "SELECT COUNT(*) AS count FROM fill_quote_comparisons WHERE status = 'passed'"
            )
        )["count"]
        if not comparison_count:
            gaps.append(
                self._gap(
                    "fill_vs_quote_comparison",
                    "Evidence that paper fills are compared with independent contemporaneous quotes.",
                    "No simulated fills are compared with independent contemporaneous quotes.",
                    ["paper_trading", "evaluation", "reports"],
                    "Add append-only fill-vs-quote comparison artifacts before Stage 3 shadow readiness is claimed.",
                )
            )
        latest_window = await LiveDataAcceptanceWindowService(self.database, clock=self.clock).latest_summary()
        if not latest_window or latest_window.get("status") != "passed":
            gaps.append(
                self._gap(
                    "stage2_owned_live_data_acceptance_window",
                    "A passed Stage 2-owned observation-only live data acceptance window.",
                    "No passed live data acceptance window is recorded.",
                    ["sources", "operational_health", "reports"],
                    "Run an observation-only acceptance window and fail closed until freshness, latency, route, and comparison metrics pass.",
                )
            )
        return gaps

    @staticmethod
    def _gap(
        missing_capability: str,
        required_evidence: str,
        current_evidence: str,
        affected_modules: list[str],
        recommended_remediation: str,
    ) -> dict[str, Any]:
        return {
            "missing_capability": missing_capability,
            "required_evidence": required_evidence,
            "current_evidence": current_evidence,
            "affected_modules": affected_modules,
            "recommended_remediation": recommended_remediation,
        }


class AcceptanceRunService:
    def __init__(self, database: Stage2Database, *, settings: Stage2Settings | None = None, clock: Clock | None = None):
        self.database = database
        self.settings = settings or Stage2Settings()
        self.clock = clock or SystemClock()
        self.snapshots = ConfigSnapshotRepository(database, clock=self.clock)
        self.domain = DomainRepository(database, clock=self.clock)

    async def configure_run(
        self,
        *,
        run_mode: str = "fixture_replay",
        configured_duration_seconds: int = 60,
        max_events: int = 50,
        max_jobs: int = 20,
        max_trades: int = 3,
    ) -> dict[str, Any]:
        snapshots = await self._create_snapshots()
        acceptance_run_id = await self.snapshots.create_acceptance_run(
            config_snapshot_id=snapshots["config_snapshot_id"],
            risk_limit_snapshot_id=snapshots["risk_limit_snapshot_id"],
            promotion_criteria_snapshot_id=snapshots["promotion_criteria_snapshot_id"],
            result="configured",
        )
        execution_id = new_id("acceptance_run_execution")
        await self.database.execute(
            """
            INSERT INTO acceptance_run_executions(
              acceptance_run_execution_id, acceptance_run_id, run_mode, status,
              configured_duration_seconds, max_events, max_jobs, max_trades,
              config_snapshot_id, risk_limit_snapshot_id, strategy_config_snapshot_id,
              promotion_criteria_snapshot_id, data_source_set_json, metadata_json
            )
            VALUES (?, ?, ?, 'configured', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                execution_id,
                acceptance_run_id,
                run_mode,
                configured_duration_seconds,
                max_events,
                max_jobs,
                max_trades,
                snapshots["config_snapshot_id"],
                snapshots["risk_limit_snapshot_id"],
                snapshots["strategy_config_snapshot_id"],
                snapshots["promotion_criteria_snapshot_id"],
                dumps_json(["fixture"]),
                dumps_json({"configured_at": isoformat_utc(self.clock.now())}),
            ),
        )
        await self._event(acceptance_run_id, execution_id, "configured", "configured", {"run_mode": run_mode})
        return {"acceptance_run_id": acceptance_run_id, "execution_id": execution_id, **snapshots}

    async def run_acceptance(self, *, run_mode: str = "fixture_replay") -> dict[str, Any]:
        configured = await self.configure_run(run_mode=run_mode)
        if run_mode == "fixture_replay":
            fixture = await self._fixture_replay(configured)
        elif run_mode == "shadow_gap_assessment":
            fixture = {"mode": "shadow_gap_assessment"}
        elif run_mode == "paper_live_data":
            await InvariantChecker(self.database, clock=self.clock).record_violation(
                acceptance_run_id=configured["acceptance_run_id"],
                finding=InvariantFinding(
                    "paper_live_data_mode_not_validated",
                    "warning",
                    "Stage 2-owned paper-live-data acceptance mode is not validated in this repo state.",
                    "Use fixture_replay and carry live-data reliability into future work.",
                    {"run_mode": run_mode},
                ),
            )
            fixture = {"mode": "paper_live_data", "status": "gap_report_required"}
        else:
            raise ValueError(f"Unsupported run mode: {run_mode}")

        await self._update_execution(configured["execution_id"], status="running", started_at=isoformat_utc(self.clock.now()))
        invariants = await InvariantChecker(self.database, clock=self.clock).run_all(
            acceptance_run_id=configured["acceptance_run_id"]
        )
        health = await OperationalHealthService(self.database, clock=self.clock).capture_snapshot(
            acceptance_run_id=configured["acceptance_run_id"]
        )
        shadow = await ShadowModeAssessmentService(self.database, clock=self.clock).assess(
            acceptance_run_id=configured["acceptance_run_id"]
        )
        final = await self.generate_final_report(
            configured=configured,
            run_mode=run_mode,
            fixture_result=fixture,
            invariant_result=invariants,
            health=health,
            shadow=shadow,
        )
        if invariants["critical_count"]:
            status = "failed"
            decision = "rejected_blocked"
        elif shadow["status"] == "gap_report_required":
            status = "gap_report_required"
            decision = "accepted_with_gaps"
        else:
            status = "passed"
            decision = "accepted_stage2_release"
        await self._update_execution(
            configured["execution_id"],
            status=status,
            ended_at=isoformat_utc(self.clock.now()),
            invariant_violation_count=invariants["finding_count"],
            critical_violation_count=invariants["critical_count"],
            signals_count=(await self._count("signals")),
            orders_count=(await self._count("paper_orders")),
            fills_count=(await self._count("paper_fills")),
            outcomes_count=(await self._count("trade_outcomes")),
            failed_fills=health["failed_fills"],
            risk_vetoes=health["risk_vetoes"],
            no_trade_decisions=(await self._count("no_trade_signals")),
            open_positions=health["open_positions"],
            closed_positions=(await self._count("trade_outcomes")),
            worker_failures=health["failed_jobs"],
            source_degradation_events=health["degraded_source_count"] + health["unavailable_source_count"],
            final_net_pnl=health["net_pnl"],
            expectancy=health["expectancy"],
            drawdown=health["drawdown"],
            leaderboard_snapshot_ref=fixture.get("leaderboard_snapshot_ref"),
            shadow_gap_report_ref=shadow.get("shadow_gap_report_id"),
            final_report_ref=final["final_acceptance_report_id"],
        )
        await self._event(configured["acceptance_run_id"], configured["execution_id"], "completed", status, {"decision": decision})
        return {
            "acceptance_run_id": configured["acceptance_run_id"],
            "execution_id": configured["execution_id"],
            "status": status,
            "decision": decision,
            "fixture_result": fixture,
            "invariant_result": invariants,
            "health": health,
            "shadow": shadow,
            "final_report": final,
        }

    async def generate_final_report(
        self,
        *,
        configured: dict[str, Any],
        run_mode: str,
        fixture_result: dict[str, Any],
        invariant_result: dict[str, Any],
        health: dict[str, Any],
        shadow: dict[str, Any],
    ) -> dict[str, Any]:
        if invariant_result["critical_count"]:
            decision = "rejected_blocked"
        elif shadow["status"] == "gap_report_required":
            decision = "accepted_with_gaps"
        else:
            decision = "accepted_stage2_release"
        strategy_decisions = await self.database.fetchall("SELECT * FROM strategy_decisions ORDER BY created_at")
        report_id = new_id("final_acceptance_report")
        report = {
            "sprints": {
                "sprint_1": "foundation implemented",
                "sprint_2": "data and wallet evidence implemented",
                "sprint_3": "risk-gated paper workflow implemented",
                "sprint_4": "parallel monitoring and strategy memory artifacts implemented",
                "sprint_5": "hardening harness and acceptance reporting implemented",
            },
            "fixture_result": fixture_result,
            "invariants": invariant_result,
            "operational_health": health,
            "shadow": shadow,
            "final_decision": decision,
            "known_limitations": [
                "No long-running production worker daemon was added.",
                "Partial exits remain unsupported.",
                "Shadow readiness is gap-reported unless quote freshness, latency, route quality, and fill comparison evidence exist.",
            ],
        }
        await self.database.execute(
            """
            INSERT INTO final_acceptance_reports(
              final_acceptance_report_id, acceptance_run_id, generated_at, decision,
              run_mode, acceptance_run_result, invariant_summary_json,
              operational_health_summary_json, paper_trading_summary_json,
              strategy_leaderboard_json, strategy_decisions_json,
              memory_review_summary_json, source_degradation_summary_json,
              shadow_status, shadow_gap_report_id, known_limitations_json,
              validation_summary_json, report_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                report_id,
                configured["acceptance_run_id"],
                isoformat_utc(self.clock.now()),
                decision,
                run_mode,
                "failed" if invariant_result["critical_count"] else ("gap_report_required" if shadow["status"] == "gap_report_required" else "passed"),
                dumps_json(invariant_result),
                dumps_json(health),
                dumps_json(fixture_result),
                dumps_json(health["leaderboard_summary"]),
                dumps_json(strategy_decisions),
                dumps_json(health["memory_review_summary"]),
                dumps_json(
                    {
                        "degraded_source_count": health["degraded_source_count"],
                        "unavailable_source_count": health["unavailable_source_count"],
                        "stale_source_count": health["stale_source_count"],
                    }
                ),
                shadow["status"],
                shadow.get("shadow_gap_report_id"),
                dumps_json(report["known_limitations"]),
                dumps_json({"external_validation_commands": "recorded in implementation progress docs"}),
                dumps_json(report),
            ),
        )
        return {"final_acceptance_report_id": report_id, "decision": decision, "report": report}

    async def _fixture_replay(self, configured: dict[str, Any]) -> dict[str, Any]:
        base = self.clock.now()
        fixture_clock = FixedClock(base)
        raw_log = RawSourceEventLog(self.database, clock=fixture_clock)
        source_event_id = await write_raw_source_event(
            map_dexscreener_payload(
                {
                    "pairAddress": "acceptance-pool-1",
                    "baseToken": {"address": "acceptance-token-1", "symbol": "ACCEPT", "name": "Acceptance Token"},
                    "chainId": "solana",
                    "priceUsd": "1.00",
                    "liquidity": {"usd": "50000"},
                    "volume": {"h24": "25000"},
                    "marketCap": "100000",
                    "fdv": "120000",
                    "txns": {"h1": {"buys": 20, "sells": 12}},
                    "pairCreatedAt": int((base - timedelta(minutes=1)).timestamp() * 1000),
                }
            ),
            raw_log,
        )
        await SourceHealthService(self.database, clock=fixture_clock).record_success(
            source_name="dexscreener",
            source_type="market_profile",
            adapter_name="DexScreenerSource",
            latency_ms=120,
            event_time=base,
            metadata={"fixture_replay": True},
        )
        normalized = await EvidenceNormalizer(self.database, clock=fixture_clock).normalize_raw_source_event(source_event_id)
        candidate_id = normalized.token_candidate_ids[0]
        market_snapshot_id = normalized.market_snapshot_ids[0]
        token_profile_id = await TokenIntelligenceService(self.database, clock=fixture_clock).create_profile_from_candidate(candidate_id)
        await TokenIntelligenceService(self.database, clock=fixture_clock).triage_token_profile(token_profile_id)

        wallet_event_id = await write_raw_source_event(
            map_dexpaprika_payload(
                {
                    "wallet": "acceptance-wallet-1",
                    "token_mint": "acceptance-token-1",
                    "pool_address": "acceptance-pool-1",
                    "side": "buy",
                    "token_amount": 100,
                    "price_usd": 1.0,
                    "timestamp": isoformat_utc(base - timedelta(seconds=30)),
                }
            ),
            raw_log,
        )
        await EvidenceNormalizer(self.database, clock=fixture_clock).normalize_raw_source_event(wallet_event_id)
        wallet_trade_id = await WalletIntelligenceService(self.database, clock=fixture_clock).reconstruct_wallet_trade_from_raw_event(
            wallet_event_id
        )
        metric_id = await WalletIntelligenceService(self.database, clock=fixture_clock).calculate_wallet_metrics("acceptance-wallet-1")
        wallet_profile_id = await WalletIntelligenceService(self.database, clock=fixture_clock).create_wallet_profile(
            "acceptance-wallet-1",
            metric_id,
        )

        fixture_domain = DomainRepository(self.database, clock=fixture_clock)
        strategy_version_id = await fixture_domain.create_strategy_version(
            strategy_config_snapshot_id=configured["strategy_config_snapshot_id"],
            rules={"fixture": True},
            params={"fixture_only": True},
            status="active",
        )
        signal_service = SignalService(self.database, fixture_domain, clock=fixture_clock)
        signal_id = await signal_service.create_signal(
            {
                "token_profile_id": token_profile_id,
                "token_candidate_id": candidate_id,
                "market_snapshot_id": market_snapshot_id,
                "wallet_profile_id": wallet_profile_id,
                "wallet_trade_id": wallet_trade_id,
                "strategy_version_id": strategy_version_id,
                "strategy_config_snapshot_id": configured["strategy_config_snapshot_id"],
                "promotion_criteria_snapshot_id": configured["promotion_criteria_snapshot_id"],
                "confidence": "medium",
                "invalidation_condition": "fixture evidence degrades",
                "expected_holding_time": "five minutes",
                "estimated_risk": {"intended_size": 10},
                "estimated_slippage": 0.01,
                "status": "candidate",
            }
        )
        no_trade_id = await signal_service.create_no_trade_signal(
            {
                "token_profile_id": token_profile_id,
                "strategy_version_id": strategy_version_id,
                "strategy_config_snapshot_id": configured["strategy_config_snapshot_id"],
                "promotion_criteria_snapshot_id": configured["promotion_criteria_snapshot_id"],
                "reason": "fixture skip path for acceptance",
                "confidence": "low",
                "observe_later": True,
                "quality_flags": ["fixture_replay"],
            }
        )
        thesis_id = await signal_service.create_trade_thesis(
            signal_id,
            {
                "why_token": "controlled fixture has timestamped token, market, and wallet evidence",
                "why_now": "acceptance replay needs deterministic ordered paper path",
                "planned_exit_logic": "exit on fixture profit target",
                "invalidation_condition": "stale fixture data",
                "wrong_condition": "risk veto, stale source, or failed fill",
                "uncopyable_risk": "fixture replay is not live market proof",
                "expected_holding_time": "five minutes",
                "evidence_refs": [source_event_id, market_snapshot_id, token_profile_id, wallet_profile_id],
            },
        )
        risk = DeterministicRiskService(self.database, fixture_domain, clock=fixture_clock)
        entry_risk_id = await risk.run_entry_risk_check(
            signal_id=signal_id,
            market_snapshot_id=market_snapshot_id,
            risk_limit_snapshot_id=configured["risk_limit_snapshot_id"],
            config_snapshot_id=configured["config_snapshot_id"],
        )
        paper = Sprint3PaperTradingService(self.database, fixture_domain, clock=fixture_clock)
        order_id = await paper.create_paper_order(signal_id=signal_id, risk_check_id=entry_risk_id)
        entry_fill_id = await paper.simulate_entry_fill(paper_order_id=order_id, market_snapshot_id=market_snapshot_id)

        stale_signal_id = await signal_service.create_signal(
            {
                "token_profile_id": token_profile_id,
                "market_snapshot_id": market_snapshot_id,
                "strategy_version_id": strategy_version_id,
                "strategy_config_snapshot_id": configured["strategy_config_snapshot_id"],
                "promotion_criteria_snapshot_id": configured["promotion_criteria_snapshot_id"],
                "confidence": "medium",
                "invalidation_condition": "stale fixture data",
                "expected_holding_time": "five minutes",
                "estimated_risk": {"intended_size": 10},
                "estimated_slippage": 0.01,
            }
        )
        await signal_service.create_trade_thesis(
            stale_signal_id,
            {
                "why_token": "controlled fixture failed-fill branch",
                "why_now": "acceptance requires failed fill evidence",
                "planned_exit_logic": "none",
                "invalidation_condition": "stale fixture data",
                "wrong_condition": "fill fails",
                "uncopyable_risk": "fixture replay only",
                "expected_holding_time": "five minutes",
            },
        )
        stale_risk_id = await risk.run_entry_risk_check(
            signal_id=stale_signal_id,
            market_snapshot_id=market_snapshot_id,
            risk_limit_snapshot_id=configured["risk_limit_snapshot_id"],
            config_snapshot_id=configured["config_snapshot_id"],
        )
        stale_order_id = await paper.create_paper_order(signal_id=stale_signal_id, risk_check_id=stale_risk_id)
        failed_fill_id = await Sprint3PaperTradingService(
            self.database,
            fixture_domain,
            clock=FixedClock(base + timedelta(hours=2)),
        ).simulate_entry_fill(paper_order_id=stale_order_id, market_snapshot_id=market_snapshot_id)
        position_id = await paper.open_position_from_fill(paper_fill_id=entry_fill_id)

        exit_clock = FixedClock(base + timedelta(minutes=5))
        exit_event_id = await write_raw_source_event(
            map_dexscreener_payload(
                {
                    "pairAddress": "acceptance-pool-1",
                    "baseToken": {"address": "acceptance-token-1", "symbol": "ACCEPT", "name": "Acceptance Token"},
                    "chainId": "solana",
                    "priceUsd": "1.50",
                    "liquidity": {"usd": "60000"},
                    "volume": {"h24": "30000"},
                    "marketCap": "150000",
                    "fdv": "180000",
                    "txns": {"h1": {"buys": 28, "sells": 14}},
                    "pairCreatedAt": int((base + timedelta(minutes=4)).timestamp() * 1000),
                }
            ),
            RawSourceEventLog(self.database, clock=exit_clock),
        )
        exit_norm = await EvidenceNormalizer(self.database, clock=exit_clock).normalize_raw_source_event(exit_event_id)
        exit_market_snapshot_id = exit_norm.market_snapshot_ids[0]
        exit_domain = DomainRepository(self.database, clock=exit_clock)
        exit_paper = Sprint3PaperTradingService(self.database, exit_domain, clock=exit_clock)
        exit_decision_id = await exit_paper.create_exit_decision(
            position_id=position_id,
            payload={
                "market_snapshot_id": exit_market_snapshot_id,
                "exit_reason": "fixture_profit_target",
                "exit_trigger": "fixture price above target",
                "expected_exit_logic": "sell full paper position",
                "created_by": "acceptance_fixture",
                "data_as_of": base + timedelta(minutes=4),
            },
        )
        exit_risk_id = await DeterministicRiskService(self.database, exit_domain, clock=exit_clock).run_exit_risk_check(
            exit_decision_id=exit_decision_id,
            market_snapshot_id=exit_market_snapshot_id,
            risk_limit_snapshot_id=configured["risk_limit_snapshot_id"],
            config_snapshot_id=configured["config_snapshot_id"],
        )
        exit_fill_id = await exit_paper.execute_paper_exit(exit_decision_id=exit_decision_id, risk_check_id=exit_risk_id)
        outcome_id = await DeterministicEvaluationService(self.database, clock=exit_clock).calculate_trade_outcome(
            position_id=position_id
        )
        review_id = await PostTradeReviewService(self.database, clock=exit_clock).create_post_trade_review(
            outcome_id=outcome_id,
            reviewer="acceptance_fixture",
            lessons=["fixture replay validates ordered paper path"],
        )
        memory = MemoryService(self.database, clock=exit_clock)
        proposal_id = await memory.propose_memory(
            claim="Fixture replay validates ordering but not market edge.",
            memory_type="lesson",
            evidence_refs=[source_event_id, exit_event_id],
            review_refs=[review_id],
            strategy_refs=[strategy_version_id],
            confidence="medium",
            validity_scope={"scope": "acceptance_fixture"},
            created_by="acceptance_fixture",
        )
        curation_id = await memory.curate_memory(
            memory_proposal_id=proposal_id,
            action="accept",
            curator="acceptance_fixture",
            reason="Accepted as fixture-scoped lesson.",
        )
        proposal = await self.database.fetchone(
            "SELECT curated_memory_entry_id FROM memory_proposals WHERE memory_proposal_id = ?",
            (proposal_id,),
        )
        memory_entry_id = str((proposal or {}).get("curated_memory_entry_id") or curation_id)
        strategy = StrategyResearchService(self.database, domain=exit_domain, clock=exit_clock)
        metric_snapshot_id = await strategy.create_metric_snapshot(
            strategy_version_id,
            promotion_criteria_snapshot_id=configured["promotion_criteria_snapshot_id"],
        )
        decision_id = await strategy.decide_strategy(
            strategy_version_id=strategy_version_id,
            promotion_criteria_snapshot_id=configured["promotion_criteria_snapshot_id"],
            metrics_snapshot_id=metric_snapshot_id,
        )
        await MonitoringService(self.database, clock=exit_clock).complete_closed_position_sessions()
        await self._event(
            configured["acceptance_run_id"],
            configured["execution_id"],
            "fixture_replay",
            "completed",
            {
                "signal_id": signal_id,
                "no_trade_signal_id": no_trade_id,
                "thesis_id": thesis_id,
                "position_id": position_id,
                "failed_fill_id": failed_fill_id,
                "exit_fill_id": exit_fill_id,
                "outcome_id": outcome_id,
                "review_id": review_id,
                "memory_entry_id": memory_entry_id,
                "strategy_decision_id": decision_id,
            },
        )
        return {
            "mode": "fixture_replay",
            "signal_id": signal_id,
            "no_trade_signal_id": no_trade_id,
            "position_id": position_id,
            "failed_fill_id": failed_fill_id,
            "outcome_id": outcome_id,
            "review_id": review_id,
            "memory_entry_id": memory_entry_id,
            "leaderboard_snapshot_ref": metric_snapshot_id,
        }

    async def _create_snapshots(self) -> dict[str, str]:
        snapshot_source = f"sprint5_acceptance:{new_id('snapshot_seed')}"
        config_id = await self.snapshots.create_config_snapshot(
            source=snapshot_source,
            settings=self.settings,
            environment=self.settings.environment,
            app_version=self.settings.app_version,
            build_info=self.settings.build_info,
        )
        risk_id = await self.snapshots.create_risk_limit_snapshot(
            config_snapshot_id=config_id,
            source=snapshot_source,
            limits={
                "min_liquidity_usd": 1000,
                "max_position_size": 1000,
                "max_open_paper_positions": 10,
                "max_position_notional_usd": 1000,
                "max_estimated_slippage_bps": 500,
                "max_stale_seconds": 3600,
                "max_fill_stale_seconds": 300,
                "fill_slippage_bps": 50,
                "paper_fee_bps": 25,
                "fill_latency_ms": 1500,
                "max_liquidity_fraction": 0.01,
            },
        )
        strategy_config_id = await self.snapshots.create_strategy_config_snapshot(
            config_snapshot_id=config_id,
            strategy_name="stage2_acceptance_fixture_strategy",
            strategy_version_label="sprint5",
            thresholds={"fixture_only": True},
            signal_rules={"source": "fixture_replay"},
            exit_rules={"profit_target_fixture": True},
            no_trade_rules={"record_skip_paths": True},
        )
        promotion_id = await self.snapshots.create_promotion_criteria_snapshot(
            config_snapshot_id=config_id,
            source=snapshot_source,
            criteria={
                "min_closed_trades": 5,
                "min_net_expectancy": 0,
                "min_cumulative_net_pnl": 0,
                "max_degraded_outcomes": 0,
            },
        )
        return {
            "config_snapshot_id": config_id,
            "risk_limit_snapshot_id": risk_id,
            "strategy_config_snapshot_id": strategy_config_id,
            "promotion_criteria_snapshot_id": promotion_id,
        }

    async def _event(
        self,
        acceptance_run_id: str,
        execution_id: str,
        event_type: str,
        status: str,
        payload: dict[str, Any],
    ) -> str:
        event_id = new_id("acceptance_run_event")
        await self.database.execute(
            """
            INSERT INTO acceptance_run_events(
              acceptance_run_event_id, acceptance_run_id, acceptance_run_execution_id,
              event_type, status, created_at, payload_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (event_id, acceptance_run_id, execution_id, event_type, status, isoformat_utc(self.clock.now()), dumps_json(payload)),
        )
        return event_id

    async def _update_execution(self, execution_id: str, **fields: Any) -> None:
        if not fields:
            return
        set_clause = ", ".join(f"{key} = ?" for key in fields)
        await self.database.execute(
            f"UPDATE acceptance_run_executions SET {set_clause} WHERE acceptance_run_execution_id = ?",
            (*fields.values(), execution_id),
        )

    async def _count(self, table: str) -> int:
        return int((await self.database.fetchone(f"SELECT COUNT(*) AS count FROM {table}"))["count"])


def render_acceptance_report(result: dict[str, Any]) -> str:
    health = result.get("health", {})
    invariants = result.get("invariant_result", {})
    shadow = result.get("shadow", {})
    return "\n".join(
        [
            "Stage 2 Final Acceptance Report",
            f"acceptance_run_id: {result.get('acceptance_run_id')}",
            f"status: {result.get('status')}",
            f"decision: {result.get('decision')}",
            f"invariant_findings: {invariants.get('finding_count', 0)}",
            f"critical_violations: {invariants.get('critical_count', 0)}",
            f"failed_fills: {health.get('failed_fills', 0)}",
            f"risk_vetoes: {health.get('risk_vetoes', 0)}",
            f"degraded_sources: {health.get('degraded_source_count', 0)}",
            f"net_pnl: {health.get('net_pnl', 0)}",
            f"expectancy: {health.get('expectancy', 0)}",
            f"drawdown: {health.get('drawdown', 0)}",
            f"shadow_status: {shadow.get('status')}",
            f"shadow_gap_report_id: {shadow.get('shadow_gap_report_id')}",
        ]
    )


__all__ = [
    "AcceptanceRunService",
    "InvariantChecker",
    "InvariantFinding",
    "OperationalHealthService",
    "ShadowModeAssessmentService",
    "render_acceptance_report",
]
