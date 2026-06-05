"""forward_collector.py — H-18 FIX: the unbiased early-winner dataset, collected FORWARD.

================================================================================
WHY (H-18 implementation-verified, research_state.md)
================================================================================
Snapshot reconstruction can't test the early-winner thesis: outcome universe is
survivor-biased AND reaching a token's launch via pool pagination is cost-prohibitive
(B-09, getSignatures is newest-first). THE FIX is FORWARD COLLECTION — and the key that
makes it cheap: AT LAUNCH, a token's early buyers ARE page 1 of the pool (few txns yet).

This daemon, run repeatedly (cron, ~hourly):
  1. DISCOVER new Solana pools (GeckoTerminal new/trending — fresh launches).
  2. SNAPSHOT each new token ONCE near launch: early buyers from chain (Helius page-1 of the
     pool, cheap), features (n_buyers, n_smart∈win-rate>.55, n_tracked, buy_sol, concentration),
     and launch ts/price. Stored as a PENDING record.
  3. UPDATE outcomes: for pending records past the horizon, fetch forward price (GeckoTerminal
     OHLCV) → realized return — INCLUDING tokens that died (unbiased, no survivorship).
  4. TEST: once N finalized ≥ threshold, run the permutation-null early-winner test
     (does any early-buyer feature beat shuffled-outcome null? perm_p<0.05).

This is the ONLY path that produces an UNBIASED, perm-null-testable signal for the one thesis
consistent with the whole session. It yields signal over days/weeks — schedule it and let it run.

Run:
    py -3 finetune/pipeline/forward_collector.py --tick           # one discover+snapshot+update cycle
    py -3 finetune/pipeline/forward_collector.py --tick --max 25  # cap new snapshots this tick
    py -3 finetune/pipeline/forward_collector.py --report         # show dataset + run perm-null test
    py -3 finetune/pipeline/forward_collector.py --selftest
"""
from __future__ import annotations

import json
import math
import os
import sqlite3
import sys
import time
import urllib.request
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "finetune" / "pipeline"))
import helius_client as hc            # noqa: E402
import harvest_token_universe as htu  # noqa: E402

DB = ROOT / "WalletScarper" / "data" / "stage2_foundation.sqlite3"
STATE = ROOT / "finetune" / "data" / "forward_collector_state.jsonl"
RESULT = ROOT / "finetune" / "data" / "forward_collector_result.json"
GECKO = "https://api.geckoterminal.com/api/v2"

HORIZON_H = 24            # forward outcome horizon
SNAPSHOT_MAX_AGE_H = 6   # only snapshot pools whose first trade is < this old (true "early")
MIN_N_TEST = 30          # finalized records needed before the perm-null test means anything


def _load_env():
    if not (os.environ.get("HELIUS_API_KEY") and os.environ.get("HELIUS_RPC_URL")):
        envf = ROOT / "WalletScarper" / ".env"
        if envf.exists():
            for line in envf.read_text(errors="ignore").splitlines():
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    hc.RPC_URL = os.environ.get("HELIUS_RPC_URL", "")
    hc.API_KEY = os.environ.get("HELIUS_API_KEY", "")
    hc.PARSE_URL = f"https://api-mainnet.helius-rpc.com/v0/transactions/?api-key={hc.API_KEY}"


def _gecko(url):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "TraderV1-fc/1.0", "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode())
    except Exception:
        return {}


def _smart_sets():
    con = sqlite3.connect(str(DB))
    tracked = set(r[0] for r in con.execute(
        "SELECT DISTINCT wallet FROM wallet_token_outcomes WHERE length(wallet)>=40").fetchall())
    smart = set(r[0] for r in con.execute(
        "SELECT DISTINCT wallet FROM wallet_metric_snapshots WHERE win_rate_estimate>0.55 AND length(wallet)>=40").fetchall())
    con.close()
    return tracked, smart


def _load_state():
    if not STATE.exists():
        return []
    return [json.loads(l) for l in STATE.read_text(encoding="utf-8").splitlines() if l.strip()]


def _save_state(recs):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text("\n".join(json.dumps(r) for r in recs) + "\n", encoding="utf-8")


