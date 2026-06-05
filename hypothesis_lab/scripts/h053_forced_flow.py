"""
H-053 — Forced-flow overshoot, BOTH sides (the symmetric twin of H-042).

H-042 found a real per-name bounce after forced-liquidation SELLING (price −8%). If forced,
non-adaptive flow is a GENERAL principle (the program's unifying thesis — carry = forced funding
payers, H-042 = forced liq sellers), the UP side must also work: after a short-squeeze (+8% spike,
forced short-COVERING), the name should FADE more than the market. Same machinery, both directions.

Also reports the tradeable BASKET form (H-058): the period-level mean excess IS an equal-weight
basket of all droppers/spikers per period, market-neutral — one honest obs per period.

  down side: long the dropper, short index  → edge = +excess
  up   side: short the spiker, long index   → edge = −excess
All trap-hardened: per-name beta-adjusted demean, period-clustered eff-n, net of taker cost.

Run: py hypothesis_lab/scripts/h053_forced_flow.py
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
import funding_leads2 as fl2          # noqa: E402
from h042_deep import block_ci        # noqa: E402
sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore
TAKER_RT = 0.0011


def main():
    panel, spot, _ = h13.load_offline_panel()
    fb, times, kept = panel["binance"], panel["times"], panel["kept"]
    pp = fl2.load_perp(times, kept)
    T, N = pp.shape
    ret = np.full_like(pp, np.nan); ret[1:] = pp[1:] / pp[:-1] - 1.0
    tradeable = np.array([k in spot for k in kept])
    mret = np.nanmean(ret, axis=1)
    beta = np.full(N, np.nan)
    for j in range(N):
        m = np.isfinite(ret[:, j]) & np.isfinite(mret)
        if m.sum() > 50 and np.var(mret[m]) > 0:
            beta[j] = np.cov(ret[m, j], mret[m])[0, 1] / np.var(mret[m])
    beta = np.where(np.isfinite(beta), beta, 1.0)

    print("=" * 92)
    print("H-053 — FORCED-FLOW OVERSHOOT, both sides (beta-adj, period-clustered). edge=trade pnl, market-neutral")
    print("=" * 92)
    print(f"{'side':>5} {'thr':>5} {'H':>2} {'events':>7} {'periods':>7} {'edge/trade':>10} {'net':>8} "
          f"{'median':>8} {'hit':>5} {'clustT':>7} {'CI95':>20}")
    for side in ("down", "up"):
        for thr in (0.05, 0.08, 0.10):
            for H in (1, 2):
                CR = np.full((T, N), np.nan)
                if T - H > 0:
                    CR[:T - H] = pp[H:] / pp[:T - H] - 1.0
                mkt = np.nanmean(CR, axis=1)
                ev_t, ev_edge = [], []
                for t in range(1, T - H):
                    rising = np.isfinite(fb[t]) & np.isfinite(fb[t - 1]) & (fb[t] > fb[t - 1])
                    if side == "down":
                        hit = np.isfinite(ret[t]) & (ret[t] < -thr) & np.isfinite(CR[t]) & rising & tradeable
                        s = +1.0
                    else:
                        hit = np.isfinite(ret[t]) & (ret[t] > thr) & np.isfinite(CR[t]) & tradeable  # squeeze: funding-agnostic
                        s = -1.0
                    for j in np.where(hit)[0]:
                        ev_t.append(t); ev_edge.append(s * (CR[t, j] - beta[j] * mkt[t]))
                if len(ev_edge) < 20:
                    print(f"{side:>5} {thr:>5.0%} {H:>2} {len(ev_edge):>7}  (too few)"); continue
                ev_t = np.array(ev_t); ev_edge = np.array(ev_edge)
                up = np.unique(ev_t)
                per = np.array([ev_edge[ev_t == t].mean() for t in up])
                cT = per.mean() / (per.std(ddof=1) / np.sqrt(len(per))) if len(per) > 1 and per.std() > 0 else 0.0
                ci = block_ci(per)
                print(f"{side:>5} {thr:>5.0%} {H:>2} {len(ev_edge):>7} {len(up):>7} {ev_edge.mean():>+10.2%} "
                      f"{ev_edge.mean()-TAKER_RT:>+8.2%} {np.median(ev_edge):>+8.2%} {(ev_edge>0).mean():>5.0%} "
                      f"{cT:>+7.2f} [{ci[0]:>+6.2%},{ci[1]:>+6.2%}]")
    print("\n  edge/trade = beta-adj market-neutral pnl per event (the period-mean IS the H-058 basket).")
    print("  down confirms H-042. up (squeeze fade) tests whether forced flow is a GENERAL both-sided principle.")
    print("  Real ONLY if net>0, CI excludes 0, clustT>2, periods>100.")


if __name__ == "__main__":
    main()
