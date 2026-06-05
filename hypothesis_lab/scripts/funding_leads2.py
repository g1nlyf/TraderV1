"""
Funding-family leads (Session 4): H-032 acceleration, H-043 seasonality, H-047 lead-lag,
H-042 liquidation bounce. One shared offline panel load. All scored honestly (perm/CI, eff-n).

Run: py hypothesis_lab/scripts/funding_leads2.py
"""
from __future__ import annotations
import sys
from datetime import datetime, timezone
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "finetune" / "pipeline"))
sys.path.insert(0, str(ROOT / "hypothesis_lab" / "scripts"))
import funding_harvest as fh          # noqa: E402
import h013_tradeable_carry as h13    # noqa: E402
sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore
MAKER = 0.0001; PPY = fh.PERIODS_PER_YEAR; SEED = 2026


def slice_panel(p, idx):
    br = p.get("basis_ret")
    return {"times": p["times"], "kept": [p["kept"][i] for i in idx], "binance": p["binance"][:, idx],
            "bybit": p["bybit"][:, idx], "btc": p["btc"], "basis_ret": br[:, idx] if br is not None else None}


# ============================================================ H-032 acceleration
def h032(panel, cut):
    fb, br, kept = panel["binance"], panel["basis_ret"], panel["kept"]
    T, N = fb.shape
    lvl = np.array([np.nanmean(fb[:cut, j]) for j in range(N)])
    W = 21  # 7d of 8h periods
    accel = np.full(N, np.nan)
    for j in range(N):
        d = fb[W:cut, j] - fb[:cut - W, j]
        accel[j] = np.nanmean(d) if np.isfinite(d).any() else np.nan
    top_lvl = np.argsort(-lvl)[:10]
    top_acc = np.argsort(-np.where(np.isfinite(accel), accel, -1e9))[:10]
    ev_l = fh.evaluate(slice_panel(panel, list(top_lvl)), "single", MAKER, use_basis=True)
    ev_a = fh.evaluate(slice_panel(panel, list(top_acc)), "single", MAKER, use_basis=True)
    print("=" * 78); print("H-032 — funding ACCELERATION selection (rising Δ7d funding)"); print("=" * 78)
    print(f"  level top-10        TEST apr={ev_l['test']['apr']:+.2%} sh={ev_l['test']['sharpe']:+.2f}")
    print(f"  acceleration top-10 TEST apr={ev_a['test']['apr']:+.2%} sh={ev_a['test']['sharpe']:+.2f}  "
          f"names={','.join(kept[j] for j in top_acc)}")
    print(f"  VERDICT: acceleration {'BEATS' if ev_a['test']['apr'] > ev_l['test']['apr'] else 'does NOT beat'} "
          f"level selection ({ev_a['test']['apr']:+.2%} vs {ev_l['test']['apr']:+.2%}).")


# ============================================================ H-043 seasonality
def h043(panel):
    fb, times = panel["binance"], panel["times"]
    T, N = fb.shape
    per = np.nanmean(fb, axis=1)  # cross-name mean funding per period
    hour = np.array([datetime.fromtimestamp(t / 1000, timezone.utc).hour for t in times])
    wday = np.array([datetime.fromtimestamp(t / 1000, timezone.utc).weekday() for t in times])
    print("\n" + "=" * 78); print("H-043 — funding SEASONALITY (settlement-hour / weekday)"); print("=" * 78)
    rng = np.random.default_rng(SEED)
    for label, key in (("settlement-hour", hour), ("weekday", wday)):
        buckets = sorted(set(key.tolist()))
        means = {b: np.nanmean(per[key == b]) * PPY for b in buckets}
        spread = max(means.values()) - min(means.values())
        # permutation: shuffle labels, recompute spread
        ge = 0; NP = 5000
        finite = np.isfinite(per)
        pv = per[finite]; kf = key[finite]
        for _ in range(NP):
            sh = rng.permutation(kf)
            m = [np.nanmean(pv[sh == b]) for b in buckets]
            if (max(m) - min(m)) * PPY >= spread:
                ge += 1
        p = (ge + 1) / (NP + 1)
        hi = max(means, key=means.get); lo = min(means, key=means.get)
        print(f"  {label}: spread={spread:+.2%} APR (high={hi}:{means[hi]:+.1%}  low={lo}:{means[lo]:+.1%})  "
              f"perm_p={p:.3f} ({'REAL' if p < 0.05 else 'noise'})")


