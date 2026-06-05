"""majors_meanrev.py — Cross-sectional (market-NEUTRAL) mean-reversion on liquid crypto majors.

================================================================================
WHY THIS EXISTS  (read research_state.md §3 H-03, B-03, B-08, §10 #1/#2 first)
================================================================================
The project's ONE real edge is mean-reversion (H-03). It failed its first
out-of-time regime test for exactly one reason: it is long-only, so its
uncontrolled market beta sank absolute EV in a down tape (-0.47%). BUT the
*relative* reversion effect beat base by +1.1pp in BOTH regimes — it held its
sign across the non-stationarity wall (B-03) that sign-flipped every other
factor. That sign-stability is the most valuable property in the whole log.

This module converts that latent edge into a tradeable one with two moves that
attack the two central walls at once:

  1. DOLLAR-NEUTRAL CONSTRUCTION (long recent losers - short recent winners,
     cross-sectional). Cancels market beta => directly fixes the H-03 failure
     mode and is structurally regime-robust (counters B-03).
  2. LIQUID MAJORS, deep history, large N. Stationary assets where short-horizon
     reversal is a documented effect; huge sample kills the small-N illusion
     (counters B-08). And unlike memecoins, the short leg is actually executable
     (deep perps / real borrow) -> the neutral construction is realistic.

This is research_state §10 #1 (market-neutral) + #2 (majors) fused into one
decisive, self-contained test. No wallets, no LLM, no latency race.

================================================================================
HONESTY DISCIPLINE (this is the work, not an add-on — Appendix B lessons)
================================================================================
- Out-of-TIME holdout: params chosen on first 70% of the timeline, reported once
  on the last 30%. (Lesson 3.)
- Pre-registered grid (look/hold/construction); we do NOT peek at test to pick.
- No-lookahead BY CONSTRUCTION: weights at t use returns over [t-look, t];
  pnl is realized over (t, t+hold]. A +hold leakage-shift selftest proves it.
- N-growth curve: does cumulative mean net return stabilize +ve or decay to 0?
  (Lesson 2 — catches small-sample illusions.)
- Block-bootstrap 95% CI on mean net return (respects autocorrelation).
- Permutation null: shuffle forward returns across assets within each rebalance;
  real edge must sit in the tail. (Overfit / leakage detector.)
- Regime split: TEST partitioned by BTC 7d trend; a neutral edge should be
  sign-stable across regimes — that is the whole thesis, and the kill criterion.
- Cost sensitivity: net Sharpe vs fee; report the breakeven fee. Short-horizon
  reversal usually dies on costs — that is the realistic killer we hunt for.

Run:
    py -3 finetune/pipeline/majors_meanrev.py            # full backtest
    py -3 finetune/pipeline/majors_meanrev.py --selftest # correctness checks
    py -3 finetune/pipeline/majors_meanrev.py --refresh  # ignore cache, refetch
"""
from __future__ import annotations

import json
import math
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import warnings

import numpy as np
import requests
from numpy.lib.stride_tricks import sliding_window_view

# --------------------------------------------------------------------------- #
# Config (PRE-REGISTERED — fixed before looking at any test result)
# --------------------------------------------------------------------------- #
ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "finetune" / "data" / "majors_cache"
RESULT_PATH = ROOT / "finetune" / "data" / "majors_meanrev_result.json"
LOG_PATH = ROOT / "finetune" / "data" / "majors_meanrev_log.jsonl"

HOSTS = ["https://api.binance.com", "https://data-api.binance.vision"]
INTERVAL = "1h"
MS_PER_HOUR = 3_600_000
WINDOW_DAYS = 730                       # ~2y => multi-regime (bull/bear/chop)
HOURS_PER_YEAR = 24 * 365

# ~45 liquid USDT pairs. Names with short history are auto-trimmed by coverage.
UNIVERSE = [
    "BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "AVAX", "DOGE", "LINK", "DOT",
    "LTC", "BCH", "TRX", "ATOM", "UNI", "ETC", "XLM", "FIL", "HBAR", "APT",
    "NEAR", "ARB", "OP", "INJ", "SUI", "SEI", "TIA", "AAVE", "MKR", "ALGO",
    "SAND", "MANA", "AXS", "GALA", "CHZ", "GRT", "LDO", "IMX", "STX", "RUNE",
    "THETA", "CRV", "SNX", "EGLD", "FTM",
]

# Pre-registered hyper-parameter grid (selected on TRAIN only).
LOOKBACKS = [1, 2, 3, 6, 12, 24]        # hours of trailing return = the signal
HOLDS = [1, 2, 3, 6, 12, 24]            # hours held = rebalance period
# Momentum lives at daily/weekly horizons (low turnover => costs manageable);
# short-horizon hourly is reversion territory, which `backtest` already refuted.
MOM_LOOKBACKS = [24, 72, 168, 336, 720]  # 1d, 3d, 7d, 14d, 30d
MOM_HOLDS = [24, 72, 168]                # 1d, 3d, 7d
CONSTRUCTIONS = ["continuous", "decile"]
DECILE_Q = 0.30                         # top/bottom 30% for the decile variant

BASE_FEE = 0.0005                       # 5 bps per side (Binance taker-ish, majors)
FEE_GRID = [0.0001, 0.0002, 0.0005, 0.00075, 0.0010]
MIN_ASSETS = 6                          # need a real cross-section to be neutral
MIN_TRAIN_REBALANCES = 150              # ignore configs that barely trade in-sample
TRAIN_FRAC = 0.70
COVERAGE_MIN = 0.40                     # keep a symbol if >=40% of window has data

PERM_ITERS = 500
BOOT_ITERS = 2000
BOOT_BLOCK = 8                          # moving-block length (hours of autocorr)


