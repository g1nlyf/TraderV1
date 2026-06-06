"""H-170 — Token Lifecycle Model + the BEAT-TOKEN-ONLY gate (the promotion machine).

Sprint-7 finding: token context dominates wallet behavior. This exploits it two ways:

  PART A  Token lifecycle state machine (ignition/acceleration/crowded_top/distribution/decay/rug/dead),
          classified deterministically from POINT-IN-TIME free-tape features, then tested for OOS predictive
          value on forward net EV: (a) per-state EV table, (b) token-only ML baseline, (c) does state add
          incremental EV over the raw token-only features, (d) avoidance no-trade filter, all temporal-OOS,
          gated by eval_stats (perm<0.05, bootstrap CI>0, n>100), vs random + token-only controls.

  PART B  Beat-token-only falsification gate on the cluster events: token-only feature ML vs token+wallet
          feature ML, temporal-OOS. Re-confirms (with full multivariate ML, not univariate rho) whether
          wallet/cluster features add ANYTHING over token context. If not -> wallet intelligence demoted.

Sampling honesty: <=3 decision points per token, spaced >= H so within-token forward windows never overlap;
cross-token temporal split by decision-time; block-bootstrap CI. May-14 = ONE session -> cross-sectional
state prediction is honest; absolute EV levels are regime-bound (no cross-day claim).

Run: py hypothesis_lab/wallet_alpha/token_lifecycle.py
"""
from __future__ import annotations

import bisect
import json
import math
from collections import defaultdict

import numpy as np

import wa_common as wa
import wa_eval as ev
from wa_eval import es  # canonical gate

wa.ensure_utf8()
H = 1800
ENTRY_WIN = 300
MIN_TRADES = 15           # token must have >=15 trades before a decision point
MAX_PTS = 3               # <=3 non-overlapping decision points per token
RNG = np.random.default_rng(2026)

TOK_FEATS = ["age_s", "n_trades", "n_buyers", "n_sellers", "cum_sol", "net_sol", "prior_ret",
             "recent_ret", "buy_sell_imb", "recent_imb", "vol", "dd_from_peak", "t_since_peak",
             "trades_per_min", "accel", "buyer_hhi"]
STATES = ["ignition", "acceleration", "crowded_top", "distribution", "decay", "rug_dead", "neutral"]


def _vwap(trs):
    s = sum(t.sol for t in trs)
    return (sum(t.price * t.sol for t in trs) / s) if s > 0 else None


def tok_features(trs, ts_list, t):
    """All strictly-pre-t, point-in-time token features."""
    i = bisect.bisect_left(ts_list, t)              # trades [0,i) are < t
    pre = trs[:i]
    if len(pre) < MIN_TRADES:
        return None
    prices = [x.price for x in pre if x.price > 0]
    if len(prices) < 5:
        return None
    first_ts = pre[0].ts
    age = t - first_ts
    peak = max(prices); peak_i = max(range(len(pre)), key=lambda j: pre[j].price)
    p_now = prices[-1]
    cum_sol = sum(x.sol for x in pre)
    buys = [x for x in pre if x.side == "buy"]; sells = [x for x in pre if x.side == "sell"]
    net_sol = sum(x.sol for x in buys) - sum(x.sol for x in sells)
    nb, ns = len(buys), len(sells)
    # recent 300s window
    rlo = bisect.bisect_left(ts_list, t - 300)
    rec = trs[rlo:i]
    rb = sum(1 for x in rec if x.side == "buy"); rs = sum(1 for x in rec if x.side == "sell")
    rec_prices = [x.price for x in rec if x.price > 0]
    recent_ret = (rec_prices[-1] / rec_prices[0] - 1.0) if len(rec_prices) >= 2 else 0.0
    # volatility = stddev of log-returns over last ~20 trades
    tail = prices[-20:]
    lr = [math.log(tail[j + 1] / tail[j]) for j in range(len(tail) - 1) if tail[j] > 0 and tail[j + 1] > 0]
    vol = float(np.std(lr)) if len(lr) >= 2 else 0.0
    prior_ret = (p_now / prices[0] - 1.0) if prices[0] > 0 else 0.0
    dd = (p_now / peak - 1.0) if peak > 0 else 0.0
    t_since_peak = t - pre[peak_i].ts
    tpm = len(pre) / max(age / 60.0, 1e-6)
    rec_tpm = len(rec) / 5.0
    accel = rec_tpm / max(tpm, 1e-6)
    buy_sol_by_w = defaultdict(float)
    for x in buys:
        buy_sol_by_w[x.wallet] += x.sol
    w = list(buy_sol_by_w.values()); tot = sum(w)
    hhi = sum((x / tot) ** 2 for x in w) if tot > 0 else 1.0
    return {"age_s": age, "n_trades": len(pre), "n_buyers": len({x.wallet for x in buys}),
            "n_sellers": len({x.wallet for x in sells}), "cum_sol": cum_sol, "net_sol": net_sol,
            "prior_ret": prior_ret, "recent_ret": recent_ret,
            "buy_sell_imb": (nb - ns) / max(nb + ns, 1), "recent_imb": (rb - rs) / max(rb + rs, 1),
            "vol": vol, "dd_from_peak": dd, "t_since_peak": t_since_peak, "trades_per_min": tpm,
            "accel": accel, "buyer_hhi": hhi, "_p_now": p_now, "_peak": peak}