# ============================================================ H-047 lead-lag
def h047(panel):
    fb, fy, kept = panel["binance"], panel["bybit"], panel["kept"]
    T, N = fb.shape
    print("\n" + "=" * 78); print("H-047 — cross-venue funding LEAD-LAG (Binance↔Bybit)"); print("=" * 78)

    def lagcorr(a, b):  # corr(a[t], b[t+1])
        m = np.isfinite(a[:-1]) & np.isfinite(b[1:])
        if m.sum() < 50:
            return np.nan
        x, y = a[:-1][m], b[1:][m]
        if x.std() == 0 or y.std() == 0:
            return np.nan
        return float(np.corrcoef(x, y)[0, 1])
    b_lead, y_lead, same = [], [], []
    for j in range(N):
        if np.isfinite(fy[:, j]).sum() < 100:
            continue
        b_lead.append(lagcorr(fb[:, j], fy[:, j]))   # binance(t)->bybit(t+1)
        y_lead.append(lagcorr(fy[:, j], fb[:, j]))   # bybit(t)->binance(t+1)
        m = np.isfinite(fb[:, j]) & np.isfinite(fy[:, j])
        same.append(float(np.corrcoef(fb[m, j], fy[m, j])[0, 1]) if m.sum() > 50 else np.nan)
    b_lead, y_lead, same = np.array(b_lead), np.array(y_lead), np.array(same)
    print(f"  names={len(b_lead)}  contemporaneous corr={np.nanmean(same):+.2f}")
    print(f"  Binance(t)→Bybit(t+1) = {np.nanmean(b_lead):+.2f}   Bybit(t)→Binance(t+1) = {np.nanmean(y_lead):+.2f}")
    edge = np.nanmean(b_lead) - np.nanmean(y_lead)
    print(f"  lead asymmetry = {edge:+.3f} ({'Binance leads' if edge > 0.02 else 'no usable lead (funding≈contemporaneous, both just autocorrelated)'})")
    print("  NOTE: even if funding leads funding, that is not a PRICE edge — carry already harvests the level.")


# ============================================================ H-042 liquidation bounce
def load_perp(times, kept):
    row = {int(x): i for i, x in enumerate(times)}
    M = np.full((len(times), len(kept)), np.nan)
    ki = {k: j for j, k in enumerate(kept)}
    for f in h13.CACHE.glob("*USDT_perp_8h.npz"):
        base = f.stem[:-len("USDT_perp_8h")]
        if base not in ki:
            continue
        z = np.load(f)
        for i, x in enumerate(z["t"]):
            k = int(x)
            if k in row:
                M[row[k], ki[base]] = z["c"][i]
    return M


def h042(panel):
    fb, times, kept = panel["binance"], panel["times"], panel["kept"]
    pp = load_perp(times, kept)
    ret = np.full_like(pp, np.nan); ret[1:] = pp[1:] / pp[:-1] - 1.0
    T, N = pp.shape
    print("\n" + "=" * 78); print("H-042 — liquidation-cascade bounce (perp drop>5% + funding flip)"); print("=" * 78)
    cov = np.isfinite(pp).sum(0)
    usable = int((cov > fh.MIN_PERIODS).sum())
    print(f"  perp-price coverage: {usable}/{N} names with >{fh.MIN_PERIODS} periods")
    ev_fwd, base_fwd = [], []
    for j in range(N):
        col, fc = ret[:, j], fb[:, j]
        for t in range(1, T - 2):
            if not np.isfinite(col[t]):
                continue
            if col[t] < -0.05 and np.isfinite(fc[t]) and np.isfinite(fc[t - 1]) and fc[t] > fc[t - 1]:
                f1 = col[t + 1] if np.isfinite(col[t + 1]) else np.nan
                if np.isfinite(f1):
                    ev_fwd.append(f1)
        good = col[np.isfinite(col)]
        if len(good):
            base_fwd.append(np.mean(good))
    ev_fwd = np.array(ev_fwd)
    if len(ev_fwd) < 20:
        print(f"  events={len(ev_fwd)} — too few (8h granularity misses intra-cascade). INCONCLUSIVE."); return
    base = float(np.nanmean(base_fwd))
    rng = np.random.default_rng(SEED)
    allret = ret[np.isfinite(ret)]
    NP = 10000; ge = 0; obs = ev_fwd.mean()
    for _ in range(NP):
        if rng.choice(allret, len(ev_fwd)).mean() >= obs:
            ge += 1
    p = (ge + 1) / (NP + 1)
    print(f"  events={len(ev_fwd)}  fwd 8h return after event = {obs:+.3%}  (base mean = {base:+.3%})")
    print(f"  perm_p (vs random same-size) = {p:.4f} ({'BOUNCE real' if p < 0.05 and obs > 0 else 'no edge'})")


def main():
    panel, spot, bybit = h13.load_offline_panel()
    cut = int(len(panel["times"]) * fh.TRAIN_FRAC)
    print(f"panel {len(panel['kept'])} names {len(panel['times'])} periods\n")
    h032(panel, cut)
    h043(panel)
    h047(panel)
    h042(panel)
    print("\n" + "=" * 78 + "\nDONE\n" + "=" * 78)


if __name__ == "__main__":
    main()
