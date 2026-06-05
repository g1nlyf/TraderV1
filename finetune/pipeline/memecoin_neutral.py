"""memecoin_neutral.py — H-15: THE SYNTHESIS. Market-neutral memecoin reversion, on-chain.

================================================================================
WHY (the convergent conclusion of 2026-06-04, research_state.md §3)
================================================================================
This session proved liquid CEX crypto is EFFICIENT — every standalone edge there is
non-stationary (directional) or arbed-to-breakeven (carry). The ONLY edge ever real was
H-03 memecoin reversion (+1.57%), which lived in an INEFFICIENT venue and only "failed"
because (a) it was long-only with uncontrolled market beta → regime-conditional, and
(b) I tried to fix it by porting to LIQUID majors (H-10/H-11), which just re-proved
liquid = efficient.

THE SYNTHESIS: take the one edge that worked (memecoin reversion) + the one construction
that worked (market-NEUTRAL, which beat B-03 for carry) and combine them IN THE
INEFFICIENT VENUE: long oversold memecoin − short SOL (beta hedge). This directly fixes
H-03's documented failure mode (market beta) without leaving the venue where the
reversion edge actually exists.

  signal  : per-token drawdown from its own rolling high (the H-03 oversold signal)
  payoff  : (token_fwd_ret − SOL_fwd_ret) − cost   [SOL = the market/beta hedge]
  vs.     : also report UNHEDGED (token_fwd − cost) → does the hedge fix the regime split?

REALISM (memecoins are EXPENSIVE — this is the real killer):
default round-trip cost 1.5% (DEX fee + slippage + priority), swept. Survivorship: we keep
each token's FULL hourly history and sample oversold events uniformly (incl. the dumps).

HONESTY: out-of-time split by time, event-study power (many tokens × times), block-bootstrap
CI, permutation null (oversold vs random events), SOL-regime split, cost sweep, selftests.

Run:
    py -3 finetune/pipeline/memecoin_neutral.py --selftest
    py -3 finetune/pipeline/memecoin_neutral.py --run --pages 6 --max-tokens 80   # harvest+test
    py -3 finetune/pipeline/memecoin_neutral.py --analyze                          # cached only
"""
from __future__ import annotations

import json
import math
import sys
import time
import urllib.request
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "finetune" / "pipeline"))
import harvest_token_universe as htu  # noqa: E402  (reuse rate-limited GeckoTerminal calls)

CACHE = ROOT / "finetune" / "data" / "memecoin_cache"
RESULT_PATH = ROOT / "finetune" / "data" / "memecoin_neutral_result.json"
LOG_PATH = ROOT / "finetune" / "data" / "memecoin_neutral_log.jsonl"

HOUR = 3600
TRAIN_FRAC = 0.70
MIN_HIST = 120                          # hours of history to use a token
MIN_EVENTS_TRAIN = 80
ROUND_TRIP_COST = 0.015                 # 1.5% memecoin round-trip (DEX fee+slippage+priority)
COST_GRID = [0.005, 0.010, 0.015, 0.020, 0.030]
LOOKS = [6, 12, 24]                     # rolling-high window (hours)
DD_THRS = [-0.10, -0.20, -0.30]         # oversold depth
HOLDS = [6, 12, 24]                     # hours held
PERM_ITERS = 400
BOOT_ITERS = 1500


