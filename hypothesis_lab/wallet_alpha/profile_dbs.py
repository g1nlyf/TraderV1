"""profile_dbs — PHASE 1 reproducible data audit. Regenerates the numbers in knowledge/DATA_AUDIT.md.

Run: py hypothesis_lab/wallet_alpha/profile_dbs.py
"""
from __future__ import annotations

import sqlite3
from collections import Counter

import wa_common as wa

wa.ensure_utf8()


def counts(db, label):
    print(f"\n===== {label} =====")
    tabs = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
    for t in tabs:
        try:
            n = db.execute(f"SELECT COUNT(*) FROM '{t}'").fetchone()[0]
            if n:
                print(f"  {t:42s} {n:>10,}")
        except Exception as e:
            print(f"  {t:42s} ERR {e}")


def audit_raw_trades(db):
    c = db.cursor()
    print("\n----- raw_trades audit -----")
    ts = sorted(t for t in (wa.parse_ts(r[0]) for r in c.execute("SELECT block_time FROM raw_trades")) if t)
    print(f"rows={len(ts):,}  span {ts[0]:.0f}..{ts[-1]:.0f}  days={(ts[-1]-ts[0])/86400:.2f}")
    days = Counter(__import__("datetime").datetime.utcfromtimestamp(t).date().isoformat() for t in ts)
    print("by day:", dict(sorted(days.items())))
    print("distinct wallets:", c.execute("SELECT COUNT(DISTINCT wallet) FROM raw_trades").fetchone()[0])
    print("distinct tokens :", c.execute("SELECT COUNT(DISTINCT token_mint) FROM raw_trades").fetchone()[0])
    print("sides:", c.execute("SELECT side,COUNT(*) FROM raw_trades GROUP BY side").fetchall())
    print("source:", c.execute("SELECT source,COUNT(*) FROM raw_trades GROUP BY source ORDER BY 2 DESC").fetchall())
    print("price_usd>0:", c.execute("SELECT COUNT(*) FROM raw_trades WHERE price_usd>0").fetchone()[0],
          " quote>0:", c.execute("SELECT COUNT(*) FROM raw_trades WHERE quote_amount>0").fetchone()[0])
    trk = c.execute("SELECT token_mint,COUNT(DISTINCT wallet) w FROM raw_trades GROUP BY token_mint").fetchall()
    for thr in (5, 10, 20):
        print(f"tokens with >= {thr} distinct wallets:", sum(1 for r in trk if r[1] >= thr))


def label_coverage():
    leg = sqlite3.connect(str(wa.LEGACY_DB)); s2 = sqlite3.connect(str(wa.STAGE2_DB))
    rt = {r[0] for r in leg.execute("SELECT DISTINCT token_mint FROM raw_trades")}
    pp = {r[0] for r in s2.execute("SELECT DISTINCT token_mint FROM token_price_paths")}
    oh = {r[0] for r in s2.execute("SELECT DISTINCT token_mint FROM token_ohlcv")}
    print("\n----- multi-day label coverage -----")
    print(f"price_paths tokens={len(pp)} ohlcv={len(oh)} raw_trades={len(rt)}")
    print(f"(price_paths ∪ ohlcv) ∩ raw_trades = {len((pp | oh) & rt)}  -> multi-day labels not viable")
    leg.close(); s2.close()


if __name__ == "__main__":
    leg = sqlite3.connect(str(wa.LEGACY_DB))
    counts(leg, "LEGACY walletscarper")
    audit_raw_trades(leg)
    leg.close()
    s2 = sqlite3.connect(str(wa.STAGE2_DB))
    counts(s2, "STAGE2 foundation")
    s2.close()
    label_coverage()