# --------------------------------------------------------------------------- #
# Data layer — Binance spot klines, paginated, cached to .npz per symbol
# --------------------------------------------------------------------------- #
def _fetch_symbol(symbol: str, start_ms: int, refresh: bool = False) -> tuple[np.ndarray, np.ndarray] | None:
    """Return (open_times_ms, closes) for SYMBOL+USDT, or None if unavailable."""
    pair = f"{symbol}USDT"
    cache_f = CACHE / f"{pair}_{INTERVAL}.npz"
    if cache_f.exists() and not refresh:
        z = np.load(cache_f)
        return z["t"], z["c"]

    times: list[int] = []
    closes: list[float] = []
    cursor = start_ms
    host_i = 0
    guard = 0
    while guard < 400:
        guard += 1
        url = (f"{HOSTS[host_i]}/api/v3/klines?symbol={pair}"
               f"&interval={INTERVAL}&startTime={cursor}&limit=1000")
        try:
            r = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
            if r.status_code != 200:
                host_i = (host_i + 1) % len(HOSTS)
                if host_i == 0:
                    return None
                continue
            rows = r.json()
        except Exception:
            host_i = (host_i + 1) % len(HOSTS)
            if host_i == 0:
                time.sleep(0.5)
            continue
        if not rows:
            break
        for k in rows:
            times.append(int(k[0]))
            closes.append(float(k[4]))
        last = int(rows[-1][0])
        if len(rows) < 1000:
            break
        cursor = last + MS_PER_HOUR
        time.sleep(0.05)
    if len(times) < 200:
        return None
    t = np.array(times, dtype=np.int64)
    c = np.array(closes, dtype=np.float64)
    # de-dup & sort (defensive)
    order = np.argsort(t)
    t, c = t[order], c[order]
    uniq = np.concatenate(([True], np.diff(t) > 0))
    t, c = t[uniq], c[uniq]
    CACHE.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(cache_f, t=t, c=c)
    return t, c


# Stable/wrapped/leveraged bases to exclude from auto-discovered universes.
_STABLES = {"USDC", "FDUSD", "TUSD", "USDP", "DAI", "BUSD", "USTC", "EUR", "EURI",
            "AEUR", "GBP", "TRY", "BRL", "ARS", "PYUSD", "USD1", "XUSD", "WBTC",
            "WBETH", "BETH", "USDE"}


def discover_universe(top_n: int) -> list[str]:
    """Top-N liquid USDT bases by 24h quote volume (pre-registered ranking rule)."""
    last = None
    for host in HOSTS:
        try:
            r = requests.get(f"{host}/api/v3/ticker/24hr", timeout=30,
                             headers={"User-Agent": "Mozilla/5.0"})
            if r.status_code == 200:
                data = r.json()
                break
        except Exception as e:
            last = e
    else:
        raise RuntimeError(f"ticker/24hr failed: {last}")
    rows = []
    for d in data:
        s = d.get("symbol", "")
        if not s.endswith("USDT"):
            continue
        base = s[:-4]
        if base in _STABLES or any(base.endswith(x) for x in ("UP", "DOWN", "BULL", "BEAR")):
            continue
        try:
            rows.append((base, float(d["quoteVolume"])))
        except Exception:
            continue
    rows.sort(key=lambda x: -x[1])
    return [b for b, _ in rows[:top_n]]


def build_matrix(universe: list[str] | None = None,
                 refresh: bool = False) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """Fetch the universe and align to a [T, N] close-price matrix (NaN = missing)."""
    universe = universe or UNIVERSE
    start_ms = int(time.time() * 1000) - WINDOW_DAYS * 24 * MS_PER_HOUR
    series: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(_fetch_symbol, s, start_ms, refresh): s for s in universe}
        for fut in as_completed(futs):
            s = futs[fut]
            try:
                res = fut.result()
            except Exception:
                res = None
            if res is not None:
                series[s] = res

    if not series:
        raise RuntimeError("No symbols fetched — data layer failed.")

    # Master hourly time grid = union of all open times.
    all_t = np.unique(np.concatenate([t for t, _ in series.values()]))
    row = {int(ts): i for i, ts in enumerate(all_t)}
    T = len(all_t)

    kept: list[str] = []
    cols: list[np.ndarray] = []
    for s in universe:                     # stable column order
        if s not in series:
            continue
        t, c = series[s]
        col = np.full(T, np.nan)
        idx = np.fromiter((row[int(ts)] for ts in t), dtype=np.int64, count=len(t))
        col[idx] = c
        if np.isfinite(col).mean() >= COVERAGE_MIN:
            kept.append(s)
            cols.append(col)
    close = np.column_stack(cols)
    return all_t, close, kept


# --------------------------------------------------------------------------- #
# Backtest engine — cross-sectional reversion, dollar-neutral, no lookahead
# --------------------------------------------------------------------------- #
def backtest(close: np.ndarray, look: int, hold: int, construction: str,
             fee: float, mode: str = "reversion", entry_offset: int = 0,
             min_assets: int = MIN_ASSETS, q: float = DECILE_Q) -> dict:
    """Run one config. Returns per-rebalance net/gross/turnover series + weights.

    entry_offset>0 DELAYS the entry by N bars while keeping the signal at t (the
    pnl window becomes (t+offset, t+offset+hold]). It is two things at once:
      * a no-lookahead proof — the signal/pnl windows never overlap, and pushing
        the trade further from the signal can only DEGRADE a real edge, never
        inflate it (a leak would do the opposite);
      * a latency-sensitivity probe — offset = bars of execution delay.
    Default 0 = decide at close t, hold (t, t+hold].
    """
    T, N = close.shape
    rb_times, gross, net, turn, navg = [], [], [], [], []
    prev_w = np.zeros(N)
    t = look
    while t + hold < T:
        past_ok = np.isfinite(close[t]) & np.isfinite(close[t - look])
        ent = t + entry_offset
        ext = t + entry_offset + hold
        if ent < 0 or ext >= T:
            t += hold
            continue
        fwd_ok = np.isfinite(close[ent]) & np.isfinite(close[ext])
        valid = past_ok & fwd_ok
        if valid.sum() < min_assets:
            t += hold
            continue
        idx = np.where(valid)[0]
        past_ret = close[t, idx] / close[t - look, idx] - 1.0
        fwd_ret = close[ext, idx] / close[ent, idx] - 1.0

        rev = (mode == "reversion")
        x = past_ret - past_ret.mean()            # cross-sectional demean
        w = np.zeros(N)
        if construction == "continuous":
            wv = (-x if rev else x)               # reversion: long losers; momentum: long winners
            g = np.abs(wv).sum()
            if g <= 0:
                t += hold
                continue
            w[idx] = wv / g                        # gross=1, dollar-neutral
        else:                                      # decile
            k = max(1, int(round(len(x) * q)))
            order = np.argsort(x)
            lo, hi = order[:k], order[-k:]         # lo=lowest past_ret, hi=highest
            longs, shorts = (lo, hi) if rev else (hi, lo)
            w[idx[longs]] = 0.5 / k
            w[idx[shorts]] = -0.5 / k              # gross=1, neutral

        pnl = float(np.dot(w[idx], fwd_ret))
        turnover = float(np.abs(w - prev_w).sum())
        rb_times.append(t)
        gross.append(pnl)
        net.append(pnl - fee * turnover)
        turn.append(turnover)
        navg.append(int(valid.sum()))
        prev_w = w
        t += hold

    return {
        "rb_times": np.array(rb_times, dtype=np.int64),
        "gross": np.array(gross),
        "net": np.array(net),
        "turn": np.array(turn),
        "n_assets": np.array(navg),
        "look": look, "hold": hold, "construction": construction, "fee": fee,
    }