def classify(f) -> str:
    """Deterministic, interpretable lifecycle state from point-in-time features (priority order)."""
    dd, pr, rr, rimb, age, accel = (f["dd_from_peak"], f["prior_ret"], f["recent_ret"],
                                    f["recent_imb"], f["age_s"], f["accel"])
    if dd < -0.75:
        return "rug_dead"                                   # collapsed >75% from peak
    if dd < -0.15 and rimb < -0.15:
        return "distribution"                               # off the top, sellers dominating recently
    if dd < -0.15:
        return "decay"                                      # off the top, bleeding without heavy selling
    if pr > 0.5 and rr <= 0.02:                             # near peak, big run, stalled
        return "crowded_top"
    if rr > 0.10 and accel > 1.0:                           # rising fast + accelerating
        return "acceleration"
    if age < 600:
        return "ignition"                                   # young, no other signal yet
    return "neutral"


def forward_net(trs, ts_list, t):
    a = bisect.bisect_right(ts_list, t); b = bisect.bisect_right(ts_list, t + ENTRY_WIN)
    entry = _vwap(trs[a:b])
    if not entry or entry <= 0:
        return None                                         # could not enter
    c = bisect.bisect_right(ts_list, t + H)
    seg = trs[b:c]
    exv = _vwap(seg[-3:]) if seg else None
    if not exv or exv <= 0:
        return ev.cap(-1.0)                                 # no forward liquidity = stuck = -100%
    return ev.cap(exv / entry - 1.0 - wa.COST_RT)


def build_lifecycle_sample(trades):
    by_token = defaultdict(list)
    for t in trades:
        by_token[t.token].append(t)
    rows = []
    for tok, trs in by_token.items():
        trs.sort(key=lambda x: x.ts)
        ts_list = [x.ts for x in trs]
        first, last = trs[0].ts, trs[-1].ts
        pts = []
        off = 300.0
        while first + off < last - H and len(pts) < MAX_PTS:
            pts.append(first + off); off += H            # spaced >= H -> non-overlapping forward windows
        for t in pts:
            f = tok_features(trs, ts_list, t)
            if f is None:
                continue
            net = forward_net(trs, ts_list, t)
            if net is None:
                continue
            st = classify(f)
            f = {k: v for k, v in f.items() if not k.startswith("_")}
            f.update({"token": tok, "t": t, "state": st, "net": net})
            rows.append(f)
    rows.sort(key=lambda r: r["t"])
    return rows


