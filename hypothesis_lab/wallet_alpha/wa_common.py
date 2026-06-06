"""wa_common — shared loaders + constants for the wallet-alpha sprint.

ONE place to parse block_time, derive price_sol, and load the raw_trades cross-section so every
script sees identical data. Leakage rule lives at the source: callers get trades with a clean unix
`ts`, and any point-in-time computation must filter `ts < event_t` itself.
"""
from __future__ import annotations

import os
import sqlite3
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LEGACY_DB = ROOT / "WalletScarper" / "data" / "walletscarper.sqlite3"
STAGE2_DB = ROOT / "WalletScarper" / "data" / "stage2_foundation.sqlite3"
CACHE = ROOT / "hypothesis_lab" / "wallet_alpha" / "_cache"
CACHE.mkdir(exist_ok=True)

# Round-trip cost on Solana memecoin DEX (entry+exit fee+slippage). Matches copy_engine COST.
# Flat assumption — a known promotion-blocker; see knowledge/QUESTIONS.md.
COST_RT = 0.018

# raw_trades is a 5.5h snapshot on 2026-05-14; the 05-16 tail is dropped to keep one clean session.
SESSION_DAY = "2026-05-14"


def ensure_utf8():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore
    except Exception:
        pass


def parse_ts(bt) -> float | None:
    """block_time -> unix seconds. Handles ISO (with/without Z) and unix-epoch strings."""
    if bt is None:
        return None
    s = str(bt)
    try:
        if s.isdigit():
            return float(int(s))
        return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
    except Exception:
        return None


@dataclass
class Trade:
    ts: float
    wallet: str
    token: str
    side: str          # 'buy' | 'sell'
    sol: float         # quote_amount (SOL notional)
    qty: float         # token_amount
    price: float       # price_sol = sol/qty (SOL per token)


def load_raw_trades(session_only: bool = True, min_sol: float = 0.0) -> list[Trade]:
    """Load raw_trades as clean Trade rows, time-sorted. price_sol = quote_amount/token_amount.

    session_only: keep only the 2026-05-14 firehose (drop the sparse 05-16 tail).
    min_sol: drop dust trades below this SOL notional (noise / failed swaps).
    """
    db = sqlite3.connect(str(LEGACY_DB))
    q = ("SELECT block_time, wallet, token_mint, side, quote_amount, token_amount "
         "FROM raw_trades WHERE quote_amount > 0 AND token_amount > 0")
    if session_only:
        q += f" AND block_time LIKE '{SESSION_DAY}%'"
    out: list[Trade] = []
    for bt, w, tok, side, sol, qty in db.execute(q):
        ts = parse_ts(bt)
        if ts is None or not w or not tok or side not in ("buy", "sell"):
            continue
        if sol < min_sol:
            continue
        out.append(Trade(ts, w, tok, side, float(sol), float(qty), float(sol) / float(qty)))
    db.close()
    out.sort(key=lambda t: t.ts)
    return out


def session_bounds(trades: list[Trade]) -> tuple[float, float]:
    return (trades[0].ts, trades[-1].ts) if trades else (0.0, 0.0)


def fmt_hms(ts: float) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%H:%M:%S")
