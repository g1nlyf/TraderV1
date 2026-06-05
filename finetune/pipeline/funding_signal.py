"""funding_signal.py — H-14: funding as a DIRECTIONAL cross-sectional positioning signal.

================================================================================
WHY (read research_state.md H-13 + the FRICTION meta-insight first)
================================================================================
H-13 found funding CARRY is arbed to ~breakeven on tradeable liquid names. But funding
is also a real-time gauge of CROWDED LEVERAGE: extreme positive funding = longs crowded
(euphoria), extreme negative = shorts crowded (capitulation). Crowding unwinds via FORCED
liquidations — non-adaptive flow — so fading it is a structural liquidation-risk premium,
not a static price factor. That mechanism *may* escape B-03 (which killed every static
DIRECTIONAL factor) because it is conditioned on a structural extreme, not always-on.

Construction = market-NEUTRAL cross-section (keeps the B-03-beating property of H-13):
  REVERSAL : long most-NEGATIVE-funding names, short most-POSITIVE  (fade crowding)
  MOMENTUM : the opposite sign (funding/positioning persists) — tested as the null-mirror
Signal at t uses funding known at t; PnL = perp returns over (t, t+hold]. No lookahead.

HONESTY (same battery as majors_meanrev / funding_harvest):
out-of-time 70/30, pre-registered grid (z-window × hold × mode), block-bootstrap CI,
permutation null (shuffle forward returns across names), BTC-regime split,
cost-sensitivity/breakeven, and selftests. Data is already cached by funding_harvest.

Run:
    py -3 finetune/pipeline/funding_signal.py --selftest
    py -3 finetune/pipeline/funding_signal.py
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "finetune" / "data" / "funding_cache"
RESULT_PATH = ROOT / "finetune" / "data" / "funding_signal_result.json"
LOG_PATH = ROOT / "finetune" / "data" / "funding_signal_log.jsonl"

MS_8H = 8 * 3600 * 1000
PERIODS_PER_YEAR = 3 * 365
TRAIN_FRAC = 0.70
MIN_ASSETS = 6
MIN_PERIODS = 200
EPS = 1e-12

ZWINS = [30, 90]                         # rolling z-score window (periods) for per-name funding
HOLDS = [1, 3, 9]                        # periods held (8h, 24h, 72h)
MODES = ["reversal", "momentum"]
BASE_FEE = 0.00055                       # taker 5.5bps (directional => assume taker)
FEE_GRID = [0.0001, 0.0003, 0.00055, 0.0008, 0.0011]
PERM_ITERS = 500
BOOT_ITERS = 2000
BOOT_BLOCK = 9


# --------------------------------------------------------------------------- #
# Data — reuse the cache populated by funding_harvest.py (funding + perp 8h)
# --------------------------------------------------------------------------- #
def load_panel() -> dict:
    fund, perp = {}, {}
    for f in CACHE.glob("*_binance.npz"):
        base = f.stem.replace("USDT_binance", "")
        z = np.load(f)
        if len(z["r"]) >= MIN_PERIODS:
            fund[base] = (z["t"], z["r"])
    for f in CACHE.glob("*_perp_8h.npz"):
        base = f.stem.replace("USDT_perp_8h", "")
        z = np.load(f)
        if len(z["c"]) >= MIN_PERIODS:
            perp[base] = (z["t"], z["c"])
    kept = [b for b in sorted(fund) if b in perp]
    if not kept:
        raise RuntimeError("No cached funding+perp data. Run funding_harvest.py --basis first.")
    all_t = np.unique(np.concatenate([fund[b][0] for b in kept]))
    row = {int(x): i for i, x in enumerate(all_t)}
    T = len(all_t)
    fmat = np.full((T, len(kept)), np.nan)
    pret = np.full((T, len(kept)), np.nan)
    for j, b in enumerate(kept):
        t, r = fund[b]
        for i, x in enumerate(t):
            k = int(x)
            if k in row:
                fmat[row[k], j] = r[i]
        t2, c2 = perp[b]
        lvl = np.full(T, np.nan)
        for i, x in enumerate(t2):
            k = int(x)
            if k in row:
                lvl[row[k]] = c2[i]
        pret[1:, j] = lvl[1:] / lvl[:-1] - 1.0
    btc = np.full(T, np.nan)
    bf = CACHE / "BTC_8h_klines.npz"
    if bf.exists():
        z = np.load(bf); bt, bc = z["t"], z["c"]
        br = {int(x): i for i, x in enumerate(bt)}
        for i, x in enumerate(all_t):
            if int(x) in br:
                btc[i] = bc[br[int(x)]]
    return {"times": all_t, "kept": kept, "funding": fmat, "perp_ret": pret, "btc": btc}


def _zscore_prev(col: np.ndarray, win: int) -> np.ndarray:
    """Rolling z-score of funding using ONLY values up to and including t (signal is the
    funding settled at t, which is known at t). Mean/std over the trailing `win`."""
    n = len(col); out = np.full(n, np.nan)
    for i in range(n):
        lo = max(0, i - win + 1)
        seg = col[lo:i + 1]
        seg = seg[np.isfinite(seg)]
        if len(seg) >= 5:
            sd = seg.std()
            if sd > EPS and np.isfinite(col[i]):
                out[i] = (col[i] - seg.mean()) / sd
    return out


# --------------------------------------------------------------------------- #
# Cross-sectional neutral backtest
# --------------------------------------------------------------------------- #
def backtest(panel: dict, zwin: int, hold: int, mode: str, fee: float,
             entry_offset: int = 0) -> dict:
    f, pr = panel["funding"], panel["perp_ret"]
    T, N = f.shape
    z = np.full((T, N), np.nan)
    for j in range(N):
        z[:, j] = _zscore_prev(f[:, j], zwin)
    rev = (mode == "reversal")
    rb, net, gross, turn, nas = [], [], [], [], []
    prev_w = np.zeros(N)
    t = 1
    while t + hold < T:
        ent, ext = t + entry_offset, t + entry_offset + hold
        if ext >= T:
            t += hold; continue
        valid = np.isfinite(z[t]) & np.isfinite(pr[ent + 1:ext + 1]).all(axis=0) if False else \
            np.isfinite(z[t])
        # forward perp return over (ent, ext] = product of (1+ret) - 1
        fwd = np.full(N, np.nan)
        block = pr[ent + 1:ext + 1]                       # rows ent+1..ext
        if block.shape[0] == hold:
            with np.errstate(invalid="ignore"):
                fwd = np.prod(1.0 + np.where(np.isfinite(block), block, np.nan), axis=0) - 1.0
        valid = np.isfinite(z[t]) & np.isfinite(fwd)
        if valid.sum() < MIN_ASSETS:
            t += hold; continue
        idx = np.where(valid)[0]
        x = z[t, idx] - z[t, idx].mean()                  # cross-sectional demean
        wv = (-x if rev else x)                           # reversal: long low funding
        g = np.abs(wv).sum()
        if g <= EPS:
            t += hold; continue
        w = np.zeros(N); w[idx] = wv / g                  # gross=1, dollar-neutral
        pnl = float(np.dot(w[idx], fwd[idx]))
        tv = float(np.abs(w - prev_w).sum())
        rb.append(t); gross.append(pnl); net.append(pnl - fee * tv)
        turn.append(tv); nas.append(int(valid.sum())); prev_w = w
        t += hold
    return {"zwin": zwin, "hold": hold, "mode": mode, "fee": fee,
            "rb": np.array(rb), "gross": np.array(gross), "net": np.array(net),
            "turn": np.array(turn), "n_assets": np.array(nas)}


def metrics(net: np.ndarray, hold: int) -> dict:
    n = len(net)
    if n == 0:
        return {"n": 0, "mean": 0.0, "sharpe": 0.0, "hit": 0.0, "maxdd": 0.0, "apr": 0.0}
    mu = float(net.mean()); sd = float(net.std(ddof=1)) if n > 1 else 0.0
    ppy = PERIODS_PER_YEAR / hold
    eq = np.cumprod(1 + net); dd = eq / np.maximum.accumulate(eq) - 1
    return {"n": n, "mean": mu, "sharpe": (mu / sd * math.sqrt(ppy)) if sd > 0 else 0.0,
            "hit": float((net > 0).mean()), "maxdd": float(dd.min()), "apr": mu * ppy}


def block_bootstrap_ci(x, block=BOOT_BLOCK, iters=BOOT_ITERS, seed=7):
    n = len(x)
    if n < 2:
        return (0.0, 0.0)
    rng = np.random.default_rng(seed); nb = int(math.ceil(n / block)); means = np.empty(iters)
    hi = max(1, n - block + 1)
    for i in range(iters):
        st = rng.integers(0, hi, size=nb)
        idx = (st[:, None] + np.arange(block)[None, :]).ravel()[:n]
        means[i] = x[np.clip(idx, 0, n - 1)].mean()
    means.sort()
    return float(means[int(0.025 * iters)]), float(means[int(0.975 * iters)])


def permutation_p(panel, bt, iters=PERM_ITERS, seed=11):
    """Null: shuffle forward returns across names within each rebalance."""
    rng = np.random.default_rng(seed)
    f, pr = panel["funding"], panel["perp_ret"]
    T, N = f.shape
    zwin, hold, mode = bt["zwin"], bt["hold"], bt["mode"]; rev = (mode == "reversal")
    z = np.full((T, N), np.nan)
    for j in range(N):
        z[:, j] = _zscore_prev(f[:, j], zwin)
    rb = bt["rb"]
    if len(rb) > 4000:
        rb = rb[np.sort(rng.choice(len(rb), 4000, replace=False))]
    pairs = []
    for t in rb:
        t = int(t); ent, ext = t, t + hold
        if ext >= T:
            continue
        block = pr[ent + 1:ext + 1]
        if block.shape[0] != hold:
            continue
        fwd = np.prod(1.0 + np.where(np.isfinite(block), block, np.nan), axis=0) - 1.0
        valid = np.isfinite(z[t]) & np.isfinite(fwd)
        if valid.sum() < MIN_ASSETS:
            continue
        idx = np.where(valid)[0]
        x = z[t, idx] - z[t, idx].mean(); wv = (-x if rev else x); g = np.abs(wv).sum()
        if g <= EPS:
            continue
        pairs.append((wv / g, fwd[idx]))
    if not pairs:
        return 1.0
    real = float(np.mean([float(np.dot(w, fv)) for w, fv in pairs]))
    ge = 0
    for _ in range(iters):
        acc = sum(float(np.dot(w, rng.permutation(fv))) for w, fv in pairs)
        if acc / len(pairs) >= real:
            ge += 1
    return (ge + 1) / (iters + 1)


def regime_split(panel, bt):
    btc = panel["btc"]; rb, net = bt["rb"], bt["net"]; win = 21
    out = {}; up = np.zeros(len(rb), bool); val = np.zeros(len(rb), bool)
    for i, t in enumerate(rb):
        t = int(t)
        if t - win < 0 or not np.isfinite(btc[t]) or not np.isfinite(btc[t - win]):
            continue
        val[i] = True; up[i] = (btc[t] / btc[t - win] - 1) > 0
    for name, m in (("btc_up", val & up), ("btc_down", val & ~up)):
        seg = net[m]
        out[name] = {"n": int(len(seg)), "mean": float(seg.mean()) if len(seg) else 0.0}
    return out


def split_idx(n):
    return int(n * TRAIN_FRAC)


def evaluate(panel, mode):
    best = None; table = []
    for zwin in ZWINS:
        for hold in HOLDS:
            bt = backtest(panel, zwin, hold, mode, BASE_FEE)
            if len(bt["net"]) < 60:
                continue
            cut = split_idx(len(bt["net"]))
            tr = metrics(bt["net"][:cut], hold)
            table.append((zwin, hold, tr["sharpe"]))
            if best is None or tr["sharpe"] > best[2]:
                best = (zwin, hold, tr["sharpe"])
    if best is None:
        return None
    zwin, hold, _ = best
    bt = backtest(panel, zwin, hold, mode, BASE_FEE)
    cut = split_idx(len(bt["net"]))
    test_bt = {**bt, "rb": bt["rb"][cut:], "net": bt["net"][cut:]}
    tr, te = metrics(bt["net"][:cut], hold), metrics(bt["net"][cut:], hold)
    ci = block_bootstrap_ci(bt["net"][cut:])
    pj = permutation_p(panel, test_bt)
    reg = regime_split(panel, test_bt)
    # cost sweep
    cc = []
    for fee in FEE_GRID:
        b = backtest(panel, zwin, hold, mode, fee)
        cc.append({"fee_bps": fee * 1e4, "apr": metrics(b["net"][split_idx(len(b["net"])):], hold)["apr"]})
    return {"mode": mode, "zwin": zwin, "hold": hold, "train": tr, "test": te,
            "test_ci95": ci, "perm_p": pj, "regimes": reg,
            "avg_turn": float(test_bt.get("turn", np.array([0])).mean()) if "turn" in bt else 0.0,
            "cost_curve": cc}


def event_study(panel: dict, thr: float, hold: int, fee: float, zwin: int = 90) -> dict:
    """Per-event test of the fade-crowding mechanism (max power). For every (name,t) with
    |z|>thr: market-hedged forward return — short if z>thr (longs crowded), long if z<-thr
    (shorts crowded). Returns per-event payoffs (time-tagged) + train/test split."""
    f, pr = panel["funding"], panel["perp_ret"]
    T, N = f.shape
    z = np.full((T, N), np.nan)
    for j in range(N):
        z[:, j] = _zscore_prev(f[:, j], zwin)
    ev_t, ev_p = [], []
    t = 1
    while t + hold < T:
        block = pr[t + 1:t + 1 + hold]
        if block.shape[0] != hold:
            t += 1; continue
        fwd = np.prod(1.0 + np.where(np.isfinite(block), block, np.nan), axis=0) - 1.0
        valid = np.isfinite(z[t]) & np.isfinite(fwd)
        if valid.sum() < MIN_ASSETS:
            t += 1; continue
        mkt = float(fwd[valid].mean())
        for j in np.where(valid)[0]:
            if z[t, j] > thr:
                ev_t.append(t); ev_p.append(-(fwd[j] - mkt) - 2 * fee)     # short crowded long
            elif z[t, j] < -thr:
                ev_t.append(t); ev_p.append((fwd[j] - mkt) - 2 * fee)      # long crowded short
        t += 1
    ev_t = np.array(ev_t); ev_p = np.array(ev_p)
    if len(ev_p) < 50:
        return {"thr": thr, "hold": hold, "n": len(ev_p)}
    cut_t = panel["times"][int(T * TRAIN_FRAC)]
    tr_mask = ev_t < int(T * TRAIN_FRAC)
    te = ev_p[~tr_mask]
    mu = float(te.mean()); sd = float(te.std(ddof=1)) if len(te) > 1 else 0.0
    se = sd / math.sqrt(len(te)) if len(te) else 0.0
    ci = block_bootstrap_ci(te, block=max(hold, 4))
    return {"thr": thr, "hold": hold, "n": int(len(te)), "n_train": int(tr_mask.sum()),
            "ev": mu, "win": float((te > 0).mean()), "tstat": (mu / se) if se > 0 else 0.0,
            "ci95": ci, "ev_annual_if_indep": mu * (PERIODS_PER_YEAR / hold)}


def verdict(ev):
    te = ev["test"]; lo, hi = ev["test_ci95"]; p = ev["perm_p"]; r = ev["regimes"]
    stable = (r.get("btc_up", {}).get("mean", 0) > 0 and r.get("btc_down", {}).get("mean", 0) > 0)
    if te["mean"] > 0 and lo > 0 and p < 0.05 and te["sharpe"] > 0.5 and stable:
        return "VALIDATED", "Net +EV OOS, CI>0, beats permutation null, Sharpe>0.5, regime-stable."
    if te["mean"] > 0 and (lo > 0 or p < 0.05):
        return "PROMISING", "Positive net EV, partial significance; refine."
    if te["mean"] > 0:
        return "WEAK", "Positive point estimate, not separable from noise."
    return "REFUTED", "No positive net edge OOS after costs."


def _now_iso():
    import datetime as dt
    return dt.datetime.now(dt.timezone.utc).isoformat()


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore
    print("[1/3] Loading cached funding + perp panel ...")
    panel = load_panel()
    print(f"      assets={len(panel['kept'])}  periods={len(panel['times'])}")
    print("[2/3] Evaluating funding-positioning signals out-of-time ...")
    results = {}
    for mode in MODES:
        ev = evaluate(panel, mode)
        if ev is None:
            print(f"  {mode}: insufficient data"); continue
        v, why = verdict(ev); ev["verdict"], ev["verdict_reason"] = v, why
        results[mode] = ev
        te = ev["test"]; lo, hi = ev["test_ci95"]; r = ev["regimes"]
        print(f"\n  === funding {mode.upper()} (zwin={ev['zwin']} hold={ev['hold']}p, taker 5.5bps) ===")
        print(f"    TRAIN sharpe={ev['train']['sharpe']:+.2f} | TEST apr={te['apr']:+.1%} "
              f"sharpe={te['sharpe']:+.2f} hit={te['hit']:.1%} maxDD={te['maxdd']:.1%} n={te['n']}")
        print(f"    TEST mean/rebal={te['mean']:+.4%} CI95=[{lo:+.4%},{hi:+.4%}] perm_p={ev['perm_p']:.3f}")
        print(f"    regime: up={r.get('btc_up',{}).get('mean',0):+.4%} down={r.get('btc_down',{}).get('mean',0):+.4%}")
        print(f"    cost sweep: " + "  ".join(f"{c['fee_bps']:.1f}->{c['apr']:+.0%}" for c in ev["cost_curve"]))
        print(f"    VERDICT: {v} — {why}")
    print("\n[3/3] EVENT STUDY — fade funding extremes, market-hedged (max power, taker 5.5bps)")
    print("      (every (name,t) with |z|>thr => hedged forward return; thousands of events)")
    ev_results = []
    for thr in (1.5, 2.0):
        for hold in (1, 3, 9):
            es = event_study(panel, thr, hold, BASE_FEE)
            ev_results.append(es)
            if es.get("n", 0) < 50:
                print(f"  thr={thr} hold={hold}p: n={es.get('n',0)} (too few)"); continue
            lo, hi = es["ci95"]
            flag = "✓+EV" if (es["ev"] > 0 and lo > 0) else ("~" if es["ev"] > 0 else "✗")
            print(f"  thr={thr} hold={hold}p: n={es['n']:>5} EV/event={es['ev']:+.3%} "
                  f"win={es['win']:.1%} t={es['tstat']:+.2f} CI=[{lo:+.3%},{hi:+.3%}] "
                  f"annEV≈{es['ev_annual_if_indep']:+.0%} {flag}")
    results["event_study"] = ev_results
    out = {"ts": _now_iso(), "assets": panel["kept"], "periods": len(panel["times"]), "results": results}
    RESULT_PATH.write_text(json.dumps(_json(out), indent=2), encoding="utf-8")
    with LOG_PATH.open("a", encoding="utf-8") as fp:
        for m, ev in results.items():
            if m not in MODES:
                continue
            fp.write(json.dumps({"ts": out["ts"], "mode": f"funding_{m}", "zwin": ev["zwin"],
                                 "hold": ev["hold"], "test_apr": ev["test"]["apr"],
                                 "test_sharpe": ev["test"]["sharpe"], "ci95": ev["test_ci95"],
                                 "perm_p": ev["perm_p"], "verdict": ev["verdict"]}) + "\n")
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
    print("SELFTEST — funding_signal cross-sectional engine")
    rng = np.random.default_rng(0); T, N = 3000, 20
    # 1) random funding + random perp returns => no edge.
    f = rng.normal(0, 0.0003, (T, N)); pr = rng.normal(0, 0.02, (T, N))
    p = {"funding": f, "perp_ret": pr, "btc": np.full(T, np.nan), "kept": list(range(N)),
         "times": np.arange(T)}
    m = metrics(backtest(p, 30, 1, "reversal", 0.0)["net"], 1)
    print(f"  [1] random => mean={m['mean']:+.5%} (≈0) -> {'PASS' if abs(m['mean'])<5e-4 else 'CHECK'}")
    # 2) injected: next-period perp return = -0.5*funding_z (high funding -> price falls) =>
    #    REVERSAL (long low funding) must be +; MOMENTUM must be -.
    fz = rng.normal(0, 1, (T, N))
    fund = fz * 0.0003
    pr2 = np.zeros((T, N)); pr2[1:] = -0.01 * fz[:-1] + rng.normal(0, 0.003, (T - 1, N))
    p2 = {"funding": fund, "perp_ret": pr2, "btc": np.full(T, np.nan), "kept": list(range(N)),
          "times": np.arange(T)}
    rv = metrics(backtest(p2, 30, 1, "reversal", 0.0)["net"], 1)["mean"]
    mo = metrics(backtest(p2, 30, 1, "momentum", 0.0)["net"], 1)["mean"]
    print(f"  [2] injected fade: reversal={rv:+.4%}(>0) momentum={mo:+.4%}(<0) -> "
          f"{'PASS' if rv > 0 and mo < 0 else 'FAIL'}")
    # 3) cost monotonicity
    a0 = metrics(backtest(p2, 30, 1, "reversal", 0.0)["net"], 1)["mean"]
    a1 = metrics(backtest(p2, 30, 1, "reversal", 0.0015)["net"], 1)["mean"]
    print(f"  [3] cost monotonicity {a0:+.4%}>{a1:+.4%} -> {'PASS' if a0 > a1 else 'FAIL'}")
    # 4) no-lookahead: entry_offset shift away from signal must not increase a real edge
    base = metrics(backtest(p2, 30, 1, "reversal", 0.0)["net"], 1)["mean"]
    shifted = metrics(backtest(p2, 30, 1, "reversal", 0.0, entry_offset=2)["net"], 1)["mean"]
    print(f"  [4] no-lookahead base={base:+.4%} shifted={shifted:+.4%} -> "
          f"{'PASS' if base > 0 and shifted < base else 'CHECK'}")
    print("SELFTEST done.")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    else:
        main()
