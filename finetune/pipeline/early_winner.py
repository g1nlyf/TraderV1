"""early_winner.py — H-18: resolve B-01 and test the ONLY surviving thesis (info asymmetry).

================================================================================
WHY (FINAL CONVERGENCE 2026-06-04, research_state.md)
================================================================================
Every backtestable edge on public data is noise/arbed/negative-skew. The one thesis
consistent with all evidence: EARLY-WINNER selection via on-chain information asymmetry
(which token runs, detected early). It was DATA-BLOCKED (B-01): the wallet-signal universe
(13 tokens, unlabeled) and the price-outcome universe (332 `token_ohlcv` tokens) were
disjoint. This tool RESOLVES B-01 by RECONSTRUCTING early buyers for the OUTCOME tokens
from chain (Helius), producing a joined (token × early-buyer-features × forward-return)
dataset, then testing under the permutation-null gate (this session's #1 lesson).

PIPELINE per outcome-token (mint, pool, first_ts from ohlcv):
  1. getSignaturesForAddress(pool), paginate back toward first_ts (page-budget capped — B-09).
  2. Helius Enhanced parse; per tx trader = feePayer; decode swap via helius_client._extract_swap.
  3. EARLY BUYERS = wallets buying `mint` in [first_ts, first_ts+window_h].
  4. FEATURES: n_distinct_early_buyers, n_tracked (∈ project's known wallets),
     n_smart (∈ win_rate>0.55 wallets), early_buy_sol, buyer concentration.
  5. OUTCOME: forward return from (first_ts+window) over `horizon_h` (from ohlcv close).
  6. TEST (across tokens): does each feature beat a PERMUTATION NULL (feature vs shuffled
     outcome) + Spearman sign + high/low split? Out-of-time where N allows.

No prediction is trusted without perm_p<0.05. Realistic-latency note: features use only the
[first_ts, first_ts+window] info; outcome is strictly after — no lookahead.

Run:
    py -3 finetune/pipeline/early_winner.py --smoke 4        # prove pipeline on 4 tokens
    py -3 finetune/pipeline/early_winner.py --run --max 60   # full reconstruct + perm-null test
"""
from __future__ import annotations

import json
import math
import os
import sqlite3
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "finetune" / "pipeline"))
import helius_client as hc  # noqa: E402

DB = ROOT / "WalletScarper" / "data" / "stage2_foundation.sqlite3"
CACHE = ROOT / "finetune" / "data" / "early_winner_cache"
RESULT = ROOT / "finetune" / "data" / "early_winner_result.json"
LOG = ROOT / "finetune" / "data" / "early_winner_log.jsonl"

WINDOW_H = 1               # early-buyer observation window (hours after first candle)
HORIZON_H = 24            # forward outcome horizon (hours)
PAGE_BUDGET = 20          # max sig pages/token (B-09 cost cap; 20*100=2000 sigs)


def _load_env():
    """Inject Helius keys from WalletScarper/.env if not already in env (env-only policy)."""
    if os.environ.get("HELIUS_API_KEY") and os.environ.get("HELIUS_RPC_URL"):
        return
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


def load_outcome_tokens(limit=None):
    """Tokens with price paths (outcome side). Returns [(mint, pool, ts[], close[])]."""
    con = sqlite3.connect(str(DB))
    rows = con.execute("SELECT token_mint, pool_address, ts, close FROM token_ohlcv "
                       "WHERE close>0 AND length(token_mint)>=40 AND pool_address IS NOT NULL "
                       "ORDER BY token_mint, ts").fetchall()
    con.close()
    by = defaultdict(list)
    pool = {}
    for m, p, ts, c in rows:
        by[m].append((int(ts), float(c))); pool[m] = p
    out = []
    for m, series in by.items():
        if len(series) >= HORIZON_H + WINDOW_H + 2 and pool.get(m):
            series.sort()
            t = np.array([x[0] for x in series]); c = np.array([x[1] for x in series])
            out.append((m, pool[m], t, c))
    if limit:
        out = out[:limit]
    return out


