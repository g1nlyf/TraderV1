"""PHASE 6 — compound distribution theory: does DISTRIBUTOR ARCHETYPE or CO-SELL NETWORK add specificity
beyond naive sell-count for predicting forward drops? (The backtest showed wallet-quality did NOT beat a
naive sell-reaction; this tests whether richer layers do.)

Layers (all point-in-time, from raw_trades pre-event):
  - sell_count        : # distinct sellers in the cluster (naive baseline)
  - wallet_quality    : mean pre-t realized SOL PnL of sellers (FIFO ledger)
  - distributor_score : mean over sellers of (frac of that wallet's COMPLETED pre-t sells that preceded a
                        30m drop) -> "repeatedly sells before collapse" archetype, strictly point-in-time
  - cohesion          : co-sell network density among the cluster's sellers (shared-token co-sells, pre-t)
  - token_ctx         : pre-t token microstructure (from event cache)

Label = SHORT payoff (capped) = the down-signal magnitude. Temporal OOS split. Ablation: Spearman(feature,
label) on test + top-half EV vs the sell_count baseline top-half. A layer "adds value" only if it beats
sell_count OOS. Run: py hypothesis_lab/wallet_alpha/distributor_theory.py
"""
from __future__ import annotations

import bisect
import json
from collections import defaultdict

import numpy as np

import wa_common as wa
import wa_eval as ev
from build_events import WalletSkill

wa.ensure_utf8()
H = 1800
DROP = -0.10        # a sell "preceded a drop" if token fell > 10% over next 30m


def short_payoff(raw):
    return ev.cap(-(raw + wa.COST_RT) - wa.COST_RT)


def main():
    print("[theory] loading raw_trades + ledger ...")
    trades = wa.load_raw_trades(session_only=True, min_sol=0.05)
    by_token = defaultdict(list); by_wallet_sells = defaultdict(list)
    for t in trades:
        by_token[t.token].append(t)
        if t.side == "sell":
            by_wallet_sells[t.wallet].append(t)
    for k in by_token:
        by_token[k].sort(key=lambda x: x.ts)
    skill = WalletSkill(); skill.build(trades)
    tok_ts = {k: [t.ts for t in v] for k, v in by_token.items()}

    def price_at(token, t):
        trs = by_token[token]; ts = tok_ts[token]
        i = bisect.bisect_right(ts, t) - 1
        return trs[i].price if i >= 0 else None

    def fwd_drop(token, t):
        p0 = price_at(token, t); p1 = price_at(token, t + H)
        return ((p1 / p0 - 1.0) if p0 and p1 and p0 > 0 else None)

    sells_ev = json.loads((wa.CACHE / "events_sell.json").read_text())["events"]
    sells_ev = [e for e in sells_ev if e.get(f"ret_{H}") is not None]
    sells_ev.sort(key=lambda e: e["form_ts"])
    U = set().union(*[set(e["wallets"]) for e in sells_ev])
    print(f"[theory] sell-events={len(sells_ev)} participant wallets={len(U)}")

    # distributor score per wallet (point-in-time, cached at event times lazily)
    def distributor_score(w, t):
        outs = []
        for s in by_wallet_sells.get(w, []):
            if s.ts >= t or s.ts + H >= t:     # require COMPLETED outcome strictly before t
                continue
            d = fwd_drop(s.token, s.ts)
            if d is not None:
                outs.append(1.0 if d < DROP else 0.0)
        return (sum(outs) / len(outs)) if outs else 0.0

    # co-sell graph among U (shared-token co-sells within 900s), built ONCE over full session (label-free).
    # NOTE: uses full-session co-sell (mild look-ahead on network membership, label-independent) -> if it
    # still fails to beat baseline, the negative is robust. cohesion = mean degree of cluster members.
    edges = defaultdict(int)
    for token, trs in by_token.items():
        s = [t for t in trs if t.side == "sell" and t.wallet in U]
        for j in range(len(s)):
            i = j - 1
            while i >= 0 and s[j].ts - s[i].ts <= 900:
                if s[i].wallet != s[j].wallet:
                    key = tuple(sorted((s[i].wallet, s[j].wallet)))
                    edges[key] += 1
                i -= 1
    deg = defaultdict(int)
    for (a, b), wt in edges.items():
        deg[a] += wt; deg[b] += wt

    rows = []
    for e in sells_ev:
        t = e["form_ts"]; ws = e["wallets"]
        q = [skill.at(w, t)[0] for w in ws]
        dist = [distributor_score(w, t) for w in ws]
        coh = [deg.get(w, 0) for w in ws]
        rows.append({
            "t": t, "label": short_payoff(e[f"ret_{H}"]),
            "sell_count": float(len(ws)),
            "wallet_quality": float(np.mean(q)),
            "distributor_score": float(np.mean(dist)),
            "cohesion": float(np.mean(coh)),
            "tok_cum_sol": float(e.get("tok_cum_sol", 0)), "tok_prior_ret": float(e.get("tok_prior_ret", 0)),
        })
    n = len(rows); cut = int(n * 0.6)
    te = rows[cut:]
    lab = np.array([r["label"] for r in te])
    base = float(lab.mean())
    print(f"\n[theory] test n={len(te)}  base SHORT EV={base:+.2%}")
    print("  ABLATION — Spearman(feature, short-payoff) OOS + top-half SHORT EV vs sell_count baseline:")
    feats = ["sell_count", "wallet_quality", "distributor_score", "cohesion", "tok_cum_sol", "tok_prior_ret"]
    res = {}
    for f in feats:
        x = np.array([r[f] for r in te])
        rho = ev.spearman(x, lab)
        hi = x > np.median(x)
        ev_hi = float(lab[hi].mean()) if hi.sum() else float("nan")
        res[f] = (rho, ev_hi, int(hi.sum()))
        print(f"   {f:18s} rho={rho:+.3f}  top-half SHORT EV={ev_hi:+.2%} (n={int(hi.sum())})")
    sc = res["sell_count"][1]
    winners = [f for f in feats if f not in ("sell_count",) and res[f][1] > sc + 0.01]
    print(f"\n  sell_count baseline top-half EV={sc:+.2%}")
    print(f"  layers beating sell_count by >1%: {winners or 'NONE'}")
    print(f"  VERDICT: {'a layer adds specificity -> investigate' if winners else 'NO layer beats naive sell_count -> H-166 specificity NOT rescued (exit-on-any-sell is the whole edge)'}")
    (wa.CACHE / "distributor_theory_result.json").write_text(json.dumps({"base": base, "res": {k: list(v) for k, v in res.items()}, "winners": winners}), encoding="utf-8")
    return res


if __name__ == "__main__":
    main()
