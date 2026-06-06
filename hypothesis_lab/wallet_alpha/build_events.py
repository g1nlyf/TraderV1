"""build_events — PHASE 2: the point-in-time wallet-event dataset.

Builds token-disjoint cluster-buy events from the raw_trades 5.5h cross-section and, for each event,
computes ONLY-from-the-past features + realistic forward-VWAP labels. Every value obeys the leakage
rules in knowledge/DATA_AUDIT.md:

  * Wallet "skill" = realized SOL PnL / win-rate from that wallet's COMPLETED round-trips strictly
    BEFORE the event (avg-cost accounting, binary-searched snapshot). Never wallet_scores/leaderboard.
  * Token context = trades strictly before the event.
  * Entry = VWAP in (t, t+300s]  (you buy AFTER seeing the cluster, at public price — not the insiders' fill).
  * Label = VWAP near t+H over entry, minus round-trip cost. Forward-only.

Event = the FIRST time >= K distinct wallets BUY a token within a W-second window (one per token =>
events are token-disjoint => independent for the n>100 gate).

Run:  py hypothesis_lab/wallet_alpha/build_events.py --k 4 --window-min 15
Out:  _cache/events.json  (+ wallet_profiles.json)
"""
from __future__ import annotations

import argparse
import bisect
import json
import math
from collections import defaultdict

import wa_common as wa


