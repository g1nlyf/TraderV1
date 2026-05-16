from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[3]
APP_ROOT = PROJECT_ROOT / "WalletScarper"
PYTHON = APP_ROOT / ".venv" / "Scripts" / "python.exe"
REPORTS_ROOT = PROJECT_ROOT / "docs" / "implementation-progress" / "reports"
KNOWN_REPORTS = (
    "final-acceptance-report.json",
    "final-acceptance-report.md",
    "shadow-mode-gap-report.json",
    "shadow-mode-gap-report.md",
    "shadow-readiness-gap-closure-report.json",
    "shadow-readiness-gap-closure-report.md",
    "validation-summary.md",
)


def _json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, default=str)


def _run_walletscarper(args: list[str]) -> dict[str, Any]:
    if not PYTHON.exists():
        return {"ok": False, "error": "WalletScarper virtualenv is missing. Run scripts/setup-env.bat first."}
    completed = subprocess.run(
        [str(PYTHON), "-m", "walletscarper", *args],
        cwd=str(APP_ROOT),
        text=True,
        capture_output=True,
        timeout=60,
        check=False,
    )
    return {
        "ok": completed.returncode == 0,
        "returncode": completed.returncode,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
    }


def _read_report(name: str, max_chars: int) -> dict[str, Any]:
    if name not in KNOWN_REPORTS:
        return {"name": name, "status": "blocked", "error": "Unknown report name."}
    path = REPORTS_ROOT / name
    if not path.exists():
        return {"name": name, "status": "missing", "path": str(path)}
    text = path.read_text(encoding="utf-8", errors="replace")
    truncated = len(text) > max_chars
    return {
        "name": name,
        "status": "available",
        "path": str(path),
        "content": text[:max_chars],
        "truncated": truncated,
    }


def _project_health(args: dict[str, Any], **_: Any) -> str:
    del args
    result = _run_walletscarper(["project-health-check"])
    if result.get("ok"):
        try:
            result["parsed"] = json.loads(result.get("stdout") or "{}")
        except json.JSONDecodeError:
            result["parsed"] = None
    return _json(result)


def _latest_reports(args: dict[str, Any], **_: Any) -> str:
    names = args.get("names") or list(KNOWN_REPORTS)
    max_chars = int(args.get("max_chars") or 6000)
    max_chars = max(500, min(max_chars, 20000))
    reports = [_read_report(str(name), max_chars=max_chars) for name in names]
    return _json({"ok": True, "reports": reports})


def _shadow_gap_summary(args: dict[str, Any], **_: Any) -> str:
    del args
    final_report = _read_report("final-acceptance-report.json", max_chars=20000)
    shadow_report = _read_report("shadow-mode-gap-report.json", max_chars=20000)

    parsed_final: dict[str, Any] | None = None
    parsed_shadow: dict[str, Any] | None = None
    if final_report.get("status") == "available":
        parsed_final = json.loads(str(final_report.get("content") or "{}"))
    if shadow_report.get("status") == "available":
        parsed_shadow = json.loads(str(shadow_report.get("content") or "{}"))

    final = (parsed_final or {}).get("final_acceptance_report") or (parsed_final or {})
    shadow = (parsed_shadow or {}).get("shadow_mode_gap_report") or (parsed_shadow or {})
    invariant_summary = final.get("invariant_summary_json") or (parsed_final or {}).get("invariant_result") or {}
    missing_capabilities = shadow.get("missing_capabilities_json")
    if missing_capabilities is None:
        missing_capabilities = (shadow.get("report_json") or {}).get("missing_capabilities")

    return _json(
        {
            "ok": True,
            "stage2_decision": final.get("decision"),
            "acceptance_status": final.get("acceptance_run_result") or final.get("status"),
            "critical_invariant_count": invariant_summary.get("critical_count"),
            "shadow_status": shadow.get("status"),
            "missing_capabilities": missing_capabilities,
            "blocks_stage3_progression": bool(shadow.get("blocks_stage3_progression")),
        }
    )


