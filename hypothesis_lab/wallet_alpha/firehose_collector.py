"""firehose_collector — durable FREE wallet-attributed Solana trade collector (PHASE 1).

The flywheel engine. Polls GeckoTerminal's FREE, keyless endpoints (new + trending pools -> per-pool
trades), which expose `tx_from_address` (the wallet), `tx_hash` (dedup key), `block_timestamp`, `kind`
(buy/sell) and both leg amounts. Appends to a durable SQLite with point-in-time provenance, dedup, and
per-run health/budget logging. Stdlib only (urllib) — no new deps, no paid sources, no API key.

Why a new table (not the 1.6 GB legacy walletscarper.sqlite3): isolation + safety. build_events_v2 unions
this with raw_trades so calendar span accrues day by day. THIS is what makes H-162 persistence testable.

Modes:
  --dry-run            fetch + parse + print sample, NO writes
  --once               one collection tick (default)
  --loop --interval S  repeat every S seconds (durable; Ctrl-C safe)
Run: py hypothesis_lab/wallet_alpha/firehose_collector.py --once
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "hypothesis_lab" / "wallet_alpha" / "_data"
DATA.mkdir(exist_ok=True)
DB = DATA / "firehose.sqlite3"

GT = "https://api.geckoterminal.com/api/v2"
UA = "TraderV1-research/1.0 (free-tier; paper-only)"
SOL = "So11111111111111111111111111111111111111112"
STABLES = {"EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",  # USDC
           "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB"}  # USDT
QUOTES = {SOL} | STABLES


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get(url: str, timeout: int = 20, retries: int = 3):
    """GET JSON with backoff + 429 handling. Returns (json|None, status_str)."""
    last = "?"
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8")), "ok"
        except urllib.error.HTTPError as e:
            last = f"http{e.code}"
            if e.code == 429:
                time.sleep(2.5 * (attempt + 1))  # rate-limited: back off
                last = "rate_limited"
                continue
            if 500 <= e.code < 600:
                time.sleep(1.5 * (attempt + 1)); continue
            return None, last
        except Exception as e:
            last = type(e).__name__
            time.sleep(1.0 * (attempt + 1))
    return None, last


def init_db():
    db = sqlite3.connect(str(DB))
    db.executescript("""
    CREATE TABLE IF NOT EXISTS firehose_trades (
        signature TEXT, wallet TEXT, token_mint TEXT, pool_address TEXT, dex TEXT,
        side TEXT, base_amount REAL, quote_amount REAL, quote_mint TEXT,
        price_quote REAL, price_usd REAL,
        block_time TEXT, block_ts INTEGER, source TEXT, ingested_at TEXT, raw_json TEXT,
        UNIQUE(signature, token_mint, side, wallet)
    );
    CREATE INDEX IF NOT EXISTS ix_fh_token ON firehose_trades(token_mint);
    CREATE INDEX IF NOT EXISTS ix_fh_wallet ON firehose_trades(wallet);
    CREATE INDEX IF NOT EXISTS ix_fh_ts ON firehose_trades(block_ts);
    CREATE TABLE IF NOT EXISTS firehose_runs (
        run_id TEXT PRIMARY KEY, started_at TEXT, finished_at TEXT, source TEXT,
        pools_polled INTEGER, trades_seen INTEGER, trades_new INTEGER,
        http_ok INTEGER, http_fail INTEGER, rate_limited INTEGER, notes TEXT
    );
    """)
    db.commit()
    return db


def _parse_trade(a: dict, pool: str, dex: str) -> dict | None:
    """GeckoTerminal trade attributes -> normalized row. price_quote = SOL (or stable) per base token."""
    sig = a.get("tx_hash"); wallet = a.get("tx_from_address"); kind = a.get("kind")
    if not sig or not wallet or kind not in ("buy", "sell"):
        return None
    ft, tt = a.get("from_token_address"), a.get("to_token_address")
    fa, ta = a.get("from_token_amount"), a.get("to_token_amount")
    try:
        fa = float(fa); ta = float(ta)
    except (TypeError, ValueError):
        return None
    # identify quote (SOL/stable) and base sides
    if ft in QUOTES and tt not in QUOTES:
        quote_mint, quote_amt, base_mint, base_amt = ft, fa, tt, ta
    elif tt in QUOTES and ft not in QUOTES:
        quote_mint, quote_amt, base_mint, base_amt = tt, ta, ft, fa
    else:
        # token<->token or quote<->quote: skip (no clean SOL price)
        return None
    if base_amt <= 0 or quote_amt <= 0:
        return None
    bt = a.get("block_timestamp")
    try:
        block_ts = int(datetime.fromisoformat(str(bt).replace("Z", "+00:00")).timestamp())
    except Exception:
        block_ts = None
    pu = a.get("price_from_in_usd") or a.get("price_to_in_usd")
    try:
        price_usd = float(pu) if pu is not None else None
    except (TypeError, ValueError):
        price_usd = None
    return {"signature": sig, "wallet": wallet, "token_mint": base_mint, "pool_address": pool, "dex": dex,
            "side": kind, "base_amount": base_amt, "quote_amount": quote_amt, "quote_mint": quote_mint,
            "price_quote": quote_amt / base_amt, "price_usd": price_usd,
            "block_time": bt, "block_ts": block_ts, "source": "geckoterminal", "ingested_at": _ts(),
            "raw_json": json.dumps(a)}


def _pools(kind: str, pages: int):
    """Return [(pool_address, dex)] from new_pools or trending_pools."""
    out = []
    for pg in range(1, pages + 1):
        j, st = _get(f"{GT}/networks/solana/{kind}?page={pg}")
        if not j:
            return out, st
        for p in j.get("data", []):
            attr = p.get("attributes", {})
            rel = p.get("relationships", {}) or {}
            dex = (rel.get("dex", {}).get("data", {}) or {}).get("id", "")
            if attr.get("address"):
                out.append((attr["address"], dex))
        time.sleep(2.2)  # free-tier pacing (~30 req/min)
    return out, "ok"


def tick(db, max_pools: int, pages: int, dry: bool) -> dict:
    run_id = f"fh_{int(time.time())}"
    started = _ts()
    health = {"pools": 0, "seen": 0, "new": 0, "ok": 0, "fail": 0, "rl": 0}
    pools = []
    for kind in ("new_pools", "trending_pools"):
        ps, st = _pools(kind, pages)
        health["ok" if st == "ok" else "fail"] += 1
        if st == "rate_limited":
            health["rl"] += 1
        pools += ps
    # de-dup pool list, cap
    seen_pool = set(); uniq = []
    for pa, dx in pools:
        if pa not in seen_pool:
            seen_pool.add(pa); uniq.append((pa, dx))
    uniq = uniq[:max_pools]
    sample = []
    for pa, dx in uniq:
        j, st = _get(f"{GT}/networks/solana/pools/{pa}/trades")
        health["pools"] += 1
        if not j:
            health["fail"] += 1
            if st == "rate_limited":
                health["rl"] += 1
            time.sleep(2.2); continue
        health["ok"] += 1
        for t in j.get("data", []):
            row = _parse_trade(t.get("attributes", {}), pa, dx)
            if not row:
                continue
            health["seen"] += 1
            if dry:
                if len(sample) < 5:
                    sample.append(row)
                continue
            cur = db.execute(
                "INSERT OR IGNORE INTO firehose_trades (signature,wallet,token_mint,pool_address,dex,side,"
                "base_amount,quote_amount,quote_mint,price_quote,price_usd,block_time,block_ts,source,"
                "ingested_at,raw_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                tuple(row[k] for k in ("signature", "wallet", "token_mint", "pool_address", "dex", "side",
                      "base_amount", "quote_amount", "quote_mint", "price_quote", "price_usd",
                      "block_time", "block_ts", "source", "ingested_at", "raw_json")))
            health["new"] += cur.rowcount
        time.sleep(2.2)
    finished = _ts()
    if not dry:
        db.execute("INSERT OR REPLACE INTO firehose_runs VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                   (run_id, started, finished, "geckoterminal", health["pools"], health["seen"],
                    health["new"], health["ok"], health["fail"], health["rl"],
                    f"max_pools={max_pools} pages={pages}"))
        db.commit()
    health["sample"] = sample
    health["run_id"] = run_id
    return health


def db_stats(db) -> str:
    n = db.execute("SELECT COUNT(*) FROM firehose_trades").fetchone()[0]
    w = db.execute("SELECT COUNT(DISTINCT wallet) FROM firehose_trades").fetchone()[0]
    tok = db.execute("SELECT COUNT(DISTINCT token_mint) FROM firehose_trades").fetchone()[0]
    rng = db.execute("SELECT MIN(block_ts), MAX(block_ts) FROM firehose_trades").fetchone()
    span = ((rng[1] - rng[0]) / 86400.0) if rng[0] and rng[1] else 0.0
    return f"firehose DB: trades={n:,} wallets={w:,} tokens={tok:,} span={span:.2f}d"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--loop", action="store_true")
    ap.add_argument("--interval", type=int, default=900, help="loop seconds (free-tier friendly)")
    ap.add_argument("--max-pools", type=int, default=40)
    ap.add_argument("--pages", type=int, default=1)
    a = ap.parse_args()
    try:
        import sys; sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore
    except Exception:
        pass

    db = init_db()
    def one():
        h = tick(db, a.max_pools, a.pages, a.dry_run)
        tag = "DRY" if a.dry_run else "LIVE"
        print(f"[{tag} {h['run_id']}] pools={h['pools']} seen={h['seen']} new={h['new']} "
              f"http_ok={h['ok']} fail={h['fail']} rate_limited={h['rl']}")
        if a.dry_run:
            for s in h["sample"]:
                print(f"   {s['side']:4s} {s['token_mint'][:8]} w={s['wallet'][:8]} "
                      f"{s['quote_amount']:.4f}{('SOL' if s['quote_mint']==SOL else 'stable')} "
                      f"@ {s['price_quote']:.3e} {s['block_time']}")
        else:
            print("   " + db_stats(db))
        return h

    if a.loop:
        print(f"[firehose] loop every {a.interval}s -> {DB}")
        while True:
            try:
                one()
            except KeyboardInterrupt:
                print("[firehose] stopped"); break
            except Exception as e:
                print(f"[firehose] tick error: {type(e).__name__}: {e}")
            time.sleep(a.interval)
    else:
        one()
    db.close()


if __name__ == "__main__":
    main()