# --------------------------------------------------------------------------- wallet skill (pre-t)
class WalletSkill:
    """Avg-cost realized-PnL ledger; produces per-wallet time-ordered snapshots for O(log n) pre-t lookup.

    Also accumulates a label-free global behavioral profile per wallet (for archetype clustering)."""

    def __init__(self):
        self.snap_ts: dict[str, list[float]] = defaultdict(list)
        self.snap_val: dict[str, list[tuple]] = defaultdict(list)  # (cum_pnl, n_closed, n_wins, n_trades)
        self.profile: dict[str, dict] = {}

    def build(self, trades: list[wa.Trade]):
        inv_qty: dict[tuple, float] = defaultdict(float)
        inv_cost: dict[tuple, float] = defaultdict(float)
        open_ts: dict[tuple, float] = {}
        st: dict[str, list] = defaultdict(lambda: [0.0, 0, 0, 0])  # cum_pnl, n_closed, n_wins, n_trades
        prof: dict[str, dict] = defaultdict(lambda: {
            "n_trades": 0, "n_buys": 0, "n_sells": 0, "tokens": set(),
            "sol_sum": 0.0, "holds": [], "first_ts": None, "last_ts": None})
        for t in trades:
            key = (t.wallet, t.token)
            p = prof[t.wallet]
            p["n_trades"] += 1
            p["sol_sum"] += t.sol
            p["tokens"].add(t.token)
            p["first_ts"] = t.ts if p["first_ts"] is None else p["first_ts"]
            p["last_ts"] = t.ts
            if t.side == "buy":
                if inv_qty[key] <= 1e-18:
                    open_ts[key] = t.ts
                inv_qty[key] += t.qty
                inv_cost[key] += t.sol
                p["n_buys"] += 1
            else:  # sell
                p["n_sells"] += 1
                q = inv_qty[key]
                if q > 1e-18:
                    avg = inv_cost[key] / q
                    sell_qty = min(t.qty, q)
                    realized = (t.price - avg) * sell_qty
                    s = st[t.wallet]
                    s[0] += realized
                    s[1] += 1
                    s[2] += 1 if realized > 0 else 0
                    inv_qty[key] -= sell_qty
                    inv_cost[key] -= avg * sell_qty
                    if key in open_ts:
                        p["holds"].append(t.ts - open_ts[key])
                    if inv_qty[key] <= 1e-12:
                        inv_qty[key] = 0.0
                        inv_cost[key] = 0.0
            s = st[t.wallet]
            s[3] += 1
            self.snap_ts[t.wallet].append(t.ts)
            self.snap_val[t.wallet].append((s[0], s[1], s[2], s[3]))
        # finalize global profiles
        for w, p in prof.items():
            holds = p["holds"]
            self.profile[w] = {
                "n_trades": p["n_trades"], "n_buys": p["n_buys"], "n_sells": p["n_sells"],
                "n_tokens": len(p["tokens"]), "avg_sol": p["sol_sum"] / max(p["n_trades"], 1),
                "median_hold_s": (sorted(holds)[len(holds) // 2] if holds else None),
                "fast_frac": (sum(1 for h in holds if h < 60) / len(holds)) if holds else 0.0,
                "active_s": (p["last_ts"] - p["first_ts"]) if p["first_ts"] else 0.0,
                "n_closed": len(holds),
            }

    def at(self, wallet: str, t: float) -> tuple:
        """Realized skill of `wallet` strictly before time t: (cum_pnl, n_closed, n_wins, n_trades)."""
        ts = self.snap_ts.get(wallet)
        if not ts:
            return (0.0, 0, 0, 0)
        i = bisect.bisect_left(ts, t) - 1   # last snapshot with ts < t
        if i < 0:
            return (0.0, 0, 0, 0)
        return self.snap_val[wallet][i]


# --------------------------------------------------------------------------- helpers
def _hhi(weights: list[float]) -> float:
    s = sum(weights)
    if s <= 0:
        return 0.0
    return sum((w / s) ** 2 for w in weights)


def _vwap(trs: list[wa.Trade]) -> float | None:
    sol = sum(t.sol for t in trs)
    return (sum(t.price * t.sol for t in trs) / sol) if sol > 0 else None


# --------------------------------------------------------------------------- builder
def build(k: int, window_s: int, min_sol: float, horizons_s: list[int],
          entry_win: int = 300, exit_win: int = 300, min_token_trades: int = 8,
          side: str = "buy") -> dict:
    wa.ensure_utf8()
    print(f"[build] loading raw_trades (session_only, min_sol={min_sol}, cluster_side={side}) ...")
    trades = wa.load_raw_trades(session_only=True, min_sol=min_sol)
    t0, t1 = wa.session_bounds(trades)
    print(f"[build] {len(trades):,} trades  {wa.fmt_hms(t0)}-{wa.fmt_hms(t1)} UTC "
          f"({(t1 - t0) / 3600:.1f}h)  wallets={len({t.wallet for t in trades}):,} "
          f"tokens={len({t.token for t in trades}):,}")

    print("[build] computing point-in-time wallet skill ledger ...")
    skill = WalletSkill()
    skill.build(trades)

    # per-token time-sorted trades
    by_token: dict[str, list[wa.Trade]] = defaultdict(list)
    for t in trades:
        by_token[t.token].append(t)

    Hmax = max(horizons_s)
    events = []
    n_tok_cluster = 0
    for token, trs in by_token.items():
        if len(trs) < min_token_trades:
            continue
        buys = [t for t in trs if t.side == side]   # 'buy' = accumulation cluster; 'sell' = distribution cluster
        if len({b.wallet for b in buys}) < k:
            continue
        # first cluster: sliding window of distinct wallets
        form = None
        i = 0
        for j in range(len(buys)):
            while buys[j].ts - buys[i].ts > window_s:
                i += 1
            win = buys[i:j + 1]
            wallets = {b.wallet for b in win}
            if len(wallets) >= k:
                form = (buys[j].ts, win, sorted(wallets))
                break
        if form is None:
            continue
        n_tok_cluster += 1
        form_ts, win, wallets = form

        # must have a session-internal forward horizon
        if form_ts + Hmax > t1:
            continue

        ts_list = [t.ts for t in trs]
        pre = trs[:bisect.bisect_left(ts_list, form_ts)]
        if len(pre) < 3:
            continue

        # entry VWAP in (form_ts, form_ts+entry_win]
        lo = bisect.bisect_right(ts_list, form_ts)
        hi = bisect.bisect_right(ts_list, form_ts + entry_win)
        entry_trs = trs[lo:hi]
        entry_vwap = _vwap(entry_trs)
        if entry_vwap is None or entry_vwap <= 0:
            continue

        # forward labels: exit at the last <=3 prints up to the horizon (realistic "exit by H at market").
        labels = {}
        for H in horizons_s:
            b = bisect.bisect_right(ts_list, form_ts + H)
            seg = trs[hi:b]                       # trades strictly after the entry window, up to horizon
            exv = _vwap(seg[-3:]) if seg else None
            labels[f"ret_{H}"] = ((exv / entry_vwap - 1.0 - wa.COST_RT) if exv and exv > 0 else None)

        # ---- token context (pre-t) ----
        pbuys = [t for t in pre if t.side == "buy"]
        psells = [t for t in pre if t.side == "sell"]
        nb, ns = len(pbuys), len(psells)
        prior_ret = (pre[-1].price / pre[0].price - 1.0) if pre[0].price > 0 else 0.0
        buy_sol_by_w: dict[str, float] = defaultdict(float)
        for t in pbuys:
            buy_sol_by_w[t.wallet] += t.sol
        tok = {
            "tok_age_s": form_ts - pre[0].ts,
            "tok_prior_trades": len(pre),
            "tok_prior_buyers": len({t.wallet for t in pbuys}),
            "tok_prior_sellers": len({t.wallet for t in psells}),
            "tok_buy_sell_imb": (nb - ns) / max(nb + ns, 1),
            "tok_cum_sol": sum(t.sol for t in pre),
            "tok_prior_ret": prior_ret,
            "tok_buyer_hhi": _hhi(list(buy_sol_by_w.values())),
        }

        # ---- cluster shape ----
        sizes = [b.sol for b in win]
        mean_sz = sum(sizes) / len(sizes)
        disp = (sum((s - mean_sz) ** 2 for s in sizes) / len(sizes)) ** 0.5 / mean_sz if mean_sz > 0 else 0.0
        clu = {
            "clu_n_wallets": len(wallets),
            "clu_window_s": win[-1].ts - win[0].ts,
            "clu_mean_buy_sol": mean_sz,
            "clu_sol_total": sum(sizes),
            "clu_size_disp": disp,
            "clu_cohesion": len(wallets) / len(win),   # distinct / buys-in-window
        }

        # ---- wallet quality (participants, pre-t) ----
        pnls, wrs, ncloseds, ntrades, known, prof_v = [], [], [], [], 0, []
        for w in wallets:
            cum, nc, nw, nt = skill.at(w, form_ts)
            if nt > 0:
                known += 1
            pnls.append(cum)
            ncloseds.append(nc)
            ntrades.append(nt)
            if nc >= 1:
                wrs.append(nw / nc)
            prof_v.append(skill.profile.get(w, {}))
        wq = {
            "wq_mean_pnl": sum(pnls) / len(pnls),
            "wq_max_pnl": max(pnls),
            "wq_frac_profitable": sum(1 for i, p in enumerate(pnls) if p > 0 and ncloseds[i] >= 1) / len(pnls),
            "wq_mean_winrate": (sum(wrs) / len(wrs)) if wrs else 0.0,
            "wq_total_prior_trades": sum(ntrades),
            "wq_mean_nclosed": sum(ncloseds) / len(ncloseds),
            "wq_frac_known": known / len(wallets),
        }

        ev = {"token": token, "form_ts": form_ts, "wallets": wallets,
              "entry_vwap": entry_vwap, **tok, **clu, **wq, **labels}
        events.append(ev)

    events.sort(key=lambda e: e["form_ts"])
    meta = {"k": k, "window_s": window_s, "min_sol": min_sol, "horizons_s": horizons_s, "side": side,
            "entry_win": entry_win, "exit_win": exit_win, "min_token_trades": min_token_trades,
            "n_trades": len(trades), "session": [t0, t1],
            "tokens_with_cluster": n_tok_cluster, "n_events": len(events)}
    for H in horizons_s:
        vals = [e[f"ret_{H}"] for e in events if e[f"ret_{H}"] is not None]
        meta[f"n_label_{H}"] = len(vals)
        meta[f"mean_ret_{H}"] = (sum(vals) / len(vals)) if vals else None

    out = {"meta": meta, "events": events}
    (wa.CACHE / f"events_{side}.json").write_text(json.dumps(out), encoding="utf-8")
    (wa.CACHE / "wallet_profiles.json").write_text(
        json.dumps({w: p for w, p in skill.profile.items() if p["n_trades"] >= 2}), encoding="utf-8")
    print(f"[build] tokens_with_cluster={n_tok_cluster}  events(with entry+forward)={len(events)}")
    for H in horizons_s:
        print(f"[build]   H={H}s: n_label={meta[f'n_label_{H}']}  mean_ret={meta[f'mean_ret_{H}']}")
    print(f"[build] wrote {wa.CACHE/('events_'+side+'.json')}")
    return out


def load_events(side: str = "buy") -> dict:
    return json.loads((wa.CACHE / f"events_{side}.json").read_text(encoding="utf-8"))


FEATURES = [
    "tok_age_s", "tok_prior_trades", "tok_prior_buyers", "tok_prior_sellers", "tok_buy_sell_imb",
    "tok_cum_sol", "tok_prior_ret", "tok_buyer_hhi",
    "clu_n_wallets", "clu_window_s", "clu_mean_buy_sol", "clu_sol_total", "clu_size_disp", "clu_cohesion",
    "wq_mean_pnl", "wq_max_pnl", "wq_frac_profitable", "wq_mean_winrate", "wq_total_prior_trades",
    "wq_mean_nclosed", "wq_frac_known",
]
TOKEN_ONLY = [f for f in FEATURES if not f.startswith("wq_")]
WQ_ONLY = [f for f in FEATURES if f.startswith("wq_")]


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--k", type=int, default=4)
    ap.add_argument("--window-min", type=float, default=15)
    ap.add_argument("--min-sol", type=float, default=0.05)
    ap.add_argument("--horizons-min", type=str, default="30,60")
    ap.add_argument("--min-token-trades", type=int, default=8)
    ap.add_argument("--side", choices=["buy", "sell"], default="buy")
    a = ap.parse_args()
    H = [int(float(x) * 60) for x in a.horizons_min.split(",")]
    build(a.k, int(a.window_min * 60), a.min_sol, H, min_token_trades=a.min_token_trades, side=a.side)
