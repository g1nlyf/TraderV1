"""
H-042 DEEP — liquidation-cascade bounce, trap-hardened.

The shallow test gave perm_p 0.0001 (+0.68% fwd vs +0.055% base) — but that is exactly where the
H-15 / H-001 traps live. Three things must be ruled out before believing it:
  1. RECOVERY BETA: a market-wide crash makes 1000+ "events" that are one move × many names. The
     bounce may just be the market rebounding. FIX: market-demean each forward return (subtract the
     cross-sectional mean forward at the same period) → per-name EXCESS bounce, dollar-neutral.
  2. EFFECTIVE-N: 1091 events cluster into a handful of crash PERIODS. FIX: collapse to period-level
     series (one obs per event-period), report eff-n = distinct periods, cluster-robust t + block CI.
  3. LOTTERY: mean driven by a few huge bounces. FIX: report median + hit-rate, and net of cost.

Also re-runs H-032 acceleration on the TRADEABLE universe (the shallow run was contaminated by
spot-less exotics LAB/H/PUMP/EPIC — the H-13 inaccessibility names).

Run: py hypothesis_lab/scripts/h042_deep.py
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
sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore
MAKER = 0.0001; PPY = fh.PERIODS_PER_YEAR; SEED = 2026
TAKER_RT = 0.0011    # perp taker entry+exit (5.5bps/side)


def block_ci(x, block=3, n=5000, seed=SEED):
    x = np.asarray(x); rng = np.random.default_rng(seed); T = len(x)
    if T < block + 1:
        return (np.nan, np.nan)
    nb = int(np.ceil(T / block)); means = []
    for _ in range(n):
        s = rng.integers(0, T - block + 1, nb)
        means.append(np.concatenate([x[i:i + block] for i in s])[:T].mean())
    return (float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5)))


def h042_deep(panel, spot_names):
    fb, times, kept = panel["binance"], panel["times"], panel["kept"]
    pp = fl2.load_perp(times, kept)
    T, N = pp.shape
    ret = np.full_like(pp, np.nan); ret[1:] = pp[1:] / pp[:-1] - 1.0
    tradeable_mask = np.array([k in spot_names for k in kept])
    # per-name beta to the equal-weight market (1-period), to test beta-scaled recovery
    mret = np.nanmean(ret, axis=1)
    beta = np.full(N, np.nan)
    for j in range(N):
        m = np.isfinite(ret[:, j]) & np.isfinite(mret)
        if m.sum() > 50 and np.var(mret[m]) > 0:
            beta[j] = np.cov(ret[m, j], mret[m])[0, 1] / np.var(mret[m])
    print("=" * 80); print("H-042 DEEP — liquidation bounce (recovery-beta removed, period-clustered)")
    print("=" * 80)
    print(f"{'thr':>6} {'H':>2} {'events':>7} {'periods':>7} {'raw_fwd':>8} {'excess':>8} "
          f"{'exc_net':>8} {'betaAdj':>8} {'bA_cT':>6} {'median':>8} {'hit':>5} {'clustT':>7} {'permP':>7}")
    for thr in (-0.05, -0.08, -0.10, -0.15):
        for H in (1, 2):
            CR = np.full((T, N), np.nan)
            if T - H > 0:
                CR[:T - H] = pp[H:] / pp[:T - H] - 1.0
            mkt = np.nanmean(CR, axis=1)                      # market forward per period
            ev_t, ev_excess, ev_raw, ev_betaadj = [], [], [], []
            for t in range(1, T - H):
                rising = np.isfinite(fb[t]) & np.isfinite(fb[t - 1]) & (fb[t] > fb[t - 1])
                hit = np.isfinite(ret[t]) & (ret[t] < thr) & np.isfinite(CR[t]) & rising & tradeable_mask
                js = np.where(hit)[0]
                for j in js:
                    ev_t.append(t); ev_raw.append(CR[t, j]); ev_excess.append(CR[t, j] - mkt[t])
                    ev_betaadj.append(CR[t, j] - (beta[j] if np.isfinite(beta[j]) else 1.0) * mkt[t])
            if len(ev_excess) < 20:
                print(f"{thr:>6.0%} {H:>2} {len(ev_excess):>7} (too few)"); continue
            ev_t = np.array(ev_t); ev_excess = np.array(ev_excess); ev_raw = np.array(ev_raw)
            ev_betaadj = np.array(ev_betaadj)
            # period-level (eff-n = distinct periods)
            uperiods = np.unique(ev_t)
            per_excess = np.array([ev_excess[ev_t == t].mean() for t in uperiods])
            per_badj = np.array([ev_betaadj[ev_t == t].mean() for t in uperiods])
            clustT = per_excess.mean() / (per_excess.std(ddof=1) / np.sqrt(len(per_excess))) if len(per_excess) > 1 and per_excess.std() > 0 else 0.0
            bA_cT = per_badj.mean() / (per_badj.std(ddof=1) / np.sqrt(len(per_badj))) if len(per_badj) > 1 and per_badj.std() > 0 else 0.0
            ci = block_ci(per_excess)
            # permutation respecting clustering: random same # of periods, event-style mean
            rng = np.random.default_rng(SEED); NP = 5000; ge = 0; obs = per_excess.mean()
            allper_mean = np.array([np.nanmean(CR[t] - mkt[t]) for t in range(1, T - H)])
            allper_mean = allper_mean[np.isfinite(allper_mean)]
            for _ in range(NP):
                if rng.choice(allper_mean, len(uperiods)).mean() >= obs:
                    ge += 1
            permp = (ge + 1) / (NP + 1)
            exc_net = ev_excess.mean() - TAKER_RT
            print(f"{thr:>6.0%} {H:>2} {len(ev_excess):>7} {len(uperiods):>7} {ev_raw.mean():>+8.2%} "
                  f"{ev_excess.mean():>+8.2%} {exc_net:>+8.2%} {ev_betaadj.mean():>+8.2%} {bA_cT:>+6.2f} "
                  f"{np.median(ev_excess):>+8.2%} {(ev_excess>0).mean():>5.0%} {clustT:>+7.2f} {permp:>7.4f}")
    print("\n  raw_fwd = bounce incl. market recovery (beta).  excess = EW-market-demeaned.")
    print("  betaAdj = per-name-beta-scaled demean (kills high-beta-recovery). bA_cT = its cluster-t.")
    print("  Verdict: real liquidation alpha ONLY if betaAdj>0 with bA_cT>2 AND periods>100.")


def h032_tradeable(panel):
    tp = fh.filter_tradeable(panel, min_cov=0.90)
    fb = tp["binance"]; T, N = fb.shape; cut = int(T * fh.TRAIN_FRAC)
    lvl = np.array([np.nanmean(fb[:cut, j]) for j in range(N)])
    W = 21; accel = np.array([np.nanmean(fb[W:cut, j] - fb[:cut - W, j]) for j in range(N)])
    top_lvl = np.argsort(-lvl)[:10]; top_acc = np.argsort(-np.where(np.isfinite(accel), accel, -1e9))[:10]
    ev_l = fh.evaluate(fl2.slice_panel(tp, list(top_lvl)), "single", MAKER, use_basis=True)
    ev_a = fh.evaluate(fl2.slice_panel(tp, list(top_acc)), "single", MAKER, use_basis=True)
    print("\n" + "=" * 80); print("H-032 re-run on TRADEABLE-only (decontaminated)"); print("=" * 80)
    print(f"  level top-10        TEST apr={ev_l['test']['apr']:+.2%} sh={ev_l['test']['sharpe']:+.2f}")
    print(f"  acceleration top-10 TEST apr={ev_a['test']['apr']:+.2%} sh={ev_a['test']['sharpe']:+.2f}  "
          f"names={','.join(tp['kept'][j] for j in top_acc)}")
    print(f"  VERDICT: acceleration {'BEATS' if ev_a['test']['apr'] > ev_l['test']['apr'] else 'does NOT beat'} "
          f"level among tradeable ({ev_a['test']['apr']:+.2%} vs {ev_l['test']['apr']:+.2%}).")


def main():
    panel, spot, bybit = h13.load_offline_panel()
    h042_deep(panel, spot)
    h032_tradeable(panel)


if __name__ == "__main__":
    main()
