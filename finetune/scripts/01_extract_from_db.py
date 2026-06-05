"""
Script 01: Extract real signal events and decisions from stage2 DB.

Output: data/raw/real_events.json
  - All tracked_wallet_signal_events (real_source only)
  - Their agent_trading_decisions (if recorded)
  - Related token_profiles and wallet_metric_snapshots
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import aiosqlite

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "WalletScarper" / "data" / "stage2_foundation.sqlite3"
OUT_PATH = ROOT / "finetune" / "data" / "raw" / "real_events.json"


async def extract() -> None:
    if not DB_PATH.exists():
        print(f"[ERROR] DB not found: {DB_PATH}", file=sys.stderr)
        sys.exit(1)

    async with aiosqlite.connect(str(DB_PATH)) as db:
        db.row_factory = aiosqlite.Row

        # All real-source signal events
        cur = await db.execute(
            """
            SELECT *
            FROM tracked_wallet_signal_events
            WHERE input_mode = 'real_source'
            ORDER BY observed_at DESC
            """
        )
        events = [dict(r) for r in await cur.fetchall()]
        print(f"[01] Found {len(events)} real_source signal events")

        # For each event, pull its decision (if any)
        for event in events:
            sid = event["tracked_wallet_signal_event_id"]
            cur = await db.execute(
                """
                SELECT *
                FROM agent_trading_decisions
                WHERE linked_tracked_wallet_signal_event_id = ?
                ORDER BY created_at DESC LIMIT 1
                """,
                (sid,),
            )
            row = await cur.fetchone()
            event["_decision"] = dict(row) if row else None

        # Pull token profiles for each unique token_mint
        mints = list({e["token_mint"] for e in events if e.get("token_mint")})
        token_profiles: dict[str, dict] = {}
        for mint in mints:
            cur = await db.execute(
                """
                SELECT *
                FROM token_profiles
                WHERE token_mint = ?
                ORDER BY latest_observed_at DESC, created_at DESC
                LIMIT 1
                """,
                (mint,),
            )
            row = await cur.fetchone()
            if row:
                token_profiles[mint] = dict(row)
        print(f"[01] Found {len(token_profiles)} token profiles")

        # Pull wallet metric snapshots for each unique wallet
        wallets = list({e["wallet"] for e in events if e.get("wallet")})
        wallet_metrics: dict[str, dict] = {}
        for wallet in wallets:
            cur = await db.execute(
                """
                SELECT *
                FROM wallet_metric_snapshots
                WHERE wallet = ?
                ORDER BY calculated_at DESC, created_at DESC
                LIMIT 1
                """,
                (wallet,),
            )
            row = await cur.fetchone()
            if row:
                wallet_metrics[wallet] = dict(row)
        print(f"[01] Found {len(wallet_metrics)} wallet metric snapshots")

        # Statistics
        with_decision = sum(1 for e in events if e["_decision"])
        signal_count = sum(
            1 for e in events
            if e["_decision"] and e["_decision"].get("decision_type") == "signal"
        )
        no_trade_count = sum(
            1 for e in events
            if e["_decision"] and e["_decision"].get("decision_type") == "no_trade"
        )

        output = {
            "stats": {
                "total_events": len(events),
                "with_decision": with_decision,
                "without_decision": len(events) - with_decision,
                "signal": signal_count,
                "no_trade": no_trade_count,
                "other": with_decision - signal_count - no_trade_count,
            },
            "events": events,
            "token_profiles": token_profiles,
            "wallet_metrics": wallet_metrics,
        }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(output, indent=2, default=str), encoding="utf-8")
    print(f"[01] Written to {OUT_PATH.relative_to(ROOT)}")
    print(f"[01] Stats: {output['stats']}")
    print()
    print("[01] NOTE: Events without decisions are candidates for teacher labeling (script 02).")
    print("[01] Events with decisions can be used as training examples (script 02 will verify quality).")


if __name__ == "__main__":
    asyncio.run(extract())