# --------------------------------------------------------------------------- #
# Metrics & honesty diagnostics
# --------------------------------------------------------------------------- #
def metrics(net: np.ndarray, hold: int) -> dict:
    n = len(net)
    if n == 0:
        return {"n": 0, "mean": 0.0, "sharpe": 0.0, "hit": 0.0, "maxdd": 0.0,
                "tstat": 0.0, "ann_ret": 0.0}
    ppy = HOURS_PER_YEAR / hold
    mu, sd = float(net.mean()), float(net.std(ddof=1)) if n > 1 else 0.0
    sharpe = (mu / sd * math.sqrt(ppy)) if sd > 0 else 0.0
    eq = np.cumprod(1.0 + net)
    dd = eq / np.maximum.accumulate(eq) - 1.0
    se = sd / math.sqrt(n) if n > 0 else 0.0
    return {
        "n": n,
        "mean": mu,                              # mean net return per rebalance
        "sharpe": sharpe,                        # annualized
        "hit": float((net > 0).mean()),
        "maxdd": float(dd.min()),
        "tstat": (mu / se) if se > 0 else 0.0,
        "ann_ret": float(eq[-1] ** (ppy / n) - 1.0) if n > 0 and eq[-1] > 0 else -1.0,
    }


def block_bootstrap_ci(x: np.ndarray, block: int = BOOT_BLOCK,
                       iters: int = BOOT_ITERS, seed: int = 7) -> tuple[float, float]:
    n = len(x)
    if n < 2:
        return (0.0, 0.0)
    rng = np.random.default_rng(seed)
    nb = int(math.ceil(n / block))
    means = np.empty(iters)
    hi = max(1, n - block + 1)
    for i in range(iters):
        starts = rng.integers(0, hi, size=nb)
        idx = (starts[:, None] + np.arange(block)[None, :]).ravel()[:n]
        idx = np.clip(idx, 0, n - 1)
        means[i] = x[idx].mean()
    means.sort()
    return float(means[int(0.025 * iters)]), float(means[int(0.975 * iters)])


def permutation_pvalue(bt: dict, close: np.ndarray, iters: int = PERM_ITERS,
                       seed: int = 11, mode: str = "reversion") -> float:
    """Null: within each rebalance, shuffle which asset gets which forward return.
    Destroys the weight<->forward-return pairing while preserving marginals.
    p = P(null mean >= real mean net)."""
    rng = np.random.default_rng(seed)
    rev = (mode == "reversion")
    look, hold, constr, fee = bt["look"], bt["hold"], bt["construction"], bt["fee"]
    rb = bt["rb_times"]
    if len(rb) == 0:
        return 1.0
    # cap for speed; subsample rebalances if huge
    if len(rb) > 4000:
        sel = rng.choice(len(rb), 4000, replace=False)
        rb = rb[np.sort(sel)]
    T, N = close.shape
    pairs = []                                   # (w_valid, fwd_valid) per rebalance
    for t in rb:
        t = int(t)
        fwd_t = t + hold
        if fwd_t >= T:
            continue
        valid = (np.isfinite(close[t]) & np.isfinite(close[t - look])
                 & np.isfinite(close[fwd_t]))
        if valid.sum() < MIN_ASSETS:
            continue
        idx = np.where(valid)[0]
        past_ret = close[t, idx] / close[t - look, idx] - 1.0
        fwd_ret = close[fwd_t, idx] / close[t, idx] - 1.0
        x = past_ret - past_ret.mean()
        if constr == "continuous":
            wv = (-x if rev else x)
            g = np.abs(wv).sum()
            if g <= 0:
                continue
            w = wv / g
        else:
            k = max(1, int(round(len(x) * DECILE_Q)))
            order = np.argsort(x)
            lo, hi = order[:k], order[-k:]
            longs, shorts = (lo, hi) if rev else (hi, lo)
            w = np.zeros(len(x))
            w[longs] = 0.5 / k
            w[shorts] = -0.5 / k
        pairs.append((w, fwd_ret))
    if not pairs:
        return 1.0
    real = float(np.mean([float(np.dot(w, f)) for w, f in pairs]))
    ge = 0
    for _ in range(iters):
        acc = 0.0
        for w, f in pairs:
            acc += float(np.dot(w, rng.permutation(f)))
        if acc / len(pairs) >= real:
            ge += 1
    return (ge + 1) / (iters + 1)


def regime_split(bt: dict, close: np.ndarray, btc_col: int | None) -> dict:
    """Split rebalances by BTC trailing-7d trend at decision time; report net EV
    in each regime. A market-neutral edge should keep its sign in both."""
    if btc_col is None:
        return {}
    rb, net = bt["rb_times"], bt["net"]
    win = 168                                    # 7 days of hours
    up_mask = np.zeros(len(rb), dtype=bool)
    valid = np.zeros(len(rb), dtype=bool)
    for i, t in enumerate(rb):
        t = int(t)
        if t - win < 0 or not np.isfinite(close[t, btc_col]) or not np.isfinite(close[t - win, btc_col]):
            continue
        valid[i] = True
        up_mask[i] = (close[t, btc_col] / close[t - win, btc_col] - 1.0) > 0
    out = {}
    for name, m in (("btc_up", valid & up_mask), ("btc_down", valid & ~up_mask)):
        seg = net[m]
        out[name] = {"n": int(len(seg)),
                     "mean": float(seg.mean()) if len(seg) else 0.0,
                     "hit": float((seg > 0).mean()) if len(seg) else 0.0}
    return out


