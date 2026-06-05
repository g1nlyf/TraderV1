"""
H-019 — memecoin CROSS-SECTIONAL reversion, dollar-neutral WITHIN the memecoin cross-section.

The corrected H-15. H-15's +17.59% was SOL-down recovery beta (long-biased, 91% of events
in one regime, eff n≈6 episodes). This removes the common factor entirely: at each rebalance,
go long the biggest losers / short the biggest winners AMONG memecoins, dollar-neutral, so the
market move (SOL/regime) cancels by construction. If memecoins mean-revert cross-sectionally
beyond the common move, this isolates it. If it's just the regime, this returns ~0 — which is
the honest answer H-15 couldn't give.

Discipline (fixes the exact things that broke H-15 and C-001):
  * NON-OVERLAPPING rebalances (step = hold) — every event independent in time, no eff-n inflation.
  * Cross-sectional permutation null: shuffle forward returns ACROSS tokens within each rebalance
    (asks "does the loser/winner RANK predict, beyond the common move?"). Robust to time-clustering.
  * REALIZED net pnl after memecoin cost (1.8% round-trip => 0.9%/side on turnover). No win-rate proxy.
  * Temporal OOS split (params chosen on train, reported on test). Block-bootstrap CI95.

Run: py hypothesis_lab/scripts/h019_memecoin_xs_reversion.py
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from finetune.pipeline.eval_stats import block_bootstrap_ci  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore

DB = ROOT / "WalletScarper" / "data" / "stage2_foundation.sqlite3"
SRC = "geckoterminal:hour1"
MINLEN = 60
MIN_ASSETS = 6
TRAIN_FRAC = 0.70
FEE_ONEWAY = 0.009                  # 1.8% round-trip / 2
LOOKS = [3, 6, 12, 24]
HOLDS = [6, 12, 24]
N_PERM = 20_000
SEED = 2026


def load_panel():
    con = sqlite3.connect(str(DB)); con.row_factory = sqlite3.Row
    rows = con.execute("SELECT token_mint, ts, close FROM token_ohlcv WHERE source=? "
                       "ORDER BY token_mint, ts", (SRC,)).fetchall()
    con.close()
    ser = {}
    for r in rows:
        ser.setdefault(r["token_mint"], []).append((int(r["ts"]), float(r["close"])))
    ser = {k: v for k, v in ser.items() if len(v) >= MINLEN}
    names = sorted(ser)
    all_t = np.array(sorted({t for v in ser.values() for t, _ in v}), dtype=np.int64)
    row = {int(t): i for i, t in enumerate(all_t)}
    close = np.full((len(all_t), len(names)), np.nan)
    for j, n in enumerate(names):
        for t, c in ser[n]:
            close[row[int(t)], j] = c
    return all_t, names, close


def backtest(close, look, hold, fee, mode="reversion"):
    """Non-overlapping dollar-neutral XS reversion/momentum. Returns (rebalance_idx, net_pnl, pairs)."""
    T, N = close.shape
    rb, net = [], []
    pairs = []                      # (weights, fwd) per rebalance for the permutation null
    prev_w = np.zeros(N)
    t = look
    while t + hold < T:
        c0, cL, cH = close[t], close[t - look], close[t + hold]
        valid = np.isfinite(c0) & np.isfinite(cL) & np.isfinite(cH) & (cL > 0) & (c0 > 0)
        if valid.sum() < MIN_ASSETS:
            t += hold; continue
        idx = np.where(valid)[0]
        ret = c0[idx] / cL[idx] - 1.0
        fwd = cH[idx] / c0[idx] - 1.0
        x = ret - ret.mean()
        wv = -x if mode == "reversion" else x   # reversion: long losers; momentum: long winners
        g = np.abs(wv).sum()
        if g <= 1e-12:
            t += hold; continue
        w = np.zeros(N); w[idx] = wv / g            # gross 1, dollar-neutral (Σw≈0)
        gross = float(np.dot(w[idx], fwd))
        cost = fee * float(np.abs(w - prev_w).sum())
        rb.append(t); net.append(gross - cost); pairs.append((w[idx].copy(), fwd.copy()))
        prev_w = w
        t += hold
    return np.array(rb), np.array(net), pairs


def perm_p_xsection(pairs, observed_mean, n_perm=N_PERM, seed=SEED):
    """Null: shuffle fwd returns across tokens within each rebalance (break the rank↔return
    link, keep the common move). p = P(shuffled mean >= observed)."""
    rng = np.random.default_rng(seed)
    ge = 0
    for _ in range(n_perm):
        acc = 0.0
        for w, fwd in pairs:
            acc += float(np.dot(w, rng.permutation(fwd)))
        if acc / len(pairs) >= observed_mean:
            ge += 1
    return (ge + 1) / (n_perm + 1)


def sharpe(x):
    return float(x.mean() / x.std(ddof=1) * np.sqrt(len(x))) if len(x) > 1 and x.std() > 0 else 0.0


def main():
    mode = "momentum" if "--momentum" in sys.argv else "reversion"
    all_t, names, close = load_panel()
    T, N = close.shape
    span_d = (all_t[-1] - all_t[0]) / 86400 if T else 0
    alive = np.isfinite(close).sum(axis=1)
    print("=" * 78)
    print(f"H-019/H-020 — memecoin cross-sectional {mode.upper()} (dollar-neutral within memecoins)")
    print("=" * 78)
    print(f"Universe: {N} tokens, {T} hourly periods (~{span_d:.0f}d). "
          f"Median tokens alive/hour: {int(np.median(alive))} (max {alive.max()})")

    # choose (look,hold) by TRAIN sharpe, report on TEST
    cut_t = all_t[int(T * TRAIN_FRAC)]
    best = None
    for look in LOOKS:
        for hold in HOLDS:
            rb, net, _ = backtest(close, look, hold, FEE_ONEWAY, mode)
            if len(net) < 20:
                continue
            tr = net[all_t[rb] < cut_t]
            if len(tr) < 10:
                continue
            sh = sharpe(tr)
            if best is None or sh > best[0]:
                best = (sh, look, hold)
    if best is None:
        print("insufficient cross-section for any (look,hold)."); return
    _, look, hold = best
    rb, net, pairs = backtest(close, look, hold, FEE_ONEWAY, mode)
    tr_mask = all_t[rb] < cut_t
    tr, te = net[~np.isnan(net)][tr_mask], net[~np.isnan(net)][~tr_mask]
    te_pairs = [p for p, m in zip(pairs, ~tr_mask) if m]
    print(f"\nBest config (TRAIN sharpe): look={look}h hold={hold}h  "
          f"rebalances train={len(tr)} test={len(te)}")

    # gross (no cost) vs net, to see how much cost eats
    rb_g, net_g, _ = backtest(close, look, hold, 0.0, mode)
    te_g = net_g[all_t[rb_g] >= cut_t]
    print(f"TEST gross EV/rebalance = {te_g.mean():+.3%}  (before cost)")
    print(f"TEST net   EV/rebalance = {te.mean():+.3%}  sharpe={sharpe(te):+.2f}  "
          f"hit={ (te>0).mean():.1%}  n={len(te)}")
    ci = block_bootstrap_ci(list(te), block=6)
    print(f"TEST net CI95 (block-bootstrap) = [{ci[0]:+.3%}, {ci[1]:+.3%}]")
    pj = perm_p_xsection(te_pairs, te_g.mean() if len(te_g) else 0.0)
    print(f"cross-sectional perm_p (gross, 20k) = {pj:.4f}  "
          f"({'rank predicts' if pj < 0.05 else 'rank does NOT beat the common move'})")

    # annualized rough (rebalances per year * mean)
    reb_per_year = (365 * 24 / hold)
    print(f"\napprox annualized net (if stationary): {te.mean()*reb_per_year:+.0%} "
          f"({reb_per_year:.0f} rebalances/yr)")

    gate = (te.mean() > 0 and ci[0] > 0 and pj < 0.05)
    print("\n" + "=" * 78)
    print(f"VERDICT: {'PASS' if gate else 'FAIL'} — net EV {te.mean():+.3%}/rebalance, "
          f"CI95 {'excludes' if ci[0] > 0 else 'spans'} zero, perm_p {pj:.3f}.")
    if not gate and te_g.mean() > 0:
        print(f"Gross reversion exists ({te_g.mean():+.3%}/rebalance) but "
              f"{'the cross-sectional rank adds nothing over the common move' if pj >= 0.05 else 'cost eats it'}.")
    print("=" * 78)


if __name__ == "__main__":
    main()
