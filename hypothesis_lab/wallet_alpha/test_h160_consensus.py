"""H-160 — Point-in-time wallet-consensus quality alpha.

Question: among cluster-buy events (>=K distinct wallets buy a token within W), does selecting by
POINT-IN-TIME wallet quality (realized pre-t PnL / win-rate of the participants) produce forward
intraday EV that (a) clears the gate and (b) beats naive-copy AND token-only-context baselines, OOS?

This is the honest replacement for copy_engine.py (which was in-sample + survivorship). Wallet quality
here is recomputed from pre-event completed round-trips only — never the look-ahead leaderboard.

Run: py hypothesis_lab/wallet_alpha/test_h160_consensus.py
"""
from __future__ import annotations

import numpy as np

import wa_common as wa
import wa_eval as ev
from build_events import FEATURES, TOKEN_ONLY, WQ_ONLY

wa.ensure_utf8()


def run_h(H: int):
    print("=" * 100)
    print(f"H-160 CONSENSUS-QUALITY  |  horizon H={H}s ({H//60}m)")
    print("=" * 100)
    meta, evs, capped, raw = ev.load("buy", H)
    n = len(evs)
    tr, te = ev.temporal_split(n, 0.6)
    ov = ev.wallet_overlap(evs, tr, te)
    print(f"events={n}  train={len(tr)} test={len(te)}  wallet-overlap(test∩train)/test={ov:.1%}")

    base = ev.describe(capped[te], raw[te])
    print(f"\nBASELINE (naive-copy = buy EVERY cluster, test fold):")
    print(f"  n={base['n']}  EV_capped={base['ev_capped']:+.3%}  median_raw={base['median_raw']:+.3%}  hit={base['hit']:.3f}")
    print(f"  => naive cluster-copy is {'PROFITABLE' if base['ev_capped']>0 else 'A LOSER'} before selection.")

    ytr = capped[tr]
    results = []

    # ---- interpretable univariate wallet-quality rules (fire on test, threshold from TRAIN) ----
    print("\n[A] INTERPRETABLE wallet-quality selection rules (threshold learned on train):")
    for feat in ["wq_mean_pnl", "wq_max_pnl", "wq_frac_profitable", "wq_mean_winrate", "wq_total_prior_trades"]:
        xtr = np.array([float(evs[i].get(feat, 0)) for i in tr])
        xte = np.array([float(evs[i].get(feat, 0)) for i in te])
        thr = np.quantile(xtr, 0.5)             # fire on above-train-median quality
        mask = xte > thr
        if mask.sum() < 5:
            continue
        r = ev.gate(capped[te], mask, f"{feat}>med")
        r["spearman_te"] = ev.spearman(xte, capped[te])
        results.append(r)
        print(ev.fmt_gate(r) + f"  rho={r['spearman_te']:+.2f}")

    # ---- models: token-only vs +wallet-quality (ablation), GBM + linear ----
    print("\n[B] MODELS (train->test, fire on top-50% predicted EV):")
    for name, feats in [("token-only", TOKEN_ONLY), ("token+wq", FEATURES), ("wq-only", WQ_ONLY)]:
        Xtr, Xte = ev.matrix([evs[i] for i in tr], feats), ev.matrix([evs[i] for i in te], feats)
        for mdl, fn in [("gbm", ev.gbm_scores), ("linear", ev.linear_scores)]:
            sc, _ = fn(Xtr, ytr, Xte)
            mask = ev.select_top(sc, 0.5)
            r = ev.gate(capped[te], mask, f"{name}/{mdl} top50%")
            r["spearman_te"] = ev.spearman(sc, capped[te])
            results.append(r)
            print(ev.fmt_gate(r) + f"  rho={r['spearman_te']:+.2f}")

    # ---- ablation verdict: does wq beat token-only on OOS rank-correlation + fired-EV? ----
    print("\n[C] ABLATION (does wallet quality ADD over token-only context?):")
    def best(prefix):
        cand = [r for r in results if r["label"].startswith(prefix) and r.get("k", 0) > 0]
        return max(cand, key=lambda r: r["rule_ev"]) if cand else None
    bt, bw = best("token-only"), best("token+wq")
    if bt and bw:
        print(f"  token-only best fired-EV={bt['rule_ev']:+.3%} (rho {bt['spearman_te']:+.2f})")
        print(f"  token+wq   best fired-EV={bw['rule_ev']:+.3%} (rho {bw['spearman_te']:+.2f})")
        print(f"  Δ(wq adds) = {bw['rule_ev']-bt['rule_ev']:+.3%} fired-EV, "
              f"{bw['spearman_te']-bt['spearman_te']:+.2f} rho")

    passes = [r for r in results if r["verdict"] == "PASS"]
    print(f"\nVERDICT H={H}: {len(passes)} rule(s) clear the full gate (EV>2% ∧ perm<0.05 ∧ CI>0 ∧ n>100).")
    for r in passes:
        print("   PASS:", ev.fmt_gate(r))
    if not passes:
        print("   No rule clears the gate. Wallet-consensus quality does NOT produce capturable intraday alpha here.")
    return {"H": H, "base": base, "results": results, "passes": passes, "overlap": ov}


def main():
    out = [run_h(1800), run_h(3600)]
    print("\n" + "=" * 100)
    print("H-160 SUMMARY")
    print("=" * 100)
    for o in out:
        b = o["base"]
        print(f"  H={o['H']//60}m: naive-copy EV={b['ev_capped']:+.2%} (hit {b['hit']:.2f}) | "
              f"gate-passes={len(o['passes'])} | wallet-overlap={o['overlap']:.0%}")
    total = sum(len(o["passes"]) for o in out)
    print(f"\n  >>> H-160 {'has a gate-clearing rule — INVESTIGATE/PROMOTE' if total else 'FAILS the gate at every horizon — wallet-quality selection is not capturable intraday alpha on this data.'}")
    return out


if __name__ == "__main__":
    main()
