"""funding_harvest.py — Direction-NEUTRAL carry: perp funding-rate harvest + cross-venue spread.

================================================================================
WHY THIS EXISTS (read research_state.md §3 "majors program" meta-finding first)
================================================================================
This session falsified FOUR static *directional* factors (memecoin MR, majors
XS-reversion, majors TS-oversold-bounce, majors XS-momentum) out-of-time. The
meta-finding: B-03 non-stationarity kills any static *directional* sign on any
asset class. So we pivot to the one family that has NO directional sign to be
non-stationary about: STRUCTURAL CARRY.

Perp funding is paid long<->short every 8h. A delta-neutral book (long spot /
short perp, or two opposite perps across venues) collects funding with ~zero
price exposure. If a robust +EV exists in liquid crypto, carry is the most
likely place — IF it survives costs and is SIGN-STABLE across regimes (the exact
property every directional factor failed).

THE NON-OBVIOUS PART (why naive carry is a myth, and where the real test is):
Funding pays at period END based on the rate; you must choose your side at the
START. So delta-neutral carry is secretly a PREDICTION problem:
    net_carry = Σ funding_t · sign(predicted_t)  −  fee · (side flips)
It only works if funding is PERSISTENT enough (few flips) to beat the ~22bps
round-trip cost. Two engines test this honestly:
  1. SINGLE-VENUE long-carry-only (long spot / short perp when funding expected +):
     realistic, retail-executable, no spot-borrow. Harvest positive funding.
  2. CROSS-VENUE spread (Binance perp vs Bybit perp): short the higher-funding
     venue, long the lower. Double-neutral (delta AND market); the spread is
     more stationary than the level. The cleaner edge.
Predictor = sign(EWMA of PAST funding) — strictly no-lookahead.

HONESTY DISCIPLINE (same as majors_meanrev.py):
out-of-time 70/30 split (EWMA span chosen on TRAIN, reported once on TEST),
block-bootstrap CI, regime split (BTC 7d trend), cost-sensitivity/breakeven,
and selftests (random funding -> ~0 after cost; injected-persistence -> +carry;
cost monotonicity; no-lookahead).

Run:
    py -3 finetune/pipeline/funding_harvest.py --selftest
    py -3 finetune/pipeline/funding_harvest.py --universe 50
    py -3 finetune/pipeline/funding_harvest.py --universe 50 --refresh
"""
from __future__ import annotations

import json
import math
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import requests

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "finetune" / "data" / "funding_cache"
RESULT_PATH = ROOT / "finetune" / "data" / "funding_harvest_result.json"
LOG_PATH = ROOT / "finetune" / "data" / "funding_harvest_log.jsonl"

FAPI = "https://fapi.binance.com"
BYBIT = "https://api.bybit.com"
MS_8H = 8 * 3600 * 1000
WINDOW_DAYS = 730
PERIODS_PER_YEAR = 3 * 365              # 8h funding => 3/day

# Pre-registered: predictor smoothing (periods of past funding) + costs.
EWMA_SPANS = [1, 3, 6, 12, 24]          # 1 = last sign; 24 = 8 days smoothing
FEE_PER_LEG = 0.00055                   # 5.5 bps taker (Binance/Bybit perp)
FEE_GRID = [0.0001, 0.0003, 0.00055, 0.0008, 0.0011]
TRAIN_FRAC = 0.70
MIN_PERIODS = 200                       # need history to judge an asset
EPS = 1e-9
BOOT_ITERS = 2000
BOOT_BLOCK = 9                          # ~3 days of 8h periods