def ncurve(net: np.ndarray, points: int = 40) -> list[list[float]]:
    """Cumulative mean net return vs #rebalances — does it stabilize or decay?"""
    n = len(net)
    if n == 0:
        return []
    cm = np.cumsum(net) / np.arange(1, n + 1)
    idx = np.unique(np.linspace(0, n - 1, min(points, n)).astype(int))
    return [[int(i + 1), float(cm[i])] for i in idx]


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #
def split_idx(n_rb: int) -> int:
    return int(n_rb * TRAIN_FRAC)


def select_on_train(close: np.ndarray, mode: str = "reversion",
                    looks: list[int] | None = None, holds: list[int] | None = None) -> dict:
    """Grid search on the TRAIN slice only. Selection metric = train net Sharpe."""
    looks = looks or LOOKBACKS
    holds = holds or HOLDS
    best = None
    table = []
    for constr in CONSTRUCTIONS:
        for look in looks:
            for hold in holds:
                bt = backtest(close, look, hold, constr, BASE_FEE, mode=mode)
                net = bt["net"]
                if len(net) < MIN_TRAIN_REBALANCES:
                    continue
                cut = split_idx(len(net))
                tr = metrics(net[:cut], hold)
                row = {"look": look, "hold": hold, "construction": constr,
                       "train_sharpe": tr["sharpe"], "train_mean": tr["mean"],
                       "train_n": tr["n"]}
                table.append(row)
                if best is None or tr["sharpe"] > best["train_sharpe"]:
                    best = row
    return {"best": best, "table": sorted(table, key=lambda r: -r["train_sharpe"])}


def evaluate(close: np.ndarray, btc_col: int | None, best: dict,
             mode: str = "reversion") -> dict:
    """Refit the chosen config and report TEST-set metrics + full honesty battery."""
    look, hold, constr = best["look"], best["hold"], best["construction"]
    bt = backtest(close, look, hold, constr, BASE_FEE, mode=mode)
    net, rb = bt["net"], bt["rb_times"]
    cut = split_idx(len(net))

    test_bt = {**bt, "rb_times": rb[cut:], "net": net[cut:],
               "gross": bt["gross"][cut:], "turn": bt["turn"][cut:],
               "n_assets": bt["n_assets"][cut:]}
    train_m = metrics(net[:cut], hold)
    test_m = metrics(net[cut:], hold)

    ci = block_bootstrap_ci(net[cut:])
    pval = permutation_pvalue(test_bt, close, mode=mode)
    regimes = regime_split(test_bt, close, btc_col)
    curve = ncurve(net[cut:])

    # Cost sensitivity on TEST: re-run config across the fee grid, report breakeven.
    cost_curve = []
    breakeven = None
    for fee in FEE_GRID:
        b = backtest(close, look, hold, constr, fee, mode=mode)
        nm = b["net"][split_idx(len(b["net"])):]
        m = metrics(nm, hold)
        cost_curve.append({"fee_bps": fee * 1e4, "sharpe": m["sharpe"], "mean": m["mean"]})
    # finer breakeven search on mean net > 0
    for fee in np.linspace(0, 0.0030, 61):
        b = backtest(close, look, hold, constr, float(fee), mode=mode)
        nm = b["net"][split_idx(len(b["net"])):]
        if nm.mean() <= 0:
            breakeven = float(fee)
            break

    return {
        "config": {"look": look, "hold": hold, "construction": constr,
                   "base_fee_bps": BASE_FEE * 1e4},
        "train": train_m, "test": test_m,
        "test_mean_ci95": ci, "permutation_p": pval,
        "regimes": regimes, "ncurve": curve,
        "avg_assets": float(test_bt["n_assets"].mean()) if len(test_bt["n_assets"]) else 0.0,
        "avg_turnover": float(test_bt["turn"].mean()) if len(test_bt["turn"]) else 0.0,
        "cost_curve": cost_curve, "breakeven_fee_bps": (breakeven * 1e4) if breakeven else None,
    }


def verdict(ev: dict) -> tuple[str, str]:
    t = ev["test"]
    lo, hi = ev["test_mean_ci95"]
    p = ev["permutation_p"]
    regimes = ev["regimes"]
    sign_stable = (regimes.get("btc_up", {}).get("mean", 0) > 0
                   and regimes.get("btc_down", {}).get("mean", 0) > 0)
    be = ev["breakeven_fee_bps"]
    survives = (t["mean"] > 0 and lo > 0 and p < 0.05 and t["sharpe"] > 0.5)
    if survives and sign_stable:
        return "VALIDATED", ("Net +EV out-of-time, CI excludes 0, beats permutation null, "
                             "Sharpe>0.5, sign-stable across BTC regimes.")
    if t["mean"] > 0 and (lo > 0 or p < 0.05):
        return "PROMISING", ("Positive net EV with partial significance; not all gates "
                             "passed (regime sign-stability or CI/p). Needs more data/refinement.")
    if t["mean"] > 0:
        return "WEAK", "Positive point estimate but not statistically separable from noise."
    return "REFUTED", ("No positive net edge out-of-time after costs. "
                       + ("Likely eaten by fees." if (be is not None and be < BASE_FEE * 1e4) else
                          "Signal absent, insufficient, or wrong-signed at tested horizons."))


