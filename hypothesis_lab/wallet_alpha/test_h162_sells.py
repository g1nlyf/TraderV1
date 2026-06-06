"""H-162 — Distribution (sell) clusters: are smart-wallet sells/rotations more predictive than buys?

For SELL-cluster events (>=K distinct wallets SELL a token within W), test:
  1. Long-side forward EV (does the token keep falling after coordinated selling? = forced-flow / H-053).
  2. SHORT-side payoff (-price change - cost) — is coordinated distribution a tradeable down signal?
  3. Does wallet quality sharpen the sell signal?
  4. Asymmetry vs buy-clusters (ties to the locked truth: forced selling reverts, FOMO continues).

Shorting memecoins is usually impractical (no borrow) — a passing short here is an AVOID/early-exit
signal, flagged as such, not a directly capturable long-book alpha.

Run: py hypothesis_lab/wallet_alpha/test_h162_sells.py
"""
from __future__ import annotations

import numpy as np

import wa_common as wa
import wa_eval as ev
from build_events import FEATURES, TOKEN_ONLY

wa.ensure_utf8()


def short_payoff(raw_ret):
    """raw_ret stored = price_change - COST_RT. Short payoff = -(price_change) - COST_RT."""
    price_change = raw_ret + wa.COST_RT
    return ev.cap(-price_change - wa.COST_RT)


def run_h(H):
    print("=" * 100)
    print(f"H-162 SELL/DISTRIBUTION CLUSTERS  |  horizon H={H}s ({H//60}m)")
    print("=" * 100)
    meta, evs, capped, raw = ev.load("sell", H)
    n = len(evs)
    tr, te = ev.temporal_split(n, 0.6)
    base_long = ev.describe(capped[te], raw[te])
    short_caps = np.array([short_payoff(r) for r in raw])
    base_short = float(short_caps[te].mean())
    print(f"events={n} train={len(tr)} test={len(te)}")
    print(f"  LONG-side after sell-cluster : EV_capped={base_long['ev_capped']:+.3%} "
          f"median_raw={base_long['median_raw']:+.3%} hit={base_long['hit']:.3f}")
    print(f"  SHORT-side payoff (=-Δ-cost) : EV_capped={base_short:+.3%}")
    print(f"  => coordinated selling {'PRECEDES further DROP (down-signal)' if base_long['ev_capped']<0 else 'precedes bounce'}.")

    results = []
    # 1. is the long-side significantly negative (down-signal real, non-random)?
    r = ev.gate(capped[te], np.ones(len(te), bool), "ALL sell-clusters (long)")
    results.append(r); print("\n[A] " + ev.fmt_gate(r))

    # 2. short-side gate (tradeable IF shortable)
    rs = ev.gate(short_caps[te], np.ones(len(te), bool), "ALL sell-clusters (SHORT)")
    results.append(rs); print("    " + ev.fmt_gate(rs) + "   [short = AVOID/exit signal, not long-book alpha]")

    # 3. does wallet quality sharpen the DOWN signal? fire shorts on high-wq sell-clusters
    print("\n[B] wallet-quality-sharpened SHORT (fire on above-median quality sells):")
    for feat in ["wq_mean_pnl", "wq_frac_profitable", "wq_total_prior_trades"]:
        xtr = np.array([float(evs[i].get(feat, 0)) for i in tr])
        xte = np.array([float(evs[i].get(feat, 0)) for i in te])
        mask = xte > np.quantile(xtr, 0.5)
        if mask.sum() < 20:
            continue
        r = ev.gate(short_caps[te], mask, f"SHORT|{feat}>med")
        r["rho_long"] = ev.spearman(xte, capped[te])
        results.append(r)
        print(ev.fmt_gate(r) + f"  rho(quality,longret)={r['rho_long']:+.2f}")

    # 4. model short selection
    print("\n[C] MODEL short selection (token+wq GBM, fire top-50% most-negative predicted):")
    ytr = capped[tr]
    Xtr, Xte = ev.matrix([evs[i] for i in tr], FEATURES), ev.matrix([evs[i] for i in te], FEATURES)
    sc, _ = ev.gbm_scores(Xtr, ytr, Xte)          # predict LONG ret; short the most-negative
    mask = sc <= np.quantile(sc, 0.5)
    r = ev.gate(short_caps[te], mask, "SHORT|gbm bottom50%")
    results.append(r); print(ev.fmt_gate(r))

    passes = [r for r in results if r["verdict"] == "PASS"]
    return {"H": H, "base_long": base_long, "base_short": base_short, "passes": passes, "results": results}


def compare_buy_sell():
    print("\n" + "=" * 100)
    print("ASYMMETRY: forward return after BUY-cluster vs SELL-cluster (test folds, H=1800)")
    print("=" * 100)
    for side in ["buy", "sell"]:
        _, evs, capped, raw = ev.load(side, 1800)
        _, te = ev.temporal_split(len(evs), 0.6)
        d = ev.describe(capped[te], raw[te])
        print(f"  {side:4s}-cluster -> forward EV_capped={d['ev_capped']:+.3%} median_raw={d['median_raw']:+.3%} hit={d['hit']:.3f} n={d['n']}")
    print("  (Locked truth check: forced selling reverts / FOMO continues — H-042/H-053.)")


def main():
    out = [run_h(1800), run_h(3600)]
    compare_buy_sell()
    print("\n" + "=" * 100)
    total = sum(len(o["passes"]) for o in out)
    print(f">>> H-162 {'has a gate-clearing rule (see above; check if short is capturable)' if total else 'FAILS the long-book gate. Sell-clusters carry a real DOWN signal but it is only an avoid/exit filter, not capturable long alpha (shorting memecoins impractical).'}")
    return out


if __name__ == "__main__":
    main()
