"""
Mass token-universe harvester (breaks the 6-token ceiling).

The replay corpus has only ~6 tokens => ~6 effective macro-samples => no model can
generalize token-direction. This harvests a LARGE universe of real Solana pools from
GeckoTerminal (free, no key) with full OHLCV history, so we can build an entry-timing
dataset with HUNDREDS of tokens.

Survivorship guard: we keep each token's FULL hourly history (limit 1000 = ~41 days),
then the dataset builder samples entry points UNIFORMLY along history (incl. the dumps).
We do NOT only take currently-pumping tokens.

Stores to token_price_paths (token_mint, pool_address, observed_at, price_usd, source).

Run:
  python -m finetune.pipeline.harvest_token_universe --test          # list endpoints only
  python -m finetune.pipeline.harvest_token_universe --run --pages 5 # harvest
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB = ROOT / "WalletScarper" / "data" / "stage2_foundation.sqlite3"
GECKO = "https://api.geckoterminal.com/api/v2"
NET = "solana"
UA = "TraderV1-harvest/1.0"


def _get(url: str, retries: int = 3) -> dict:
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(8 * (i + 1)); continue
            raise
    raise RuntimeError(f"failed after {retries}: {url}")


def _pool_token(p: dict) -> tuple[str, str] | None:
    """Extract (token_mint, pool_address) from a GeckoTerminal pool object."""
    try:
        pool_addr = p["attributes"]["address"]
        base = p["relationships"]["base_token"]["data"]["id"]  # 'solana_<mint>'
        mint = base.split("_", 1)[1] if "_" in base else base
        return mint, pool_addr
    except Exception:
        return None


def list_pools(pages: int) -> list[tuple[str, str]]:
    """Collect distinct (mint, pool) from trending + new + top-volume pools."""
    seen: dict[str, str] = {}
    sources = [f"{GECKO}/networks/{NET}/trending_pools?page=1",
               f"{GECKO}/networks/{NET}/new_pools?page=1"]
    for pg in range(1, pages + 1):
        sources.append(f"{GECKO}/networks/{NET}/pools?page={pg}")
    for url in sources:
        try:
            data = _get(url)
            for p in data.get("data", []):
                mt = _pool_token(p)
                if mt:
                    seen.setdefault(mt[0], mt[1])
            time.sleep(2.2)
            print(f"  listed {url.split('/')[-1]}: total distinct={len(seen)}", flush=True)
        except Exception as e:
            print(f"  list fail {url}: {e}", flush=True)
    return [(m, p) for m, p in seen.items()]


def ohlcv(pool: str, tf="hour", agg=1, limit=1000) -> list[tuple[int, float]]:
    url = f"{GECKO}/networks/{NET}/pools/{pool}/ohlcv/{tf}?aggregate={agg}&limit={limit}"
    data = _get(url)
    rows = data.get("data", {}).get("attributes", {}).get("ohlcv_list", [])
    out = []
    for r in rows:
        try:
            ts, close = int(r[0]), float(r[4])
            if close > 0:
                out.append((ts, close))
        except Exception:
            continue
    return out


def ohlcv_full(pool: str, tf="hour", agg=1, limit=1000) -> list[tuple]:
    """Return [(ts,o,h,l,c,volume)] — for volume/order-flow features (#65) and
    intrabar high/low (accurate triple-barrier touches)."""
    url = f"{GECKO}/networks/{NET}/pools/{pool}/ohlcv/{tf}?aggregate={agg}&limit={limit}"
    data = _get(url)
    rows = data.get("data", {}).get("attributes", {}).get("ohlcv_list", [])
    out = []
    for r in rows:
        try:
            ts = int(r[0]); o, h, l, c, v = (float(r[1]), float(r[2]), float(r[3]),
                                             float(r[4]), float(r[5]))
            if c > 0:
                out.append((ts, o, h, l, c, v))
        except Exception:
            continue
    return out


def _ensure_ohlcv_table(con):
    con.execute("""CREATE TABLE IF NOT EXISTS token_ohlcv (
        token_mint TEXT NOT NULL, pool_address TEXT, ts INTEGER NOT NULL,
        open REAL, high REAL, low REAL, close REAL, volume REAL,
        source TEXT NOT NULL, UNIQUE(token_mint, ts, source))""")
    con.execute("CREATE INDEX IF NOT EXISTS ix_ohlcv_tok ON token_ohlcv(token_mint, ts)")
    con.commit()


def _store_ohlcv(con, mint, pool, pts, source):
    n = 0
    for ts, o, h, l, c, v in pts:
        try:
            con.execute("INSERT OR IGNORE INTO token_ohlcv VALUES (?,?,?,?,?,?,?,?,?)",
                        (mint, pool, ts, o, h, l, c, v, source)); n += 1
        except Exception:
            pass
    con.commit()
    return n


def _ensure_table(con):
    con.execute("""CREATE TABLE IF NOT EXISTS token_price_paths (
        token_mint TEXT NOT NULL, pool_address TEXT, observed_at TEXT NOT NULL,
        price_usd REAL NOT NULL, source TEXT NOT NULL, created_at TEXT NOT NULL,
        UNIQUE(token_mint, observed_at, source))""")
    con.execute("CREATE INDEX IF NOT EXISTS ix_tpp_token ON token_price_paths(token_mint, observed_at)")
    con.commit()


def _store(con, mint, pool, pts, source):
    now = datetime.now(timezone.utc).isoformat()
    n = 0
    for ts, px in pts:
        iso = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
        try:
            con.execute("INSERT OR IGNORE INTO token_price_paths VALUES (?,?,?,?,?,?)",
                        (mint, pool, iso, px, source, now)); n += 1
        except Exception:
            pass
    con.commit()
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--test", action="store_true")
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--pages", type=int, default=5, help="pages of top pools (~20/page)")
    ap.add_argument("--max-tokens", type=int, default=200)
    ap.add_argument("--tf", default="hour", choices=["minute", "hour", "day"])
    ap.add_argument("--agg", type=int, default=1, help="aggregate (e.g. 5 with --tf minute = 5min)")
    ap.add_argument("--full", action="store_true", help="store full OHLCV+volume to token_ohlcv (#65)")
    a = ap.parse_args()

    if a.test:
        d = _get(f"{GECKO}/networks/{NET}/trending_pools?page=1")
        pools = d.get("data", [])
        print(f"[harvest] trending_pools returned {len(pools)} pools")
        for p in pools[:3]:
            mt = _pool_token(p)
            print(f"  sample: mint={mt[0][:18] if mt else '?'} pool={mt[1][:18] if mt else '?'}")
        if pools:
            mt = _pool_token(pools[0])
            pts = ohlcv(mt[1])
            print(f"[harvest] OHLCV proof for {mt[0][:18]}: {len(pts)} candles")
        return

    if a.run:
        print(f"[harvest] listing pools (pages={a.pages})...")
        pools = list_pools(a.pages)[: a.max_tokens]
        print(f"[harvest] {len(pools)} distinct tokens to harvest")
        con = sqlite3.connect(str(DEFAULT_DB))
        _ensure_table(con)
        if a.full:
            _ensure_ohlcv_table(con)
        ok = fail = pts_total = 0
        for i, (mint, pool) in enumerate(pools):
            try:
                if a.full:
                    pts = ohlcv_full(pool, tf=a.tf, agg=a.agg)
                    n = _store_ohlcv(con, mint, pool, pts, f"geckoterminal:{a.tf}{a.agg}")
                else:
                    pts = ohlcv(pool, tf=a.tf, agg=a.agg)
                    n = _store(con, mint, pool, pts, f"geckoterminal:{a.tf}{a.agg}")
                pts_total += n; ok += 1
                if i % 10 == 0:
                    print(f"  [{i}/{len(pools)}] {mint[:14]}: {len(pts)} candles (total pts={pts_total})", flush=True)
                time.sleep(2.2)
            except Exception as e:
                fail += 1
                print(f"  [{i}] {mint[:14]} FAIL: {str(e)[:60]}", flush=True)
        con.close()
        print(f"[harvest] DONE ok={ok} fail={fail} points={pts_total}")


if __name__ == "__main__":
    main()
