"""
Wallet leaderboard builder — score our wallet pool from chain, rank, persist.

Answers "track the best wallets from our DB": scores each candidate wallet via
Helius (real on-chain PnL), ranks by composite score, writes a leaderboard.
Incremental checkpoint to JSON after every wallet (restart-safe).

Forward-validation: pass --since (unix ts) to score only post-discovery trades.

SECURITY: Helius keys via env only.

Run:
  python -m finetune.pipeline.wallet_leaderboard --limit 150 --pages 2
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from dataclasses import asdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore

ROOT = Path(__file__).resolve().parents[2]
DB = ROOT / "WalletScarper" / "data" / "stage2_foundation.sqlite3"
OUT = ROOT / "finetune" / "data" / "wallet_leaderboard.json"

from finetune.pipeline.wallet_scoring import score_wallet


def candidate_wallets() -> list[str]:
    con = sqlite3.connect(str(DB))
    rows = con.execute(
        "SELECT DISTINCT wallet FROM wallet_token_outcomes "
        "WHERE length(wallet) BETWEEN 43 AND 44 "
        "AND wallet NOT LIKE '%fixture%' AND wallet NOT LIKE 'acceptance%'"
    ).fetchall()
    con.close()
    return [r[0] for r in rows]


def _load() -> list[dict]:
    if OUT.exists():
        try:
            return json.loads(OUT.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def _save(results: list[dict]) -> None:
    ranked = sorted(results, key=lambda r: r["score"], reverse=True)
    OUT.write_text(json.dumps(ranked, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=150)
    ap.add_argument("--pages", type=int, default=2)
    ap.add_argument("--since", type=int, default=0, help="unix ts: score only trades after")
    a = ap.parse_args()

    wallets = candidate_wallets()
    results = _load()
    done = {r["wallet"] for r in results}
    todo = [w for w in wallets if w not in done][: a.limit]
    print(f"[lb] candidates={len(wallets)} already_scored={len(done)} scoring_now={len(todo)}")

    ok = fail = 0
    for i, w in enumerate(todo):
        try:
            sc = score_wallet(w, pages=a.pages, since_ts=a.since)
            if sc:
                results.append(asdict(sc)); ok += 1
                _save(results)
            else:
                fail += 1
        except Exception as e:
            fail += 1
            print(f"  [{i}] {w[:14]} ERR {str(e)[:60]}", flush=True)
        if i % 10 == 0:
            top = sorted(results, key=lambda r: r["score"], reverse=True)[:1]
            t = top[0] if top else {}
            print(f"  [{i}/{len(todo)}] scored ok={ok} fail={fail} "
                  f"best={t.get('wallet','')[:12]}({t.get('score')})", flush=True)
        time.sleep(0.2)

    _save(results)
    print(f"\n[lb] DONE ok={ok} fail={fail} total={len(results)} -> {OUT.name}")
    print("\n=== TOP 15 WALLETS (by score) ===")
    for r in sorted(results, key=lambda r: r["score"], reverse=True)[:15]:
        print(f"  {r['wallet'][:24]}  score={r['score']}  pnl={r['realized_pnl_sol']:+.2f}SOL  "
              f"win={r['win_rate']:.0%}  payoff={r['payoff_ratio']}  tokens={r['n_tokens']}  "
              f"hold={r['avg_hold_sec']:.0f}s")


if __name__ == "__main__":
    main()
