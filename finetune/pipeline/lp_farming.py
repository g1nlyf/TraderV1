"""lp_farming.py — H-16: LP fee farming — the MECHANICAL edge (survives the permutation null).

================================================================================
WHY (FOUNDATIONAL CORRECTION 2026-06-04, research_state.md top + Appendix B 17/18)
================================================================================
A permutation null killed every SELECTION/PREDICTION edge (directional factors, H-03
reversion, H-14 funding-direction — all perm_p > 0.05 = no info over random). The ONLY
class it cannot refute is MECHANICAL income: you are paid regardless of any prediction.
LP fee farming is exactly that — provide liquidity, earn fee_rate × volume mechanically.

THE HONEST QUESTION: memecoin pools have FAT fees (huge volume × 0.25-1% fee) but BRUTAL
impermanent loss / rug risk (price→0 ⇒ LP holds the dead token). Do fees beat IL?

Constant-product full-range LP, price ratio k = p_end/p_start (derivation in selftest):
  LP value ratio              = √k                       (vs initial capital)
  HODL value ratio            = (1+k)/2
  IL (cost, ≥0)               = (1+k)/2 − √k
  fees over window (% of cap) = fee_rate × Σ volume / reserve
Two metrics:
  UNHEDGED  net = (√k − 1)        + fees − gas   (full memecoin/rug exposure; directional)
  NEUTRAL   net = fees − IL − gas                (delta-hedged: the PURE mechanical edge)

The NEUTRAL metric is the one that matters: it is direction-free, so no permutation null
applies — if fees > IL out-of-time across regimes, it is a real mechanical edge.

HONESTY: out-of-time split, SOL-regime split, gas-cost sweep, distribution (mean/median/win),
block-bootstrap CI, selftests (IL formula, k=1 ⇒ net=fees, cost monotonic). NB: reserve uses
the CURRENT snapshot as scale for historical fee-yield — a first-order approximation, flagged.

Run:
    py -3 finetune/pipeline/lp_farming.py --selftest
    py -3 finetune/pipeline/lp_farming.py --run --max-tokens 90     # harvest+analyze
    py -3 finetune/pipeline/lp_farming.py --analyze
"""
from __future__ import annotations

import json
import math
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "finetune" / "pipeline"))
import harvest_token_universe as htu  # noqa: E402

CACHE = ROOT / "finetune" / "data" / "lp_cache"
MEME_POOL_LIST = ROOT / "finetune" / "data" / "memecoin_cache" / "pool_list.json"
RESULT_PATH = ROOT / "finetune" / "data" / "lp_farming_result.json"
LOG_PATH = ROOT / "finetune" / "data" / "lp_farming_log.jsonl"
GECKO = "https://api.geckoterminal.com/api/v2"

HOUR = 3600
TRAIN_FRAC = 0.70
MIN_HIST = 120
HOLDS = [24, 72, 168]                   # 1d, 3d, 7d LP holding windows
GAS_USD = 2.0                           # round-trip add+remove liquidity (SOL gas+priority)
LP_CAPITAL = 1000.0                     # notional per position (gas% = GAS_USD/LP_CAPITAL)
GAS_GRID = [0.5, 1.0, 2.0, 5.0, 10.0]
# fee_rate by GeckoTerminal dex id (approx; default 0.25%)
DEX_FEE = {"raydium": 0.0025, "raydium-clmm": 0.0025, "orca": 0.003, "whirlpool": 0.003,
           "orca-whirlpools": 0.003, "meteora": 0.002, "meteora-dlmm": 0.002,
           "pumpswap": 0.0025, "pump-fun": 0.0025, "fluxbeam": 0.0025, "lifinity": 0.0002}


def _get(url, retries=3):
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "TraderV1-lp/1.0",
                                                       "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:  # type: ignore
            if e.code == 429:
                time.sleep(8 * (i + 1)); continue
            raise
        except Exception:
            time.sleep(2); continue
    return {}


def pool_meta(pool: str) -> tuple[float, float]:
    """(reserve_in_usd, fee_rate) for a pool."""
    d = _get(f"{GECKO}/networks/solana/pools/{pool}")
    a = d.get("data", {}).get("attributes", {})
    rel = d.get("data", {}).get("relationships", {})
    try:
        reserve = float(a.get("reserve_in_usd") or 0.0)
    except Exception:
        reserve = 0.0
    dex = ""
    try:
        dex = rel.get("dex", {}).get("data", {}).get("id", "")
    except Exception:
        pass
    return reserve, DEX_FEE.get(dex, 0.0025)


