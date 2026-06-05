"""
Wallet Behavioral Feature Engine (blueprint §A) — REAL data, point-in-time.

Turns a wallet into a behavioral profile, not 4 scalars. Reads
wallet_metric_snapshots (time-series of computed metrics) from the real DB.

Point-in-time discipline (CRITICAL — survivorship guard #59):
  Features for a decision at time `as_of` use ONLY snapshots with
  calculated_at <= as_of. A wallet's later success cannot leak backward.

Behavioral axes (A.1) computed from what the DB actually carries today:
  - aggression       ← position_sizing_summary (average_usd, count)
  - patience         ← holding_time_summary (average_seconds)
  - edge             ← expectancy_estimate / payoff_ratio
  - consistency      ← win_rate stability across snapshots
  - experience       ← trade_count / sample_size
Form (A.2): trend of expectancy across the wallet's snapshot history (hot/cold).

Many fields are null in the current acceptance DB; every getter is null-safe and
degrades to `data_sufficiency` flags rather than fabricating values.
"""
from __future__ import annotations

import json
import math
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB = ROOT / "WalletScarper" / "data" / "stage2_foundation.sqlite3"


def _parse_ts(s: str | None) -> float | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00")).timestamp()
    except Exception:
        return None


def _f(v: Any) -> float | None:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


@dataclass
class WalletProfile:
    wallet: str
    scalars: dict[str, Any] = field(default_factory=dict)
    axes: dict[str, float | None] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    form_state: dict[str, Any] = field(default_factory=dict)
    snapshot_count: int = 0
    post_discovery_validated: bool = False
    data_sufficiency: str = "insufficient"