def gate_mask(rows, mask, label):
    nets = [r["net"] for r in rows]
    return ev.gate(nets, mask, label)


def main():
    print("[lifecycle] loading raw_trades (session, min_sol=0.05) ...")
    trades = wa.load_raw_trades(session_only=True, min_sol=0.05)
    rows = build_lifecycle_sample(trades)
    n = len(rows)
    print(f"[lifecycle] decision points={n} across {len({r['token'] for r in rows})} tokens "
          f"(<= {MAX_PTS}/token, spaced >= {H}s)\n")
    nets = np.array([r["net"] for r in rows])
    tr_idx, te_idx = ev.temporal_split(n, 0.6)
    te = [rows[i] for i in te_idx]
    base_te = float(np.mean([r["net"] for r in te]))
    print("=" * 96)
    print(f"PART A — TOKEN LIFECYCLE (H={H//60}m, n={n}, test n={len(te)}, base EV={base_te:+.2%}, "
          f"source=ORGANIC raw_trades, ONE session)")
    print("=" * 96)

    # (a) per-state forward EV on TEST fold + gate each state's selection (computed over full timeline)
    print("\n  [A1] Per-state forward EV (test fold) + canonical gate (selection = 'enter in this state'):")
    full_mask_by_state = {s: [r["state"] == s for r in rows] for s in STATES}
    state_rows = []
    for s in STATES:
        sub = [r["net"] for r in te if r["state"] == s]
        if not sub:
            print(f"   {s:14s} test n=0"); continue
        g = gate_mask(rows, full_mask_by_state[s], f"state={s}")
        state_rows.append((s, len(sub), float(np.mean(sub)), g))
        print(f"   {s:14s} test n={len(sub):4d} EV={np.mean(sub):+.2%}  | {ev.fmt_gate(g).strip()}")

    # (b) token-only ML baseline: train GBM on train fold, select top frac on test -> gate
    print("\n  [A2] Token-only ML baseline (GBM, temporal OOS, select top 30% by predicted net):")
    Xtr = ev.matrix([rows[i] for i in tr_idx], TOK_FEATS); ytr = nets[tr_idx]
    Xte = ev.matrix(te, TOK_FEATS)
    scores_tok, _ = ev.gbm_scores(Xtr, ytr, Xte)
    for frac in (0.3,):
        fired = ev.select_top(scores_tok, frac)
        full = np.zeros(n, bool); full[te_idx[fired]] = True
        g = gate_mask(rows, full.tolist(), f"token_only_top{int(frac*100)}")
        print(f"   {ev.fmt_gate(g).strip()}")
        tok_ev = g["rule_ev"]

    # (c) token-only + lifecycle state one-hot: does state ADD incremental OOS EV?
    print("\n  [A3] Token-only + state one-hot (does lifecycle state beat token-only OOS?):")
    def onehot(rs):
        return np.array([[1.0 if r["state"] == s else 0.0 for s in STATES] for r in rs])
    Xtr2 = np.hstack([Xtr, onehot([rows[i] for i in tr_idx])])
    Xte2 = np.hstack([Xte, onehot(te)])
    scores_ts, _ = ev.gbm_scores(Xtr2, ytr, Xte2)
    fired = ev.select_top(scores_ts, 0.3)
    full = np.zeros(n, bool); full[te_idx[fired]] = True
    g_ts = gate_mask(rows, full.tolist(), "token+state_top30")
    print(f"   {ev.fmt_gate(g_ts).strip()}")
    print(f"   -> incremental EV from state: {g_ts['rule_ev'] - tok_ev:+.3%} "
          f"({'state ADDS' if g_ts['rule_ev'] > tok_ev + 0.005 else 'state adds ~nothing'})")

    # (d) avoidance no-trade filter: drop rug_dead+distribution+decay -> does the book improve?
    print("\n  [A4] Avoidance no-trade filter (skip rug_dead/distribution/decay):")
    avoid = {"rug_dead", "distribution", "decay"}
    keep = [r["net"] for r in te if r["state"] not in avoid]
    print(f"   base(all) EV={base_te:+.2%} n={len(te)}  ->  kept EV={np.mean(keep):+.2%} n={len(keep)} "
          f"(filtered {len(te)-len(keep)})  delta={np.mean(keep)-base_te:+.3%}")

    # (e) control: random top-30%
    fired_r = RNG.random(len(te)) > 0.7
    full = np.zeros(n, bool); full[te_idx[fired_r]] = True
    g_rand = gate_mask(rows, full.tolist(), "random_top30")
    print(f"\n  [A5] Random control: {ev.fmt_gate(g_rand).strip()}")

    # ---------- PART B: beat-token-only on cluster events ----------
    print("\n" + "=" * 96)
    print("PART B — BEAT-TOKEN-ONLY GATE on cluster events (does wallet/cluster add over token context?)")
    print("=" * 96)
    part_b(H)

    # persist
    out = {"H": H, "n": n, "base_ev_test": base_te,
           "state_ev": {s: float(np.mean([r["net"] for r in te if r["state"] == s]) if any(r["state"] == s for r in te) else float("nan")) for s in STATES},
           "token_only_ev": tok_ev, "token_state_ev": g_ts["rule_ev"],
           "avoid_delta": float(np.mean(keep) - base_te)}
    (wa.CACHE / "token_lifecycle_result.json").write_text(json.dumps(out, default=str), encoding="utf-8")
    print("\n[lifecycle] wrote _cache/token_lifecycle_result.json")