# --------------------------------------------------------------------------- #
# Data
# --------------------------------------------------------------------------- #
def fetch_sol() -> tuple[np.ndarray, np.ndarray]:
    """SOL/USDT hourly from Binance (the market/beta hedge). ts in seconds."""
    f = CACHE / "SOL_1h.npz"
    if f.exists():
        z = np.load(f); return z["t"], z["c"]
    t, c, cur = [], [], int(time.time() * 1000) - 365 * 24 * 3600 * 1000
    for _ in range(20):
        url = f"https://api.binance.com/api/v3/klines?symbol=SOLUSDT&interval=1h&startTime={cur}&limit=1000"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        rows = json.loads(urllib.request.urlopen(req, timeout=30).read())
        if not rows:
            break
        for k in rows:
            t.append(int(k[0]) // 1000); c.append(float(k[4]))
        if len(rows) < 1000:
            break
        cur = int(rows[-1][0]) + 1
    t = (np.array(t, np.int64) // HOUR) * HOUR; c = np.array(c)
    CACHE.mkdir(parents=True, exist_ok=True); np.savez_compressed(f, t=t, c=c)
    return t, c


def harvest(pages: int, max_tokens: int):
    CACHE.mkdir(parents=True, exist_ok=True)
    plist_f = CACHE / "pool_list.json"
    if plist_f.exists():
        pools = json.loads(plist_f.read_text())
    else:
        pools = htu.list_pools(pages)[:max_tokens]
        plist_f.write_text(json.dumps(pools))
    print(f"[harvest] {len(pools)} pools; fetching OHLCV (cached skipped) ...", flush=True)
    for i, (mint, pool) in enumerate(pools):
        cf = CACHE / f"tok_{mint[:24]}.npz"
        if cf.exists():
            continue
        try:
            pts = htu.ohlcv_full(pool, tf="hour", agg=1, limit=1000)  # [(ts,o,h,l,c,v)]
            if len(pts) >= MIN_HIST:
                arr = np.array([(p[0], p[4]) for p in pts], float)
                np.savez_compressed(cf, t=(arr[:, 0].astype(np.int64) // HOUR) * HOUR, c=arr[:, 1])
            time.sleep(2.2)
        except Exception as e:
            print(f"  [{i}] {mint[:12]} fail: {str(e)[:50]}", flush=True)
    fetch_sol()
    print("[harvest] done.", flush=True)


def build_panel() -> dict:
    toks = {}
    for f in CACHE.glob("tok_*.npz"):
        z = np.load(f)
        if len(z["c"]) >= MIN_HIST:
            toks[f.stem] = (z["t"], z["c"])
    if not toks:
        raise RuntimeError("No cached tokens. Run with --run first.")
    st, sc = fetch_sol()
    all_t = np.unique(np.concatenate([t for t, _ in toks.values()]))
    # restrict grid to SOL coverage
    all_t = all_t[(all_t >= st.min()) & (all_t <= st.max())]
    row = {int(x): i for i, x in enumerate(all_t)}; T = len(all_t)
    names = sorted(toks)
    close = np.full((T, len(names)), np.nan)
    for j, n in enumerate(names):
        t, c = toks[n]
        for i, x in enumerate(t):
            k = int(x)
            if k in row:
                close[row[k], j] = c[i]
    sol = np.full(T, np.nan)
    sr = {int(x): i for i, x in enumerate(st)}
    for i, x in enumerate(all_t):
        if int(x) in sr:
            sol[i] = sc[sr[int(x)]]
    # forward-fill SOL small gaps
    last = np.nan
    for i in range(T):
        if np.isfinite(sol[i]):
            last = sol[i]
        elif np.isfinite(last):
            sol[i] = last
    return {"times": all_t, "names": names, "close": close, "sol": sol}


# --------------------------------------------------------------------------- #
# Reversion event study (hedged vs unhedged)
# --------------------------------------------------------------------------- #
def events(panel: dict, look: int, dd_thr: float, hold: int, cost: float, hedge: bool):
    close, sol, T = panel["close"], panel["sol"], len(panel["times"])
    N = close.shape[1]
    ev_t, ev_p = [], []
    for j in range(N):
        c = close[:, j]
        for t in range(look, T - hold):
            if not (np.isfinite(c[t]) and np.isfinite(c[t + hold])):
                continue
            win = c[t - look:t + 1]
            win = win[np.isfinite(win)]
            if len(win) < look // 2 or win.max() <= 0:
                continue
            dd = c[t] / win.max() - 1.0
            if dd >= dd_thr:
                continue
            fwd = c[t + hold] / c[t] - 1.0
            if hedge:
                if not (np.isfinite(sol[t]) and np.isfinite(sol[t + hold])):
                    continue
                fwd -= (sol[t + hold] / sol[t] - 1.0)
            ev_t.append(int(panel["times"][t])); ev_p.append(fwd - cost)
    return np.array(ev_t), np.array(ev_p)


def stats(p):
    n = len(p)
    if n == 0:
        return {"n": 0, "ev": 0.0, "win": 0.0, "tstat": 0.0}
    mu = float(p.mean()); sd = float(p.std(ddof=1)) if n > 1 else 0.0
    se = sd / math.sqrt(n) if n else 0.0
    return {"n": n, "ev": mu, "win": float((p > 0).mean()), "tstat": (mu / se) if se > 0 else 0.0}


def block_ci(x, block=12, iters=BOOT_ITERS, seed=7):
    n = len(x)
    if n < 2:
        return (0.0, 0.0)
    rng = np.random.default_rng(seed); nb = int(math.ceil(n / block)); m = np.empty(iters)
    hi = max(1, n - block + 1)
    for i in range(iters):
        s = rng.integers(0, hi, size=nb)
        idx = (s[:, None] + np.arange(block)[None, :]).ravel()[:n]
        m[i] = x[np.clip(idx, 0, n - 1)].mean()
    m.sort(); return float(m[int(0.025 * iters)]), float(m[int(0.975 * iters)])


def perm_p(panel, look, dd_thr, hold, cost, hedge, te_lo, iters=PERM_ITERS, seed=11):
    """Null: oversold events vs RANDOM (token,t) events (same count). p=P(null>=real)."""
    rng = np.random.default_rng(seed)
    close, sol, T = panel["close"], panel["sol"], len(panel["times"])
    N = close.shape[1]; all_p, over_mask = [], []
    for j in range(N):
        c = close[:, j]
        for t in range(look, T - hold):
            if not (np.isfinite(c[t]) and np.isfinite(c[t + hold]) and int(panel["times"][t]) >= te_lo):
                continue
            if hedge and not (np.isfinite(sol[t]) and np.isfinite(sol[t + hold])):
                continue
            win = c[t - look:t + 1]; win = win[np.isfinite(win)]
            if len(win) < look // 2 or win.max() <= 0:
                continue
            fwd = c[t + hold] / c[t] - 1.0
            if hedge:
                fwd -= (sol[t + hold] / sol[t] - 1.0)
            all_p.append(fwd - cost); over_mask.append((c[t] / win.max() - 1.0) < dd_thr)
    all_p = np.array(all_p); over_mask = np.array(over_mask)
    k = int(over_mask.sum())
    if k < 20 or len(all_p) - k < 20:
        return 1.0
    real = all_p[over_mask].mean(); ge = 0
    for _ in range(iters):
        if rng.choice(len(all_p), k, replace=False).size and all_p[rng.choice(len(all_p), k, replace=False)].mean() >= real:
            ge += 1
    return (ge + 1) / (iters + 1)


def regime(panel, ev_t, ev_p):
    st, sc = panel["times"], panel["sol"]
    sr = {int(x): i for i, x in enumerate(panel["times"])}
    out = {}; up, dn = [], []
    win = 168
    for tt, pp in zip(ev_t, ev_p):
        i = sr.get(int(tt))
        if i is None or i - win < 0 or not np.isfinite(panel["sol"][i]) or not np.isfinite(panel["sol"][i - win]):
            continue
        (up if (panel["sol"][i] / panel["sol"][i - win] - 1) > 0 else dn).append(pp)
    for nm, seg in (("sol_up", up), ("sol_down", dn)):
        seg = np.array(seg)
        out[nm] = {"n": len(seg), "ev": float(seg.mean()) if len(seg) else 0.0}
    return out


def evaluate(panel, hedge):
    best = None
    for look in LOOKS:
        for dd in DD_THRS:
            for hold in HOLDS:
                t, p = events(panel, look, dd, hold, ROUND_TRIP_COST, hedge)
                if len(p) < 40:
                    continue
                cut = int(panel["times"][int(len(panel["times"]) * TRAIN_FRAC)])
                tr = stats(p[t < cut])
                if tr["n"] < MIN_EVENTS_TRAIN:
                    continue
                if best is None or tr["tstat"] > best[0]:
                    best = (tr["tstat"], look, dd, hold)
    if best is None:
        return None
    _, look, dd, hold = best
    t, p = events(panel, look, dd, hold, ROUND_TRIP_COST, hedge)
    cut = int(panel["times"][int(len(panel["times"]) * TRAIN_FRAC)])
    tr, te = stats(p[t < cut]), stats(p[t >= cut])
    ci = block_ci(p[t >= cut])
    pj = perm_p(panel, look, dd, hold, ROUND_TRIP_COST, hedge, cut)
    reg = regime(panel, t[t >= cut], p[t >= cut])
    cc = []
    for c in COST_GRID:
        tt, pp = events(panel, look, dd, hold, c, hedge)
        cc.append({"cost": c, "test_ev": stats(pp[tt >= cut])["ev"]})
    return {"hedge": hedge, "look": look, "dd_thr": dd, "hold": hold,
            "train": tr, "test": te, "test_ci95": ci, "perm_p": pj, "regimes": reg, "cost_curve": cc}


def verdict(ev):
    te = ev["test"]; lo, hi = ev["test_ci95"]; p = ev["perm_p"]; r = ev["regimes"]
    stable = (r.get("sol_up", {}).get("ev", 0) > 0 and r.get("sol_down", {}).get("ev", 0) > 0)
    # HARD GATE: if oversold events don't beat RANDOM events, the +EV is universe/survivorship,
    # not the signal — no t-stat or EV can rescue it. (perm_p is robust to overlap inflation.)
    if p >= 0.05:
        return "REFUTED", (f"Oversold events do NOT beat random (perm_p={p:.2f}) — the +EV is "
                           f"survivorship/sample bias, not a reversion edge.")
    if te["ev"] > 0 and lo > 0 and stable:
        return "VALIDATED", "Net +EV/event OOS after 1.5% cost, CI>0, beats null, SOL-regime-stable."
    if te["ev"] > 0 and lo > 0:
        return "PROMISING", "Positive net EV, beats null, CI>0; regime-stability unmet — refine."
    if te["ev"] > 0:
        return "WEAK", "Positive point estimate, not separable from noise."
    return "REFUTED", "No positive net EV/event OOS after realistic memecoin costs."


def _now():
    import datetime as dt
    return dt.datetime.now(dt.timezone.utc).isoformat()


def analyze():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore
    print("[analyze] building panel from cache ...")
    panel = build_panel()
    print(f"      tokens={len(panel['names'])} periods={len(panel['times'])} "
          f"(~{(panel['times'][-1]-panel['times'][0])/86400:.0f}d)")
    out = {"ts": _now(), "tokens": len(panel["names"]), "periods": int(len(panel["times"])), "results": {}}
    for hedge in (False, True):
        ev = evaluate(panel, hedge)
        tag = "NEUTRAL (long memecoin − short SOL)" if hedge else "UNHEDGED (long-only, = H-03)"
        if ev is None:
            print(f"\n  {tag}: insufficient events"); continue
        v, why = verdict(ev); ev["verdict"] = v
        out["results"]["hedged" if hedge else "unhedged"] = ev
        te = ev["test"]; lo, hi = ev["test_ci95"]; r = ev["regimes"]
        print(f"\n  === {tag} (look={ev['look']}h dd<{ev['dd_thr']} hold={ev['hold']}h, cost 1.5%) ===")
        print(f"    TRAIN EV={ev['train']['ev']:+.2%} t={ev['train']['tstat']:+.2f} n={ev['train']['n']}")
        print(f"    TEST  EV/event={te['ev']:+.2%} win={te['win']:.1%} t={te['tstat']:+.2f} n={te['n']}")
        print(f"    TEST  CI95=[{lo:+.2%},{hi:+.2%}] perm_p={ev['perm_p']:.3f}")
        print(f"    regime: SOL-up EV={r.get('sol_up',{}).get('ev',0):+.2%} (n={r.get('sol_up',{}).get('n',0)})  "
              f"SOL-down EV={r.get('sol_down',{}).get('ev',0):+.2%} (n={r.get('sol_down',{}).get('n',0)})")
        print(f"    cost sweep: " + "  ".join(f"{c['cost']*100:.1f}%->{c['test_ev']:+.2%}" for c in ev["cost_curve"]))
        print(f"    VERDICT: {v} — {why}")
    RESULT_PATH.write_text(json.dumps(_json(out), indent=2), encoding="utf-8")
    with LOG_PATH.open("a", encoding="utf-8") as f:
        for k, ev in out["results"].items():
            f.write(json.dumps({"ts": out["ts"], "variant": k, "look": ev["look"], "dd_thr": ev["dd_thr"],
                                "hold": ev["hold"], "test_ev": ev["test"]["ev"], "perm_p": ev["perm_p"],
                                "ci95": ev["test_ci95"], "verdict": ev["verdict"]}) + "\n")
    print(f"\n  wrote {RESULT_PATH.relative_to(ROOT)}; appended {LOG_PATH.relative_to(ROOT)}")


def _json(o):
    if isinstance(o, dict):
        return {k: _json(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_json(v) for v in o]
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    return o


def selftest():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore
    print("SELFTEST — memecoin_neutral")
    rng = np.random.default_rng(0); T, N = 2000, 30
    base = rng.normal(0, 0.03, (T, N))
    # common SOL beta: each token = beta*sol + idio; + a true reversion in idio
    solret = rng.normal(0, 0.02, T)
    rev = np.zeros((T, N)); rev[1:] = -0.25 * base[:-1]
    tok = base + rev + solret[:, None]                       # tokens carry SOL beta
    close = 100 * np.cumprod(1 + tok, axis=0)
    sol = 100 * np.cumprod(1 + solret)
    p = {"times": (np.arange(T) * HOUR).astype(np.int64), "names": list(range(N)),
         "close": close, "sol": sol}
    # 1) random-ish: unhedged dd reversion should show SOME signal; hedged removes beta noise
    eu = stats(events(p, 6, -0.05, 1, 0.0, False)[1])
    eh = stats(events(p, 6, -0.05, 1, 0.0, True)[1])
    print(f"  [1] events fire: unhedged n={eu['n']} hedged n={eh['n']} -> {'PASS' if eu['n']>100 and eh['n']>100 else 'CHECK'}")
    # 2) hedge reduces variance (removes SOL beta) => hedged |tstat noise| structure differs;
    #    injected idio reversion => hedged EV>0.
    print(f"  [2] injected reversion hedged EV={eh['ev']:+.3%} (expect >0) -> {'PASS' if eh['ev']>0 else 'CHECK'}")
    # 3) cost monotonic
    a0 = stats(events(p, 6, -0.05, 1, 0.0, True)[1])["ev"]
    a1 = stats(events(p, 6, -0.05, 1, 0.02, True)[1])["ev"]
    print(f"  [3] cost monotonic {a0:+.3%}>{a1:+.3%} -> {'PASS' if a0>a1 else 'FAIL'}")
    # 4) hedge removes pure-beta: tokens = SOL only (no idio reversion) => hedged EV ~0
    tok2 = solret[:, None] + rng.normal(0, 0.001, (T, N))
    c2 = 100 * np.cumprod(1 + tok2, axis=0)
    p2 = {**p, "close": c2}
    eh2 = stats(events(p2, 6, -0.05, 1, 0.0, True)[1])
    print(f"  [4] pure-beta hedged EV={eh2['ev']:+.4%} (expect ~0) -> {'PASS' if abs(eh2['ev'])<0.01 else 'CHECK'}")
    print("SELFTEST done.")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    elif "--analyze" in sys.argv:
        analyze()
    elif "--run" in sys.argv:
        pages = int(sys.argv[sys.argv.index("--pages") + 1]) if "--pages" in sys.argv else 6
        maxt = int(sys.argv[sys.argv.index("--max-tokens") + 1]) if "--max-tokens" in sys.argv else 80
        harvest(pages, maxt)
        analyze()
    else:
        print("use --selftest | --run [--pages P --max-tokens M] | --analyze")
