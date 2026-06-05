"""
Realistic-Exit Labeler (blueprint #2/#5) — honest reward, REAL price paths.

Replaces the hindsight-leaking `max(price)` label (which assumes perfect exit
timing and violates the project's own "no hindsight" principle) with P&L under
the ACTUAL exit rule the policy committed to: stop-loss at the invalidation
threshold, otherwise exit at the holding horizon.

Reward = net expectancy after costs (fees + slippage) = the project north-star.

Reads market_snapshots (token price time-series) from the real DB, point-in-time:
only snapshots with observed_at in (entry_time, entry_time + holding] are used.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB = ROOT / "WalletScarper" / "data" / "stage2_foundation.sqlite3"

# Confidence-tier exit rules (mirror generate_real_sessions conf_params).
EXIT_RULES = {
    "high":   {"invalidation_pct": 0.15, "holding_seconds": 90 * 60},
    "medium": {"invalidation_pct": 0.20, "holding_seconds": 4 * 3600},
    "low":    {"invalidation_pct": 0.25, "holding_seconds": 8 * 3600},
}
DEFAULT_FEE_BPS = 30      # round-trip fee estimate
DEFAULT_SLIPPAGE_BPS = 150  # memecoin slippage estimate (size-dependent in reality)


def _parse_ts(s: Any) -> float | None:
    if s is None:
        return None
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00")).timestamp()
    except Exception:
        return None


@dataclass
class ExitResult:
    label: str
    realized_pnl_net: float | None          # fraction, after costs (e.g. +0.14 = +14%)
    exit_rule_applied: str
    exit_reason: str                         # stop_loss | horizon | no_path
    gross_ratio: float | None
    checkpoints: dict[str, float]
    n_path_points: int


class RealisticExitLabeler:
    def __init__(self, db_path: str | Path = DEFAULT_DB,
                 fee_bps: float = DEFAULT_FEE_BPS,
                 slippage_bps: float = DEFAULT_SLIPPAGE_BPS) -> None:
        self.db_path = str(db_path)
        self.cost_frac = (fee_bps + slippage_bps) / 10_000.0

    def _price_path(self, token_mint: str, start_ts: float, end_ts: float) -> list[tuple[float, float]]:
        con = sqlite3.connect(self.db_path)
        con.row_factory = sqlite3.Row
        try:
            rows = con.execute(
                "SELECT observed_at, price_usd FROM market_snapshots "
                "WHERE token_mint = ? AND price_usd IS NOT NULL",
                (token_mint,),
            ).fetchall()
            # Union backfilled price paths (token_price_paths) if the table exists.
            try:
                rows = list(rows) + con.execute(
                    "SELECT observed_at, price_usd FROM token_price_paths "
                    "WHERE token_mint = ? AND price_usd IS NOT NULL",
                    (token_mint,),
                ).fetchall()
            except sqlite3.OperationalError:
                pass  # table not created yet
        finally:
            con.close()
        rows = sorted(rows, key=lambda r: r["observed_at"])
        path = []
        for r in rows:
            ts = _parse_ts(r["observed_at"])
            px = r["price_usd"]
            if ts is None or px is None:
                continue
            if start_ts < ts <= end_ts:
                try:
                    path.append((ts, float(px)))
                except (TypeError, ValueError):
                    continue
        return path

    def label_signal(
        self,
        token_mint: str,
        entry_time: str | float,
        entry_price: float,
        confidence_tier: str = "medium",
    ) -> ExitResult:
        """Label a SIGNAL decision by simulating its committed exit rule."""
        rule = EXIT_RULES.get(confidence_tier, EXIT_RULES["medium"])
        inval = rule["invalidation_pct"]
        hold = rule["holding_seconds"]
        rule_str = f"invalidation:-{inval:.0%} | hold:{hold // 60}m"

        start = _parse_ts(entry_time) if not isinstance(entry_time, (int, float)) else float(entry_time)
        if start is None or not entry_price or entry_price <= 0:
            return ExitResult("loss", None, rule_str, "no_path", None, {}, 0)

        path = self._price_path(token_mint, start, start + hold)
        if not path:
            return ExitResult("unlabeled", None, rule_str, "no_path", None, {}, 0)

        stop_price = entry_price * (1 - inval)
        exit_px = None
        reason = "horizon"
        checkpoints: dict[str, float] = {}
        for ts, px in path:
            checkpoints[str(int(ts - start))] = px
            if px <= stop_price:
                exit_px = stop_price   # assume stop fills at threshold (conservative)
                reason = "stop_loss"
                break
        if exit_px is None:
            exit_px = path[-1][1]       # exit at horizon = last observed price in window

        gross_ratio = exit_px / entry_price
        net_pnl = (gross_ratio - 1.0) - self.cost_frac
        label = self._label_from_pnl(net_pnl)
        return ExitResult(label, round(net_pnl, 4), rule_str, reason,
                          round(gross_ratio, 4), checkpoints, len(path))

    def label_no_trade(
        self, token_mint: str, ref_time: str | float, ref_price: float,
        horizon_seconds: int = 4 * 3600,
    ) -> ExitResult:
        """Label a NO_TRADE: did we correctly avoid it? Uses realistic horizon, not max."""
        start = _parse_ts(ref_time) if not isinstance(ref_time, (int, float)) else float(ref_time)
        if start is None or not ref_price or ref_price <= 0:
            return ExitResult("neutral_no_trade", None, "horizon:4h", "no_path", None, {}, 0)
        path = self._price_path(token_mint, start, start + horizon_seconds)
        if not path:
            return ExitResult("unlabeled", None, "horizon:4h", "no_path", None, {}, 0)
        # Counterfactual: what a medium-confidence trade WOULD have netted.
        cf = self.label_signal(token_mint, start, ref_price, "medium")
        cf_pnl = cf.realized_pnl_net or 0.0
        if cf_pnl >= 0.10:
            label = "bad_no_trade"     # we skipped a real winner
        elif cf_pnl <= 0.02:
            label = "good_no_trade"    # correctly avoided
        else:
            label = "neutral_no_trade"
        return ExitResult(label, round(cf_pnl, 4), "horizon:4h", "counterfactual",
                          cf.gross_ratio, cf.checkpoints, cf.n_path_points)

    @staticmethod
    def _label_from_pnl(net: float) -> str:
        if net >= 0.20:
            return "excellent"
        if net >= 0.08:
            return "good"
        if net >= 0.0:
            return "marginal"
        return "loss"


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore
    lab = RealisticExitLabeler()
    con = sqlite3.connect(lab.db_path)
    con.row_factory = sqlite3.Row
    # token with a real price path
    row = con.execute(
        "SELECT token_mint, COUNT(*) c FROM market_snapshots WHERE price_usd IS NOT NULL "
        "AND token_mint NOT LIKE '%fixture%' AND token_mint NOT LIKE 'acceptance%' "
        "GROUP BY token_mint HAVING c>=3 ORDER BY c DESC LIMIT 1"
    ).fetchone()
    if not row:
        print("No real token price path found.")
    else:
        tok = row["token_mint"]
        path = con.execute(
            "SELECT observed_at, price_usd FROM market_snapshots WHERE token_mint=? "
            "AND price_usd IS NOT NULL ORDER BY observed_at ASC", (tok,)
        ).fetchall()
        entry_ts = _parse_ts(path[0]["observed_at"])
        entry_px = float(path[0]["price_usd"])
        print(f"token={tok[:20]} path_points={len(path)} entry_px={entry_px}")
        res = lab.label_signal(tok, entry_ts, entry_px, "medium")
        print("SIGNAL label:", res.label, "net_pnl:", res.realized_pnl_net,
              "reason:", res.exit_reason, "gross:", res.gross_ratio, "rule:", res.exit_rule_applied)
        res2 = lab.label_no_trade(tok, entry_ts, entry_px)
        print("NO_TRADE label:", res2.label, "cf_pnl:", res2.realized_pnl_net)
    con.close()