def part_b(H):
    _, evs, capped, raw = ev.load("buy", H)
    n = len(evs)
    tok_feats = ["tok_age_s", "tok_prior_trades", "tok_prior_buyers", "tok_prior_sellers",
                 "tok_buy_sell_imb", "tok_cum_sol", "tok_prior_ret", "tok_buyer_hhi"]
    wal_feats = ["clu_n_wallets", "clu_cohesion", "clu_sol_total", "clu_mean_buy_sol", "clu_size_disp",
                 "wq_mean_pnl", "wq_max_pnl", "wq_frac_profitable", "wq_mean_winrate", "wq_frac_known"]
    tr, te = ev.temporal_split(n, 0.6)
    y = capped
    Xtok_tr, Xtok_te = ev.matrix([evs[i] for i in tr], tok_feats), ev.matrix([evs[i] for i in te], tok_feats)
    Xall_tr = np.hstack([Xtok_tr, ev.matrix([evs[i] for i in tr], wal_feats)])
    Xall_te = np.hstack([Xtok_te, ev.matrix([evs[i] for i in te], wal_feats)])
    s_tok, _ = ev.gbm_scores(Xtok_tr, y[tr], Xtok_te)
    s_all, _ = ev.gbm_scores(Xall_tr, y[tr], Xall_te)
    print(f"  cluster events n={n}, test n={len(te)}, base EV={y[te].mean():+.2%}")
    for name, sc in (("token_only", s_tok), ("token+wallet", s_all)):
        fired = ev.select_top(sc, 0.3)
        full = np.zeros(n, bool); full[te[fired]] = True
        g = ev.gate(list(y), full.tolist(), f"{name}_top30")
        print(f"   {ev.fmt_gate(g).strip()}")
    # rank-corr of predictions vs truth on test (OOS R-ish)
    print(f"   OOS Spearman: token_only={ev.spearman(s_tok, y[te]):+.3f}  "
          f"token+wallet={ev.spearman(s_all, y[te]):+.3f}  "
          f"(wallet adds {ev.spearman(s_all, y[te]) - ev.spearman(s_tok, y[te]):+.3f})")
    print("   VERDICT: wallet features earn their place ONLY if token+wallet beats token_only OOS on BOTH "
          "gate EV and Spearman. Sprint-7 prior: they do not.")


if __name__ == "__main__":
    main()
