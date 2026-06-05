"""
Harvest 1m spot+perp klines from Binance for the 10 level-fixed carry names (H-021).
Purpose: intra-8h price PATHS → honest leverage/liquidation simulation (the leverage gate).
The 8h-close maxDD (−0.24%) is a TRAP; 1m paths reveal intra-period gap/liquidation risk.

180 days of 1m = ~540 8h-periods/name → ample to estimate liquidation frequency at leverage L.
(Not 730d: a benign window still bounds normal-conditions safe leverage; a true crash is noted
as un-sampled. 180d keeps the harvest ~30min instead of ~2h.)

Output: finetune/data/intraday_1m/{NAME}_{venue}_1m.parquet  (+ .csv fallback)
Progress: hypothesis_lab/sessions/2026-06-05-harvest.log

Run (background): py hypothesis_lab/scripts/harvest_intraday_1m.py
"""
from __future__ import annotations
import sys, time
from pathlib import Path
import numpy as np
import requests

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "finetune" / "pipeline"))
sys.path.insert(0, str(ROOT / "hypothesis_lab" / "scripts"))
import funding_harvest as fh          # noqa: E402
import h013_tradeable_carry as h13    # noqa: E402

OUT = ROOT / "finetune" / "data" / "intraday_1m"; OUT.mkdir(parents=True, exist_ok=True)
LOG = ROOT / "hypothesis_lab" / "sessions" / "2026-06-05-harvest.log"
DAYS = 180
ENDPOINTS = {"perp": "https://fapi.binance.com/fapi/v1/klines",
             "spot": "https://api.binance.com/api/v3/klines"}


def log(msg):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def carry_names():
    panel, _, _ = h13.load_offline_panel()
    tp = fh.filter_tradeable(panel, min_cov=0.90)
    cut = int(len(tp["times"]) * fh.TRAIN_FRAC)
    lvl = np.array([np.nanmean(tp["binance"][:cut, j]) for j in range(len(tp["kept"]))])
    top = np.argsort(-lvl)[:10]
    return [tp["kept"][j] for j in top]


def fetch(url, symbol, start_ms, end_ms):
    rows, cur, sess = [], start_ms, requests.Session()
    while cur < end_ms:
        try:
            r = sess.get(url, params={"symbol": symbol, "interval": "1m",
                                      "startTime": cur, "limit": 1000}, timeout=20)
        except Exception as e:
            log(f"    net error {e}; retry in 3s"); time.sleep(3); continue
        if r.status_code in (429, 418):
            wait = int(r.headers.get("Retry-After", 5)); log(f"    rate-limited; sleep {wait}s"); time.sleep(wait); continue
        if r.status_code != 200:
            log(f"    HTTP {r.status_code} {symbol}; stop"); break
        data = r.json()
        if not data:
            break
        rows.extend(data)
        nxt = data[-1][0] + 60_000
        if nxt <= cur:
            break
        cur = nxt
        time.sleep(0.16)
    return rows


def save(rows, name, venue):
    arr = np.array([[float(x[i]) for i in (0, 1, 2, 3, 4, 5)] for x in rows], dtype=np.float64)
    uniq = np.unique(arr[:, 0], return_index=True)[1]
    arr = arr[np.sort(uniq)]                      # dedup + chronological
    p = OUT / f"{name}_{venue}_1m.npz"
    np.savez_compressed(p, open_time=arr[:, 0], open=arr[:, 1], high=arr[:, 2],
                        low=arr[:, 3], close=arr[:, 4], volume=arr[:, 5])
    return len(arr), p.name


def main():
    end_ms = int(time.time() * 1000); start_ms = end_ms - DAYS * 86400 * 1000
    names = carry_names()
    log(f"=== HARVEST START — {DAYS}d 1m, names={names} ===")
    for k, name in enumerate(names, 1):
        sym = f"{name}USDT"
        for venue, url in ENDPOINTS.items():
            t0 = time.time()
            rows = fetch(url, sym, start_ms, end_ms)
            if not rows:
                log(f"[{k}/10] {sym} {venue}: NO DATA (symbol may not exist on venue)"); continue
            n, fn = save(rows, name, venue)
            log(f"[{k}/10] {sym} {venue}: {n} bars -> {fn} ({time.time()-t0:.0f}s)")
    log("=== HARVEST DONE ===")


if __name__ == "__main__":
    main()