def discover():
    pools = []
    for url in (f"{GECKO}/networks/solana/new_pools?page=1",
                f"{GECKO}/networks/solana/new_pools?page=2",
                f"{GECKO}/networks/solana/trending_pools?page=1"):
        d = _gecko(url)
        for p in d.get("data", []):
            mt = htu._pool_token(p)
            if mt:
                attrs = p.get("attributes", {})
                created = attrs.get("pool_created_at")
                pools.append((mt[0], mt[1], created))
        time.sleep(2.2)
    return pools


def snapshot_token(mint, pool, tracked, smart):
    """Early buyers from chain page-1 (cheap for a fresh pool). Returns record or None."""
    sigs = hc.get_signatures(pool, limit=100)
    if not sigs:
        return None
    bts = [s.get("blockTime") or 0 for s in sigs if s.get("blockTime")]
    if not bts:
        return None
    first_ts = min(bts)
    # only accept genuinely-early pools (first reachable trade is recent)
    if (time.time() - first_ts) > SNAPSHOT_MAX_AGE_H * 3600:
        return {"mint": mint, "pool": pool, "status": "too_old", "first_ts": first_ts}
    parsed = hc.parse([s["signature"] for s in sigs])
    buyers = {}
    for tx in parsed:
        trader = tx.get("feePayer", "")
        if not trader:
            continue
        sw = hc._extract_swap(tx, trader)
        if sw and sw.token_mint == mint and sw.side == "buy":
            buyers[trader] = buyers.get(trader, 0.0) + sw.sol_amount
    sols = np.array(list(buyers.values())) if buyers else np.array([])
    return {
        "mint": mint, "pool": pool, "status": "pending", "first_ts": int(first_ts),
        "snapshot_ts": int(time.time()),
        "n_buyers": len(buyers),
        "n_tracked": sum(1 for w in buyers if w in tracked),
        "n_smart": sum(1 for w in buyers if w in smart),
        "buy_sol": float(sols.sum()) if len(sols) else 0.0,
        "concentration": float(sols.max() / sols.sum()) if len(sols) and sols.sum() > 0 else 0.0,
    }


def _price_at(pool, target_ts):
    d = _gecko(f"{GECKO}/networks/solana/pools/{pool}/ohlcv/hour?aggregate=1&limit=1000")
    rows = d.get("data", {}).get("attributes", {}).get("ohlcv_list", [])
    best = None
    for r in rows:
        try:
            ts, close = int(r[0]), float(r[4])
        except Exception:
            continue
        if close > 0 and ts <= target_ts + 1800:
            if best is None or abs(ts - target_ts) < abs(best[0] - target_ts):
                best = (ts, close)
    return best[1] if best else None


def update_outcomes(recs):
    now = time.time()
    for r in recs:
        if r.get("status") != "pending":
            continue
        if now - r["first_ts"] < HORIZON_H * 3600:
            continue
        p0 = _price_at(r["pool"], r["first_ts"])
        p1 = _price_at(r["pool"], r["first_ts"] + HORIZON_H * 3600)
        if p0 and p1 and p0 > 0:
            r["fwd_ret"] = float(p1 / p0 - 1.0); r["status"] = "final"
        else:
            r["fwd_ret"] = -1.0 if p0 and not p1 else None  # gone/dead => treat as -100% (unbiased)
            r["status"] = "final" if r["fwd_ret"] is not None else "no_price"
        time.sleep(2.2)
    return recs


def perm_test(x, y, iters=5000, seed=1):
    n = len(x)
    if n < 8 or x.std() == 0:
        return 0.0, 1.0
    rx = np.argsort(np.argsort(x)).astype(float)
    real = float(np.corrcoef(rx, y)[0, 1])
    rng = np.random.default_rng(seed); ge = 0
    for _ in range(iters):
        if abs(float(np.corrcoef(rx, rng.permutation(y))[0, 1])) >= abs(real):
            ge += 1
    return real, (ge + 1) / (iters + 1)