def harvest(max_tokens: int):
    CACHE.mkdir(parents=True, exist_ok=True)
    if not MEME_POOL_LIST.exists():
        pools = htu.list_pools(6)[:max_tokens]
    else:
        pools = json.loads(MEME_POOL_LIST.read_text())[:max_tokens]
    print(f"[lp] {len(pools)} pools; fetching OHLCV+volume+reserve ...", flush=True)
    for i, (mint, pool) in enumerate(pools):
        cf = CACHE / f"lp_{mint[:24]}.npz"
        mf = CACHE / f"lp_{mint[:24]}.json"
        if cf.exists() and mf.exists():
            continue
        try:
            pts = htu.ohlcv_full(pool, tf="hour", agg=1, limit=1000)  # (ts,o,h,l,c,v)
            if len(pts) >= MIN_HIST:
                arr = np.array([(p[0], p[4], p[5]) for p in pts], float)
                np.savez_compressed(cf, t=(arr[:, 0].astype(np.int64) // HOUR) * HOUR,
                                    c=arr[:, 1], v=arr[:, 2])
                time.sleep(2.2)
                res, fee = pool_meta(pool)
                mf.write_text(json.dumps({"reserve": res, "fee": fee, "pool": pool}))
                time.sleep(2.2)
            if i % 10 == 0:
                print(f"  [{i}/{len(pools)}] {mint[:12]} ok", flush=True)
        except Exception as e:
            print(f"  [{i}] {mint[:12]} fail: {str(e)[:50]}", flush=True)
    print("[lp] harvest done.", flush=True)


def fetch_sol():
    f = CACHE / "SOL_1h.npz"
    if f.exists():
        z = np.load(f); return z["t"], z["c"]
    src = ROOT / "finetune" / "data" / "memecoin_cache" / "SOL_1h.npz"
    if src.exists():
        z = np.load(src); CACHE.mkdir(exist_ok=True)
        np.savez_compressed(f, t=z["t"], c=z["c"]); return z["t"], z["c"]
    t, c, cur = [], [], int(time.time() * 1000) - 365 * 24 * 3600 * 1000
    for _ in range(20):
        rows = _get(f"https://api.binance.com/api/v3/klines?symbol=SOLUSDT&interval=1h&startTime={cur}&limit=1000")
        if not rows:
            break
        for k in rows:
            t.append(int(k[0]) // 1000); c.append(float(k[4]))
        if len(rows) < 1000:
            break
        cur = int(rows[-1][0]) + 1
    t = (np.array(t, np.int64) // HOUR) * HOUR; c = np.array(c)
    CACHE.mkdir(exist_ok=True); np.savez_compressed(f, t=t, c=c); return t, c


def load_pools():
    out = []
    for cf in CACHE.glob("lp_*.npz"):
        mf = cf.with_suffix(".json")
        if not mf.exists():
            continue
        z = np.load(cf); meta = json.loads(mf.read_text())
        if len(z["c"]) >= MIN_HIST and meta.get("reserve", 0) > 1000:
            out.append({"t": z["t"], "c": z["c"], "v": z["v"],
                        "reserve": meta["reserve"], "fee": meta["fee"]})
    return out


# --------------------------------------------------------------------------- #
def il_cost(k):
    """Impermanent loss as a positive cost fraction: (1+k)/2 − √k  (≥0)."""
    return (1.0 + k) / 2.0 - np.sqrt(k)


def backtest(pools, sol_t, sol_c, hold, gas_usd):
    sol_map = {int(x): sc for x, sc in zip(sol_t, sol_c)}
    gas_frac = gas_usd / LP_CAPITAL
    ev_t, unh, neu, fee_only, il_only = [], [], [], [], []
    for P in pools:
        c, v, res, fee = P["c"], P["v"], P["reserve"], P["fee"]
        T = len(c)
        for t in range(0, T - hold):
            if not (np.isfinite(c[t]) and np.isfinite(c[t + hold]) and c[t] > 0):
                continue
            k = c[t + hold] / c[t]
            if not np.isfinite(k) or k <= 0:
                continue
            vol = np.nansum(v[t:t + hold])
            fees = fee * vol / res                       # % of LP capital
            il = float(il_cost(k))
            price = math.sqrt(k) - 1.0
            ev_t.append(int(P["t"][t]))
            unh.append(price + fees - gas_frac)
            neu.append(fees - il - gas_frac)
            fee_only.append(fees); il_only.append(il)
    return (np.array(ev_t), np.array(unh), np.array(neu),
            np.array(fee_only), np.array(il_only))


def stats(x):
    n = len(x)
    if n == 0:
        return {"n": 0, "mean": 0.0, "median": 0.0, "win": 0.0}
    return {"n": n, "mean": float(np.mean(x)), "median": float(np.median(x)),
            "win": float(np.mean(np.array(x) > 0))}


def block_ci(x, block=24, iters=1500, seed=7):
    n = len(x)
    if n < 2:
        return (0.0, 0.0)
    rng = np.random.default_rng(seed); nb = int(math.ceil(n / block)); m = np.empty(iters)
    hi = max(1, n - block + 1)
    for i in range(iters):
        s = rng.integers(0, hi, size=nb)
        idx = (s[:, None] + np.arange(block)[None, :]).ravel()[:n]
        m[i] = np.mean(x[np.clip(idx, 0, n - 1)])
    m.sort(); return float(m[int(0.025 * iters)]), float(m[int(0.975 * iters)])


def regime(ev_t, vals, sol_t, sol_c):
    sm = {int(x): i for i, x in enumerate(sol_t)}; win = 168 * HOUR
    up, dn = [], []
    for tt, vv in zip(ev_t, vals):
        i = sm.get(int(tt)); j = sm.get(int(tt) - win)
        if i is None or j is None:
            continue
        (up if sol_c[i] / sol_c[j] - 1 > 0 else dn).append(vv)
    return ({"n": len(up), "mean": float(np.mean(up)) if up else 0.0},
            {"n": len(dn), "mean": float(np.mean(dn)) if dn else 0.0})


def analyze():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore
    pools = load_pools()
    if not pools:
        print("[lp] no usable pools (need reserve>1000 + >=120h). Run --run first."); return
    sol_t, sol_c = fetch_sol()
    tot_h = sum(len(P["c"]) for P in pools)
    print(f"[lp] pools={len(pools)}  total pool-hours={tot_h}  "
          f"median reserve=${np.median([P['reserve'] for P in pools]):,.0f}")
    out = {"ts": _now(), "pools": len(pools), "results": {}}
    for hold in HOLDS:
        ev_t, unh, neu, fo, ilo = backtest(pools, sol_t, sol_c, hold, GAS_USD)
        if len(neu) < 50:
            print(f"  hold={hold}h: n={len(neu)} too few"); continue
        cut = int(np.quantile(ev_t, TRAIN_FRAC))
        te = ev_t >= cut
        su, sn = stats(unh[te]), stats(neu[te])
        ci = block_ci(neu[te])
        ru, rd = regime(ev_t[te], neu[te], sol_t, sol_c)
        # annualized fee vs IL (descriptive)
        ann = 8760 / hold
        print(f"\n  === LP hold={hold}h (fee≈{np.mean([P['fee'] for P in pools])*100:.2f}%, gas ${GAS_USD}) ===")
        print(f"    fee income/window: mean={np.mean(fo[te]):+.2%} (≈{np.mean(fo[te])*ann:+.0%} APR)  "
              f"IL/window: mean={np.mean(ilo[te]):.2%}")
        print(f"    UNHEDGED net/window: mean={su['mean']:+.2%} median={su['median']:+.2%} win={su['win']:.1%} n={su['n']}")
        print(f"    NEUTRAL  net/window: mean={sn['mean']:+.2%} median={sn['median']:+.2%} win={sn['win']:.1%}")
        print(f"    NEUTRAL  CI95=[{ci[0]:+.2%},{ci[1]:+.2%}]  regime: SOL-up {ru['mean']:+.2%} SOL-down {rd['mean']:+.2%}")
        gsweep = []
        for g in GAS_GRID:
            _, _, n2, _, _ = backtest(pools, sol_t, sol_c, hold, g)
            gsweep.append((g, float(np.mean(n2[ev_t >= cut]))))
        print(f"    gas sweep (neutral mean): " + "  ".join(f"${g}->{m:+.2%}" for g, m in gsweep))
        v = ("VALIDATED mechanical edge" if (sn["mean"] > 0 and ci[0] > 0 and ru["mean"] > 0 and rd["mean"] > 0)
             else "PROMISING" if sn["mean"] > 0 and ci[0] > 0
             else "WEAK" if sn["mean"] > 0 else "REFUTED (IL+gas > fees)")
        print(f"    VERDICT(neutral): {v}")
        out["results"][f"hold_{hold}"] = {"fee_window": float(np.mean(fo[te])), "il_window": float(np.mean(ilo[te])),
                                          "unhedged": su, "neutral": sn, "neutral_ci": ci,
                                          "regime_up": ru, "regime_down": rd, "verdict": v}
    RESULT_PATH.write_text(json.dumps(out, indent=2), encoding="utf-8")
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": out["ts"], "pools": out["pools"],
                            "summary": {k: {"neutral_mean": r["neutral"]["mean"], "verdict": r["verdict"]}
                                        for k, r in out["results"].items()}}) + "\n")
    print(f"\n  wrote {RESULT_PATH.relative_to(ROOT)}")


