"""
Historical Replay Engine (blueprint #38) — THE data unlock.

Turns historical wallet→token events into outcome-labelled Decision Records
WITHOUT waiting for real-time horizons: the future price is already in the DB,
so the reward-optimal action is known.

For each real wallet_token_outcome that has an entry_time and a token price path:
  1. as_of = entry_time
  2. wallet_features  = point-in-time (data <= as_of)   ← survivorship-safe
  3. token snapshot   = nearest market_snapshot <= as_of ← point-in-time
  4. realistic-exit    = simulate the committed exit rule on the FUTURE path
  5. target action     = signal if a trade would net > threshold, else no_trade
  6. emit DecisionRecord(source="replay", decision=target, outcome=realized)

The TARGET uses the outcome (that is the label); FEATURES never do (no leakage).
This is outcome-as-teacher at the record level — strictly better than formula labels.

Today the corpus is small (few tokens have real price paths). The engine is ready
and scales automatically as market_snapshots / wallet_token_outcomes accumulate.

Run:
  python -m finetune.pipeline.replay_engine --report          # corpus size truth
  python -m finetune.pipeline.replay_engine --emit-sft out.jsonl
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB = ROOT / "WalletScarper" / "data" / "stage2_foundation.sqlite3"
PROMPTS_DIR = ROOT / "finetune" / "prompts"

from finetune.pipeline.decision_record import (
    DecisionRecord, SignalBlock, WalletFeatures, TokenFeatures,
    MarketFeatures, DecisionBlock, OutcomeBlock, Provenance,
)
from finetune.pipeline.wallet_features import WalletFeatureEngine, _parse_ts
from finetune.pipeline.realistic_exit import RealisticExitLabeler

# A replay trade is "worth taking" if its realistic net P&L clears this bar.
SIGNAL_THRESHOLD = 0.0


def _confidence_from_pnl(net: float) -> str:
    if net >= 0.20:
        return "high"
    if net >= 0.08:
        return "medium"
    return "low"


class ReplayEngine:
    def __init__(self, db_path: str | Path = DEFAULT_DB) -> None:
        self.db_path = str(db_path)
        self.wallets = WalletFeatureEngine(db_path)
        self.labeler = RealisticExitLabeler(db_path)

    def _candidates(self) -> list[sqlite3.Row]:
        """Real wallet_token_outcomes with an entry_time (replayable)."""
        con = sqlite3.connect(self.db_path)
        con.row_factory = sqlite3.Row
        try:
            return con.execute(
                "SELECT * FROM wallet_token_outcomes "
                "WHERE entry_time IS NOT NULL "
                "AND wallet NOT LIKE '%fixture%' AND wallet NOT LIKE 'acceptance%' "
                "AND token_mint NOT LIKE '%fixture%' AND token_mint NOT LIKE 'acceptance%' "
                "ORDER BY entry_time ASC"
            ).fetchall()
        finally:
            con.close()

    def _entry_snapshot(self, token_mint: str, as_of_ts: float) -> sqlite3.Row | None:
        """Nearest market snapshot at or before entry (point-in-time)."""
        con = sqlite3.connect(self.db_path)
        con.row_factory = sqlite3.Row
        try:
            rows = con.execute(
                "SELECT * FROM market_snapshots WHERE token_mint = ? AND price_usd IS NOT NULL "
                "ORDER BY observed_at ASC", (token_mint,)
            ).fetchall()
        finally:
            con.close()
        best = None
        for r in rows:
            ts = _parse_ts(r["observed_at"])
            if ts is not None and ts <= as_of_ts:
                best = r
            elif ts is not None and ts > as_of_ts:
                break
        return best

    def _has_future_path(self, token_mint: str, as_of_ts: float) -> bool:
        con = sqlite3.connect(self.db_path)
        try:
            n = con.execute(
                "SELECT COUNT(*) FROM market_snapshots WHERE token_mint=? AND price_usd IS NOT NULL "
                "AND observed_at > ?", (token_mint, datetime.utcfromtimestamp(as_of_ts).isoformat())
            ).fetchone()[0]
        finally:
            con.close()
        return n > 0

    def build_records(self, limit: int | None = None) -> list[DecisionRecord]:
        out: list[DecisionRecord] = []
        for row in self._candidates():
            as_of_ts = _parse_ts(row["entry_time"])
            if as_of_ts is None:
                continue
            snap = self._entry_snapshot(row["token_mint"], as_of_ts)
            if not snap:
                continue
            entry_price = None
            try:
                entry_price = float(snap["price_usd"])
            except (TypeError, ValueError):
                continue
            # Need a FUTURE path to label honestly.
            exit_res = self.labeler.label_signal(row["token_mint"], as_of_ts, entry_price, "medium")
            if exit_res.realized_pnl_net is None:
                continue  # no future path → cannot label

            net = exit_res.realized_pnl_net
            target = "signal" if net > SIGNAL_THRESHOLD else "no_trade"
            tier = _confidence_from_pnl(net) if target == "signal" else None

            wp = self.wallets.point_in_time(row["wallet"], as_of_ts)

            buy_vs_liq = None
            notional = row["notional_usd"]
            liq = snap["liquidity_usd"]
            try:
                if notional and liq and float(liq) > 0:
                    buy_vs_liq = round(float(notional) / float(liq), 4)
            except (TypeError, ValueError):
                pass

            rec = DecisionRecord(
                signal=SignalBlock(wallet=row["wallet"], token_mint=row["token_mint"],
                                   side="buy", observed_at=str(row["entry_time"])),
                source="replay",
                model_version="replay-groundtruth",
                wallet_features=WalletFeatures(
                    scalars=wp.scalars, style_tags=wp.tags, form_state=wp.form_state,
                    post_discovery_validated=wp.post_discovery_validated,
                    buy_size_vs_liquidity=buy_vs_liq,
                ),
                token_features=TokenFeatures(
                    liquidity_usd=_safe(snap["liquidity_usd"]),
                    market_cap=_safe(snap["market_cap"]),
                    microstructure={"holder_count": snap["holder_count"],
                                    "volume_24h": _safe(snap["volume_24h"])},
                ),
                market_features=MarketFeatures(price_usd=entry_price),
                decision=DecisionBlock(
                    type=target, confidence_tier=tier,
                    reasoning=(f"Replay ground-truth: realistic-exit net {net:+.1%} "
                               f"({exit_res.exit_reason}, {exit_res.exit_rule_applied}). "
                               f"Reward-optimal action = {target}."),
                ),
                outcome=OutcomeBlock(
                    exit_rule_applied=exit_res.exit_rule_applied,
                    realized_pnl_net=net, label=exit_res.label,
                    checkpoints=exit_res.checkpoints,
                ),
                provenance=Provenance(propensity=1.0, exploration=False),
            )
            out.append(rec)
            if limit and len(out) >= limit:
                break
        return out


def _safe(v):
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", action="store_true", help="Print corpus-size truth and exit.")
    ap.add_argument("--emit-sft", metavar="PATH", help="Write replay records as text-to-text SFT JSONL.")
    ap.add_argument("--emit-records", metavar="PATH", help="Write raw Decision Records JSONL.")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    eng = ReplayEngine()
    cands = eng._candidates()
    print(f"[replay] replayable wallet_token_outcomes (entry_time present): {len(cands)}")

    recs = eng.build_records(limit=args.limit)
    print(f"[replay] Decision Records built (had future price path): {len(recs)}")
    if recs:
        from collections import Counter
        print("[replay] target actions:", dict(Counter(r.decision.type for r in recs)))
        print("[replay] outcome labels:", dict(Counter(r.outcome.label for r in recs)))

    if args.report:
        if not recs:
            print("[replay] Corpus is data-starved today (few tokens have real price paths).")
            print("[replay] Engine is ready; corpus grows as market_snapshots accumulates.")
        return

    if args.emit_records and recs:
        Path(args.emit_records).write_text(
            "\n".join(r.to_json() for r in recs), encoding="utf-8")
        print(f"[replay] wrote {len(recs)} records -> {args.emit_records}")

    if args.emit_sft and recs:
        system = (PROMPTS_DIR / "teacher_system.md").read_text(encoding="utf-8")
        with open(args.emit_sft, "w", encoding="utf-8") as f:
            for r in recs:
                f.write(json.dumps(r.to_sft_example(system), ensure_ascii=False) + "\n")
        print(f"[replay] wrote {len(recs)} SFT examples -> {args.emit_sft}")


if __name__ == "__main__":
    main()