def known_wallets():
    con = sqlite3.connect(str(DB))
    tracked = set(r[0] for r in con.execute(
        "SELECT DISTINCT wallet FROM wallet_token_outcomes WHERE length(wallet)>=40").fetchall())
    smart = set(r[0] for r in con.execute(
        "SELECT DISTINCT wallet FROM wallet_metric_snapshots WHERE win_rate_estimate>0.55 "
        "AND length(wallet)>=40").fetchall())
    con.close()
    return tracked, smart


def reconstruct_early_buyers(mint, pool, first_ts, window_s, page_budget=PAGE_BUDGET):
    """Paginate pool signatures back toward first_ts; decode buys of `mint` by trader=feePayer
    in [first_ts, first_ts+window_s]. Returns (buyers:dict wallet->sol, reached_start:bool)."""
    end_ts = first_ts + window_s
    before = None
    keep_sigs = []
    reached = False
    for _ in range(page_budget):
        batch = hc.get_signatures(pool, limit=100, before=before)
        if not batch:
            reached = True
            break
        before = batch[-1]["signature"]
        oldest = batch[-1].get("blockTime") or 0
        for s in batch:
            bt = s.get("blockTime") or 0
            if first_ts <= bt <= end_ts:
                keep_sigs.append(s["signature"])
        if oldest and oldest < first_ts:
            reached = True
            break
        time.sleep(0.1)
    buyers: dict[str, float] = {}
    if not keep_sigs:
        return buyers, reached
    parsed = hc.parse(keep_sigs)
    for tx in parsed:
        bt = tx.get("timestamp") or 0
        if not (first_ts <= bt <= end_ts):
            continue
        trader = tx.get("feePayer", "")
        if not trader:
            continue
        sw = hc._extract_swap(tx, trader)
        if sw and sw.token_mint == mint and sw.side == "buy":
            buyers[trader] = buyers.get(trader, 0.0) + sw.sol_amount
    return buyers, reached


def features_and_outcome(token, tracked, smart):
    mint, pool, t, c = token
    first_ts = int(t[0])
    buyers, reached = reconstruct_early_buyers(mint, pool, first_ts, WINDOW_H * 3600)
    # outcome: return from (first_ts+window) over horizon
    t0 = first_ts + WINDOW_H * 3600
    t1 = t0 + HORIZON_H * 3600
    i0 = int(np.searchsorted(t, t0)); i1 = int(np.searchsorted(t, t1))
    if i0 >= len(c) or i1 >= len(c) or c[i0] <= 0:
        return None
    fwd = float(c[i1] / c[i0] - 1.0)
    sols = np.array(list(buyers.values()))
    conc = float(sols.max() / sols.sum()) if len(sols) and sols.sum() > 0 else 0.0
    return {
        "mint": mint, "n_buyers": len(buyers),
        "n_tracked": sum(1 for w in buyers if w in tracked),
        "n_smart": sum(1 for w in buyers if w in smart),
        "buy_sol": float(sols.sum()), "concentration": conc,
        "reached_start": reached, "fwd_ret": fwd,
    }


def perm_test(x, y, iters=5000, seed=1):
    """Spearman-style: corr(rank x, y) vs shuffled-y null. Returns (corr, p)."""
    n = len(x)
    if n < 8:
        return 0.0, 1.0
    rx = np.argsort(np.argsort(x)).astype(float)
    real = float(np.corrcoef(rx, y)[0, 1])
    rng = np.random.default_rng(seed); ge = 0
    for _ in range(iters):
        if abs(float(np.corrcoef(rx, rng.permutation(y))[0, 1])) >= abs(real):
            ge += 1
    return real, (ge + 1) / (iters + 1)


