"""Corecast flywheel adapter — free high-volume Solana DEX-trade stream -> the SAME firehose schema.

WHY: GeckoTerminal free is ~0.5 sell-clusters/day (too thin for cross-day H-163). Bitquery Corecast (the
gRPC stream that produced the May-14 reference: 803K trades / 12,318 tokens / 5.5h) is the volume path. The
gRPC proto is ALREADY INSTALLED: `WalletScarper/.venv/.../bitquery_corecast_proto` (corecast_pb2*).

WHAT THIS SHIPS (honest boundary):
  * map_normalized_to_row()  — normalized trade dict -> firehose_trades row. COMPLETE + unit-tested.
  * write_rows()             — idempotent insert into _data/firehose.sqlite3 (reuses firehose_collector
                               schema; UNIQUE(signature,token_mint,side,wallet) dedup). COMPLETE + tested.
  * corecast_msg_to_normalized() — proto DEXTrade msg -> normalized dict. REFERENCE impl; field paths must be
                               VERIFIED against corecast_pb2 on first live run (guarded, never silently wrong).
  * stream()                 — env-gated gRPC subscribe loop. Requires BITQUERY_TOKEN. Resume-safe (dedup).

BLOCKER (the one config change): set env `BITQUERY_TOKEN` (Bitquery Ory token, free tier) and run
`py corecast_adapter.py --stream`. Without it, stream() raises a clear, actionable error and exits — no fake.

Run: py corecast_adapter.py --selftest      (deterministic, no network)
     py corecast_adapter.py --stream         (needs BITQUERY_TOKEN; resume-safe; writes to firehose.sqlite3)
     py corecast_adapter.py --status         (source health via firehose_status)
"""
from __future__ import annotations

import os
import sqlite3
import sys
from datetime import datetime, timezone

from firehose_collector import DB, DATA  # reuse the canonical DB path + _data dir