def main(refresh: bool = False, mode: str = "reversion", top_n: int | None = None) -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore
    label = "cross-sectional REVERSION" if mode == "reversion" else "cross-sectional MOMENTUM"
    looks, holds = (LOOKBACKS, HOLDS) if mode == "reversion" else (MOM_LOOKBACKS, MOM_HOLDS)
    if top_n:
        print(f"[0/4] Discovering top-{top_n} liquid USDT pairs by 24h volume ...")
        universe = discover_universe(top_n)
    else:
        universe = UNIVERSE
    print(f"[1/4] Fetching {len(universe)} symbols x ~{WINDOW_DAYS}d @ {INTERVAL} "
          f"(cache: {CACHE}) ...")
    times, close, kept = build_matrix(universe, refresh=refresh)
    btc_col = kept.index("BTC") if "BTC" in kept else None
    span_days = (times[-1] - times[0]) / (24 * MS_PER_HOUR)
    print(f"      universe kept: {len(kept)}/{len(universe)}  bars={close.shape[0]} (~{span_days:.0f}d)")

    print(f"[2/4] Grid search on TRAIN (first 70% of timeline) — {label} ...")
    sel = select_on_train(close, mode, looks, holds)
    if sel["best"] is None:
        print("      No config met MIN_TRAIN_REBALANCES — aborting.")
        return
    b = sel["best"]
    print(f"      best-on-train: {b['construction']} look={b['look']}h hold={b['hold']}h "
          f"train_sharpe={b['train_sharpe']:.2f}")
    print("      top-5 train configs:")
    for r in sel["table"][:5]:
        print(f"        {r['construction']:<10} look={r['look']:>2} hold={r['hold']:>2} "
              f"sharpe={r['train_sharpe']:+.2f} mean={r['train_mean']:+.4%} n={r['train_n']}")

    print("[3/4] Evaluating chosen config ONCE on TEST (last 30%) + honesty battery ...")
    ev = evaluate(close, btc_col, b, mode)
    v, why = verdict(ev)

    print(f"[4/4] RESULT — {label}")
    t, tr = ev["test"], ev["train"]
    lo, hi = ev["test_mean_ci95"]
    print(f"  config         : {ev['config']['construction']} look={ev['config']['look']}h "
          f"hold={ev['config']['hold']}h  fee={ev['config']['base_fee_bps']:.1f}bps/side")
    print(f"  avg cross-sec  : {ev['avg_assets']:.1f} assets   avg turnover/rebal: {ev['avg_turnover']:.2f}")
    print(f"  TRAIN  net     : mean={tr['mean']:+.4%}/rebal sharpe={tr['sharpe']:+.2f} "
          f"hit={tr['hit']:.1%} n={tr['n']}")
    print(f"  TEST   net     : mean={t['mean']:+.4%}/rebal sharpe={t['sharpe']:+.2f} "
          f"hit={t['hit']:.1%} maxDD={t['maxdd']:.1%} ann={t['ann_ret']:+.1%} n={t['n']}")
    print(f"  TEST mean 95%CI: [{lo:+.4%}, {hi:+.4%}]   permutation p={ev['permutation_p']:.4f}   "
          f"t={t['tstat']:+.2f}")
    if ev["regimes"]:
        ru, rd = ev["regimes"].get("btc_up", {}), ev["regimes"].get("btc_down", {})
        print(f"  regime (TEST)  : BTC-up   mean={ru.get('mean',0):+.4%} hit={ru.get('hit',0):.1%} n={ru.get('n',0)}")
        print(f"                   BTC-down mean={rd.get('mean',0):+.4%} hit={rd.get('hit',0):.1%} n={rd.get('n',0)}")
    print(f"  cost sweep     : " + "  ".join(
        f"{c['fee_bps']:.1f}bps->Sh{c['sharpe']:+.2f}" for c in ev["cost_curve"]))
    print(f"  breakeven fee  : {ev['breakeven_fee_bps']}" + (" bps/side" if ev['breakeven_fee_bps'] else " (n/a)"))
    print(f"  N-curve (tail) : " + "  ".join(f"{n}:{m:+.3%}" for n, m in ev["ncurve"][-5:]))
    print(f"\n  VERDICT: {v} — {why}")

    out = {"ts": _now_iso(), "mode": mode, "universe": kept, "bars": int(close.shape[0]),
           "span_days": round(float(span_days), 1), "train_table_top": sel["table"][:10],
           "evaluation": _jsonify(ev), "verdict": v, "verdict_reason": why}
    res_path = RESULT_PATH if mode == "reversion" else (
        ROOT / "finetune" / "data" / "majors_xsmom_result.json")
    res_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": out["ts"], "mode": f"xs_{mode}", "config": ev["config"],
                            "test_mean": t["mean"], "test_sharpe": t["sharpe"],
                            "ci95": ev["test_mean_ci95"], "perm_p": ev["permutation_p"],
                            "breakeven_fee_bps": ev["breakeven_fee_bps"],
                            "verdict": v}) + "\n")
    print(f"\n  wrote {res_path.relative_to(ROOT)} and appended {LOG_PATH.relative_to(ROOT)}")


# --------------------------------------------------------------------------- #
# Self-tests — prove the engine is honest before trusting any number
# --------------------------------------------------------------------------- #
def selftest() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore
    print("SELFTEST — correctness gates (no edge should appear from leakage/cost bugs)")
    rng = np.random.default_rng(0)
    T, N = 6000, 20

    # 1) Pure random-walk closes => NO cross-sectional reversion edge expected.
    rets = rng.normal(0, 0.01, size=(T, N))
    close = 100 * np.cumprod(1 + rets, axis=0)
    bt = backtest(close, look=3, hold=3, construction="continuous", fee=0.0)
    m = metrics(bt["net"], 3)
    print(f"  [1] random-walk gross mean={m['mean']:+.5%} (expect ~0)  "
          f"-> {'PASS' if abs(m['mean']) < 5e-4 else 'CHECK'}")

    # 2) Dollar-neutrality: weights sum ~0 each rebalance (continuous & decile).
    ok_neutral = True
    for constr in ("continuous", "decile"):
        t = 100
        valid = np.isfinite(close[t]) & np.isfinite(close[t - 3])
        idx = np.where(valid)[0]
        x = (close[t, idx] / close[t - 3, idx] - 1.0)
        x = x - x.mean()
        if constr == "continuous":
            w = -x / np.abs(-x).sum()
        else:
            k = max(1, int(round(len(x) * DECILE_Q)))
            o = np.argsort(x); w = np.zeros(len(x)); w[o[:k]] = 0.5 / k; w[o[-k:]] = -0.5 / k
        if abs(w.sum()) > 1e-9 or abs(np.abs(w).sum() - 1.0) > 1e-9:
            ok_neutral = False
    print(f"  [2] dollar-neutral & unit-gross weights -> {'PASS' if ok_neutral else 'FAIL'}")

    # 3) Injected 1-bar reversion: base (offset 0) captures it (edge>0); delaying
    #    entry past the reversal bar (offset 2) must COLLAPSE the edge -> proves the
    #    pnl is tied to the immediate post-signal window (no lookahead) and that the
    #    signal is latency-sensitive.
    base = rng.normal(0, 0.01, size=(T, N))
    rev = np.zeros_like(base)
    rev[1:] = -0.30 * base[:-1]                  # next bar partially reverses prior
    r = base + rev
    closer = 100 * np.cumprod(1 + r, axis=0)
    edge = metrics(backtest(closer, 1, 1, "continuous", 0.0)["net"], 1)["mean"]
    delayed = metrics(backtest(closer, 1, 1, "continuous", 0.0, entry_offset=2)["net"], 1)["mean"]
    print(f"  [3] injected reversion: base mean={edge:+.5%} (expect >0)  "
          f"delayed-2bar mean={delayed:+.5%} (expect ~0)  -> "
          f"{'PASS' if edge > 0 and delayed < 0.5 * edge else 'CHECK'}")

    # 4) Cost monotonicity: net mean strictly decreases as fee rises.
    means = [metrics(backtest(closer, 1, 1, "continuous", f)["net"], 1)["mean"]
             for f in (0.0, 0.0005, 0.0015)]
    mono = means[0] > means[1] > means[2]
    print(f"  [4] cost monotonicity {means[0]:+.4%}>{means[1]:+.4%}>{means[2]:+.4%} -> "
          f"{'PASS' if mono else 'FAIL'}")

    # 5) Permutation null on random data ~ uniform => p not tiny.
    p = permutation_pvalue(backtest(close, 3, 3, "continuous", 0.0), close, iters=200)
    print(f"  [5] permutation p on random-walk = {p:.3f} (expect not <0.05)  "
          f"-> {'PASS' if p > 0.05 else 'CHECK'}")
    print("SELFTEST done.")