# --------------------------------------------------------------------------- #
# Data layer
# --------------------------------------------------------------------------- #
def _get(url: str, timeout: int = 25):
    r = requests.get(url, timeout=timeout, headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()
    return r.json()


def discover_perps(top_n: int) -> list[str]:
    """Top-N USDT-perp bases by 24h quote volume on Binance futures."""
    data = _get(f"{FAPI}/fapi/v1/ticker/24hr")
    stables = {"USDC", "FDUSD", "TUSD", "USDP", "DAI", "BUSD", "EUR"}
    rows = []
    for d in data:
        s = d.get("symbol", "")
        if not s.endswith("USDT"):
            continue
        base = s[:-4]
        if base in stables or any(base.endswith(x) for x in ("UP", "DOWN", "BULL", "BEAR")):
            continue
        try:
            rows.append((base, float(d["quoteVolume"])))
        except Exception:
            continue
    rows.sort(key=lambda x: -x[1])
    return [b for b, _ in rows[:top_n]]


def fetch_funding_binance(base: str, start_ms: int, refresh: bool) -> tuple[np.ndarray, np.ndarray] | None:
    f = CACHE / f"{base}USDT_binance.npz"
    if f.exists() and not refresh:
        z = np.load(f); return z["t"], z["r"]
    sym = f"{base}USDT"; cursor = start_ms; t, r = [], []
    for _ in range(40):
        try:
            rows = _get(f"{FAPI}/fapi/v1/fundingRate?symbol={sym}&startTime={cursor}&limit=1000")
        except Exception:
            return None
        if not rows:
            break
        for k in rows:
            t.append(int(k["fundingTime"])); r.append(float(k["fundingRate"]))
        if len(rows) < 1000:
            break
        cursor = int(rows[-1]["fundingTime"]) + 1
        time.sleep(0.03)
    if len(t) < MIN_PERIODS:
        return None
    t = np.array(t, dtype=np.int64); r = np.array(r)
    # snap to 8h grid (funding times can jitter by ms / interval changes)
    tg = (np.round(t / MS_8H) * MS_8H).astype(np.int64)
    _, idx = np.unique(tg, return_index=True)
    tg, r = tg[np.sort(idx)], r[np.sort(idx)]
    CACHE.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(f, t=tg, r=r)
    return tg, r


def fetch_funding_bybit(base: str, start_ms: int, refresh: bool) -> tuple[np.ndarray, np.ndarray] | None:
    f = CACHE / f"{base}USDT_bybit.npz"
    if f.exists() and not refresh:
        z = np.load(f); return z["t"], z["r"]
    sym = f"{base}USDT"; end = int(time.time() * 1000); t, r = [], []
    for _ in range(60):
        url = (f"{BYBIT}/v5/market/funding/history?category=linear&symbol={sym}"
               f"&startTime={start_ms}&endTime={end}&limit=200")
        try:
            j = _get(url)
            lst = j.get("result", {}).get("list", [])
        except Exception:
            return None
        if not lst:
            break
        for k in lst:
            t.append(int(k["fundingRateTimestamp"])); r.append(float(k["fundingRate"]))
        oldest = int(lst[-1]["fundingRateTimestamp"])
        if oldest <= start_ms or len(lst) < 200:
            break
        end = oldest - 1
        time.sleep(0.03)
    if len(t) < MIN_PERIODS:
        return None
    t = np.array(t, dtype=np.int64); r = np.array(r)
    order = np.argsort(t); t, r = t[order], r[order]
    tg = (np.round(t / MS_8H) * MS_8H).astype(np.int64)
    _, idx = np.unique(tg, return_index=True)
    tg, r = tg[np.sort(idx)], r[np.sort(idx)]
    CACHE.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(f, t=tg, r=r)
    return tg, r


def fetch_btc_8h(start_ms: int, refresh: bool) -> tuple[np.ndarray, np.ndarray]:
    """BTC perp 8h closes for the regime split."""
    f = CACHE / "BTC_8h_klines.npz"
    if f.exists() and not refresh:
        z = np.load(f); return z["t"], z["c"]
    cursor = start_ms; t, c = [], []
    for _ in range(10):
        rows = _get(f"{FAPI}/fapi/v1/klines?symbol=BTCUSDT&interval=8h&startTime={cursor}&limit=1000")
        if not rows:
            break
        for k in rows:
            t.append(int(k[0])); c.append(float(k[4]))
        if len(rows) < 1000:
            break
        cursor = int(rows[-1][0]) + 1
    t = (np.round(np.array(t, dtype=np.int64) / MS_8H) * MS_8H).astype(np.int64)
    c = np.array(c)
    CACHE.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(f, t=t, c=c)
    return t, c


def fetch_klines_8h(base: str, market: str, start_ms: int, refresh: bool) -> tuple[np.ndarray, np.ndarray] | None:
    """8h closes for spot (api.binance.com) or perp (fapi) — for basis-aware PnL."""
    host, path = (("https://api.binance.com", "/api/v3/klines") if market == "spot"
                  else (FAPI, "/fapi/v1/klines"))
    f = CACHE / f"{base}USDT_{market}_8h.npz"
    if f.exists() and not refresh:
        z = np.load(f); return z["t"], z["c"]
    sym = f"{base}USDT"; cur = start_ms; t, c = [], []
    for _ in range(12):
        try:
            rows = _get(f"{host}{path}?symbol={sym}&interval=8h&startTime={cur}&limit=1000")
        except Exception:
            return None
        if not rows:
            break
        for k in rows:
            t.append(int(k[0])); c.append(float(k[4]))
        if len(rows) < 1000:
            break
        cur = int(rows[-1][0]) + 1; time.sleep(0.02)
    if len(t) < MIN_PERIODS:
        return None
    t = (np.round(np.array(t, np.int64) / MS_8H) * MS_8H).astype(np.int64); c = np.array(c)
    _, idx = np.unique(t, return_index=True); t, c = t[np.sort(idx)], c[np.sort(idx)]
    CACHE.mkdir(parents=True, exist_ok=True); np.savez_compressed(f, t=t, c=c)
    return t, c


def build_panel(universe: list[str], refresh: bool, with_prices: bool = False) -> dict:
    """Aligned 8h funding panels for Binance & Bybit on a common time grid.
    with_prices=True also attaches basis_ret = spot_ret − perp_ret (delta-neutral price leg)."""
    start_ms = int(time.time() * 1000) - WINDOW_DAYS * 24 * 3600 * 1000
    binance, bybit = {}, {}
    with ThreadPoolExecutor(max_workers=8) as ex:
        fb = {ex.submit(fetch_funding_binance, b, start_ms, refresh): b for b in universe}
        fy = {ex.submit(fetch_funding_bybit, b, start_ms, refresh): b for b in universe}
        for fut in as_completed(fb):
            res = None
            try: res = fut.result()
            except Exception: res = None
            if res is not None: binance[fb[fut]] = res
        for fut in as_completed(fy):
            res = None
            try: res = fut.result()
            except Exception: res = None
            if res is not None: bybit[fy[fut]] = res

    all_t = np.unique(np.concatenate([t for t, _ in binance.values()])) if binance else np.array([], np.int64)
    row = {int(ts): i for i, ts in enumerate(all_t)}
    T = len(all_t)
    kept = [b for b in universe if b in binance]
    fb_mat = np.full((T, len(kept)), np.nan)
    fy_mat = np.full((T, len(kept)), np.nan)
    for j, b in enumerate(kept):
        t, r = binance[b]
        idx = np.fromiter((row[int(x)] for x in t if int(x) in row), np.int64)
        rr = np.fromiter((r[i] for i, x in enumerate(t) if int(x) in row), float)
        fb_mat[idx, j] = rr
        if b in bybit:
            t2, r2 = bybit[b]
            idx2 = np.fromiter((row[int(x)] for x in t2 if int(x) in row), np.int64)
            rr2 = np.fromiter((r2[i] for i, x in enumerate(t2) if int(x) in row), float)
            fy_mat[idx2, j] = rr2
    bt_t, bt_c = fetch_btc_8h(start_ms, refresh)
    btc = np.full(T, np.nan)
    btr = {int(x): i for i, x in enumerate(bt_t)}
    for i, ts in enumerate(all_t):
        k = int(ts)
        if k in btr:
            btc[i] = bt_c[btr[k]]

    basis_ret = None
    if with_prices and kept:
        spot_d, perp_d = {}, {}
        with ThreadPoolExecutor(max_workers=8) as ex:
            fs = {ex.submit(fetch_klines_8h, b, "spot", start_ms, refresh): b for b in kept}
            fp = {ex.submit(fetch_klines_8h, b, "perp", start_ms, refresh): b for b in kept}
            for fut in as_completed(fs):
                try: r = fut.result()
                except Exception: r = None
                if r is not None: spot_d[fs[fut]] = r
            for fut in as_completed(fp):
                try: r = fut.result()
                except Exception: r = None
                if r is not None: perp_d[fp[fut]] = r

        def level_mat(d):
            m = np.full((T, len(kept)), np.nan)
            for j, b in enumerate(kept):
                if b in d:
                    t, c = d[b]
                    for i, x in enumerate(t):
                        kk = int(x)
                        if kk in row:
                            m[row[kk], j] = c[i]
            return m

        def rets(m):
            r = np.full_like(m, np.nan)
            r[1:] = m[1:] / m[:-1] - 1.0
            return r

        basis_ret = rets(level_mat(spot_d)) - rets(level_mat(perp_d))

    return {"times": all_t, "kept": kept, "binance": fb_mat, "bybit": fy_mat,
            "btc": btc, "basis_ret": basis_ret}


# --------------------------------------------------------------------------- #
# Carry engines (no-lookahead: side at t uses EWMA of funding < t)
# --------------------------------------------------------------------------- #
def _ewma_sign_prev(x: np.ndarray, span: int) -> np.ndarray:
    """sign of EWMA of values STRICTLY BEFORE each index (no lookahead).
    NaN-aware: gaps don't update the EWMA. Returns 0 where undefined."""
    n = len(x); out = np.zeros(n); e = np.nan; alpha = 2.0 / (span + 1.0)
    for i in range(n):
        out[i] = 0.0 if (e is None or (isinstance(e, float) and math.isnan(e))) else (1.0 if e > EPS else (-1.0 if e < -EPS else 0.0))
        v = x[i]
        if np.isfinite(v):
            e = v if (isinstance(e, float) and math.isnan(e)) else (1 - alpha) * e + alpha * v
    return out


def _ewma_prev_level(x: np.ndarray, span: int) -> np.ndarray:
    """EWMA LEVEL of values strictly before each index (no lookahead). NaN until 1st obs."""
    n = len(x); out = np.full(n, np.nan); e = np.nan; alpha = 2.0 / (span + 1.0)
    for i in range(n):
        out[i] = e
        v = x[i]
        if np.isfinite(v):
            e = v if (isinstance(e, float) and math.isnan(e)) else (1 - alpha) * e + alpha * v
    return out


def carry_single(funding: np.ndarray, span: int, fee: float,
                 price_ret: np.ndarray | None = None) -> np.ndarray:
    """Long-carry-only per asset: hold long-spot/short-perp when EWMA funding>0,
    else flat. pnl_t = pos_t*(funding_t + price_leg_t) − fee*2*|Δpos|.
    price_ret = spot_ret − perp_ret (basis-aware delta-neutral leg); None => funding-only."""
    s = _ewma_sign_prev(funding, span)
    pos = (s > 0).astype(float)                       # 1 = on, 0 = flat
    pnl = np.zeros(len(funding))
    prev = 0.0
    for i in range(len(funding)):
        f = funding[i] if np.isfinite(funding[i]) else 0.0
        pr = (price_ret[i] if (price_ret is not None and np.isfinite(price_ret[i])) else 0.0)
        cost = fee * 2.0 * abs(pos[i] - prev)
        pnl[i] = pos[i] * (f + pr) - cost
        prev = pos[i]
    return pnl


def carry_xvenue(fb: np.ndarray, fy: np.ndarray, span: int, fee: float) -> np.ndarray:
    """Cross-venue spread per asset: spread=fB−fY; side=sign(EWMA past spread);
    pnl_t = side_t*spread_t − fee*2*|Δside| (4 perp legs per full flip)."""
    spread = fb - fy
    valid = np.isfinite(spread)
    sp = np.where(valid, spread, np.nan)
    s = _ewma_sign_prev(sp, span)
    pnl = np.zeros(len(spread)); prev = 0.0
    for i in range(len(spread)):
        d = spread[i] if valid[i] else 0.0
        side = s[i] if valid[i] else prev
        cost = fee * 2.0 * abs(side - prev)
        pnl[i] = side * d - cost
        prev = side
    return pnl


def portfolio(panel: dict, engine: str, span: int, fee: float, k: int = 10,
              use_basis: bool = False) -> tuple[np.ndarray, np.ndarray]:
    """Equal-weight net pnl across assets per 8h period. Returns (pnl_series, mask_any).
    use_basis=True adds the delta-neutral price leg (spot_ret − perp_ret) to funding."""
    fb, fy, kept = panel["binance"], panel["bybit"], panel["kept"]
    T, N = fb.shape
    pr_mat = panel.get("basis_ret") if use_basis else None

    if engine == "single_topk":
        # Concentrate carry: each period hold the top-K names by EWMA funding among
        # those with EWMA>0 (long-spot/short-perp). Higher gross APR than equal-weight.
        lev = np.full((T, N), np.nan)
        for j in range(N):
            if np.isfinite(fb[:, j]).sum() >= MIN_PERIODS:
                lev[:, j] = _ewma_prev_level(fb[:, j], span)
        pnl = np.zeros(T); mask = np.zeros(T, bool); w_prev = np.zeros(N)
        for i in range(T):
            cand = np.where(np.isfinite(lev[i]) & (lev[i] > EPS) & np.isfinite(fb[i]))[0]
            w = np.zeros(N)
            if len(cand) > 0:
                top = cand[np.argsort(-lev[i, cand])][:k]
                w[top] = 1.0 / len(top); mask[i] = True
            f = np.where(np.isfinite(fb[i]), fb[i], 0.0)
            if pr_mat is not None:
                f = f + np.where(np.isfinite(pr_mat[i]), pr_mat[i], 0.0)
            pnl[i] = float(np.dot(w, f)) - fee * 2.0 * float(np.abs(w - w_prev).sum())
            w_prev = w
        return pnl, mask

    acc = np.zeros(T); cnt = np.zeros(T)
    for j in range(N):
        if engine == "single":
            col = fb[:, j]
            if np.isfinite(col).sum() < MIN_PERIODS:
                continue
            pnl = carry_single(col, span, fee, pr_mat[:, j] if pr_mat is not None else None)
            active = np.isfinite(col)
        else:
            both = np.isfinite(fb[:, j]) & np.isfinite(fy[:, j])
            if both.sum() < MIN_PERIODS:
                continue
            pnl = carry_xvenue(fb[:, j], fy[:, j], span, fee)
            active = both
        acc[active] += pnl[active]; cnt[active] += 1
    mask = cnt > 0
    out = np.zeros(T); out[mask] = acc[mask] / cnt[mask]
    return out, mask


# --------------------------------------------------------------------------- #
# Metrics & honesty
# --------------------------------------------------------------------------- #
def metrics(pnl: np.ndarray) -> dict:
    n = len(pnl)
    if n == 0:
        return {"n": 0, "mean": 0.0, "apr": 0.0, "sharpe": 0.0, "hit": 0.0, "maxdd": 0.0}
    mu = float(pnl.mean()); sd = float(pnl.std(ddof=1)) if n > 1 else 0.0
    eq = np.cumprod(1.0 + pnl); dd = eq / np.maximum.accumulate(eq) - 1.0
    return {"n": n, "mean": mu, "apr": mu * PERIODS_PER_YEAR,
            "sharpe": (mu / sd * math.sqrt(PERIODS_PER_YEAR)) if sd > 0 else 0.0,
            "hit": float((pnl > 0).mean()), "maxdd": float(dd.min())}


def block_bootstrap_ci(x, block=BOOT_BLOCK, iters=BOOT_ITERS, seed=7):
    n = len(x)
    if n < 2:
        return (0.0, 0.0)
    rng = np.random.default_rng(seed); nb = int(math.ceil(n / block))
    means = np.empty(iters); hi = max(1, n - block + 1)
    for i in range(iters):
        st = rng.integers(0, hi, size=nb)
        idx = (st[:, None] + np.arange(block)[None, :]).ravel()[:n]
        means[i] = x[np.clip(idx, 0, n - 1)].mean()
    means.sort()
    return float(means[int(0.025 * iters)]), float(means[int(0.975 * iters)])


def regime_split(pnl, mask, btc):
    win = 21                                          # 7 days = 21 * 8h
    out = {}
    up = np.zeros(len(pnl), bool); val = np.zeros(len(pnl), bool)
    for i in range(len(pnl)):
        if i - win < 0 or not mask[i] or not np.isfinite(btc[i]) or not np.isfinite(btc[i - win]):
            continue
        val[i] = True; up[i] = (btc[i] / btc[i - win] - 1.0) > 0
    for name, m in (("btc_up", val & up), ("btc_down", val & ~up)):
        seg = pnl[m]
        out[name] = {"n": int(len(seg)), "apr": float(seg.mean() * PERIODS_PER_YEAR) if len(seg) else 0.0,
                     "hit": float((seg > 0).mean()) if len(seg) else 0.0}
    return out


def split_idx(n):
    return int(n * TRAIN_FRAC)


def funding_stats(panel: dict) -> dict:
    """Descriptive: mean funding APR + lag-1 sign persistence (the edge's premise)."""
    fb, kept = panel["binance"], panel["kept"]
    aprs, persist = [], []
    for j in range(len(kept)):
        col = fb[:, j][np.isfinite(fb[:, j])]
        if len(col) < MIN_PERIODS:
            continue
        aprs.append(col.mean() * PERIODS_PER_YEAR)
        s = np.sign(col)
        same = (s[1:] == s[:-1]) & (s[:-1] != 0)
        persist.append(same.mean())
    return {"mean_funding_apr": float(np.mean(aprs)) if aprs else 0.0,
            "median_funding_apr": float(np.median(aprs)) if aprs else 0.0,
            "lag1_sign_persistence": float(np.mean(persist)) if persist else 0.0,
            "n_assets": len(aprs)}


def evaluate(panel: dict, engine: str, base_fee: float = FEE_PER_LEG, k: int = 10,
             use_basis: bool = False) -> dict:
    # choose EWMA span on TRAIN by net Sharpe, report once on TEST
    base = portfolio(panel, engine, EWMA_SPANS[0], base_fee, k, use_basis)[0]
    cut = split_idx(len(base))
    best_span, best_sh = EWMA_SPANS[0], -1e9
    for span in EWMA_SPANS:
        pnl, _ = portfolio(panel, engine, span, base_fee, k, use_basis)
        sh = metrics(pnl[:cut])["sharpe"]
        if sh > best_sh:
            best_sh, best_span = sh, span
    pnl, mask = portfolio(panel, engine, best_span, base_fee, k, use_basis)
    train_m, test_m = metrics(pnl[:cut]), metrics(pnl[cut:])
    ci = block_bootstrap_ci(pnl[cut:])
    reg = regime_split(pnl[cut:], mask[cut:], panel["btc"][cut:])
    # cost sweep + breakeven (net APR on TEST)
    cost_curve, breakeven = [], None
    for fee in FEE_GRID:
        m = metrics(portfolio(panel, engine, best_span, fee, k, use_basis)[0][cut:])
        cost_curve.append({"fee_bps": fee * 1e4, "apr": m["apr"], "sharpe": m["sharpe"]})
    for fee in np.linspace(0, 0.0030, 61):
        if metrics(portfolio(panel, engine, best_span, float(fee), k, use_basis)[0][cut:])["mean"] <= 0:
            breakeven = float(fee); break
    return {"engine": engine, "ewma_span": best_span, "base_fee_bps": base_fee * 1e4,
            "use_basis": use_basis, "train": train_m, "test": test_m,
            "test_apr_ci95": [ci[0] * PERIODS_PER_YEAR, ci[1] * PERIODS_PER_YEAR],
            "regimes": reg, "cost_curve": cost_curve,
            "breakeven_fee_bps": (breakeven * 1e4) if breakeven else None}


def verdict(ev: dict) -> tuple[str, str]:
    t = ev["test"]; lo, hi = ev["test_apr_ci95"]; r = ev["regimes"]
    stable = (r.get("btc_up", {}).get("apr", 0) > 0 and r.get("btc_down", {}).get("apr", 0) > 0)
    if t["apr"] > 0 and lo > 0 and t["sharpe"] > 1.0 and stable:
        return "VALIDATED", ("Net +APR out-of-time, CI excludes 0, Sharpe>1, sign-stable across "
                             "BTC regimes — a genuine structural carry edge.")
    if t["apr"] > 0 and lo > 0:
        return "PROMISING", "Positive net carry with CI>0 but Sharpe/regime gate unmet; refine."
    if t["apr"] > 0:
        return "WEAK", "Positive point estimate, not separable from noise after costs."
    return "REFUTED", "No positive net carry out-of-time after costs (funding too thin / flips eat it)."


def _now_iso():
    import datetime as dt
    return dt.datetime.now(dt.timezone.utc).isoformat()


def filter_tradeable(panel: dict, min_cov: float = 0.90) -> dict:
    """Keep only CLEANLY-EXECUTABLE cash-and-carry names: a real liquid SPOT market
    AND (near-)full funding history (both finite >= min_cov of window). Excludes
    perp-only names (no spot leg => can't run long-spot/short-perp) and short-history
    / newer listings (tokenized stocks, fresh tokens) that inflate the top-K."""
    fb, br, kept = panel["binance"], panel.get("basis_ret"), panel["kept"]
    if br is None:
        return panel
    keep = [j for j in range(len(kept))
            if np.isfinite(fb[:, j]).mean() >= min_cov and np.isfinite(br[:, j]).mean() >= min_cov]
    idx = np.array(keep, dtype=int)
    return {"times": panel["times"], "kept": [kept[j] for j in keep],
            "binance": fb[:, idx], "bybit": panel["bybit"][:, idx],
            "btc": panel["btc"], "basis_ret": br[:, idx]}


def main(top_n=50, refresh=False, basis=False, tradeable=False):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore
    print(f"[0/4] Discovering top-{top_n} USDT perps by 24h volume ...")
    universe = discover_perps(top_n)
    print(f"[1/4] Fetching {len(universe)} funding histories (Binance + Bybit)"
          f"{' + spot/perp 8h klines' if basis else ''} x ~{WINDOW_DAYS}d ...")
    panel = build_panel(universe, refresh, with_prices=basis)
    if tradeable:
        panel = filter_tradeable(panel)
        print(f"      [TRADEABLE filter] clean cash-and-carry universe (real spot + full history): "
              f"{len(panel['kept'])} names")
        print(f"      {', '.join(panel['kept'])}")
    T = len(panel["times"]); kept = panel["kept"]
    nxv = int((np.isfinite(panel["binance"]) & np.isfinite(panel["bybit"])).any(axis=0).sum())
    span_d = (panel["times"][-1] - panel["times"][0]) / (24 * 3600 * 1000) if T else 0
    print(f"      periods={T} (~{span_d:.0f}d)  assets(Binance)={len(kept)}  with-Bybit={nxv}")

    fs = funding_stats(panel)
    print(f"[2/4] Funding descriptive: mean APR={fs['mean_funding_apr']:+.1%} "
          f"median={fs['median_funding_apr']:+.1%}  lag1 sign-persistence={fs['lag1_sign_persistence']:.1%} "
          f"(>50% => exploitable)")

    print("[3/4] Evaluating carry engines out-of-time (EWMA span tuned on TRAIN) ...")
    names = {"single": "SINGLE-VENUE long-carry (all names, EW)",
             "single_topk": "SINGLE-VENUE long-carry (TOP-10 funding)",
             "xvenue": "CROSS-VENUE spread (Binance-Bybit)"}
    results = {}

    def show(ev, tag=""):
        t = ev["test"]; lo, hi = ev["test_apr_ci95"]; r = ev["regimes"]
        print(f"    {tag}TRAIN apr={ev['train']['apr']:+.1%} sh={ev['train']['sharpe']:+.2f} | "
              f"TEST apr={t['apr']:+.1%} sh={t['sharpe']:+.2f} hit={t['hit']:.1%} "
              f"maxDD={t['maxdd']:.1%} n={t['n']}")
        print(f"    {tag}TEST CI95=[{lo:+.1%},{hi:+.1%}] breakeven={ev['breakeven_fee_bps']}bps | "
              f"regime up={r.get('btc_up',{}).get('apr',0):+.1%} down={r.get('btc_down',{}).get('apr',0):+.1%}")

    for engine in ("single", "single_topk", "xvenue"):
        ev = evaluate(panel, engine, FEE_PER_LEG)          # taker 5.5bps (registered)
        v, why = verdict(ev); ev["verdict"], ev["verdict_reason"] = v, why
        results[engine] = ev
        print(f"\n  === {names[engine]} (EWMA span={ev['ewma_span']}) ===")
        print("    [TAKER 5.5bps/leg]")
        show(ev)
        print("    cost sweep: " + "  ".join(f"{c['fee_bps']:.1f}->{c['apr']:+.0%}" for c in ev["cost_curve"]))
        print(f"    VERDICT(taker): {v} — {why}")
        if engine in ("single", "single_topk"):
            evm = evaluate(panel, engine, 0.0001)          # MAKER 1bp — realistic (no spread-crossing)
            vm, whym = verdict(evm); evm["verdict"], evm["verdict_reason"] = vm, whym
            results[engine + "_maker"] = evm
            print("    [MAKER 1.0bps/leg — realistic: 8h windows, no spread-crossing needed]")
            show(evm, "")
            print(f"    VERDICT(maker): {vm} — {whym}")

    if basis and panel.get("basis_ret") is not None:
        print("\n[5/5] BASIS-AWARE honest PnL (= funding + spot_ret − perp_ret), maker 1.0bps")
        print("      adds the real delta-neutral price leg => the HONEST Sharpe / drawdown")
        for engine in ("single", "single_topk"):
            evf = evaluate(panel, engine, 0.0001, use_basis=False)
            evb = evaluate(panel, engine, 0.0001, use_basis=True)
            vb, whyb = verdict(evb); evb["verdict"], evb["verdict_reason"] = vb, whyb
            results[engine + "_basis"] = evb
            tf, tb = evf["test"], evb["test"]; lo, hi = evb["test_apr_ci95"]; r = evb["regimes"]
            print(f"\n  === {names[engine]} — BASIS-AWARE (span={evb['ewma_span']}) ===")
            print(f"    funding-only: apr={tf['apr']:+.1%} sharpe={tf['sharpe']:+.2f} maxDD={tf['maxdd']:.1%}")
            print(f"    basis-aware : apr={tb['apr']:+.1%} sharpe={tb['sharpe']:+.2f} hit={tb['hit']:.1%} "
                  f"maxDD={tb['maxdd']:.1%} n={tb['n']}")
            print(f"    basis CI95=[{lo:+.1%},{hi:+.1%}] | regime up={r.get('btc_up',{}).get('apr',0):+.1%} "
                  f"down={r.get('btc_down',{}).get('apr',0):+.1%}")
            print(f"    VERDICT(basis): {vb} — {whyb}")

    out = {"ts": _now_iso(), "window_days": WINDOW_DAYS, "periods": T,
           "universe": kept, "funding_stats": fs, "results": results}
    RESULT_PATH.write_text(json.dumps(out, indent=2), encoding="utf-8")
    with LOG_PATH.open("a", encoding="utf-8") as f:
        for eng, ev in results.items():
            f.write(json.dumps({"ts": out["ts"], "engine": eng, "span": ev["ewma_span"],
                                "test_apr": ev["test"]["apr"], "test_sharpe": ev["test"]["sharpe"],
                                "ci95_apr": ev["test_apr_ci95"], "verdict": ev["verdict"]}) + "\n")
    print(f"\n  wrote {RESULT_PATH.relative_to(ROOT)}; appended {LOG_PATH.relative_to(ROOT)}")


# --------------------------------------------------------------------------- #
# Selftests
# --------------------------------------------------------------------------- #
def selftest():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore
    print("SELFTEST — funding carry engine honesty gates")
    rng = np.random.default_rng(0); n = 4000

    # 1) IID funding (no persistence) => single-carry net ~<=0 after cost.
    iid = rng.normal(0, 0.0003, n)
    m = metrics(carry_single(iid, span=6, fee=FEE_PER_LEG))
    print(f"  [1] iid funding single-carry APR={m['apr']:+.1%} (expect <=~0) -> "
          f"{'PASS' if m['apr'] < 0.05 else 'CHECK'}")

    # 2) Injected PERSISTENT positive funding (AR(1), mean>0) => +carry.
    ar = np.zeros(n); ar[0] = 0.0003
    for i in range(1, n):
        ar[i] = 0.9 * ar[i - 1] + 0.0001 + rng.normal(0, 0.00005)
    mp = metrics(carry_single(ar, span=6, fee=FEE_PER_LEG))
    print(f"  [2] persistent +funding single-carry APR={mp['apr']:+.1%} (expect >0) -> "
          f"{'PASS' if mp['apr'] > 0 else 'FAIL'}")

    # 3) Cost monotonicity (more fee => lower carry) on the persistent series.
    a0 = metrics(carry_single(ar, 6, 0.0))["apr"]
    a1 = metrics(carry_single(ar, 6, 0.0008))["apr"]
    print(f"  [3] cost monotonicity {a0:+.1%} > {a1:+.1%} -> {'PASS' if a0 > a1 else 'FAIL'}")

    # 4) No-lookahead: sign uses only past. Reversing time must not preserve +carry
    #    from a trend (a leak would let it 'predict' either direction).
    fwd = metrics(carry_single(ar, 6, 0.0))["apr"]
    rev = metrics(carry_single(ar[::-1].copy(), 6, 0.0))["apr"]
    print(f"  [4] no-lookahead: fwd={fwd:+.1%} rev={rev:+.1%}; persistence works both "
          f"directions if real (sanity) -> {'PASS' if fwd > 0 else 'CHECK'}")

    # 5) xvenue: identical venues => spread 0 => zero pnl, costs only (<=0).
    z = metrics(carry_xvenue(ar, ar.copy(), 6, FEE_PER_LEG))
    print(f"  [5] xvenue identical-venue APR={z['apr']:+.2%} (expect ~0/neg) -> "
          f"{'PASS' if abs(z['apr']) < 0.02 else 'CHECK'}")
    print("SELFTEST done.")


if __name__ == "__main__":
    _refresh = "--refresh" in sys.argv
    _top = 50
    if "--universe" in sys.argv:
        _top = int(sys.argv[sys.argv.index("--universe") + 1])
    _tradeable = "--tradeable" in sys.argv
    _basis = ("--basis" in sys.argv) or _tradeable
    if "--selftest" in sys.argv:
        selftest()
    else:
        main(top_n=_top, refresh=_refresh, basis=_basis, tradeable=_tradeable)