V2_TOOLS: dict[str, str] = {
    # ── STEP 1: Discover tokens ──────────────────────────────────────────────
    "token.scan_universe": (
        "STEP 1 — Normalize raw discovery events into token candidates and profiles. "
        "Call this first to populate the candidate pool. "
        "Returns token_candidates_created and profiles_created. "
        "Next: token.request_deep_parse on promising candidates, or wallet.extract_from_token directly."
    ),
    "token.get_profile": (
        "Read the latest auditable token profile by token_profile_id or token_mint. "
        "Use to inspect quality_flags and evidence before committing to deep analysis."
    ),
    "token.request_deep_parse": (
        "STEP 2 — Build a TokenTradeCorpus from Stage 2 or legacy trade evidence for a specific token_mint. "
        "Required before wallet.extract_from_token if you need full corpus control. "
        "Returns corpus with data_sufficiency and quality_flags. "
        "Next: wallet.extract_from_token with the returned token_trade_corpus_id."
    ),
    "token.record_agent_decision": (
        "Record your triage decision for a token (active_watch, pass, revisit_later, insufficient_data). "
        "This is research state only — not a trading signal. "
        "Call after reviewing a token profile or corpus to track your reasoning."
    ),
    # ── STEP 3: Extract and profile wallets ──────────────────────────────────
    "wallet.extract_from_token": (
        "STEP 3 — Extract wallet candidates from a token's trade corpus. "
        "Pass token_trade_corpus_id (from token.request_deep_parse) or token_mint directly. "
        "Returns wallet_candidates_extracted. "
        "Next: wallet.profile_history for each candidate, then wallet.record_agent_review."
    ),
    "wallet.calculate_token_outcomes": (
        "STEP 3b - Calculate token-specific wallet outcomes from a TokenTradeCorpus. "
        "This identifies wallets that made at least +20% ROI on the selected token and marks which are eligible for agent review. "
        "Pass token_trade_corpus_id from token.request_deep_parse or wallet.extract_from_token. "
        "Next: wallet.profile_history for eligible wallets, then wallet.record_agent_review."
    ),
    "wallet.profile_history": (
        "STEP 4 — Build a deterministic wallet history profile (P&L, win rate, payoff ratio, bot-like flags). "
        "Pass wallet address. "
        "Returns data_sufficiency — if insufficient, note it in your review. "
        "Next: wallet.record_agent_review."
    ),
    "wallet.get_metrics": (
        "Read the latest deterministic wallet metric snapshot for a wallet. "
        "Use as a quick check before a full profile_history call."
    ),
    "wallet.record_agent_review": (
        "STEP 5 — Record your qualitative assessment of a wallet (elite, probation, reject, insufficient_data). "
        "Include reasons, unknowns, and data_sufficiency in your review. "
        "Elite/probation wallets enter the signal pool — LiveMonitor will emit wallet.record_signal_event when they trade. "
        "Next: wallet.list_elite to confirm, then wait for signal events."
    ),
    "wallet.list_elite": (
        "List the current elite and probation wallets from the auditable review table. "
        "Use to understand which wallets are being monitored for live signals."
    ),
    # ── STEP 6: React to live signals ────────────────────────────────────────
    "wallet.record_signal_event": (
        "STEP 6 — Record a tracked wallet buy or sell event. "
        "LiveMonitor calls this automatically for real tracked wallet transactions (input_mode=real_source). "
        "You may also call this manually for fixture/smoke testing. "
        "Next: agent.record_trading_decision linked to this signal event."
    ),
    # ── STEP 7-8: Make and execute trading decisions ──────────────────────────
    "agent.record_trading_decision": (
        "STEP 7 — Record your pre-action synthesis: signal, no_trade, wait, exit, downgrade_wallet, or downgrade_token. "
        "Mandatory before any signal.create or paper order. "
        "Link to the tracked_wallet_signal_event_id that triggered this decision. "
        "Next: signal.create (if decision_type=signal) or signal.create_no_trade (if no_trade)."
    ),
    "signal.create": (
        "STEP 8a — Create a Signal from an agent_trading_decision_id. "
        "Only call after agent.record_trading_decision with decision_type=signal. "
        "Next: risk.check_entry."
    ),
    "signal.create_no_trade": (
        "STEP 8b — Create a first-class NoTradeSignal from an agent_trading_decision_id. "
        "Use when you decide not to trade — this is a research artifact, not a skip."
    ),
    "risk.check_entry": (
        "STEP 9 — Run deterministic entry risk check against the signal. "
        "You cannot override the result. If passed=1, proceed. If passed=0, do not create a paper order. "
        "Next (if passed): paper.create_order."
    ),
    "paper.create_order": (
        "STEP 10 — Create a paper order after a passed risk.check_entry. "
        "Requires risk_check_id from a passed entry risk check. "
        "Next: paper.simulate_fill."
    ),
    "paper.simulate_fill": (
        "STEP 11 — Simulate a conservative paper entry fill and open a paper position. "
        "Returns position_id. Hold the position until your exit condition is met. "
        "Next (when ready to exit): paper.create_exit_decision."
    ),
    # ── STEP 12-14: Exit ──────────────────────────────────────────────────────
    "paper.create_exit_decision": (
        "STEP 12 — Record your exit reasoning before simulating an exit fill. "
        "Mandatory pre-exit audit step. "
        "Next: risk.check_exit."
    ),
    "risk.check_exit": (
        "STEP 13 — Run deterministic exit risk check. "
        "You cannot override. If passed=1, proceed to paper.execute_exit."
    ),
    "paper.execute_exit": (
        "STEP 14 — Simulate deterministic paper exit and calculate outcome (net_pnl, outcome_type). "
        "Next: review.create_post_trade."
    ),
    # ── STEP 15-16: Learn ─────────────────────────────────────────────────────
    "review.create_post_trade": (
        "STEP 15 — Create a post-trade review linked to the deterministic outcome. "
        "Capture what the trade taught you about the signal source or wallet. "
        "Next: memory.propose."
    ),
    "memory.propose": (
        "STEP 16 — Propose a memory entry derived from post-trade review evidence. "
        "Does not mutate outcomes. Use to encode lessons, edge hypotheses, or wallet re-ratings. "
        "Next: return to token.scan_universe or wallet.list_elite for next research cycle."
    ),
    "metrics.wallet_report": (
        "Create a wallet contribution draft report aggregating forward paper evidence for a wallet. "
        "Use after several completed paper trades to evaluate a wallet's signal quality."
    ),
}


