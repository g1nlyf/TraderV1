"""GMGN flywheel adapter — PRIMARY free point-in-time event source (before Bitquery/Corecast fallback).

`gmgn-cli track smartmoney|follow-wallet|kol --raw` returns RAW per-trade records that are POINT-IN-TIME:
each has transaction_hash, maker (wallet), base_address (token), side, base/quote amounts, price, and a
unix `timestamp` (the actual block event time). This is pre-filtered to the smart-money population we study —
higher signal-per-byte than a full firehose. We map it into the SAME firehose schema (source=gmgn), dedupe,
store the raw response (enrichment), and label provenance.

FIELD CLASSIFICATION (see GMGN_DATA_AUDIT.md):
  POINT-IN-TIME (safe features): transaction_hash, maker, base_address, side, base_amount, quote_amount,
                                 token_amount, price, price_usd, amount_usd, timestamp.
  DISCOVERY-ONLY: the feed is smart-money-filtered (use to FIND wallets/tokens, not as a per-decision feature).
  ENRICHMENT-ONLY snapshot (store, do NOT use as point-in-time feature): maker_info.tags, base_token.*.
  FORBIDDEN lookahead (NOT collected here): `portfolio stats` aggregates (realized_profit/winrate/pnl_dist) —
                                 trailing full-history = leaderboard class. That stays in gmgn_enrichment.py.

Run: py gmgn_adapter.py --selftest                 (deterministic map+dedup, no network)
     py gmgn_adapter.py --once [--limit 200]        (one smartmoney poll -> firehose.sqlite3, live)
     py gmgn_adapter.py --loop [--interval 300]      (repeat poll; resume-safe dedup)
     py gmgn_adapter.py --status                     (source health / volume)
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from corecast_adapter import write_rows, ROW_KEYS  # reuse canonical schema + idempotent writer
from firehose_collector import DB, DATA

SOL_MINT = "So11111111111111111111111111111111111111112"
ENV_PATH = Path(__file__).resolve().parents[1] / ".env"


def _now():
    return datetime.now(timezone.utc).isoformat()


def _load_key() -> str:
    k = os.environ.get("GMGN_API_KEY", "")
    if not k and ENV_PATH.exists():
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            if line.startswith("GMGN_API_KEY="):
                k = line.split("=", 1)[1].strip()
                break
    return k


def _resolve_cli() -> list[str]:
    if sys.platform == "win32":
        d = shutil.which("gmgn-cli.cmd") or shutil.which("gmgn-cli")
        return [d] if d else [shutil.which("npx.cmd") or shutil.which("npx") or "npx.cmd", "gmgn-cli"]
    d = shutil.which("gmgn-cli")
    return [d] if d else [shutil.which("npx") or "npx", "gmgn-cli"]


def fetch(kind: str = "smartmoney", chain: str = "sol", limit: int = 200, wallet: str | None = None) -> list[dict]:
    """Call gmgn-cli track <kind> --raw. kind in {smartmoney, follow-wallet, kol}. Returns list of records."""
    key = _load_key()
    if not key:
        raise SystemExit("BLOCKER: GMGN_API_KEY not set (env or hypothesis_lab/.env).")
    env = dict(os.environ); env["GMGN_API_KEY"] = key
    cmd = _resolve_cli() + ["track", kind, "--chain", chain, "--limit", str(limit), "--raw"]
    if wallet:
        cmd += ["--wallet", wallet]
    proc = subprocess.run(cmd, capture_output=True, timeout=60, env=env)
    out = (proc.stdout or b"").decode("utf-8", errors="replace").strip()
    if proc.returncode != 0 or not out:
        err = (proc.stdout or b"").decode("utf-8", "replace") + (proc.stderr or b"").decode("utf-8", "replace")
        raise RuntimeError(f"gmgn-cli {kind} failed rc={proc.returncode}: {err[:200]}")
    data = json.loads(out)
    return data.get("list") or data.get("data") or (data if isinstance(data, list) else [])


def map_gmgn_trade(rec: dict, kind: str = "smartmoney") -> dict | None:
    """GMGN trade record -> firehose row (source=gmgn). Point-in-time: block_ts = rec.timestamp (event time)."""
    sig = rec.get("transaction_hash") or rec.get("tx_hash")
    maker = rec.get("maker") or rec.get("address")
    tok = rec.get("base_address") or rec.get("token_address")
    side = rec.get("side")
    ts = rec.get("timestamp")
    if not (sig and maker and tok and side in ("buy", "sell") and ts):
        return None
    base_amt = float(rec.get("base_amount") or rec.get("token_amount") or 0.0)   # token qty
    quote_amt = float(rec.get("quote_amount") or 0.0)                            # SOL notional
    price = rec.get("price")
    price_q = float(price) if price is not None else ((quote_amt / base_amt) if base_amt > 0 else None)
    bts = int(ts)
    return {"signature": str(sig), "wallet": str(maker), "token_mint": str(tok),
            "pool_address": (rec.get("base_token") or {}).get("launchpad"),
            "dex": (rec.get("base_token") or {}).get("launchpad"), "side": side,
            "base_amount": base_amt, "quote_amount": quote_amt, "quote_mint": SOL_MINT,
            "price_quote": price_q, "price_usd": rec.get("price_usd"),
            "block_time": datetime.fromtimestamp(bts, timezone.utc).isoformat(), "block_ts": bts,
            "source": f"gmgn:{kind}", "ingested_at": _now(),
            "raw_json": json.dumps(rec, separators=(",", ":"))}     # tags + token meta kept here (enrichment)


def poll_once(kind="smartmoney", limit=200) -> dict:
    recs = fetch(kind, limit=limit)
    rows = [r for r in (map_gmgn_trade(x, kind) for x in recs) if r]
    seen, new = write_rows(rows)
    wallets = len({r["wallet"] for r in rows}); toks = len({r["token_mint"] for r in rows})
    tss = [r["block_ts"] for r in rows]
    span = (max(tss) - min(tss)) if tss else 0
    rep = {"kind": kind, "fetched": len(recs), "mapped": len(rows), "new": new, "wallets": wallets,
           "tokens": toks, "span_s": span, "ts": _now()}
    print(f"[gmgn] {kind}: fetched={len(recs)} mapped={len(rows)} new={new} wallets={wallets} "
          f"tokens={toks} span={span}s")
    return rep


def loop(kind="smartmoney", interval=300, limit=200):
    print(f"[gmgn] loop kind={kind} every {interval}s -> {DB} (Ctrl-C to stop)")
    while True:
        try:
            poll_once(kind, limit)
        except Exception as e:
            print(f"[gmgn] poll error: {e}")
        time.sleep(interval)


_FIXTURE = {"transaction_hash": "61Sg5yMP", "maker": "71pAfN1n", "base_amount": 2087818.55, "side": "buy",
            "quote_amount": 0.961085927, "token_amount": 2087818.55, "amount_usd": 59.55, "price": 4.6033e-7,
            "price_usd": 2.85e-5, "timestamp": 1780788827, "base_address": "7gW8pDR1pump",
            "base_token": {"symbol": "VANCE", "total_supply": "999964164", "launchpad": "pump"},
            "maker_info": {"tags": ["smart_degen"]}}


def _selftest():
    row = map_gmgn_trade(_FIXTURE)
    assert row["signature"] == "61Sg5yMP" and row["wallet"] == "71pAfN1n"
    assert row["token_mint"] == "7gW8pDR1pump" and row["side"] == "buy"
    assert row["block_ts"] == 1780788827 and row["source"] == "gmgn:smartmoney"
    assert abs(row["price_quote"] - 4.6033e-7) < 1e-12
    assert set(row.keys()) == set(ROW_KEYS), set(row) ^ set(ROW_KEYS)
    assert "smart_degen" in row["raw_json"]                       # enrichment preserved in raw
    # malformed -> None
    assert map_gmgn_trade({"maker": "x"}) is None
    # idempotent dedup into temp db
    import tempfile
    tmp = Path(tempfile.gettempdir()) / "gmgn_selftest.sqlite3"
    if tmp.exists():
        tmp.unlink()
    _, n1 = write_rows([row], tmp); _, n2 = write_rows([row], tmp)
    assert n1 == 1 and n2 == 0, (n1, n2)                          # 2nd write deduped
    _, n3 = write_rows([map_gmgn_trade({**_FIXTURE, "side": "sell"})], tmp)
    assert n3 == 1                                                 # different side = distinct row
    tmp.unlink()
    print("gmgn_adapter selftest: ALL PASS (map + price + schema + enrichment + dedup + side-distinct)")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        _selftest()
    elif "--status" in sys.argv:
        import firehose_status; firehose_status.main()
    elif "--once" in sys.argv:
        lim = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else 200
        poll_once("smartmoney", lim)
    elif "--loop" in sys.argv:
        iv = int(sys.argv[sys.argv.index("--interval") + 1]) if "--interval" in sys.argv else 300
        loop("smartmoney", iv)
    else:
        print(__doc__)
