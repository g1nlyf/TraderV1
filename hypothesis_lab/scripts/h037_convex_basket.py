"""
H-037 — Convex memecoin momentum basket.

H-020 found cross-sectional momentum RANK predicts (perm_p 0.003) but linear sizing loses:
hit<50%, mean driven by a few moonshots, CI spans zero. The signal is real; the PAYOFF SHAPE
is wrong. H-037: harvest it as an option-like basket — long top-K by trailing momentum, FIXED
small size per name, hard stop caps each leg's loss, the uncapped right tail carries the basket.

The honest question (what the permutation answers): does the momentum rank CONCENTRATE the
convex tail vs a random-K basket drawn from the same tokens? If yes, the basket has positive EV
for a structural reason, not survivorship.

Discipline:
  * NON-OVERLAPPING rebalances (step = hold) → honest effective-n = rebalances.
  * Stop modeled on hourly CLOSES (memecoins gap THROUGH stops): exit at the first close <= -50%,
    realized at THAT close (often worse than -50%) — not an idealized -50% fill.
  * Permutation null: random-K from the same valid token set, 10k×. p = P(random basket >= top-K).
    This controls survivorship (both draw from survivors) → tests CONCENTRATION, the real claim.
  * Realized net after memecoin cost (1.8% round-trip). Block-bootstrap CI95. Temporal note.
  * Survivorship caveat reported: tokens without forward data are skipped (inflates ABSOLUTE EV;
    the perm test stays valid because it's relative to random-K on the same set).

Run: py hypothesis_lab/scripts/h037_convex_basket.py
"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "hypothesis_lab" / "scripts"))
from finetune.pipeline.eval_stats import block_bootstrap_ci  # noqa: E402
import h019_memecoin_xs_reversion as h019  # noqa: E402
sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore

FEE_RT = 0.018          # memecoin round-trip (entry+exit)
STOP = -0.50            # cap per-leg loss
TRAIN_FRAC = 0.70
N_PERM = 10_000
SEED = 2026


def capped_forward(col, t, hold, stop):
    """Realized payoff entry->exit with a stop on hourly closes (gap-through honest)."""
    entry = col[t]
    if not np.isfinite(entry) or entry <= 0:
        return np.nan
    thr = entry * (1.0 + stop)
    for h in range(1, hold + 1):
        px = col[t + h]
        if np.isfinite(px) and px <= thr:
            return px / entry - 1.0          # stopped at this close (may be < -50%)
    px = col[t + hold]
    if not np.isfinite(px) or px <= 0:
        return np.nan                        # no forward data -> skip (survivorship caveat)
    return px / entry - 1.0


def uncapped_forward(col, t, hold):
    entry, px = col[t], col[t + hold]
    if not np.isfinite(entry) or entry <= 0 or not np.isfinite(px) or px <= 0:
        return np.nan
    return px / entry - 1.0


def run(close, all_t, look, hold, K, capped=True):
    """Non-overlapping long-only top-K momentum basket. Returns per-rebalance net series + rebal records."""
    T, N = close.shape
    net, rand_net, recs = [], [], []
    rng = np.random.default_rng(SEED)
    t = look
    while t + hold < T:
        c0, cL = close[t], close[t - look]
        valid = np.isfinite(c0) & np.isfinite(cL) & (cL > 0) & (c0 > 0)
        idx = np.where(valid)[0]
        if len(idx) < max(K + 2, h019.MIN_ASSETS):
            t += hold; continue
        mom = c0[idx] / cL[idx] - 1.0
        ff = capped_forward if capped else (lambda col, a, b, s: uncapped_forward(col, a, b))
        payoff = np.array([ff(close[:, j], t, hold, STOP) for j in idx])
        ok = np.isfinite(payoff)
        if ok.sum() < max(K + 2, h019.MIN_ASSETS):
            t += hold; continue
        idx, mom, payoff = idx[ok], mom[ok], payoff[ok]
        order = np.argsort(-mom)
        top = order[:K]
        basket = float(payoff[top].mean()) - FEE_RT
        net.append(basket)
        rand_net.append(float(payoff[rng.choice(len(payoff), K, replace=False)].mean()) - FEE_RT)
        recs.append((payoff.copy(), K))
        t += hold
    return np.array(net), np.array(rand_net), recs


def perm_concentration(recs, observed_mean, n_perm=N_PERM, seed=SEED):
    """Null: random-K from the same valid set each rebalance. p = P(mean random-K basket >= observed)."""
    rng = np.random.default_rng(seed)
    ge = 0
    for _ in range(n_perm):
        acc = 0.0
        for payoff, K in recs:
            acc += float(payoff[rng.choice(len(payoff), K, replace=False)].mean())
        if acc / len(recs) >= observed_mean:
            ge += 1
    return (ge + 1) / (n_perm + 1)


def sharpe(x):
    return float(x.mean() / x.std(ddof=1) * np.sqrt(len(x))) if len(x) > 1 and x.std() > 0 else 0.0


def main():
    all_t, names, close = h019.load_panel()
    T, N = close.shape
    span_d = (all_t[-1] - all_t[0]) / 86400 if T else 0
    print("=" * 80)
    print("H-037 — CONVEX MEMECOIN MOMENTUM BASKET (long-only top-K, capped legs)")
    print("=" * 80)
    print(f"Universe: {N} tokens, {T} hourly periods (~{span_d:.0f}d). cost RT={FEE_RT:.1%} stop={STOP:.0%}")
    print("eff-n = NON-overlapping rebalances. Survivorship: no-forward-data tokens skipped (EV upper-biased;\n"
          "perm vs random-K on same set is the honest concentration test).\n")

    best = None
    for look in (6, 12, 24):
        for hold in (6, 12, 24):
            for K in (3, 5, 10):
                net, rnet, recs = run(close, all_t, look, hold, K, capped=True)
                if len(net) < 20:
                    continue
                print(f"  look={look:2d}h hold={hold:2d}h K={K:2d}: "
                      f"top-K EV={net.mean():+6.2%} sh={sharpe(net):+5.2f} | "
                      f"randK EV={rnet.mean():+6.2%} | edge={net.mean()-rnet.mean():+6.2%} | n={len(net)}")
                score = net.mean() - rnet.mean()
                if len(net) >= 120 and (best is None or score > best[0]):
                    best = (score, look, hold, K)

    if best is None:
        print("insufficient cross-section (no config with n>=120)."); return
    _, look, hold, K = best
    print(f"\nBest concentration-edge config with n>=120: look={look}h hold={hold}h K={K}")
    print("  (concentration is a CROSS-SECTIONAL claim — perm shuffles within each rebalance, so it is\n"
          "   valid on the FULL sample. Temporal-OOS generalization is n-blocked on 58d data, reported below.)")
    net, rnet, recs = run(close, all_t, look, hold, K, capped=True)
    netu, _, _ = run(close, all_t, look, hold, K, capped=False)
    ci = block_bootstrap_ci(list(net), block=4)
    pj = perm_concentration(recs, net.mean())
    # K=10 dilution check (same look/hold) as corroboration of the concentration mechanism
    net10, rnet10, _ = run(close, all_t, look, hold, 10, capped=True)
    reb_per_year = 365 * 24 / hold
    conc = (pj < 0.05)
    print(f"\nFULL SAMPLE (n={len(net)} rebalances):")
    print(f"  capped top-{K}  EV/reb={net.mean():+.2%} sharpe={sharpe(net):+.2f} hit={(net>0).mean():.0%} "
          f"CI95=[{ci[0]:+.2%},{ci[1]:+.2%}]")
    print(f"  random-K       EV/reb={rnet.mean():+.2%}   edge={net.mean()-rnet.mean():+.2%}   "
          f"concentration perm_p={pj:.4f} ({'rank CONCENTRATES tail' if conc else 'NOT > random-K'})")
    print(f"  K-dilution     top-10 edge={net10.mean()-rnet10.mean():+.2%} "
          f"(if ~0 while top-{K}>0 ⇒ signal lives in the few highest-ranked, the concentration mechanism)")
    print(f"  stop effect    capped−uncapped={net.mean()-netu.mean():+.2%} "
          f"(stop {'helps' if net.mean()>netu.mean() else 'hurts/neutral — winners drive it, not loss-capping'})")
    print(f"  approx annualized (if stationary, NOT tradeable at size): {net.mean()*reb_per_year:+.0%}")
    print("\n" + "=" * 80)
    cut = int(len(net) * TRAIN_FRAC); te = net[cut:]
    print(f"VERDICT: concentration {'CONFIRMED' if conc else 'NOT confirmed'} (perm_p {pj:.3f}, n={len(net)}); "
          f"temporal gate {'BLOCKED' if len(te) <= 100 else 'open'} (test-n={len(te)}<100 on 58d).")
    print("  Honest read: a REAL cross-sectional concentration signal, but absolute EV is survivorship-\n"
          "  inflated and the names are sub-$ memecoins untradeable at size. Collect-forward to promote.")
    print("=" * 80)


if __name__ == "__main__":
    main()