class WalletFeatureEngine:
    def __init__(self, db_path: str | Path = DEFAULT_DB) -> None:
        self.db_path = str(db_path)

    def _rows(self, wallet: str, as_of_ts: float | None) -> list[sqlite3.Row]:
        con = sqlite3.connect(self.db_path)
        con.row_factory = sqlite3.Row
        try:
            rows = con.execute(
                "SELECT * FROM wallet_metric_snapshots WHERE wallet = ? ORDER BY calculated_at ASC",
                (wallet,),
            ).fetchall()
        finally:
            con.close()
        if as_of_ts is None:
            return rows
        # Point-in-time filter
        return [r for r in rows if (_parse_ts(r["calculated_at"]) or 0) <= as_of_ts]

    def point_in_time(self, wallet: str, as_of: str | float | None = None) -> WalletProfile:
        as_of_ts = as_of if isinstance(as_of, (int, float)) else _parse_ts(as_of) if as_of else None
        rows = self._rows(wallet, as_of_ts)
        prof = WalletProfile(wallet=wallet, snapshot_count=len(rows))
        if not rows:
            return prof

        latest = rows[-1]
        win_rate = _f(latest["win_rate_estimate"])
        payoff = _f(latest["payoff_ratio"])
        expectancy = _f(latest["expectancy_estimate"])
        net_pnl = _f(latest["net_pnl_estimate"])
        trade_count = _f(latest["trade_count"]) or 0
        sample = _f(latest["sample_size"]) or trade_count

        prof.scalars = {
            "win_rate_estimate": win_rate,
            "payoff_ratio": payoff,
            "expectancy_estimate": expectancy,
            "net_pnl_estimate": net_pnl,
            "trade_count": int(trade_count),
        }

        # ── behavioral axes ──────────────────────────────────────────────────────
        hold = self._json(latest["holding_time_summary_json"])
        size = self._json(latest["position_sizing_summary_json"])
        avg_hold_s = _f(hold.get("average_seconds"))
        avg_size = _f(size.get("average_usd"))

        axes: dict[str, float | None] = {
            # patience: 0 (seconds) → 1 (hours+). log-scaled.
            "patience": (min(1.0, math.log10(avg_hold_s) / 4.0) if avg_hold_s and avg_hold_s > 1 else None),
            # aggression: bigger avg size = more aggressive. $50→0, $5000→1 (log).
            "aggression": (min(1.0, max(0.0, (math.log10(avg_size) - 1.7) / 1.7)) if avg_size and avg_size > 0 else None),
            # edge: expectancy sign/magnitude proxy via payoff.
            "edge": (min(1.0, payoff / 5.0) if payoff is not None and payoff >= 0 else None),
            # experience: trade depth.
            "experience": min(1.0, max(0.0, (sample - 3) / 47.0)) if sample else 0.0,
        }
        # consistency: stability of win_rate across snapshots (lower variance = higher).
        wrs = [_f(r["win_rate_estimate"]) for r in rows]
        wrs = [w for w in wrs if w is not None]
        if len(wrs) >= 2:
            mean = sum(wrs) / len(wrs)
            var = sum((w - mean) ** 2 for w in wrs) / len(wrs)
            axes["consistency"] = max(0.0, 1.0 - min(1.0, var * 4))
        else:
            axes["consistency"] = None
        prof.axes = axes

        # ── form / regime (A.2): trend of expectancy hot↔cold ────────────────────
        exps = [_f(r["expectancy_estimate"]) for r in rows]
        exps = [e for e in exps if e is not None]
        if len(exps) >= 2:
            recent = exps[-1]
            prior = sum(exps[:-1]) / len(exps[:-1])
            hot_cold = math.tanh((recent - prior))  # >0 hot, <0 cold
            prof.form_state = {"hot_cold": round(hot_cold, 3), "snapshots": len(exps)}
        else:
            prof.form_state = {"hot_cold": 0.0, "snapshots": len(exps)}

        # ── tags ──────────────────────────────────────────────────────────────────
        prof.tags = self._tags(axes, prof.form_state)

        # ── survivorship guard: validated only if >=2 snapshots span time ─────────
        prof.post_discovery_validated = len(rows) >= 2
        prof.data_sufficiency = (
            "sufficient" if (sample and sample >= 20 and payoff is not None)
            else "partial" if rows else "insufficient"
        )
        return prof

    @staticmethod
    def _json(s: Any) -> dict:
        if not s or s == "null":
            return {}
        try:
            d = json.loads(s)
            return d if isinstance(d, dict) else {}
        except Exception:
            return {}

    @staticmethod
    def _tags(axes: dict, form: dict) -> list[str]:
        t: list[str] = []
        p, a, c = axes.get("patience"), axes.get("aggression"), axes.get("consistency")
        if p is not None:
            t.append("patient" if p >= 0.5 else "fast_flipper")
        if a is not None:
            t.append("aggressive" if a >= 0.5 else "conservative_size")
        if c is not None and c >= 0.6:
            t.append("consistent")
        hc = form.get("hot_cold", 0.0)
        if hc >= 0.2:
            t.append("hot_streak")
        elif hc <= -0.2:
            t.append("cold_streak")
        return t


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore
    eng = WalletFeatureEngine()
    # Find a real wallet with multiple snapshots
    con = sqlite3.connect(eng.db_path)
    con.row_factory = sqlite3.Row
    cand = con.execute(
        "SELECT wallet, COUNT(*) c FROM wallet_metric_snapshots "
        "WHERE wallet NOT LIKE '%fixture%' AND wallet NOT LIKE 'acceptance%' "
        "GROUP BY wallet ORDER BY c DESC LIMIT 3"
    ).fetchall()
    con.close()
    print("Top real wallets by snapshot count:", [(r["wallet"][:16], r["c"]) for r in cand])
    for r in cand:
        prof = eng.point_in_time(r["wallet"])
        print(f"\n{r['wallet'][:20]}  snapshots={prof.snapshot_count}  suff={prof.data_sufficiency}")
        print("  scalars:", prof.scalars)
        print("  axes:", {k: (round(v, 3) if isinstance(v, float) else v) for k, v in prof.axes.items()})
        print("  tags:", prof.tags, " form:", prof.form_state)