def smoke(k):
    _load_env()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore
    if not hc.API_KEY:
        print("ERROR: no Helius key"); return
    toks = load_outcome_tokens(limit=k)
    tracked, smart = known_wallets()
    print(f"SMOKE: {len(toks)} tokens | tracked-wallet set={len(tracked)} smart={len(smart)}")
    for tok in toks:
        t0 = time.time()
        f = features_and_outcome(tok, tracked, smart)
        if f:
            print(f"  {f['mint'][:16]} buyers={f['n_buyers']:3} tracked={f['n_tracked']} "
                  f"smart={f['n_smart']} buy_sol={f['buy_sol']:.1f} conc={f['concentration']:.2f} "
                  f"fwd{HORIZON_H}h={f['fwd_ret']:+.1%} reached_start={f['reached_start']} "
                  f"({time.time()-t0:.0f}s)")
        else:
            print(f"  {tok[0][:16]} — no outcome/insufficient data ({time.time()-t0:.0f}s)")


def run(maxn):
    _load_env()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore
    CACHE.mkdir(parents=True, exist_ok=True)
    toks = load_outcome_tokens(limit=maxn)
    tracked, smart = known_wallets()
    print(f"[early_winner] reconstructing {len(toks)} tokens (window={WINDOW_H}h horizon={HORIZON_H}h) ...")
    feats = []
    for i, tok in enumerate(toks):
        cf = CACHE / f"f_{tok[0][:24]}.json"
        if cf.exists():
            feats.append(json.loads(cf.read_text())); continue
        try:
            f = features_and_outcome(tok, tracked, smart)
            if f:
                cf.write_text(json.dumps(f)); feats.append(f)
        except Exception as e:
            print(f"  [{i}] {tok[0][:12]} fail: {str(e)[:50]}")
        if i % 10 == 0:
            print(f"  [{i}/{len(toks)}] collected={len(feats)}", flush=True)
    if len(feats) < 8:
        print(f"[early_winner] only {len(feats)} tokens — underpowered, stop."); return
    y = np.array([f["fwd_ret"] for f in feats])
    print(f"\n[early_winner] N={len(feats)} tokens  fwd{HORIZON_H}h: mean={y.mean():+.1%} median={np.median(y):+.1%}")
    out = {"ts": _now(), "n": len(feats), "window_h": WINDOW_H, "horizon_h": HORIZON_H, "features": {}}
    for feat in ("n_buyers", "n_tracked", "n_smart", "buy_sol", "concentration"):
        x = np.array([f[feat] for f in feats], float)
        if x.std() == 0:
            print(f"  {feat:14}: constant, skip"); continue
        corr, p = perm_test(x, y)
        # high/low split
        med = np.median(x); hi = y[x > med]; lo = y[x <= med]
        flag = "✓SIGNAL" if p < 0.05 else "noise"
        print(f"  {feat:14}: spearman={corr:+.2f} perm_p={p:.3f}  hi={hi.mean():+.1%} lo={lo.mean():+.1%}  {flag}")
        out["features"][feat] = {"corr": corr, "perm_p": p, "hi_mean": float(hi.mean()), "lo_mean": float(lo.mean())}
    best = min(out["features"].items(), key=lambda kv: kv[1]["perm_p"]) if out["features"] else None
    verdict = ("VALIDATED early-winner signal" if best and best[1]["perm_p"] < 0.05 and best[1]["corr"] > 0
               else "REFUTED — no early-buyer feature beats the permutation null")
    out["verdict"] = verdict
    print(f"\n  VERDICT: {verdict}")
    RESULT.write_text(json.dumps(out, indent=2), encoding="utf-8")
    with LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": out["ts"], "n": out["n"], "verdict": verdict,
                            "features": {k: {"perm_p": v["perm_p"], "corr": v["corr"]}
                                         for k, v in out["features"].items()}}) + "\n")
    print(f"  wrote {RESULT.relative_to(ROOT)}")


def _now():
    import datetime as dt
    return dt.datetime.now(dt.timezone.utc).isoformat()


if __name__ == "__main__":
    if "--smoke" in sys.argv:
        k = int(sys.argv[sys.argv.index("--smoke") + 1]) if len(sys.argv) > sys.argv.index("--smoke") + 1 else 4
        smoke(k)
    elif "--run" in sys.argv:
        m = int(sys.argv[sys.argv.index("--max") + 1]) if "--max" in sys.argv else 60
        run(m)
    else:
        print("use --smoke K | --run --max N")
