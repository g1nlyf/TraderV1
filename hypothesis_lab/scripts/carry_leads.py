"""
Session 2 carry leads — H-024, H-021, H-022 in one shared harness.

All three share the cached funding panel + funding_harvest engines, so they run inline
(no cold re-derivation). Each is scored on REALIZED payoff with honest effective-n:
  H-024 new-listing funding decay : eff n = distinct in-window listings (rare → small n)
  H-021 persistence-selected carry: period series, block-bootstrap CI (autocorrelation-aware)
  H-022 cross-venue agreement gate: same, plus n_active after the gate

Run: py hypothesis_lab/scripts/carry_leads.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "finetune" / "pipeline"))
sys.path.insert(0, str(ROOT / "hypothesis_lab" / "scripts"))
import funding_harvest as fh            # noqa: E402
import h013_tradeable_carry as h13      # noqa: E402  (reuse offline panel loader)

sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore

MAKER = 0.0001
PPY = fh.PERIODS_PER_YEAR               # 1095 (3 funding/day)
DAY_MS = 86_400_000
RNG = np.random.default_rng(2026)


def slice_panel(p, idx):
    br = p.get("basis_ret")
    return {"times": p["times"], "kept": [p["kept"][i] for i in idx],
            "binance": p["binance"][:, idx], "bybit": p["bybit"][:, idx],
            "btc": p["btc"], "basis_ret": (br[:, idx] if br is not None else None)}


# ===================================================================== H-024
def h024(panel, spot_names):
    print("\n" + "=" * 80)
    print("H-024 — NEW-LISTING FUNDING DECAY (harvest launch-hype crowding)")
    print("=" * 80)
    fb, kept, times = panel["binance"], panel["kept"], panel["times"]
    win_start = int(times.min())
    # detect genuinely-new in-window listings: first finite funding ts well after window open
    new = []
    for j, b in enumerate(kept):
        fin = np.where(np.isfinite(fb[:, j]))[0]
        if len(fin) < fh.MIN_PERIODS:
            continue
        first_t = int(times[fin[0]])
        if first_t > win_start + 14 * DAY_MS:            # caught the actual listing
            new.append((j, b, first_t))
    print(f"Genuinely new in-window listings (first funding > window_start+14d): {len(new)}")
    if len(new) < 5:
        print("  too few new listings to test."); return None

    def age_apr(j, first_t, lo_d, hi_d):
        col = fb[:, j]; fin = np.isfinite(col)
        age = (times - first_t) / DAY_MS
        m = fin & (age >= lo_d) & (age < hi_d)
        return (col[m].mean() * PPY, int(m.sum())) if m.any() else (np.nan, 0)

    buckets = [("d1-3", 0, 3), ("d4-7", 3, 7), ("d8-30", 7, 30), ("d31+", 30, 1e9)]
    print(f"\n  Funding APR by listing age (mean across {len(new)} new listings):")
    bucket_means = {}
    for name, lo, hi in buckets:
        vals = [age_apr(j, ft, lo, hi)[0] for j, _, ft in new]
        vals = [v for v in vals if np.isfinite(v)]
        bucket_means[name] = float(np.mean(vals)) if vals else float("nan")
        print(f"    {name:>6}: {bucket_means[name]:+7.1%}   (n_names={len(vals)})")

    # headline test: first-week (d1-7) vs mature (d31+), paired across names, permutation
    for N_label, N in (("d1-7", 7), ("d1-3", 3), ("d1-14", 14)):
        pairs = []
        spot_hedge_early = []
        for j, b, ft in new:
            col = fb[:, j]; fin = np.isfinite(col); age = (times - ft) / DAY_MS
            em = fin & (age >= 0) & (age < N)
            mm = fin & (age >= 31)
            if em.sum() < 3 or mm.sum() < 3:
                continue
            pairs.append((col[em].copy(), col[mm].copy()))
            if b in spot_names:
                spot_hedge_early.append(col[em].mean() * PPY)
        if len(pairs) < 5:
            print(f"\n  [{N_label}] too few paired names ({len(pairs)})."); continue
        diffs = np.array([e.mean() - m.mean() for e, m in pairs])
        obs = float(diffs.mean()) * PPY
        # permutation: relabel which periods are 'early' within each name's pooled funding
        ge = 0
        for _ in range(10000):
            nd = []
            for e, m in pairs:
                pool = np.concatenate([e, m]); RNG.shuffle(pool)
                nd.append(pool[:len(e)].mean() - pool[len(e):].mean())
            if np.mean(nd) * PPY >= obs:
                ge += 1
        perm_p = (ge + 1) / 10001
        early_apr = float(np.mean([e.mean() * PPY for e, _ in pairs]))
        mat_apr = float(np.mean([m.mean() * PPY for _, m in pairs]))
        hedge_apr = float(np.mean(spot_hedge_early)) if spot_hedge_early else float("nan")
        print(f"\n  [{N_label} vs d31+]  n_listings={len(pairs)}  "
              f"early_APR={early_apr:+.1%}  mature_APR={mat_apr:+.1%}  "
              f"excess={obs:+.1%}  perm_p={perm_p:.4f}")
        print(f"            hedgeable (has spot leg) early_APR={hedge_apr:+.1%}  "
              f"n_hedgeable={len(spot_hedge_early)}")
    print("\n  NOTE: effective-n = distinct listings (rare events). Even a real, large excess")
    print("  cannot clear the n>100 gate from this cache — it is collect-forward limited.")
    return bucket_means


# ===================================================================== H-021
def h021(panel):
    print("\n" + "=" * 80)
    print("H-021 — PERSISTENCE-SELECTED CARRY (pick names by funding sign-stability)")
    print("=" * 80)
    tp = fh.filter_tradeable(panel, min_cov=0.90)
    fb, kept, times = tp["binance"], tp["kept"], tp["times"]
    cut = int(len(times) * fh.TRAIN_FRAC)
    # persistence on TRAIN only (no lookahead): fraction of periods with positive funding
    persist = []
    for j in range(len(kept)):
        col = fb[:cut, j]; col = col[np.isfinite(col)]
        persist.append(col.mean() if False else float((col > 0).mean()) if len(col) else 0.0)
    persist = np.array(persist)
    order = np.argsort(-persist)
    K = 10
    top = order[:K]; bot = order[-K:]
    print(f"Tradeable universe: {len(kept)} names. Persistence (train, % periods funding>0):")
    print(f"  MOST persistent {K}: " + ", ".join(f"{kept[j]}({persist[j]:.0%})" for j in top))
    print(f"  LEAST persistent {K}: " + ", ".join(f"{kept[j]}({persist[j]:.0%})" for j in bot))

    def run(idx, tag):
        sub = slice_panel(tp, list(idx))
        ev = fh.evaluate(sub, "single", MAKER, use_basis=True)
        t = ev["test"]; lo, hi = ev["test_apr_ci95"]; v, _ = fh.verdict(ev)
        print(f"  {tag:<22} TEST apr={t['apr']:+.2%} sharpe={t['sharpe']:+.2f} "
              f"n={t['n']} CI95=[{lo:+.2%},{hi:+.2%}]  {v}")
        return t["apr"], t["sharpe"], (lo, hi), t["n"]

    print("\n  Carry (single EW, basis-aware, maker) on selected universes:")
    full = run(range(len(kept)), "ALL tradeable (29)")
    tp_top = run(top, "TOP-K persistence")
    tp_bot = run(bot, "BOTTOM-K persistence")
    # also: level-selected top-K (the H-13 loser) for contrast
    lvl = np.array([np.nanmean(fb[:cut, j]) for j in range(len(kept))])
    lvl_top = run(np.argsort(-lvl)[:K], "TOP-K by LEVEL (H-13)")
    return {"all": full, "persist_top": tp_top, "persist_bot": tp_bot, "level_top": lvl_top}


# ===================================================================== H-022
def _gated_carry_ew(panel, agree, span, fee, use_basis):
    """Equal-weight single-venue carry, positions gated to agreement periods."""
    fb = panel["binance"]; br = panel.get("basis_ret")
    T, N = fb.shape
    acc = np.zeros(T); cnt = np.zeros(T); active = np.zeros(T)
    for j in range(N):
        col = fb[:, j]
        if np.isfinite(col).sum() < fh.MIN_PERIODS:
            continue
        s = fh._ewma_sign_prev(col, span)
        pos = (s > 0).astype(float) * agree[:, j]              # hold only when agreed
        pnl = np.zeros(T); prev = 0.0
        for i in range(T):
            f = col[i] if np.isfinite(col[i]) else 0.0
            pr = (br[i, j] if (use_basis and br is not None and np.isfinite(br[i, j])) else 0.0)
            pnl[i] = pos[i] * (f + pr) - fee * 2.0 * abs(pos[i] - prev); prev = pos[i]
        a = np.isfinite(col)
        acc[a] += pnl[a]; cnt[a] += 1; active += (pos > 0)
    mask = cnt > 0; out = np.zeros(T); out[mask] = acc[mask] / cnt[mask]
    return out, active


def h022(panel):
    print("\n" + "=" * 80)
    print("H-022 — CROSS-VENUE AGREEMENT as carry quality filter")
    print("=" * 80)
    tp = fh.filter_tradeable(panel, min_cov=0.90)
    fb, fy = tp["binance"], tp["bybit"]
    T, N = fb.shape
    cut = int(T * fh.TRAIN_FRAC)
    both = np.isfinite(fb) & np.isfinite(fy)
    same_sign = np.sign(fb) == np.sign(fy)
    denom = np.maximum(np.abs(fb), np.abs(fy))
    with np.errstate(invalid="ignore"):
        close = np.abs(fb - fy) < 0.5 * denom                  # default thr
    span = 6

    def metr(pnl):
        te = pnl[cut:]
        m = fh.metrics(te); lo, hi = fh.block_bootstrap_ci(te)
        return m, (lo * PPY, hi * PPY)

    # baseline (no gate) vs agreement gate at thresholds
    base, _ = _gated_carry_ew(tp, np.ones((T, N)), span, MAKER, True)
    bm, bci = metr(base)
    print(f"  baseline (no gate)      TEST apr={bm['apr']:+.2%} sharpe={bm['sharpe']:+.2f} "
          f"n={bm['n']} CI95=[{bci[0]:+.2%},{bci[1]:+.2%}]")
    for thr in (0.2, 0.5, 1.0):
        with np.errstate(invalid="ignore"):
            agree = (both & same_sign & (np.abs(fb - fy) < thr * denom)).astype(float)
        gated, active = _gated_carry_ew(tp, agree, span, MAKER, True)
        gm, gci = metr(gated)
        frac = float(both.sum() and (both & same_sign & (np.abs(fb - fy) < thr * denom)).sum() / both.sum())
        print(f"  agree thr={thr:<3}           TEST apr={gm['apr']:+.2%} sharpe={gm['sharpe']:+.2f} "
              f"n={gm['n']} CI95=[{gci[0]:+.2%},{gci[1]:+.2%}]  (agree {frac:.0%} of both-venue periods)")
    return bm, bci


# ===================================================================== STACK
def _best_span_series(panel, engine, fee, use_basis):
    cut = int(len(panel["times"]) * fh.TRAIN_FRAC)
    best = (-1e9, fh.EWMA_SPANS[0])
    for span in fh.EWMA_SPANS:
        pnl, _ = fh.portfolio(panel, engine, span, fee, 10, use_basis)
        sh = fh.metrics(pnl[:cut])["sharpe"]
        if sh > best[0]:
            best = (sh, span)
    pnl, _ = fh.portfolio(panel, engine, best[1], fee, 10, use_basis)
    return pnl, cut, best[1]


def stack_test(panel):
    print("\n" + "=" * 80)
    print("STACK — level-fixed single carry  +  cross-venue maker spread (50/50 book)")
    print("=" * 80)
    tp = fh.filter_tradeable(panel, min_cov=0.90)
    cut = int(len(tp["times"]) * fh.TRAIN_FRAC)
    lvl = np.array([np.nanmean(tp["binance"][:cut, j]) for j in range(len(tp["kept"]))])
    top = np.argsort(-lvl)[:10]
    sub = slice_panel(tp, list(top))
    s1, _, sp1 = _best_span_series(sub, "single", MAKER, True)     # level-fixed single carry
    s2, _, sp2 = _best_span_series(panel, "xvenue", MAKER, False)  # cross-venue spread
    te1, te2 = s1[cut:], s2[cut:]
    comb = 0.5 * te1 + 0.5 * te2
    for nm, se in (("level-fixed single", te1), ("xvenue maker", te2), ("50/50 STACK", comb)):
        m = fh.metrics(se); lo, hi = fh.block_bootstrap_ci(se)
        print(f"  {nm:<20} apr={m['apr']:+.2%} sharpe={m['sharpe']:+.2f} maxDD={m['maxdd']:+.1%} "
              f"n={m['n']} CI95=[{lo*PPY:+.2%},{hi*PPY:+.2%}]")
    corr = float(np.corrcoef(te1, te2)[0, 1])
    print(f"  correlation(level, xvenue) = {corr:+.2f}  (lower = better diversification)")
    return comb


def _maxdd(series):
    eq = np.cumprod(1.0 + series)
    return float((eq / np.maximum.accumulate(eq) - 1.0).min())


def tail_stress(panel):
    """Bound the champion-candidate's left tail over the FULL 730d (the leverage gate)."""
    print("\n" + "=" * 80)
    print("TAIL STRESS — champion-candidate stack over FULL 730d (leverage gate)")
    print("=" * 80)
    tp = fh.filter_tradeable(panel, min_cov=0.90)
    cut = int(len(tp["times"]) * fh.TRAIN_FRAC)
    lvl = np.array([np.nanmean(tp["binance"][:cut, j]) for j in range(len(tp["kept"]))])
    top = np.argsort(-lvl)[:10]
    sub = slice_panel(tp, list(top))
    s1, _, _ = _best_span_series(sub, "single", MAKER, True)
    s2, _, _ = _best_span_series(panel, "xvenue", MAKER, False)
    stack = 0.5 * s1 + 0.5 * s2
    full_apr = float(stack.mean()) * PPY
    oos_apr = float(stack[cut:].mean()) * PPY
    full_dd, oos_dd = _maxdd(stack), _maxdd(stack[cut:])
    # worst rolling windows (1 period=8h, day=3, week=21)
    def worst_roll(s, w):
        if len(s) < w:
            return float(s.sum())
        c = np.convolve(s, np.ones(w), "valid")
        return float(c.min())
    print(f"  span={len(stack)} periods (~{len(stack)/3:.0f}d). "
          f"Selection on first 70% (in-sample); tail uses FULL history (conservative).")
    print(f"  APR: full-history {full_apr:+.2%} | OOS {oos_apr:+.2%}")
    print(f"  maxDD: full-history {full_dd:+.2%} | OOS {oos_dd:+.2%}")
    print(f"  worst 8h={stack.min():+.3%}  worst day={worst_roll(stack,3):+.3%}  "
          f"worst week={worst_roll(stack,21):+.3%}")
    print(f"\n  Leverage to a target maxDD budget (using full-history maxDD {full_dd:+.2%}):")
    base_dd = abs(full_dd) if full_dd < 0 else 0.001
    for budget in (0.02, 0.05, 0.10):
        lev = budget / base_dd
        print(f"    budget maxDD −{budget:.0%}: leverage {lev:4.1f}x → levered APR "
              f"{full_apr*lev:+.1%} (OOS {oos_apr*lev:+.1%})")
    print("\n  CAVEAT: 730d may still lack a true tail event (FTX/LUNA-scale basis blowout,")
    print("  exchange funding clamp). Treat levered APR as an UPPER bound; real sizing needs a")
    print("  stress add-on for the un-sampled tail. This is the gate, not a green light.")
    return full_apr, full_dd, oos_apr, oos_dd


def main():
    panel, spot_names, bybit_names = h13.load_offline_panel()
    print(f"Panel: {len(panel['kept'])} names, {len(panel['times'])} periods. "
          f"spot-leg names={len(spot_names)} bybit names={len(bybit_names)}")
    h024(panel, spot_names)
    h021(panel)
    h022(panel)
    stack_test(panel)
    tail_stress(panel)
    print("\n" + "=" * 80)
    print("DONE — transcribe verdicts to H-024 / H-021 / H-022 files.")
    print("=" * 80)


if __name__ == "__main__":
    main()