def _now_iso() -> str:
    import datetime as dt
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _jsonify(o):
    if isinstance(o, dict):
        return {k: _jsonify(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_jsonify(v) for v in o]
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    return o


# --------------------------------------------------------------------------- #
# TIME-SERIES reversion engine — the FAITHFUL H-03 port.
# Per-asset oversold-bounce (price below its OWN rolling high), beta-hedged
# against the equal-weight index so it stays market-neutral. This is the
# absolute reversion H-03 actually found, as opposed to the cross-sectional
# (peer-relative) reversion that `backtest()` just refuted on majors.
# --------------------------------------------------------------------------- #
TS_LOOKS = [24, 48, 72, 168]            # rolling-high window (hours): 1d..7d
TS_DDS = [-0.05, -0.10, -0.20]          # below own rolling high = oversold
TS_HOLDS = [6, 12, 24]                  # hours held
TS_VOL = [False, True]                  # require above-median range vs peers?
TS_MIN_TRAIN_TRADES = 200

# Config selected by the 44-asset grid search (run 2026-06-04, train t-stat +2.62).
# --lock re-tests THIS exact config on a wider universe to add power WITHOUT
# re-searching (avoids multiple-testing inflation).
LOCKED_TS = {"look": 72, "dd_thr": -0.20, "hold": 24, "use_vol": True}


def _rolling_max_min(close: np.ndarray, look: int) -> tuple[np.ndarray, np.ndarray]:
    """Right-aligned rolling max/min over [t-look, t]; NaN for t<look."""
    rmax = np.full_like(close, np.nan)
    rmin = np.full_like(close, np.nan)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)
        for i in range(close.shape[1]):
            sw = sliding_window_view(close[:, i], look + 1)
            rmax[look:, i] = np.nanmax(sw, axis=1)
            rmin[look:, i] = np.nanmin(sw, axis=1)
    return rmax, rmin


def ts_backtest(close: np.ndarray, look: int, dd_thr: float, hold: int,
                use_vol: bool, fee: float, rmax: np.ndarray, rmin: np.ndarray,
                entry_offset: int = 0) -> dict:
    """Emit BOTH per-trade hedged payoffs (H-03 EV/win parity) and a tradeable
    dollar-neutral portfolio series. No lookahead: signal at t, pnl on
    (t+entry_offset, t+entry_offset+hold]."""
    T, N = close.shape
    tg, tn, tt = [], [], []                       # per-trade gross / net / time
    rb, pg, pn, turn, nact = [], [], [], [], []
    prev_w = np.zeros(N)
    t = look
    while t + hold < T:
        ent, ext = t + entry_offset, t + entry_offset + hold
        if ext >= T:
            t += hold
            continue
        valid = (np.isfinite(close[t]) & np.isfinite(close[ent])
                 & np.isfinite(close[ext]) & np.isfinite(rmax[t]))
        if valid.sum() < MIN_ASSETS:
            t += hold
            continue
        vidx = np.where(valid)[0]
        fwd = close[ext, vidx] / close[ent, vidx] - 1.0
        mkt = float(fwd.mean())                   # equal-weight index = beta hedge
        dd = close[t, vidx] / rmax[t, vidx] - 1.0
        over = dd < dd_thr
        if use_vol:
            rng = (rmax[t, vidx] - rmin[t, vidx]) / close[t, vidx]
            over &= rng > np.median(rng)
        k = int(over.sum())
        for p in fwd[over]:
            tg.append(float(p) - mkt)
            tn.append(float(p) - mkt - 2.0 * fee)  # asset round-trip; hedge ~ +same
            tt.append(t)
        w = np.zeros(N)
        if k > 0:
            w[vidx[over]] += 1.0 / k               # long oversold, gross 1
            w[vidx] -= 1.0 / valid.sum()           # short index, gross 1 -> neutral
        gross = float(np.dot(w[vidx], fwd))
        tv = float(np.abs(w - prev_w).sum())
        rb.append(t); pg.append(gross); pn.append(gross - fee * tv)
        turn.append(tv); nact.append(k); prev_w = w
        t += hold
    return {
        "look": look, "dd_thr": dd_thr, "hold": hold, "use_vol": use_vol, "fee": fee,
        "trades_gross": np.array(tg), "trades_net": np.array(tn),
        "trades_t": np.array(tt, dtype=np.int64), "rb_times": np.array(rb, dtype=np.int64),
        "port_gross": np.array(pg), "net": np.array(pn), "turn": np.array(turn),
        "n_active": np.array(nact),
    }


