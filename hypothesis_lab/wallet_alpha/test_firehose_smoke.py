"""Deterministic smoke test for firehose_collector (no network). Run: py test_firehose_smoke.py"""
from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

import firehose_collector as fc


def test_parse():
    SOL = fc.SOL
    # buy: from=SOL -> base=token, price = sol/token
    buy = {"tx_hash": "sig1", "tx_from_address": "W1", "kind": "buy",
           "from_token_address": SOL, "to_token_address": "TOK",
           "from_token_amount": "1.0", "to_token_amount": "1000.0",
           "block_timestamp": "2026-06-06T18:00:00Z", "price_from_in_usd": "150"}
    r = fc._parse_trade(buy, "pool1", "raydium")
    assert r and r["side"] == "buy" and r["token_mint"] == "TOK"
    assert abs(r["price_quote"] - 0.001) < 1e-9, r["price_quote"]
    assert r["quote_mint"] == SOL and r["block_ts"] == 1780768800, r["block_ts"]
    # sell: to=SOL
    sell = {"tx_hash": "sig2", "tx_from_address": "W2", "kind": "sell",
            "from_token_address": "TOK", "to_token_address": SOL,
            "from_token_amount": "2000.0", "to_token_amount": "1.5",
            "block_timestamp": "2026-06-06T18:01:00Z"}
    r2 = fc._parse_trade(sell, "pool1", "raydium")
    assert r2 and r2["side"] == "sell" and abs(r2["price_quote"] - 0.00075) < 1e-9
    # rejects: token<->token, missing wallet, bad amounts, bad kind
    assert fc._parse_trade({**buy, "from_token_address": "TOKA", "to_token_address": "TOKB"}, "p", "d") is None
    assert fc._parse_trade({**buy, "tx_from_address": None}, "p", "d") is None
    assert fc._parse_trade({**buy, "to_token_amount": "0"}, "p", "d") is None
    assert fc._parse_trade({**buy, "kind": "approve"}, "p", "d") is None
    print("  parse: OK (buy/sell price, ts, rejects)")


def test_dedup():
    tmp = Path(tempfile.mkdtemp()) / "fh_test.sqlite3"
    fc.DB = tmp                     # redirect module DB
    db = fc.init_db()
    row = ("sigX", "W", "TOK", "pool", "dex", "buy", 1000.0, 1.0, fc.SOL, 0.001, 150.0,
           "2026-06-06T18:00:00Z", 1780768800, "geckoterminal", "now", "{}")
    ins = ("INSERT OR IGNORE INTO firehose_trades (signature,wallet,token_mint,pool_address,dex,side,"
           "base_amount,quote_amount,quote_mint,price_quote,price_usd,block_time,block_ts,source,"
           "ingested_at,raw_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)")
    db.execute(ins, row); db.execute(ins, row); db.commit()   # same row twice
    n = db.execute("SELECT COUNT(*) FROM firehose_trades").fetchone()[0]
    assert n == 1, f"dedup failed: {n}"
    # different side same sig => kept (multi-leg)
    db.execute(ins, ("sigX", "W", "TOK", "pool", "dex", "sell", *row[6:])); db.commit()
    n2 = db.execute("SELECT COUNT(*) FROM firehose_trades").fetchone()[0]
    assert n2 == 2, f"expected 2, got {n2}"
    db.close()
    print("  dedup: OK (idempotent insert; multi-side kept)")


if __name__ == "__main__":
    test_parse()
    test_dedup()
    print("firehose smoke: ALL PASS")