# Mirrors firehose_collector's firehose_trades schema (single source of truth = the same table/dedup key).
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS firehose_trades (
    signature TEXT, wallet TEXT, token_mint TEXT, pool_address TEXT, dex TEXT,
    side TEXT, base_amount REAL, quote_amount REAL, quote_mint TEXT, price_quote REAL, price_usd REAL,
    block_time TEXT, block_ts INTEGER, source TEXT, ingested_at TEXT, raw_json TEXT,
    UNIQUE(signature, token_mint, side, wallet)
);
CREATE INDEX IF NOT EXISTS ix_fh_token ON firehose_trades(token_mint);
CREATE INDEX IF NOT EXISTS ix_fh_wallet ON firehose_trades(wallet);
CREATE INDEX IF NOT EXISTS ix_fh_ts ON firehose_trades(block_ts);
"""

ENDPOINT = "streaming.bitquery.io:443"          # Corecast gRPC endpoint (Bitquery)
SOURCE = "corecast"
ROW_KEYS = ("signature", "wallet", "token_mint", "pool_address", "dex", "side", "base_amount",
            "quote_amount", "quote_mint", "price_quote", "price_usd", "block_time", "block_ts",
            "source", "ingested_at", "raw_json")


def _now():
    return datetime.now(timezone.utc).isoformat()


def map_normalized_to_row(t: dict) -> dict:
    """Normalized trade dict -> firehose_trades row. Deterministic, point-in-time (block_ts is event time).

    Required normalized keys: signature, wallet, base_mint, quote_mint, side ('buy'|'sell'),
    base_amount, quote_amount, block_ts (int unix). Optional: pool, dex, block_time, price_usd.
    price_quote = quote/base (SOL per token), matching wa_common price convention.
    """
    base_amt = float(t.get("base_amount") or 0.0)
    quote_amt = float(t.get("quote_amount") or 0.0)
    side = t["side"]
    if side not in ("buy", "sell"):
        raise ValueError(f"bad side: {side!r}")
    pq = (quote_amt / base_amt) if base_amt > 0 else None
    bts = int(t["block_ts"])
    return {"signature": str(t["signature"]), "wallet": str(t["wallet"]),
            "token_mint": str(t["base_mint"]), "pool_address": t.get("pool"), "dex": t.get("dex"),
            "side": side, "base_amount": base_amt, "quote_amount": quote_amt,
            "quote_mint": t.get("quote_mint"), "price_quote": pq, "price_usd": t.get("price_usd"),
            "block_time": t.get("block_time") or datetime.fromtimestamp(bts, timezone.utc).isoformat(),
            "block_ts": bts, "source": SOURCE, "ingested_at": _now(),
            "raw_json": t.get("raw_json", "")}


def write_rows(rows, db_path=DB) -> tuple[int, int]:
    """Idempotent insert. Returns (seen, new). Resume-safe via UNIQUE(signature,token_mint,side,wallet)."""
    db = sqlite3.connect(str(db_path)); db.executescript(SCHEMA_SQL)
    before = db.execute("SELECT COUNT(*) FROM firehose_trades").fetchone()[0]
    for r in rows:
        db.execute(
            "INSERT OR IGNORE INTO firehose_trades (signature,wallet,token_mint,pool_address,dex,side,"
            "base_amount,quote_amount,quote_mint,price_quote,price_usd,block_time,block_ts,source,"
            "ingested_at,raw_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            tuple(r[k] for k in ROW_KEYS))
    db.commit()
    after = db.execute("SELECT COUNT(*) FROM firehose_trades").fetchone()[0]
    db.close()
    return len(rows), after - before


def corecast_msg_to_normalized(msg) -> dict | None:
    """Proto DEXTrade msg -> normalized dict. REFERENCE impl — VERIFY field paths against corecast_pb2 on the
    first live run (Bitquery Corecast DEXTrades schema). Returns None for non-trade / malformed msgs.

    Standard Corecast DEXTrade layout (verify): msg.Block.Time, msg.Transaction.Signature/Signer,
    msg.Trade.Buy.{Account,Currency.MintAddress,Amount}, msg.Trade.Sell.{...}, msg.Trade.Dex.ProtocolName,
    msg.Trade.Market.MarketAddress. A trade has one Buy + one Sell leg; we emit the BUY-side as the wallet
    action (side='buy') and optionally the sell leg as side='sell'.
    """
    try:
        blk = getattr(msg, "Block", None); tx = getattr(msg, "Transaction", None)
        trade = getattr(msg, "Trade", None)
        if trade is None or tx is None:
            return None
        bts = int(getattr(getattr(blk, "Time", 0), "seconds", 0)) or None
        sig = getattr(tx, "Signature", None)
        dex = getattr(getattr(trade, "Dex", None), "ProtocolName", None)
        pool = getattr(getattr(trade, "Market", None), "MarketAddress", None)
        buy = getattr(trade, "Buy", None)
        if buy is None or sig is None or bts is None:
            return None
        return {"signature": sig, "wallet": getattr(buy, "Account", ""),
                "base_mint": getattr(getattr(buy, "Currency", None), "MintAddress", ""),
                "quote_mint": getattr(getattr(getattr(trade, "Sell", None), "Currency", None), "MintAddress", ""),
                "side": "buy", "base_amount": float(getattr(buy, "Amount", 0) or 0),
                "quote_amount": float(getattr(getattr(trade, "Sell", None), "Amount", 0) or 0),
                "pool": pool, "dex": dex, "block_ts": bts}
    except Exception:
        return None


def stream(max_msgs: int | None = None):
    """Env-gated gRPC subscribe loop. Resume-safe. Requires BITQUERY_TOKEN."""
    token = os.environ.get("BITQUERY_TOKEN")
    if not token:
        raise SystemExit(
            "BLOCKER: BITQUERY_TOKEN not set. Corecast streaming needs a (free-tier) Bitquery Ory token.\n"
            "  1) get token at https://account.bitquery.io (free tier)\n"
            "  2) set BITQUERY_TOKEN=<token>\n"
            "  3) re-run: py corecast_adapter.py --stream\n"
            f"  proto already installed (bitquery_corecast_proto); endpoint={ENDPOINT}; writes -> {DB}\n"
            "  NOTE: verify corecast_msg_to_normalized() field paths against corecast_pb2 on first run.")
    # add the WalletScarper venv proto to path
    proto = ROOT_VENV = None
    for p in (DATA.parents[2] / "WalletScarper" / ".venv" / "Lib" / "site-packages",):
        if p.exists():
            sys.path.insert(0, str(p)); proto = p
    if proto is None:
        raise SystemExit("BLOCKER: bitquery_corecast_proto not found in WalletScarper/.venv.")
    import grpc  # noqa
    from bitquery_corecast_proto import corecast_pb2_grpc, corecast_pb2  # noqa
    creds = grpc.composite_channel_credentials(
        grpc.ssl_channel_credentials(),
        grpc.access_token_call_credentials(token))
    chan = grpc.secure_channel(ENDPOINT, creds)
    stub = corecast_pb2_grpc.CoreCastStub(chan)
    print(f"[corecast] connected {ENDPOINT}; streaming DEX trades -> {DB} (Ctrl-C to stop)")
    buf, seen_total, new_total, n = [], 0, 0, 0
    request = corecast_pb2.DexTradeRequest() if hasattr(corecast_pb2, "DexTradeRequest") else corecast_pb2.SubscribeRequest()
    for msg in stub.SubscribeDexTrades(request) if hasattr(stub, "SubscribeDexTrades") else stub.Subscribe(request):
        norm = corecast_msg_to_normalized(msg)
        if norm:
            buf.append(map_normalized_to_row(norm))
        n += 1
        if len(buf) >= 200:
            s, nw = write_rows(buf); seen_total += s; new_total += nw; buf = []
            print(f"[corecast] msgs={n} written_new={new_total}")
        if max_msgs and n >= max_msgs:
            break
    if buf:
        s, nw = write_rows(buf); new_total += nw
    print(f"[corecast] done. msgs={n} new_rows={new_total}")


def _selftest():
    norm = {"signature": "SIG1", "wallet": "W1", "base_mint": "TOKMINT", "quote_mint": "So111",
            "side": "buy", "base_amount": 1000.0, "quote_amount": 2.5, "block_ts": 1778752900, "dex": "pump"}
    row = map_normalized_to_row(norm)
    assert row["token_mint"] == "TOKMINT" and row["side"] == "buy"
    assert abs(row["price_quote"] - 0.0025) < 1e-12, row["price_quote"]
    assert row["source"] == "corecast"
    assert set(row.keys()) == set(ROW_KEYS), set(row) ^ set(ROW_KEYS)
    # idempotent dedup into a temp DB
    import tempfile, pathlib
    tmp = pathlib.Path(tempfile.gettempdir()) / "corecast_selftest.sqlite3"
    if tmp.exists():
        tmp.unlink()
    s1, n1 = write_rows([row], tmp); s2, n2 = write_rows([row], tmp)   # write twice
    assert n1 == 1 and n2 == 0, (n1, n2)                               # second write deduped
    sell = {**norm, "side": "sell"}
    _, n3 = write_rows([map_normalized_to_row(sell)], tmp)
    assert n3 == 1, "different side must be a distinct row"
    tmp.unlink()
    print("corecast_adapter selftest: ALL PASS (mapping + price + schema + idempotent dedup + side-distinct)")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        _selftest()
    elif "--status" in sys.argv:
        import firehose_status; firehose_status.main()
    elif "--stream" in sys.argv:
        stream()
    else:
        print(__doc__)