def trade_stats(x: np.ndarray) -> dict:
    n = len(x)
    if n == 0:
        return {"n": 0, "ev": 0.0, "win": 0.0, "tstat": 0.0}
    mu = float(x.mean()); sd = float(x.std(ddof=1)) if n > 1 else 0.0
    se = sd / math.sqrt(n) if n > 0 else 0.0
    return {"n": n, "ev": mu, "win": float((x > 0).mean()),
            "tstat": (mu / se) if se > 0 else 0.0}


def ts_perm_pvalue(close: np.ndarray, rmax: np.ndarray, rmin: np.ndarray,
                   look: int, dd_thr: float, hold: int, use_vol: bool,
                   test_ts: np.ndarray, iters: int = PERM_ITERS, seed: int = 11) -> float:
    """Selection null: does the oversold set beat a RANDOM same-size set drawn from
    the same bar (same time => same regime)? p = P(null mean >= real mean)."""
    rng = np.random.default_rng(seed)
    T = close.shape[0]
    events = []                                    # (hedged_fwd_all_valid, k_over)
    real_sum = 0.0; total = 0
    for t in test_ts:
        t = int(t); ext = t + hold
        if ext >= T:
            continue
        valid = (np.isfinite(close[t]) & np.isfinite(close[ext]) & np.isfinite(rmax[t]))
        if valid.sum() < MIN_ASSETS:
            continue
        vidx = np.where(valid)[0]
        fwd = close[ext, vidx] / close[t, vidx] - 1.0
        hedged = fwd - float(fwd.mean())
        dd = close[t, vidx] / rmax[t, vidx] - 1.0
        over = dd < dd_thr
        if use_vol:
            r = (rmax[t, vidx] - rmin[t, vidx]) / close[t, vidx]
            over &= r > np.median(r)
        k = int(over.sum())
        if k == 0:
            continue
        events.append((hedged, k))
        real_sum += float(hedged[over].sum()); total += k
    if total == 0:
        return 1.0
    real = real_sum / total
    ge = 0
    for _ in range(iters):
        s = 0.0
        for hedged, k in events:
            s += hedged[rng.choice(len(hedged), k, replace=False)].sum()
        if s / total >= real:
            ge += 1
    return (ge + 1) / (iters + 1)


def evaluate_ts(close: np.ndarray, rmax: np.ndarray, rmin: np.ndarray,
                btc_col: int | None, best: dict) -> dict:
    look, dd_thr, hold, use_vol = best["look"], best["dd_thr"], best["hold"], best["use_vol"]
    bt = ts_backtest(close, look, dd_thr, hold, use_vol, BASE_FEE, rmax, rmin)
    split = split_idx(len(bt["rb_times"]))
    cutoff = int(bt["rb_times"][split])
    tr_mask = bt["trades_t"] < cutoff
    te_g = bt["trades_gross"][~tr_mask]
    te_n = bt["trades_net"][~tr_mask]
    train_net = trade_stats(bt["trades_net"][tr_mask])
    test_gross = trade_stats(te_g)
    test_net = trade_stats(te_n)
    ci = block_bootstrap_ci(te_n)
    test_rb = bt["rb_times"][split:]
    pval = ts_perm_pvalue(close, rmax, rmin, look, dd_thr, hold, use_vol, test_rb)
    port_te = bt["net"][split:]
    portm = metrics(port_te, hold)
    regimes = regime_split({"rb_times": test_rb, "net": port_te}, close, btc_col)
    curve = ncurve(te_n)
    be_trade = (test_gross["ev"] / 2.0) if test_gross["ev"] > 0 else None  # closed form
    pg_te, turn_te = bt["port_gross"][split:], bt["turn"][split:]
    be_port = (float(pg_te.mean()) / float(turn_te.mean())
               if turn_te.mean() > 0 and pg_te.mean() > 0 else None)
    return {
        "config": {"look": look, "dd_thr": dd_thr, "hold": hold, "use_vol": use_vol,
                   "base_fee_bps": BASE_FEE * 1e4},
        "train_trade": train_net, "test_trade_gross": test_gross, "test_trade_net": test_net,
        "test_net_ci95": ci, "permutation_p": pval,
        "portfolio_test": portm, "regimes": regimes, "ncurve": curve,
        "avg_active": float(bt["n_active"][split:].mean()) if len(bt["n_active"]) > split else 0.0,
        "avg_turnover": float(turn_te.mean()) if len(turn_te) else 0.0,
        "breakeven_fee_bps_trade": (be_trade * 1e4) if be_trade else None,
        "breakeven_fee_bps_port": (be_port * 1e4) if be_port else None,
    }


def verdict_ts(ev: dict) -> tuple[str, str]:
    tn = ev["test_trade_net"]; lo, hi = ev["test_net_ci95"]; p = ev["permutation_p"]
    sh = ev["portfolio_test"]["sharpe"]
    r = ev["regimes"]
    sign_stable = (r.get("btc_up", {}).get("mean", 0) > 0
                   and r.get("btc_down", {}).get("mean", 0) > 0)
    if tn["ev"] > 0 and lo > 0 and p < 0.05 and sh > 0.5 and sign_stable:
        return "VALIDATED", ("Per-trade net EV>0, bootstrap CI excludes 0, beats selection "
                             "null, portfolio Sharpe>0.5, sign-stable across BTC regimes.")
    if tn["ev"] > 0 and (lo > 0 or p < 0.05):
        return "PROMISING", "Positive net EV with partial significance; refine before sizing."
    if tn["ev"] > 0:
        return "WEAK", "Positive point estimate, not separable from noise."
    return "REFUTED", "No positive beta-hedged oversold-bounce out-of-time after costs on majors."