def _now():
    import datetime as dt
    return dt.datetime.now(dt.timezone.utc).isoformat()


def selftest():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore
    print("SELFTEST — lp_farming")
    # 1) IL: k=1 => 0; k=4 => (1+4)/2-2 = 0.5 (HODL) - 2 ... = 0.5; check formula sign
    print(f"  [1] IL(k=1)={il_cost(1.0):.4f} (=0) IL(k=4)={il_cost(4.0):.4f} (>0) IL(k=0.25)={il_cost(0.25):.4f} (>0) "
          f"-> {'PASS' if abs(il_cost(1.0))<1e-9 and il_cost(4.0)>0 and il_cost(0.25)>0 else 'FAIL'}")
    # 2) k=1 (flat price): neutral net = fees - gas (no IL); unhedged = fees - gas too.
    pools = [{"t": (np.arange(300) * HOUR).astype(np.int64), "c": np.full(300, 100.0),
              "v": np.full(300, 10000.0), "reserve": 100000.0, "fee": 0.0025}]
    st, sc = (np.arange(300) * HOUR).astype(np.int64), np.full(300, 50.0)
    _, unh, neu, fo, ilo = backtest(pools, st, sc, 24, 0.0)
    exp_fee = 0.0025 * 10000 * 24 / 100000  # = 0.006
    print(f"  [2] flat price: fee/window={fo.mean():.4f} (exp {exp_fee:.4f}) IL={ilo.mean():.5f}(=0) "
          f"neutral={neu.mean():.4f} -> {'PASS' if abs(fo.mean()-exp_fee)<1e-6 and ilo.mean()<1e-9 else 'FAIL'}")
    # 3) price crash k->0.01: unhedged ~ -90%, IL large
    pc = np.concatenate([np.full(150, 100.0), np.full(150, 1.0)])
    pools2 = [{"t": (np.arange(300) * HOUR).astype(np.int64), "c": pc,
               "v": np.full(300, 1e6), "reserve": 1e6, "fee": 0.0025}]
    _, unh2, neu2, fo2, ilo2 = backtest(pools2, st, sc, 24, 0.0)
    crash = unh2.min()
    print(f"  [3] price crash: min unhedged net={crash:+.1%} (√0.01-1=-90%) IL max={ilo2.max():.1%} "
          f"-> {'PASS' if crash < -0.5 else 'CHECK'}")
    # 4) gas monotonic
    _, _, na, _, _ = backtest(pools, st, sc, 24, 0.0)
    _, _, nb, _, _ = backtest(pools, st, sc, 24, 50.0)
    print(f"  [4] gas monotonic {na.mean():.4f}>{nb.mean():.4f} -> {'PASS' if na.mean()>nb.mean() else 'FAIL'}")
    print("SELFTEST done.")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    elif "--analyze" in sys.argv:
        analyze()
    elif "--run" in sys.argv:
        mt = int(sys.argv[sys.argv.index("--max-tokens") + 1]) if "--max-tokens" in sys.argv else 90
        harvest(mt); analyze()
    else:
        print("use --selftest | --run [--max-tokens M] | --analyze")
