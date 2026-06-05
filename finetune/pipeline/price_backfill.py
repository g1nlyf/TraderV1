"""
Price-Path Backfill Fabric (blueprint B.3) — unblocks the replay engine.

Replay (#38) needs price paths for the tokens in the outcome corpus. Today the
corpus is concentrated in ~9 distinct pools, so backfilling is cheap.

Source: GeckoTerminal OHLCV (free, no API key, ~30 req/min).
  GET /networks/solana/pools/{pool}/ohlcv/{timeframe}?aggregate=1&limit=1000

Writes to a dedicated `token_price_paths` table (non-invasive — does NOT touch the
real market_snapshots schema). realistic_exit / replay read it as a price source.

Parallel by design (ThreadPoolExecutor) — one fetch per pool, deduped. Scales to
hundreds of pools when the corpus grows (idea B.3: one shared poll per token).

Run:
  python -m finetune.pipeline.price_backfill --dry-run         # plan only, no network
  python -m finetune.pipeline.price_backfill --test-one        # ONE real fetch (proof)
  python -m finetune.pipeline.price_backfill --run             # backfill all corpus pools
  python -m finetune.pipeline.price_backfill --run --timeframe hour --workers 4
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB = ROOT / "WalletScarper" / "data" / "stage2_foundation.sqlite3"

GECKO_BASE = "https://api.geckoterminal.com/api/v2"
NETWORK = "solana"
USER_AGENT = "TraderV1-backfill/1.0"


def _ensure_table(con: sqlite3.Connection) -> None:
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS token_price_paths (
            token_mint   TEXT NOT NULL,
            pool_address TEXT,
            observed_at  TEXT NOT NULL,
            price_usd    REAL NOT NULL,
            source       TEXT NOT NULL,
            created_at   TEXT NOT NULL,
            UNIQUE(token_mint, observed_at, source)
        )
        """
    )
    con.execute("CREATE INDEX IF NOT EXISTS ix_tpp_token ON token_price_paths(token_mint, observed_at)")
    con.commit()


def corpus_pools(db_path: str) -> list[tuple[str, str]]:
    """Distinct (token_mint, pool_address) in the replayable outcome corpus."""
    con = sqlite3.connect(db_path)
    try:
        rows = con.execute(
            "SELECT DISTINCT token_mint, pool_address FROM wallet_token_outcomes "
            "WHERE entry_time IS NOT NULL AND pool_address IS NOT NULL "
            "AND token_mint NOT LIKE '%fixture%' AND token_mint NOT LIKE 'acceptance%' "
            "AND pool_address NOT LIKE '%fixture%' AND pool_address NOT LIKE 'acceptance%'"
        ).fetchall()
    finally:
        con.close()
    return [(r[0], r[1]) for r in rows]


class GeckoTerminalSource:
    def __init__(self, timeframe: str = "hour", aggregate: int = 1, limit: int = 1000):
        self.timeframe = timeframe
        self.aggregate = aggregate
        self.limit = limit

    def fetch(self, pool: str) -> list[tuple[int, float]]:
        url = (f"{GECKO_BASE}/networks/{NETWORK}/pools/{pool}/ohlcv/{self.timeframe}"
               f"?aggregate={self.aggregate}&limit={self.limit}")
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT,
                                                   "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        ohlcv = (data.get("data", {}).get("attributes", {}).get("ohlcv_list", []))
        out = []
        for row in ohlcv:
            # [timestamp, open, high, low, close, volume]
            try:
                ts = int(row[0]); close = float(row[4])
                if close > 0:
                    out.append((ts, close))
            except (IndexError, TypeError, ValueError):
                continue
        return out


def _write_path(con: sqlite3.Connection, token: str, pool: str,
                points: list[tuple[int, float]], source: str) -> int:
    now = datetime.now(timezone.utc).isoformat()
    n = 0
    for ts, px in points:
        iso = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
        try:
            con.execute(
                "INSERT OR IGNORE INTO token_price_paths "
                "(token_mint, pool_address, observed_at, price_usd, source, created_at) "
                "VALUES (?,?,?,?,?,?)",
                (token, pool, iso, px, source, now),
            )
            n += 1
        except Exception:
            continue
    con.commit()
    return n


def backfill(db_path: str, timeframe: str, workers: int, limit_pools: int | None) -> None:
    pools = corpus_pools(db_path)
    if limit_pools:
        pools = pools[:limit_pools]
    print(f"[backfill] corpus pools to fetch: {len(pools)} (timeframe={timeframe}, workers={workers})")

    src = GeckoTerminalSource(timeframe=timeframe)
    con = sqlite3.connect(db_path)
    _ensure_table(con)

    done = failed = total_points = 0

    def work(item):
        token, pool = item
        try:
            pts = src.fetch(pool)
            time.sleep(2.1)  # ~28 req/min, under the free limit
            return token, pool, pts, None
        except urllib.error.HTTPError as e:
            return token, pool, [], f"HTTP {e.code}"
        except Exception as e:
            return token, pool, [], str(e)[:120]

    with ThreadPoolExecutor(max_workers=workers) as pool_exec:
        futs = {pool_exec.submit(work, it): it for it in pools}
        for fut in as_completed(futs):
            token, pool, pts, err = fut.result()
            if err:
                failed += 1
                print(f"  [FAIL] {token[:16]} pool={pool[:14]}: {err}")
            else:
                n = _write_path(con, token, pool, pts, f"geckoterminal:{timeframe}")
                total_points += n
                done += 1
                print(f"  [OK]   {token[:16]} pool={pool[:14]}: {len(pts)} candles -> {n} stored")

    con.close()
    print(f"[backfill] done={done} failed={failed} points_stored={total_points}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--test-one", action="store_true", help="One real fetch to prove the source.")
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--timeframe", default="hour", choices=["minute", "hour", "day"])
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--limit-pools", type=int, default=None)
    args = ap.parse_args()

    pools = corpus_pools(str(DEFAULT_DB))
    print(f"[backfill] distinct corpus pools: {len(pools)}")

    if args.dry_run or (not args.run and not args.test_one):
        for t, p in pools[:20]:
            print(f"  would fetch: token={t[:18]} pool={p[:18]}")
        print(f"[backfill] DRY RUN — {len(pools)} pools. Add --run to fetch, --test-one to prove source.")
        return

    if args.test_one:
        if not pools:
            print("[backfill] no pools."); return
        t, p = pools[0]
        print(f"[backfill] test fetch: token={t[:18]} pool={p}")
        src = GeckoTerminalSource(timeframe=args.timeframe)
        pts = src.fetch(p)
        print(f"[backfill] got {len(pts)} candles.")
        if pts:
            print(f"  first: {datetime.fromtimestamp(pts[0][0], tz=timezone.utc).isoformat()} = {pts[0][1]}")
            print(f"  last:  {datetime.fromtimestamp(pts[-1][0], tz=timezone.utc).isoformat()} = {pts[-1][1]}")
            con = sqlite3.connect(str(DEFAULT_DB)); _ensure_table(con)
            n = _write_path(con, t, p, pts, f"geckoterminal:{args.timeframe}"); con.close()
            print(f"[backfill] stored {n} points for proof.")
        return

    if args.run:
        backfill(str(DEFAULT_DB), args.timeframe, args.workers, args.limit_pools)


if __name__ == "__main__":
    main()