def main_ts(refresh: bool = False, top_n: int | None = None, lock: bool = False) -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore
    if top_n:
        print(f"[0/4] Discovering top-{top_n} liquid USDT pairs by 24h volume ...")
        universe = discover_universe(top_n)
    else:
        universe = UNIVERSE
    print(f"[1/4] Fetching {len(universe)} symbols x ~{WINDOW_DAYS}d @ {INTERVAL} ...")
    times, close, kept = build_matrix(universe, refresh=refresh)
    btc_col = kept.index("BTC") if "BTC" in kept else None
    span = (times[-1] - times[0]) / (24 * MS_PER_HOUR)
    print(f"      universe kept: {len(kept)}/{len(universe)}  bars={close.shape[0]} (~{span:.0f}d)")

    table = []
    if lock:
        best = dict(LOCKED_TS)
        print(f"[2/4] LOCKED config (no grid search): dd<{best['dd_thr']} look={best['look']}h "
              f"hold={best['hold']}h vol={best['use_vol']}  — re-testing on wider universe for power.")
        rolls = {best["look"]: _rolling_max_min(close, best["look"])}
    else:
        print("[2/4] Precomputing rolling highs + grid search on TRAIN (TS reversion) ...")
        rolls = {lk: _rolling_max_min(close, lk) for lk in TS_LOOKS}
        best = None
        for use_vol in TS_VOL:
            for look in TS_LOOKS:
                rmax, rmin = rolls[look]
                for dd in TS_DDS:
                    for hold in TS_HOLDS:
                        bt = ts_backtest(close, look, dd, hold, use_vol, BASE_FEE, rmax, rmin)
                        if len(bt["rb_times"]) < MIN_TRAIN_REBALANCES:
                            continue
                        split = split_idx(len(bt["rb_times"]))
                        cutoff = int(bt["rb_times"][split])
                        st = trade_stats(bt["trades_net"][bt["trades_t"] < cutoff])
                        if st["n"] < TS_MIN_TRAIN_TRADES:
                            continue
                        row = {"look": look, "dd_thr": dd, "hold": hold, "use_vol": use_vol,
                               "train_tstat": st["tstat"], "train_ev": st["ev"],
                               "train_win": st["win"], "train_n": st["n"]}
                        table.append(row)
                        if best is None or st["tstat"] > best["train_tstat"]:
                            best = row
        if best is None:
            print("      No TS config met thresholds — aborting.")
            return
        table.sort(key=lambda r: -r["train_tstat"])
        print(f"      best-on-train: dd<{best['dd_thr']} look={best['look']}h hold={best['hold']}h "
              f"vol={best['use_vol']} train_tstat={best['train_tstat']:+.2f} "
              f"train_ev={best['train_ev']:+.3%} win={best['train_win']:.1%}")
        print("      top-5 train configs (by t-stat):")
        for r in table[:5]:
            print(f"        dd<{r['dd_thr']:<5} look={r['look']:>3} hold={r['hold']:>2} vol={str(r['use_vol']):<5} "
                  f"tstat={r['train_tstat']:+.2f} ev={r['train_ev']:+.3%} win={r['train_win']:.1%} n={r['train_n']}")

    print("[3/4] Evaluating chosen config ONCE on TEST + honesty battery ...")
    rmax, rmin = rolls[best["look"]]
    ev = evaluate_ts(close, rmax, rmin, btc_col, best)
    v, why = verdict_ts(ev)

    print("[4/4] RESULT (time-series oversold-bounce, beta-hedged)")
    c = ev["config"]; tg, tn = ev["test_trade_gross"], ev["test_trade_net"]
    lo, hi = ev["test_net_ci95"]; pm = ev["portfolio_test"]
    print(f"  config         : dd<{c['dd_thr']} look={c['look']}h hold={c['hold']}h "
          f"vol={c['use_vol']}  fee={c['base_fee_bps']:.1f}bps/side")
    print(f"  avg active     : {ev['avg_active']:.1f} longs/rebal   avg turnover: {ev['avg_turnover']:.2f}")
    print(f"  TEST per-trade : gross EV={tg['ev']:+.3%} | net EV={tn['ev']:+.3%} win={tn['win']:.1%} n={tn['n']}")
    print(f"  TEST net CI95  : [{lo:+.3%}, {hi:+.3%}]   selection-null p={ev['permutation_p']:.4f}   t={tn['tstat']:+.2f}")
    print(f"  TEST portfolio : net mean={pm['mean']:+.4%}/rebal sharpe={pm['sharpe']:+.2f} "
          f"hit={pm['hit']:.1%} maxDD={pm['maxdd']:.1%} ann={pm['ann_ret']:+.1%}")
    if ev["regimes"]:
        ru, rd = ev["regimes"].get("btc_up", {}), ev["regimes"].get("btc_down", {})
        print(f"  regime (TEST)  : BTC-up   port mean={ru.get('mean',0):+.4%} n={ru.get('n',0)}")
        print(f"                   BTC-down port mean={rd.get('mean',0):+.4%} n={rd.get('n',0)}")
    print(f"  breakeven fee  : per-trade={ev['breakeven_fee_bps_trade']}  portfolio={ev['breakeven_fee_bps_port']}")
    print(f"  N-curve (tail) : " + "  ".join(f"{n}:{m:+.3%}" for n, m in ev["ncurve"][-5:]))
    print(f"\n  VERDICT: {v} — {why}")

    out = {"ts": _now_iso(), "mode": "ts_reversion", "universe": kept,
           "bars": int(close.shape[0]), "span_days": round(float(span), 1),
           "train_table_top": table[:10], "evaluation": _jsonify(ev),
           "verdict": v, "verdict_reason": why}
    p = ROOT / "finetune" / "data" / "majors_ts_reversion_result.json"
    p.write_text(json.dumps(out, indent=2), encoding="utf-8")
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": out["ts"], "mode": "ts_reversion", "config": ev["config"],
                            "test_net_ev": tn["ev"], "test_win": tn["win"],
                            "ci95": ev["test_net_ci95"], "perm_p": ev["permutation_p"],
                            "port_sharpe": pm["sharpe"], "verdict": v}) + "\n")
    print(f"\n  wrote {p.relative_to(ROOT)} and appended {LOG_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    _refresh = "--refresh" in sys.argv
    _top_n = None
    if "--universe" in sys.argv:
        _top_n = int(sys.argv[sys.argv.index("--universe") + 1])
    _lock = "--lock" in sys.argv
    if "--selftest" in sys.argv:
        selftest()
    elif "--ts" in sys.argv:
        main_ts(refresh=_refresh, top_n=_top_n, lock=_lock)
    elif "--xsmom" in sys.argv:
        main(refresh=_refresh, mode="momentum", top_n=_top_n)
    else:
        main(refresh=_refresh, mode="reversion", top_n=_top_n)
