"""
Script 05: Label existing sessions with real price outcomes.

For SIGNAL sessions:
  - Extract entry price from paper_simulate_fill response (fill_price field)
  - Extract token_mint from token_get_profile call args
  - Call market_get_token_snapshot NOW to get current price
  - If session_age < 4h: skip (not enough time to judge outcome)
  - Compute pct_change = (current_price - entry_price) / entry_price * 100
  - Labels:
    excellent:  pct_change >= +20%
    good:       pct_change >= +8%
    marginal:   pct_change >= 0%
    loss:       pct_change < 0% (any loss)
  - If current price unavailable (token dead): label "loss" if entry was >4h ago

For NO_TRADE sessions:
  - Extract reference price from market_get_token_snapshot tool response in the session
  - Call market_get_token_snapshot NOW for current price
  - If session_age < 4h: skip
  - pct_change = (current_price - ref_price) / ref_price * 100
  - Labels:
    bad_no_trade:     pct_change >= +20% (missed good trade)
    neutral_no_trade: -10% <= pct_change < +20%
    good_no_trade:    pct_change < -10% (correct to skip)

Usage:
  python finetune/scripts/05_label_outcomes.py
  python finetune/scripts/05_label_outcomes.py --dry-run
  python finetune/scripts/05_label_outcomes.py --force        # re-label already labeled sessions
  python finetune/scripts/05_label_outcomes.py --min-age 2    # override min session age in hours
  python finetune/scripts/05_label_outcomes.py --workers 4    # parallel workers (default 4)
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[2]
SESSIONS_DIR = ROOT / "finetune" / "data" / "sessions"
WALLETSCARPER_PYTHON = ROOT / "WalletScarper" / ".venv" / "Scripts" / "python.exe"
WALLETSCARPER_ROOT = ROOT / "WalletScarper"

TOOL_NAME_MAP: dict[str, str] = {
    "wallet_profile_history": "wallet.profile_history",
    "token_get_profile": "token.get_profile",
    "market_get_token_snapshot": "market.get_token_snapshot",
    "agent_record_trading_decision": "agent.record_trading_decision",
    "signal_create": "signal.create",
    "risk_check_entry": "risk.check_entry",
    "paper_create_order": "paper.create_order",
    "paper_simulate_fill": "paper.simulate_fill",
}

_STRIP_ENV: frozenset[str] = frozenset({"PYTHONHOME", "PYTHONPATH", "PYTHONEXECUTABLE"})

# Thread-safe print lock
_print_lock = threading.Lock()


def _tprint(msg: str) -> None:
    """Thread-safe print."""
    with _print_lock:
        print(msg, flush=True)


def _clean_env() -> dict[str, str]:
    """Return os.environ without PYTHONHOME/PYTHONPATH/PYTHONEXECUTABLE."""
    return {k: v for k, v in os.environ.items() if k not in _STRIP_ENV}


def call_tool(tool_name: str, payload: dict) -> dict:
    """Invoke a stage2-v2-tool via subprocess and return parsed JSON response."""
    v2_name = TOOL_NAME_MAP.get(tool_name, tool_name)
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
            encoding="utf-8",
            timeout=60,
            check=False,
            env=_clean_env(),
        )
        stdout = result.stdout.strip()
        if not stdout:
            return {
                "ok": False,
                "error": f"empty output rc={result.returncode}",
                "stderr": result.stderr[:300],
            }
        return json.loads(stdout, strict=False)
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "tool call timed out"}
    except json.JSONDecodeError as exc:
        return {"ok": False, "error": f"json decode error: {exc}"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


# ─── Extraction helpers ────────────────────────────────────────────────────────

def _extract_signal_info(session: dict) -> Optional[dict]:
    """
    Returns {"token_mint": ..., "entry_price": ..., "decision_type": ...} or None.

    - token_mint: pulled from token_get_profile call arguments
    - entry_price: pulled from paper_simulate_fill tool response (fill_price)
    - decision_type: pulled from agent_record_trading_decision call arguments
    - For no_trade: entry_price is the reference price from market_get_token_snapshot response
    """
    messages: list[dict] = session.get("messages") or []
    token_mint: Optional[str] = None
    entry_price: Optional[float] = None
    decision_type: Optional[str] = None

    # Scan assistant messages for tool call arguments
    for msg in messages:
        if msg.get("role") != "assistant":
            continue
        for tc in (msg.get("tool_calls") or []):
            fn = tc.get("function", {})
            name: str = fn.get("name", "")
            args_str: str = fn.get("arguments", "{}")
            try:
                args = json.loads(args_str, strict=False)
            except Exception:
                continue

            if name == "token_get_profile":
                tm = args.get("token_mint")
                if tm:
                    token_mint = str(tm)

            elif name == "agent_record_trading_decision":
                dt = args.get("decision_type")
                if dt:
                    decision_type = str(dt)

    # For SIGNAL: extract entry_price from paper_simulate_fill tool response
    # We look at ALL tool role messages for a "filled" / "fill_price" payload
    for msg in messages:
        if msg.get("role") != "tool":
            continue
        content_str = msg.get("content", "{}")
        try:
            content = json.loads(content_str, strict=False)
        except Exception:
            continue
        # paper_simulate_fill response has "filled": true and "fill_price"
        if content.get("filled") and "fill_price" in content:
            fp = content.get("fill_price")
            if fp is not None and str(fp).lower() not in ("", "market", "null", "none"):
                try:
                    entry_price = float(fp)
                except (ValueError, TypeError):
                    pass
            break  # only the first fill response matters

    # For NO_TRADE: get reference price from market_get_token_snapshot tool response
    resolved_decision = decision_type or "no_trade"
    if resolved_decision == "no_trade" and token_mint:
        for msg in messages:
            if msg.get("role") != "tool":
                continue
            try:
                content = json.loads(msg.get("content", "{}"), strict=False)
            except Exception:
                continue
            if content.get("ok") and "snapshot" in content:
                p = content["snapshot"].get("price_usd")
                if p is not None and str(p).lower() not in ("", "null", "none"):
                    try:
                        entry_price = float(p)
                        break
                    except (ValueError, TypeError):
                        pass

    if not token_mint:
        return None

    return {
        "token_mint": token_mint,
        "entry_price": entry_price,
        "decision_type": resolved_decision,
    }


def _session_age_hours(session: dict) -> Optional[float]:
    """Return session age in hours from its timestamp field, or None if unparseable."""
    ts_str: Optional[str] = session.get("timestamp")
    if not ts_str:
        return None
    try:
        ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        return (now - ts).total_seconds() / 3600.0
    except Exception:
        return None


def _get_current_price(token_mint: str) -> Optional[float]:
    """Fetch the current price for a token via market_get_token_snapshot."""
    resp = call_tool("market_get_token_snapshot", {"token_mint": token_mint})
    if not resp.get("ok"):
        return None
    snap = resp.get("snapshot", {})
    p = snap.get("price_usd")
    if p is None:
        return None
    try:
        return float(p)
    except (ValueError, TypeError):
        return None


# ─── Labeling logic ────────────────────────────────────────────────────────────

def _label_signal(
    entry_price: Optional[float],
    current_price: Optional[float],
    session_age_h: float,
) -> tuple[str, Optional[float]]:
    """
    Returns (label, pct_change).

    pct_change is None when price data is unavailable.
    """
    if entry_price is None or entry_price <= 0.0:
        # Cannot compute; if token is dead, call it a loss
        return ("loss", None)

    if current_price is None or current_price <= 0.0:
        # Token appears dead — label loss (entry was >4h ago, already checked upstream)
        return ("loss", None)

    pct_change = (current_price - entry_price) / entry_price * 100.0

    if pct_change >= 20.0:
        label = "excellent"
    elif pct_change >= 8.0:
        label = "good"
    elif pct_change >= 0.0:
        label = "marginal"
    else:
        label = "loss"

    return (label, pct_change)


def _label_no_trade(
    ref_price: Optional[float],
    current_price: Optional[float],
) -> tuple[str, Optional[float]]:
    """
    Returns (label, pct_change).

    pct_change is None when price data is unavailable.
    """
    if ref_price is None or ref_price <= 0.0:
        return ("neutral_no_trade", None)

    if current_price is None or current_price <= 0.0:
        # Token appears dead — correct to skip
        return ("good_no_trade", None)

    pct_change = (current_price - ref_price) / ref_price * 100.0

    if pct_change >= 20.0:
        label = "bad_no_trade"
    elif pct_change >= -10.0:
        label = "neutral_no_trade"
    else:
        label = "good_no_trade"

    return (label, pct_change)


# ─── Per-session worker ────────────────────────────────────────────────────────

def process_session(
    sf: Path,
    *,
    dry_run: bool,
    force: bool,
    min_age_h: float,
) -> str:
    """
    Process one session file.

    Returns one of: "labeled", "skipped_young", "already_labeled", "skipped_nodata", "error".
    """
    try:
        session = json.loads(sf.read_text(encoding="utf-8"), strict=False)
    except Exception as exc:
        _tprint(f"[error] {sf.name}: cannot parse JSON — {exc}")
        return "error"

    session_id: str = session.get("session_id") or sf.stem

    # Skip synthetic sessions — their labels are hardcoded, not market-derived
    if session.get("provider") in ("synthetic",) or sf.name.startswith("synth_"):
        return "already_labeled"

    # Check if already labeled
    existing_label: Optional[str] = session.get("outcome_label")
    if existing_label is not None and not force:
        return "already_labeled"

    # Session age gate
    age_h = _session_age_hours(session)
    if age_h is None:
        # Unparseable timestamp — treat conservatively as too young
        _tprint(f"[skip] {session_id}: cannot determine session age (no timestamp)")
        return "skipped_nodata"

    if age_h < min_age_h:
        return "skipped_young"

    # Extract signal info
    info = _extract_signal_info(session)
    if info is None:
        _tprint(f"[skip] {session_id}: cannot extract token_mint from messages")
        return "skipped_nodata"

    token_mint: str = info["token_mint"]
    entry_price: Optional[float] = info["entry_price"]
    decision_type: str = info["decision_type"]

    # Fetch current price
    current_price = _get_current_price(token_mint)

    # Compute label
    pct_change: Optional[float] = None
    if decision_type == "signal":
        label, pct_change = _label_signal(entry_price, current_price, age_h)
    else:
        label, pct_change = _label_no_trade(entry_price, current_price)

    # Format pct for display
    pct_str = f"{pct_change:+.1f}%" if pct_change is not None else "n/a"
    _tprint(f"[label] {session_id} -> {label} ({pct_str})")

    if dry_run:
        return "labeled"

    # Write outcome data back to session
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    session["outcome_label"] = label
    session["outcome_data"] = {
        "entry_price": entry_price,
        "current_price": current_price,
        "pct_change": round(pct_change, 4) if pct_change is not None else None,
        "labeled_at": now_str,
        "session_age_h": round(age_h, 2),
    }

    try:
        sf.write_text(
            json.dumps(session, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
    except Exception as exc:
        _tprint(f"[error] {session_id}: cannot write file — {exc}")
        return "error"

    return "labeled"


# ─── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Label existing fine-tune sessions with real price outcomes."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print labels but do not write files.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-label sessions that already have an outcome_label.",
    )
    parser.add_argument(
        "--min-age",
        type=float,
        default=4.0,
        metavar="HOURS",
        help="Minimum session age in hours before labeling (default: 4).",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=4,
        metavar="N",
        help="Number of parallel worker threads (default: 4).",
    )
    parser.add_argument(
        "--sessions-dir",
        type=Path,
        default=SESSIONS_DIR,
        metavar="DIR",
        help="Path to session JSON directory.",
    )
    args = parser.parse_args()

    sessions_dir: Path = args.sessions_dir
    if not sessions_dir.exists():
        print(f"[label] ERROR: sessions directory not found: {sessions_dir}")
        sys.exit(1)

    session_files = sorted(sessions_dir.glob("*.json"))
    total = len(session_files)
    if total == 0:
        print(f"[label] No session files found in {sessions_dir}")
        return

    print(f"[label] Found {total} session file(s) in {sessions_dir}")
    if args.dry_run:
        print("[label] DRY RUN — no files will be modified")
    if args.force:
        print("[label] FORCE — will re-label already-labeled sessions")
    print(f"[label] min_age={args.min_age}h  workers={args.workers}")
    print()

    stats: dict[str, int] = {
        "labeled": 0,
        "skipped_young": 0,
        "already_labeled": 0,
        "skipped_nodata": 0,
        "error": 0,
    }

    def _worker(sf: Path) -> str:
        return process_session(
            sf,
            dry_run=args.dry_run,
            force=args.force,
            min_age_h=args.min_age,
        )

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        future_to_path = {pool.submit(_worker, sf): sf for sf in session_files}
        for future in as_completed(future_to_path):
            result = future.result()
            stats[result] = stats.get(result, 0) + 1

    print()
    print("=" * 60)
    print(f"[label] Summary ({total} sessions total):")
    print(f"  labeled          : {stats['labeled']}")
    print(f"  skipped (too young) : {stats['skipped_young']}")
    print(f"  already labeled  : {stats['already_labeled']}")
    print(f"  skipped (no data): {stats['skipped_nodata']}")
    print(f"  errors           : {stats['error']}")
    print("=" * 60)


if __name__ == "__main__":
    main()