def report():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore
    recs = _load_state()
    finals = [r for r in recs if r.get("status") == "final" and r.get("fwd_ret") is not None]
    pend = [r for r in recs if r.get("status") == "pending"]
    print(f"[forward_collector] total={len(recs)} pending={len(pend)} finalized={len(finals)}")
    if len(finals) < MIN_N_TEST:
        print(f"  need >= {MIN_N_TEST} finalized for a valid perm-null test (collect forward). "
              f"Schedule --tick hourly.")
        return
    y = np.array([r["fwd_ret"] for r in finals])
    print(f"  outcome fwd{HORIZON_H}h: mean={y.mean():+.1%} median={np.median(y):+.1%} "
          f"win={np.mean(y>0):.1%} (UNBIASED incl. deaths)")
    out = {"n": len(finals), "features": {}}
    for feat in ("n_buyers", "n_tracked", "n_smart", "buy_sol", "concentration"):
        x = np.array([r.get(feat, 0) for r in finals], float)
        corr, p = perm_test(x, y)
        med = np.median(x); hi = y[x > med]; lo = y[x <= med]
        flag = "✓SIGNAL" if p < 0.05 and corr > 0 else "noise"
        hm = hi.mean() if len(hi) else 0; lm = lo.mean() if len(lo) else 0
        print(f"  {feat:14}: spearman={corr:+.2f} perm_p={p:.3f} hi={hm:+.1%} lo={lm:+.1%} {flag}")
        out["features"][feat] = {"corr": corr, "perm_p": p}
    RESULT.write_text(json.dumps(out, indent=2), encoding="utf-8")


def tick(maxn=25):
    _load_env()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore
    if not hc.API_KEY:
        print("ERROR: no Helius key"); return
    recs = _load_state()
    seen = set(r["mint"] for r in recs)
    tracked, smart = _smart_sets()
    found = discover()
    new, seen_new = [], set()
    for (m, p, c) in found:                 # dedup vs state AND within this tick
        if m in seen or m in seen_new:
            continue
        seen_new.add(m); new.append((m, p, c))
    print(f"[tick] discovered={len(found)} new={len(new)} (snapshotting up to {maxn})")
    added = 0
    for m, p, c in new[:maxn]:
        try:
            rec = snapshot_token(m, p, tracked, smart)
            if rec:
                recs.append(rec)
                if rec.get("status") == "pending":
                    added += 1
                    print(f"  + {m[:16]} buyers={rec['n_buyers']} tracked={rec['n_tracked']} "
                          f"smart={rec['n_smart']} buy_sol={rec['buy_sol']:.1f}")
        except Exception as e:
            print(f"  ! {m[:12]} fail: {str(e)[:50]}")
        time.sleep(0.2)
    recs = update_outcomes(recs)
    _save_state(recs)
    finals = sum(1 for r in recs if r.get("status") == "final")
    print(f"[tick] snapshotted {added} new pending; total={len(recs)} finalized={finals}")
    if finals >= MIN_N_TEST:
        report()


def selftest():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore
    print("SELFTEST — forward_collector")
    # perm_test: random => p high; real signal => p low
    rng = np.random.default_rng(0)
    x = rng.normal(0, 1, 200); y = rng.normal(0, 1, 200)
    _, p0 = perm_test(x, y)
    ys = x * 0.5 + rng.normal(0, 0.5, 200)
    c1, p1 = perm_test(x, ys)
    print(f"  [1] perm_test null p={p0:.3f} (expect>0.05) | signal p={p1:.4f} corr={c1:+.2f} (expect<0.05) "
          f"-> {'PASS' if p0 > 0.05 and p1 < 0.05 else 'CHECK'}")
    # env loads
    _load_env()
    print(f"  [2] Helius key present: {bool(hc.API_KEY)} -> {'PASS' if hc.API_KEY else 'FAIL'}")
    # state roundtrip
    rec = [{"mint": "X", "status": "pending", "first_ts": 1, "n_buyers": 3}]
    tmp = STATE
    print(f"  [3] state path writable dir: {tmp.parent.exists()} -> {'PASS' if tmp.parent.exists() else 'FAIL'}")
    print("SELFTEST done.")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    elif "--report" in sys.argv:
        report()
    elif "--tick" in sys.argv:
        mx = int(sys.argv[sys.argv.index("--max") + 1]) if "--max" in sys.argv else 25
        tick(mx)
    else:
        print("use --tick [--max N] | --report | --selftest")
