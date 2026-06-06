"""H-161 — Wallet archetype mix as a cluster-quality signal.

Define archetypes by UNSUPERVISED clustering of label-free wallet behavior (trade count, token breadth,
size, hold time, churn) — KMeans, no forward labels touched. Then test: does the archetype MIX of a
cluster's participants (e.g. "smart swing wallets" vs "bots/snipers") predict forward intraday return OOS,
and beat the token-only baseline + the gate?

Caveat (documented): archetype is computed over the full session, a mild look-ahead on a wallet's own
later trades. But archetype is a behavioral TYPE (~stationary) and label-INDEPENDENT, so if it still
fails the gate the negative is robust (the leak could only help).

Run: py hypothesis_lab/wallet_alpha/test_h161_archetype.py
"""
from __future__ import annotations

import json
import numpy as np

import wa_common as wa
import wa_eval as ev
from build_events import TOKEN_ONLY

wa.ensure_utf8()
K_ARCH = 5


def build_archetypes():
    prof = json.loads((wa.CACHE / "wallet_profiles.json").read_text(encoding="utf-8"))
    wallets = list(prof.keys())
    def feat(p):
        hold = p["median_hold_s"] if p["median_hold_s"] is not None else p["active_s"]
        sells_ratio = p["n_sells"] / max(p["n_trades"], 1)
        return [np.log1p(p["n_trades"]), np.log1p(p["n_tokens"]), np.log1p(max(p["avg_sol"], 0)),
                np.log1p(max(hold, 0)), p["fast_frac"], sells_ratio]
    X = np.array([feat(prof[w]) for w in wallets])
    mu, sd = X.mean(0), X.std(0) + 1e-9
    Xs = (X - mu) / sd
    from sklearn.cluster import KMeans
    km = KMeans(n_clusters=K_ARCH, random_state=2026, n_init=10).fit(Xs)
    lab = km.labels_
    # name clusters from centroids (un-standardized)
    cent = km.cluster_centers_ * sd + mu
    names = {}
    for c in range(K_ARCH):
        nt, ntok, sol, hold, fast, sells = cent[c]
        nt, ntok, sol, hold = np.expm1([nt, ntok, sol, hold])
        if nt > 50 and fast > 0.5:
            nm = "bot"
        elif hold < 120 and fast > 0.3:
            nm = "sniper"
        elif sells < 0.25:
            nm = "hodler"
        elif ntok > 8:
            nm = "rotator"
        else:
            nm = "swing"
        names[c] = f"{nm}#{c}"
        print(f"  archetype {names[c]:10s}: n_wallets={int((lab==c).sum()):6d} "
              f"trades~{nt:.0f} tokens~{ntok:.1f} sol~{sol:.2f} hold~{hold:.0f}s fast={fast:.2f} sells={sells:.2f}")
    w2c = {w: int(lab[i]) for i, w in enumerate(wallets)}
    return w2c, names


def arch_mix(evs, w2c, names):
    cols = [names[c] for c in range(K_ARCH)] + ["unknown"]
    rows = []
    for e in evs:
        cnt = np.zeros(K_ARCH + 1)
        for w in e["wallets"]:
            c = w2c.get(w)
            cnt[c if c is not None else K_ARCH] += 1
        rows.append(cnt / max(cnt.sum(), 1))
    return np.array(rows), cols


def run_h(H, w2c, names):
    print("=" * 100)
    print(f"H-161 ARCHETYPE MIX  |  horizon H={H}s ({H//60}m)")
    print("=" * 100)
    meta, evs, capped, raw = ev.load("buy", H)
    n = len(evs)
    tr, te = ev.temporal_split(n, 0.6)
    M, cols = arch_mix(evs, w2c, names)
    base = ev.describe(capped[te], raw[te])
    print(f"events={n} train={len(tr)} test={len(te)}  base EV_capped={base['ev_capped']:+.3%} hit={base['hit']:.3f}")

    # per-dominant-archetype EV (test fold) — interpretable
    print("\n[A] EV by DOMINANT archetype in the cluster (test fold):")
    dom = M[te].argmax(1)
    results = []
    for ci, name in enumerate(cols):
        mask = dom == ci
        if mask.sum() >= 20:
            r = ev.gate(capped[te], mask, f"dom={name}")
            results.append(r)
            print(ev.fmt_gate(r))

    # model: archetype-mix only, and token+archetype (ablation vs token-only)
    print("\n[B] MODELS (train->test, fire top-50%):")
    ytr = capped[tr]
    Xtok_tr, Xtok_te = ev.matrix([evs[i] for i in tr], TOKEN_ONLY), ev.matrix([evs[i] for i in te], TOKEN_ONLY)
    feats_sets = {
        "arch-only": (M[tr], M[te]),
        "token-only": (Xtok_tr, Xtok_te),
        "token+arch": (np.hstack([Xtok_tr, M[tr]]), np.hstack([Xtok_te, M[te]])),
    }
    for name, (Xtr, Xte) in feats_sets.items():
        sc, _ = ev.gbm_scores(Xtr, ytr, Xte)
        mask = ev.select_top(sc, 0.5)
        r = ev.gate(capped[te], mask, f"{name}/gbm")
        r["rho"] = ev.spearman(sc, capped[te])
        results.append(r)
        print(ev.fmt_gate(r) + f"  rho={r['rho']:+.2f}")

    passes = [r for r in results if r["verdict"] == "PASS"]
    print(f"\nVERDICT H={H}: {len(passes)} gate-clearing rule(s).")
    return {"H": H, "passes": passes, "results": results}


def main():
    print("Building label-free archetypes (KMeans on wallet behavior):")
    w2c, names = build_archetypes()
    out = [run_h(1800, w2c, names), run_h(3600, w2c, names)]
    print("\n" + "=" * 100)
    total = sum(len(o["passes"]) for o in out)
    print(f">>> H-161 {'has a gate-clearing archetype rule' if total else 'FAILS — archetype mix does not produce capturable intraday alpha (token context already captures what little signal exists).'}")
    return out


if __name__ == "__main__":
    main()
