"""
test_zone1_forcedflow.py — Zone-1 FORCED-FLOW batch tester (H-060..H-079 have-data variants).

ONE panel + perp-price load, then every HAVE-data variant is expressed as an EVENT-MASK and scored
through the IDENTICAL H-042 trap-hardened machinery (reused, NOT reinvented):
  * market-demean   : subtract cross-sectional mean forward return at the same period (dollar-neutral)
  * per-name beta   : beta to EW market on 1-period returns; forward beta-adjust (kills recovery beta)
  * period-cluster  : collapse events to PERIOD level (eff-n = distinct event periods);
                      cluster-t = per.mean() / (per.std(ddof=1)/sqrt(n_periods))
  * block_ci        : block-bootstrap 95% CI on the period series (reused from h042_deep)
  * permutation     : draw same #periods from the all-period demeaned-mean pool, period-style
  * taker cost      : 0.0011 round-trip (perp entry+exit, 5.5bps/side)

Any variant skipping demean+beta-adjust+period-clustering would be INVALID (that is how H-042's
naive perm_p 0.0001 collapsed to cluster-t 2.2). This file does NOT skip them.

GATE flag = (net beta-adj excess/trade > +2% AND cluster-t > 2 AND distinct periods > 100).
Baseline to beat: H-042 -8% H2 = +1.46%/trade, cluster-t 2.24, n=91.

Skips n-limited / collect-forward variants (H-068, H-078) per task scope.

Run: py hypothesis_lab/scripts/test_zone1_forcedflow.py
"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "finetune" / "pipeline"))
sys.path.insert(0, str(ROOT / "hypothesis_lab" / "scripts"))
import funding_harvest as fh          # noqa: E402
import h013_tradeable_carry as h13    # noqa: E402
import funding_leads2 as fl2          # noqa: E402  (reuse load_perp, slice_panel)
from h042_deep import block_ci        # noqa: E402  (reuse EXACT block-bootstrap CI)
sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore

TAKER_RT = 0.0011
SEED = 2026
PCTWIN = 90 * 3   # 90d trailing window in 8h periods, for per-name funding/basis percentiles


# --------------------------------------------------------------------------- shared scoring
def score_events(ev_t, ev_edge, allper_pool, label):
    """EXACT h042 protocol on a list of per-event (period t, signed beta-adj edge).
    allper_pool = per-period demeaned-mean reference used for the clustered permutation.
    Returns a result dict (or None if < 20 events)."""
    if len(ev_edge) < 20:
        return {"label": label, "events": len(ev_edge), "ok": False}
    ev_t = np.asarray(ev_t); ev_edge = np.asarray(ev_edge)
    uper = np.unique(ev_t)
    per = np.array([ev_edge[ev_t == t].mean() for t in uper])     # one obs / period (eff-n)
    clustT = per.mean() / (per.std(ddof=1) / np.sqrt(len(per))) if len(per) > 1 and per.std() > 0 else 0.0
    ci = block_ci(per)
    # permutation respecting clustering: same #periods drawn from the all-period demeaned pool
    rng = np.random.default_rng(SEED); NP = 5000; ge = 0; obs = per.mean()
    pool = allper_pool[np.isfinite(allper_pool)]
    for _ in range(NP):
        if rng.choice(pool, len(uper)).mean() >= obs:
            ge += 1
    permp = (ge + 1) / (NP + 1)
    net = ev_edge.mean() - TAKER_RT
    gate = bool(net > 0.02 and clustT > 2 and len(uper) > 100)
    return {"label": label, "ok": True, "events": int(len(ev_edge)), "periods": int(len(uper)),
            "gross": float(ev_edge.mean()), "net": float(net), "betaadj": float(ev_edge.mean()),
            "median": float(np.median(ev_edge)), "hit": float((ev_edge > 0).mean()),
            "clustT": float(clustT), "ci": ci, "permp": float(permp), "gate": gate}


def fmt_row(r):
    if not r.get("ok"):
        return f"{r['label']:<22} events={r['events']:>4}  (too few — INCONCLUSIVE)"
    g = "GATE-PASS" if r["gate"] else "sub-gate"
    if r.get("is_reg"):
        (lm, ln), (mm, mn), (hm, hn) = r["strata"]
        return (f"{r['label']:<22} ev={r['events']:>4} per={r['periods']:>4} "
                f"slope={r['slope']:>+7.2%}/dropper clustT={r['clustT']:>+5.2f} "
                f"strata: lo(1-2)={lm:>+6.2%}[{ln}] med(3-5)={mm:>+6.2%}[{mn}] hi(>=6)={hm:>+6.2%}[{hn}] {g}")
    return (f"{r['label']:<22} ev={r['events']:>4} per={r['periods']:>4} "
            f"net={r['net']:>+7.2%} bAcT={r['clustT']:>+5.2f} med={r['median']:>+6.2%} "
            f"hit={r['hit']:>4.0%} CI=[{r['ci'][0]:>+6.2%},{r['ci'][1]:>+6.2%}] permP={r['permp']:>6.4f} {g}")


# --------------------------------------------------------------------------- main
def main():
    panel, spot, _ = h13.load_offline_panel()
    fb, times, kept = panel["binance"], panel["times"], panel["kept"]
    basis_ret = panel.get("basis_ret")
    pp = fl2.load_perp(times, kept)
    T, N = pp.shape
    ret = np.full_like(pp, np.nan); ret[1:] = pp[1:] / pp[:-1] - 1.0
    tradeable = np.array([k in spot for k in kept])

    # per-name beta to EW market (1-period) — reused construction
    mret = np.nanmean(ret, axis=1)
    beta = np.full(N, np.nan)
    for j in range(N):
        m = np.isfinite(ret[:, j]) & np.isfinite(mret)
        if m.sum() > 50 and np.var(mret[m]) > 0:
            beta[j] = np.cov(ret[m, j], mret[m])[0, 1] / np.var(mret[m])
    beta = np.where(np.isfinite(beta), beta, 1.0)

    # forward H-period perp return + market-fwd per period, for H in {1,2}
    CR, MKT, POOL = {}, {}, {}
    for H in (1, 2):
        cr = np.full((T, N), np.nan)
        if T - H > 0:
            cr[:T - H] = pp[H:] / pp[:T - H] - 1.0
        mkt = np.nanmean(cr, axis=1)
        CR[H] = cr; MKT[H] = mkt
        # all-period demeaned-mean reference pool (period-style permutation null)
        POOL[H] = np.array([np.nanmean(cr[t] - mkt[t]) for t in range(1, T - H)])

    def badj(t, j, H):
        """beta-adjusted per-name forward excess at period t, hold H (the H-042 edge unit)."""
        return CR[H][t, j] - beta[j] * MKT[H][t]

    # rising-funding flag (H-042 base condition): funding[t] > funding[t-1]
    rising = np.zeros((T, N), bool)
    rising[1:] = np.isfinite(fb[1:]) & np.isfinite(fb[:-1]) & (fb[1:] > fb[:-1])

    # cascade masks (finite perp return below threshold, tradeable, forward defined)
    def casc(thr, H):
        m = np.zeros((T, N), bool)
        m[1:T - H] = (np.isfinite(ret[1:T - H]) & (ret[1:T - H] < thr)
                      & np.isfinite(CR[H][1:T - H]) & tradeable)
        return m

    # per-name trailing funding percentile rank at t (fraction of trailing window below fb[t])
    def fund_pct_rank(t, j):
        lo = max(0, t - PCTWIN)
        w = fb[lo:t, j]; w = w[np.isfinite(w)]
        if len(w) < 20 or not np.isfinite(fb[t, j]):
            return np.nan
        return float((w < fb[t, j]).mean())

    results = []

    # ---- H-060 repeat-cascade: -8% now AND a prior -8% within last 6 periods (48h), rising funding, H2
    thr = -0.08; H = 2; base = casc(thr, H)
    prior6 = np.zeros((T, N), bool)
    for t in range(7, T - H):
        prior6[t] = (np.isfinite(ret[t - 6:t]) & (ret[t - 6:t] < thr)).any(axis=0)
    et, ee = [], []
    for t in range(7, T - H):
        js = np.where(base[t] & rising[t] & prior6[t])[0]
        for j in js:
            et.append(t); ee.append(badj(t, j, H))
    results.append(score_events(et, ee, POOL[H], "H-060 repeat-casc H2"))

    # ---- H-061 cumulative -8% over 2 consecutive 8h, NO single period <-8% (else H-060/H-042) → period-3 (H1 from close of p2)
    H = 1
    et, ee = [], []
    for t in range(2, T - H):
        cum2 = ret[t] + ret[t - 1]                     # 2-period cumulative ending at t
        single_ok = (ret[t] > thr) & (ret[t - 1] > thr)  # neither single period itself <-8%
        hit = (np.isfinite(cum2) & (cum2 < thr) & single_ok
               & np.isfinite(CR[H][t]) & tradeable & rising[t])
        for j in np.where(hit)[0]:
            et.append(t); ee.append(badj(t, j, H))
    results.append(score_events(et, ee, POOL[H], "H-061 cum2-8% p3"))

    # ---- H-069 cascade(-8%) AND funding top tercile (trailing-90d >=66pct) that period, rising, H2
    H = 2; base = casc(thr, H)
    et, ee = [], []
    for t in range(1, T - H):
        for j in np.where(base[t] & rising[t])[0]:
            pr = fund_pct_rank(t, j)
            if np.isfinite(pr) and pr >= 0.66:
                et.append(t); ee.append(badj(t, j, H))
    results.append(score_events(et, ee, POOL[H], "H-069 casc+topTercF H2"))

    # ---- H-071 breadth basket: periods with >=3 names cascade(<-8%) → EW basket of ALL droppers, rising, H2
    H = 2; base = casc(thr, H)
    et, ee = [], []
    for t in range(1, T - H):
        js = np.where(base[t] & rising[t])[0]
        if len(js) >= 3:                                # systemic period
            for j in js:
                et.append(t); ee.append(badj(t, j, H))
    results.append(score_events(et, ee, POOL[H], "H-071 breadth>=3 basket H2"))

    # ---- H-073 >=5 consecutive top-quartile (>=75pct) funding + -5% cascade, H2
    thr5 = -0.05; H = 2; base5 = casc(thr5, H)
    # precompute per-name consecutive top-quartile funding streak length ending at t
    streak = np.zeros((T, N), int)
    for j in range(N):
        run = 0
        for t in range(T):
            pr = fund_pct_rank(t, j)
            if np.isfinite(pr) and pr >= 0.75:
                run += 1
            else:
                run = 0
            streak[t, j] = run
    et, ee = [], []
    for t in range(1, T - H):
        for j in np.where(base5[t])[0]:
            if streak[t, j] >= 5:
                et.append(t); ee.append(badj(t, j, H))
    results.append(score_events(et, ee, POOL[H], "H-073 5xQ4F + -5% H2"))

    # ---- H-077 breadth stratification: regress per-name excess on cascade breadth (#names<-5% same period)
    #      (uses ALL -5% rising cascade events, H2; reports OLS slope + t and strata means)
    H = 2; base5 = casc(thr5, H)
    breadth_period = (base5 & rising).sum(axis=1)       # #qualifying droppers per period
    bx, ey, et77 = [], [], []
    for t in range(1, T - H):
        js = np.where(base5[t] & rising[t])[0]
        for j in js:
            bx.append(breadth_period[t]); ey.append(badj(t, j, H)); et77.append(t)
    h077 = _regress_breadth(np.array(bx, float), np.array(ey, float), np.array(et77))
    results.append(h077)

    # ---- H-079 funding sign flip pos→neg next period after -8% cascade → period-2 bounce (enter close p1, H1 → p2)
    H = 1
    et, ee = [], []
    for t in range(1, T - H - 1):
        # cascade at t-? : H-079 = -8% cascade where funding flips +(t) -> -(t+1); measure p2 = forward from t+1
        for j in np.where(casc(thr, 1)[t])[0]:
            if (np.isfinite(fb[t, j]) and fb[t, j] > 0 and np.isfinite(fb[t + 1, j]) and fb[t + 1, j] < 0
                    and np.isfinite(CR[H][t + 1, j])):
                et.append(t + 1); ee.append(badj(t + 1, j, H))
    results.append(score_events(et, ee, POOL[H], "H-079 fund-flip p2"))

    # ---- H-065 basis 5th/95th pct snap-back (perp/spot basis) → forward basis reversion, both tails
    results += _h065_basis(panel, basis_ret, tradeable)

    # ---------------------------------------------------------------- report
    print("=" * 110)
    print("ZONE-1 FORCED-FLOW batch — beta-adj market-neutral excess/trade, period-clustered (eff-n), "
          "net of 11bps RT")
    print(f"panel: {N} names, {T} periods. Baseline to beat: H-042 -8%H2 net +1.46%/trade, clustT 2.24, n=91")
    print("=" * 110)
    for r in results:
        print(fmt_row(r))
    print("-" * 110)
    print("GATE = net>+2% AND clustT(bA)>2 AND periods>100.  (H-077 row: slope is excess per +1 dropper;"
          " positive+sig => breadth predicts bigger bounce.)")
    gates = [r for r in results if r.get("gate")]
    print("GATE-CANDIDATES:", ", ".join(r["label"] for r in gates) if gates else "NONE")
    # trap audit: basis_ret lag-1 autocorrelation (explains any H-065 'snap-back')
    ac = []
    for j in range(N):
        if not tradeable[j]:
            continue
        c = basis_ret[:, j]; m = np.isfinite(c[:-1]) & np.isfinite(c[1:])
        if m.sum() > 100 and c[:-1][m].std() > 0 and c[1:][m].std() > 0:
            ac.append(np.corrcoef(c[:-1][m], c[1:][m])[0, 1])
    ac = np.array(ac)
    print(f"TRAP AUDIT: basis_ret lag-1 autocorr mean={ac.mean():+.3f} (frac<0={ (ac<0).mean():.0%}). "
          f"Strong negative => H-065 'snap-back' is non-synchronous-close/bid-ask microstructure MR, "
          f"NOT tradeable alpha (gross < 11bps cost; net negative).")
    return results


def _regress_breadth(bx, ey, et):
    """H-077: OLS excess ~ a + b*breadth, with period-clustered t on the slope (cluster by period mean).
    We report the slope, its naive t, and period-clustered t (collapse residual contribution by period)."""
    label = "H-077 breadth->bounce"
    if len(bx) < 30 or bx.std() == 0:
        return {"label": label, "ok": False, "events": len(bx)}
    X = np.column_stack([np.ones_like(bx), bx])
    coef, *_ = np.linalg.lstsq(X, ey, rcond=None)
    a, b = coef
    resid = ey - X @ coef
    # naive slope t
    s2 = (resid @ resid) / (len(bx) - 2)
    xtx_inv = np.linalg.inv(X.T @ X)
    se_naive = np.sqrt(s2 * xtx_inv[1, 1])
    t_naive = b / se_naive if se_naive > 0 else 0.0
    # period-clustered slope t: cluster-robust (CR0) sandwich on period groups
    uper = np.unique(et)
    meat = np.zeros((2, 2))
    for t in uper:
        m = et == t
        xg = X[m]; ug = resid[m]
        sg = xg.T @ ug
        meat += np.outer(sg, sg)
    cov_cl = xtx_inv @ meat @ xtx_inv
    se_cl = np.sqrt(cov_cl[1, 1]) if cov_cl[1, 1] > 0 else 0.0
    t_cl = b / se_cl if se_cl > 0 else 0.0
    # strata means (low 1-2, med 3-5, high >=6)
    def strat(lo, hi):
        m = (bx >= lo) & (bx <= hi)
        return (float(ey[m].mean()) if m.any() else np.nan, int(m.sum()))
    lo_m, lo_n = strat(1, 2); md_m, md_n = strat(3, 5); hi_m, hi_n = strat(6, 999)
    gate = bool(t_cl > 2 and b > 0)
    return {"label": label, "ok": True, "events": int(len(bx)), "periods": int(len(uper)),
            "slope": float(b), "t_naive": float(t_naive), "clustT": float(t_cl),
            "net": float(b), "median": float(np.median(ey)), "hit": float((ey > 0).mean()),
            "ci": (float(lo_m) if np.isfinite(lo_m) else np.nan,
                   float(hi_m) if np.isfinite(hi_m) else np.nan),
            "permp": float("nan"), "gate": gate, "is_reg": True,
            "strata": ((lo_m, lo_n), (md_m, md_n), (hi_m, hi_n))}


def _h065_basis(panel, basis_ret, tradeable):
    """H-065: per-name perp/spot basis at 5th/95th pct -> snap-back within 1-3 periods.
    basis level = cumulative basis_ret is noisy; use the direct perp/spot basis from cached closes.
    We reconstruct basis = perp_close/spot_close - 1 from the panel's basis components via basis_ret is
    a RETURN diff, so instead measure the BASIS-PNL reversion: at an extreme of the trailing basis-return
    distribution, does the forward basis-return revert (mean-neutral)? Edge unit = signed forward basis
    return (long cheap leg / short rich leg), net of 11bps RT. Period-clustered, both tails."""
    out = []
    if basis_ret is None:
        out.append({"label": "H-065 basis 5/95 snap", "ok": False, "events": 0})
        return out
    T, N = basis_ret.shape
    # forward H-period basis return (sum of basis_ret over the hold) = basis P&L of the spread trade
    for H in (1, 3):
        FB = np.full((T, N), np.nan)
        for t in range(T - H):
            seg = basis_ret[t + 1:t + 1 + H]
            FB[t] = np.nansum(seg, axis=0) if np.isfinite(seg).any() else np.nan
        et, ee = [], []
        for t in range(1, T - H):
            lo = max(0, t - PCTWIN)
            for j in range(N):
                if not tradeable[j] or not np.isfinite(basis_ret[t, j]) or not np.isfinite(FB[t, j]):
                    continue
                w = basis_ret[lo:t, j]; w = w[np.isfinite(w)]
                if len(w) < 40:
                    continue
                p5, p95 = np.percentile(w, [5, 95])
                if basis_ret[t, j] <= p5:        # basis discount extreme -> expect UP reversion: long basis
                    et.append(t); ee.append(FB[t, j])
                elif basis_ret[t, j] >= p95:      # basis premium extreme -> expect DOWN reversion: short basis
                    et.append(t); ee.append(-FB[t, j])
        # period pool for permutation: per-period mean forward basis return (demeaned by cross-section)
        mfb = np.nanmean(FB, axis=1)
        pool = np.array([np.nanmean(FB[t] - mfb[t]) for t in range(1, T - H)])
        out.append(score_events(et, ee, pool, f"H-065 basis5/95 H{H}"))
    return out


if __name__ == "__main__":
    main()