def _v2_tool(tool_name: str, args: dict[str, Any]) -> str:
    result = _run_walletscarper(["stage2-v2-tool", tool_name, "--payload-json", json.dumps(args or {}, ensure_ascii=False)])
    if result.get("ok"):
        try:
            return _json(json.loads(result.get("stdout") or "{}"))
        except json.JSONDecodeError:
            return _json(
                {
                    "ok": False,
                    "tool": tool_name,
                    "blocked_reason": "tool returned non-JSON output",
                    "stdout": result.get("stdout"),
                    "stderr": result.get("stderr"),
                }
            )
    return _json(
        {
            "ok": False,
            "tool": tool_name,
            "blocked_reason": "walletscarper CLI returned an error",
            "returncode": result.get("returncode"),
            "stdout": result.get("stdout"),
            "stderr": result.get("stderr"),
        }
    )


def _v2_handler(tool_name: str):
    def _handler(args: dict[str, Any], **_: Any) -> str:
        return _v2_tool(tool_name, args)

    return _handler


def register(ctx) -> None:
    ctx.register_tool(
        name="traderv1_project_health",
        toolset="traderv1_operator",
        schema={
            "name": "traderv1_project_health",
            "description": "Run the read-only TraderV1 system health check. Call this at session start to understand current pipeline state before beginning the research cycle.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        handler=_project_health,
        emoji="H",
    )
    ctx.register_tool(
        name="traderv1_latest_reports",
        toolset="traderv1_operator",
        schema={
            "name": "traderv1_latest_reports",
            "description": "Read deterministic TraderV1 reports from docs/implementation-progress/reports.",
            "parameters": {
                "type": "object",
                "properties": {
                    "names": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional report names to read. Unknown names are rejected.",
                    },
                    "max_chars": {
                        "type": "integer",
                        "description": "Maximum characters per report, clamped to 500..20000.",
                    },
                },
                "additionalProperties": False,
            },
        },
        handler=_latest_reports,
        emoji="R",
    )
    ctx.register_tool(
        name="traderv1_shadow_gap_summary",
        toolset="traderv1_operator",
        schema={
            "name": "traderv1_shadow_gap_summary",
            "description": "Summarize the latest Stage 2 acceptance and shadow-gap state from deterministic report files.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        handler=_shadow_gap_summary,
        emoji="S",
    )
    for tool_name, description in V2_TOOLS.items():
        ctx.register_tool(
            name=tool_name,
            toolset="traderv1_operator",
            schema={
                "name": tool_name,
                "description": description,
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "additionalProperties": True,
                },
            },
            handler=_v2_handler(tool_name),
            emoji="V",
        )
