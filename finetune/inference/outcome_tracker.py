"""
outcome_tracker.py — Tracks paper trade outcomes and labels sessions.

Every 30 minutes, for each open paper trade:
1. Calls market_get_token_snapshot to get current price
2. Records price checkpoint (T+30m, T+1h, T+2h, T+4h)
3. At T+4h: computes label and updates the session JSON file

Price checkpoints stored in outcome_tracker_state.json (next to sessions/).
Labels written to session JSON (outcome_label field).

Usage:
  python finetune/inference/outcome_tracker.py
  python finetune/inference/outcome_tracker.py --check-interval 1800   # seconds (default 1800 = 30min)
  python finetune/inference/outcome_tracker.py --once                  # run one check cycle then exit
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ── stdout encoding ────────────────────────────────────────────────────────────
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ── path setup ─────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[2]
WALLETSCARPER_ROOT = ROOT / "WalletScarper"
WALLETSCARPER_PYTHON = WALLETSCARPER_ROOT / ".venv" / "Scripts" / "python.exe"

SESSIONS_DIR = ROOT / "finetune" / "data" / "sessions"
STATE_FILE = ROOT / "finetune" / "data" / "outcome_tracker_state.json"

# Checkpoint intervals in seconds
CHECKPOINTS_SEC = [1800, 3600, 7200, 14400]  # T+30m, T+1h, T+2h, T+4h
LABEL_HORIZON_SEC = 14400  # 4 hours — when we finalize the label

# ── logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

# ── tool dispatch (mirrors signal_reviewer.py) ─────────────────────────────────
TOOL_NAME_MAP = {
    "market_get_token_snapshot": "market.get_token_snapshot",
}

_STRIP_ENV = {"PYTHONHOME", "PYTHONPATH", "PYTHONEXECUTABLE"}


def _clean_env() -> dict[str, str]:
    import os
    return {k: v for k, v in __import__("os").environ.items() if k not in _STRIP_ENV}


def _call_market_snapshot(token_mint: str) -> float | None:
    """
    Call market.get_token_snapshot for token_mint.
    Returns price_usd as float, or None on failure.
    """
    if not WALLETSCARPER_PYTHON.exists():
        log.warning("venv python not found: %s", WALLETSCARPER_PYTHON)
        return None

    payload = {"token_mint": token_mint}
    v2_name = TOOL_NAME_MAP["market_get_token_snapshot"]

    try:
        result = subprocess.run(
            [
                str(WALLETSCARPER_PYTHON),
                "-m", "walletscarper",
                "stage2-v2-tool", v2_name,
                "--payload-json", json.dumps(payload),
            ],
            cwd=str(WALLETSCARPER_ROOT),
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
            env=_clean_env(),
        )
        if result.returncode != 0 and not result.stdout.strip():
            log.warning(
                "market snapshot rc=%d stderr=%s",
                result.returncode,
                result.stderr[:200],
            )
            return None

        data = json.loads(result.stdout.strip())
        if not data.get("ok"):
            log.debug("market snapshot not ok for %s: %s", token_mint[:12], data)
            return None

        snapshot = data.get("snapshot") or {}
        raw_price = snapshot.get("price_usd")
        if raw_price is None:
            return None

        return float(raw_price)

    except subprocess.TimeoutExpired:
        log.warning("market snapshot timed out for %s", token_mint[:12])
        return None
    except (json.JSONDecodeError, ValueError, Exception) as exc:
        log.warning("market snapshot error for %s: %s", token_mint[:12], exc)
        return None


# ── state persistence ──────────────────────────────────────────────────────────

def _load_state() -> dict:
    """Load outcome tracker state, creating empty state if missing."""
    if not STATE_FILE.exists():
        return {"trades": {}}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception as exc:
        log.warning("failed to load state file (%s), starting fresh", exc)
        return {"trades": {}}


def _save_state(state: dict) -> None:
    """Persist state atomically via a temp file."""
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")
    tmp.replace(STATE_FILE)


# ── session helpers ────────────────────────────────────────────────────────────

def _extract_decision_type(session: dict) -> str:
    """Extract decision_type from agent_record_trading_decision tool call."""
    for msg in session.get("messages") or []:
        if msg.get("role") != "assistant":
            continue
        for tc in msg.get("tool_calls") or []:
            fn = tc.get("function", {})
            if fn.get("name") == "agent_record_trading_decision":
                try:
                    args = json.loads(fn.get("arguments") or "{}")
                    return str(args.get("decision_type") or "unknown")
                except Exception:
                    pass
    return "unknown"


def _extract_trade_info(session: dict) -> dict | None:
    """
    Extract trade information from a session dict.

    For signal sessions: returns token_mint, fill_price, session_timestamp.
    For no_trade sessions: returns token_mint, ref_price=None, session_timestamp.
    Returns None if essential fields are missing.

    Mirrors extraction logic from 05_label_outcomes.py, adapted for live tracking.
    """
    signal_id = session.get("signal_id")
    session_id = session.get("session_id")
    timestamp_str = session.get("timestamp")

    if not session_id or not timestamp_str:
        return None

    # Parse session timestamp
    try:
        # Handle both Z suffix and +00:00
        ts_clean = timestamp_str.replace("Z", "+00:00")
        session_ts = datetime.fromisoformat(ts_clean).timestamp()
    except Exception:
        log.debug("cannot parse session timestamp: %s", timestamp_str)
        return None

    decision_type = _extract_decision_type(session)

    # Walk messages for relevant tool results
    token_mint: str | None = None
    fill_price: float | None = None
    ref_price: float | None = None  # from market snapshot for no_trade sessions

    messages = session.get("messages") or []

    # Build a map: tool_call_id → tool_name for correlating results
    call_id_to_name: dict[str, str] = {}
    for msg in messages:
        if msg.get("role") == "assistant":
            for tc in msg.get("tool_calls") or []:
                fn = tc.get("function", {})
                call_id_to_name[tc.get("id", "")] = fn.get("name", "")

    # Walk tool results
    for msg in messages:
        if msg.get("role") != "tool":
            continue
        tool_call_id = msg.get("tool_call_id", "")
        tool_name = call_id_to_name.get(tool_call_id, "")
        try:
            content = json.loads(msg.get("content") or "{}")
        except Exception:
            continue

        if not content.get("ok"):
            continue

        # Extract token_mint from token_get_profile or market_get_token_snapshot
        if tool_name in ("token_get_profile", "market_get_token_snapshot"):
            if token_mint is None:
                token_mint = content.get("token_mint")

        # Extract ref_price from market snapshot
        if tool_name == "market_get_token_snapshot":
            snapshot = content.get("snapshot") or {}
            raw = snapshot.get("price_usd")
            if raw is not None and ref_price is None:
                try:
                    ref_price = float(raw)
                except (TypeError, ValueError):
                    pass

        # Extract fill_price from paper_simulate_fill
        if tool_name == "paper_simulate_fill" and content.get("filled"):
            raw_fill = content.get("fill_price")
            if raw_fill is not None:
                try:
                    fill_price = float(raw_fill)
                except (TypeError, ValueError):
                    pass

        # Also check paper_orders result (paper_create_order response may carry token_mint)
        if tool_name == "paper_create_order":
            if token_mint is None:
                token_mint = content.get("token_mint")

    # Also try top-level signal user message for token_mint (fallback)
    if token_mint is None:
        for msg in messages:
            if msg.get("role") == "user":
                content_str = msg.get("content") or ""
                for line in content_str.splitlines():
                    if "token_mint:" in line:
                        token_mint = line.split("token_mint:")[-1].strip()
                        break
                if token_mint:
                    break

    if not token_mint:
        return None

    return {
        "session_id": session_id,
        "signal_id": signal_id,
        "token_mint": token_mint,
        "fill_price": fill_price,      # None for no_trade
        "ref_price": ref_price,        # market snapshot price at review time
        "decision_type": decision_type,
        "session_timestamp": session_ts,
    }


# ── labeling ───────────────────────────────────────────────────────────────────

def _compute_label(trade: dict, checkpoints: dict[str, float]) -> str | None:
    """
    Compute outcome label from recorded price checkpoints.

    Returns label string, or None if no checkpoints are available yet.
    """
    if not checkpoints:
        return None

    prices = list(checkpoints.values())
    best_price = max(prices)

    decision_type = trade.get("decision_type", "unknown")
    fill_price = trade.get("fill_price")
    ref_price = trade.get("ref_price")

    if decision_type == "signal" and fill_price is not None and fill_price > 0:
        ratio = best_price / fill_price
        if ratio >= 1.20:
            return "excellent"
        elif ratio >= 1.08:
            return "good"
        elif ratio >= 1.00:
            return "marginal"
        else:
            return "loss"

    elif decision_type == "no_trade":
        # Compare against ref_price captured at review time
        base = ref_price
        if base is None or base <= 0:
            # Fallback: first checkpoint as base
            first_key = min(checkpoints, key=lambda k: int(k))
            base = checkpoints[first_key]

        if base is None or base <= 0:
            return "neutral_no_trade"

        ratio = best_price / base
        if ratio >= 1.20:
            return "bad_no_trade"    # we skipped a big gainer
        elif ratio <= 1.05:
            return "good_no_trade"   # correctly avoided (flat/loss)
        else:
            return "neutral_no_trade"

    # Unknown decision type — can't label
    return "neutral_no_trade"


# ── scan & register new trades ─────────────────────────────────────────────────

def _scan_sessions(state: dict) -> int:
    """
    Walk sessions dir. For any session with outcome_label == null,
    extract trade info and register in state if not already tracked.
    Returns count of newly registered trades.
    """
    registered = 0
    for sf in sorted(SESSIONS_DIR.glob("*.json")):
        try:
            session = json.loads(sf.read_text(encoding="utf-8"))
        except Exception as exc:
            log.debug("skip %s: %s", sf.name, exc)
            continue

        # Only track sessions that haven't been labeled yet
        if session.get("outcome_label") is not None:
            continue

        session_id = session.get("session_id")
        if not session_id:
            continue

        # Already tracked
        if session_id in state["trades"]:
            continue

        info = _extract_trade_info(session)
        if not info:
            log.debug("skip %s: cannot extract trade info", sf.name)
            continue

        state["trades"][session_id] = {
            "session_id": session_id,
            "session_file": sf.name,
            "token_mint": info["token_mint"],
            "fill_price": info["fill_price"],
            "ref_price": info["ref_price"],
            "decision_type": info["decision_type"],
            "session_timestamp": info["session_timestamp"],
            "registered_at": time.time(),
            "checkpoints": {},
        }
        log.info(
            "[tracker] registered session=%s token=%.12s... decision=%s fill_price=%s",
            session_id[:12],
            info["token_mint"],
            info["decision_type"],
            info["fill_price"],
        )
        registered += 1

    return registered


# ── check cycle ────────────────────────────────────────────────────────────────

def _run_check_cycle(state: dict) -> dict[str, int]:
    """
    For each tracked trade:
    1. Determine which checkpoint we're at based on elapsed time
    2. If a checkpoint is due and not yet recorded, call market snapshot
    3. If past T+4h, compute label, write to session file, remove from state

    Returns stats dict.
    """
    now = time.time()
    stats = {"checked": 0, "labeled": 0, "errors": 0, "skipped": 0}

    to_remove: list[str] = []

    for session_id, trade in list(state["trades"].items()):
        try:
            elapsed = now - trade["session_timestamp"]
            token_mint = trade["token_mint"]
            checkpoints: dict[str, float] = trade.get("checkpoints") or {}

            # Determine which checkpoints are due
            due_checkpoints = [
                cp for cp in CHECKPOINTS_SEC
                if elapsed >= cp and str(cp) not in checkpoints
            ]

            # Fetch price for due checkpoints (one API call, reuse for all due)
            if due_checkpoints:
                price = _call_market_snapshot(token_mint)
                stats["checked"] += 1

                if price is not None:
                    for cp in due_checkpoints:
                        checkpoints[str(cp)] = price
                        log.info(
                            "[tracker] checkpoint T+%ds session=%s price=%g",
                            cp,
                            session_id[:12],
                            price,
                        )
                    trade["checkpoints"] = checkpoints
                else:
                    log.warning(
                        "[tracker] no price for %s (session=%s)", token_mint[:12], session_id[:12]
                    )
                    stats["errors"] += 1

            # Label if past horizon and we have at least one checkpoint
            if elapsed >= LABEL_HORIZON_SEC:
                if checkpoints:
                    label = _compute_label(trade, checkpoints)
                    if label:
                        _write_label_to_session(session_id, trade, label)
                        log.info(
                            "[tracker] labeled session=%s label=%s decision=%s",
                            session_id[:12],
                            label,
                            trade.get("decision_type"),
                        )
                        stats["labeled"] += 1
                        to_remove.append(session_id)
                    else:
                        log.warning(
                            "[tracker] could not compute label for session=%s", session_id[:12]
                        )
                        to_remove.append(session_id)  # remove to avoid infinite loop
                else:
                    log.warning(
                        "[tracker] past horizon but no checkpoints for session=%s — removing",
                        session_id[:12],
                    )
                    to_remove.append(session_id)
            else:
                stats["skipped"] += 1

        except Exception as exc:
            log.warning("[tracker] error processing session=%s: %s", session_id[:12], exc, exc_info=True)
            stats["errors"] += 1

    # Remove labeled / expired trades
    for session_id in to_remove:
        state["trades"].pop(session_id, None)

    return stats


def _write_label_to_session(session_id: str, trade: dict, label: str) -> None:
    """Write outcome_label (and checkpoint prices) to the session JSON file."""
    sf_name = trade.get("session_file")
    if not sf_name:
        log.warning("[tracker] no session_file in trade record for session=%s", session_id[:12])
        return

    sf = SESSIONS_DIR / sf_name
    if not sf.exists():
        # Try searching by session_id
        matches = list(SESSIONS_DIR.glob("*.json"))
        found = None
        for candidate in matches:
            try:
                data = json.loads(candidate.read_text(encoding="utf-8"))
                if data.get("session_id") == session_id:
                    found = candidate
                    break
            except Exception:
                pass
        if not found:
            log.warning("[tracker] session file not found for session=%s", session_id[:12])
            return
        sf = found

    try:
        session = json.loads(sf.read_text(encoding="utf-8"))
    except Exception as exc:
        log.warning("[tracker] cannot read session file %s: %s", sf.name, exc)
        return

    session["outcome_label"] = label
    session["outcome_checkpoints"] = trade.get("checkpoints", {})
    session["outcome_fill_price"] = trade.get("fill_price")
    session["outcome_ref_price"] = trade.get("ref_price")
    session["outcome_decision_type"] = trade.get("decision_type")
    session["outcome_labeled_at"] = datetime.now(timezone.utc).isoformat()

    sf.write_text(json.dumps(session, indent=2, default=str), encoding="utf-8")
    log.info("[tracker] wrote label=%s to %s", label, sf.name)


# ── main loop ──────────────────────────────────────────────────────────────────

async def main_loop(check_interval: int, once: bool) -> None:
    state = _load_state()
    log.info(
        "[tracker] starting — interval=%ds once=%s state_file=%s",
        check_interval,
        once,
        STATE_FILE,
    )

    try:
        while True:
            # 1. Scan for new unlabeled sessions
            new_count = _scan_sessions(state)
            if new_count:
                log.info("[tracker] registered %d new trade(s)", new_count)
                _save_state(state)

            # 2. Check open trades
            active_count = len(state["trades"])
            if active_count > 0:
                stats = _run_check_cycle(state)
                _save_state(state)
                log.info(
                    "[tracker] cycle: active=%d checked=%d labeled=%d errors=%d",
                    active_count,
                    stats["checked"],
                    stats["labeled"],
                    stats["errors"],
                )
            else:
                log.info("[tracker] no active trades to track")

            if once:
                log.info("[tracker] --once flag set, exiting after one cycle")
                break

            await asyncio.sleep(check_interval)

    except KeyboardInterrupt:
        log.info("[tracker] stopped")
        _save_state(state)
    except Exception as exc:
        log.error("[tracker] fatal error: %s", exc, exc_info=True)
        _save_state(state)
        raise


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Track paper trade outcomes and label session files",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--check-interval",
        type=int,
        default=1800,
        help="How often to check open trades (seconds; default 1800 = 30min)",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run one check cycle then exit",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        asyncio.run(main_loop(check_interval=args.check_interval, once=args.once))
    except KeyboardInterrupt:
        log.info("[tracker] stopped")


if __name__ == "__main__":
    main()
