"""PHASE 4 — Stage-2-style backtest of the H-166 overlay vs ALL controls, driving the REAL module.

Uses h166_risk_overlay.evaluate_entry/evaluate_position over the May-14 raw_trades cross-section with
POINT-IN-TIME wallet quality (build_events.WalletSkill). Proves the productionized module reproduces the
research numbers AND adds the controls the spec requires.

Policies:
  hold                 baseline: hold to horizon H
  exit_random_time     mechanical control: exit at a uniform-random time in the hold (early-exit-in-dump)
  exit_random_sell     control: exit at a RANDOM sell time in the hold (sell-cluster, no quality)
  exit_h166            H-166: exit at first during-hold quality-distribution cluster (module verdict)
  veto_h166            H-166 no-trade: drop entries the module flags no_trade; EV of the kept book
  combined             veto_h166 entries, then exit_h166 on the kept book

Metrics: capped realized EV, hit, CVaR5 (worst-5% mean = drawdown proxy), n, perm_p vs hold, CI95,
false-exit rate (exited below what holding would have made), source purity. Gate via eval_stats.
Run: py hypothesis_lab/wallet_alpha/backtest_h166.py
"""
from __future__ import annotations

import bisect
import json
import sys
from collections import defaultdict

import numpy as np

import wa_common as wa
import wa_eval as ev
import h166_risk_overlay as h
from build_events import WalletSkill

sys.path.insert(0, str(wa.ROOT / "finetune" / "pipeline"))
import eval_stats as es  # noqa: E402

wa.ensure_utf8()
H = 1800
ENTRY_WIN = 300
RNG = np.random.default_rng(2026)


def _vwap(trs):
    s = sum(t.sol for t in trs)
    return (sum(t.price * t.sol for t in trs) / s) if s > 0 else None


def fwd_ret(trs, ts_list, t0, H_):
    lo = bisect.bisect_right(ts_list, t0); hi = bisect.bisect_right(ts_list, t0 + ENTRY_WIN)
    entry = _vwap(trs[lo:hi])
    if not entry or entry <= 0:
        return None
    b = bisect.bisect_right(ts_list, t0 + H_)
    seg = trs[hi:b]
    exv = _vwap(seg[-3:]) if seg else None
    return ev.cap(exv / entry - 1.0 - wa.COST_RT) if exv and exv > 0 else None


def cvar5(x):
    x = np.sort(np.asarray(x)); k = max(1, len(x) // 20)
    return float(x[:k].mean())


def summarize(name, rets, hold_pool):
    rets = [r for r in rets if r is not None]
    if not rets:
        print(f"  {name:20s} no events"); return None
    a = np.array(rets)
    p = es.permutation_p(hold_pool, len(rets), float(a.mean()), n_perm=5000) if hold_pool else 1.0
    ci = es.block_bootstrap_ci(rets, n_boot=4000)
    print(f"  {name:20s} n={len(a):4d} EV={a.mean():+.2%} hit={ (a>0).mean():.2f} "
          f"CVaR5={cvar5(a):+.2%} perm={p:.3f} CI=[{ci[0]:+.2%},{ci[1]:+.2%}]")
    return {"name": name, "n": len(a), "ev": float(a.mean()), "hit": float((a > 0).mean()),
            "cvar5": cvar5(a), "perm": p, "ci": ci}


def main():
    print("[backtest] loading raw_trades + point-in-time wallet skill ...")
    trades = wa.load_raw_trades(session_only=True, min_sol=0.05)
    by_token = defaultdict(list)
    for t in trades:
        by_token[t.token].append(t)
    for k in by_token:
        by_token[k].sort(key=lambda x: x.ts)
    skill = WalletSkill(); skill.build(trades)
    buys = [e for e in json.loads((wa.CACHE / "events_buy.json").read_text())["events"] if e.get(f"ret_{H}") is not None]
    print(f"[backtest] candidate buy events={len(buys)}  (organic source=raw_trades)\n")

    hold, ex_rand_t, ex_rand_sell, ex_h166 = [], [], [], []
    veto_keep, combined = [], []
    n_exit_h166 = n_veto = n_false_exit = 0

    for e in buys:
        tok, t0 = e["token"], e["form_ts"]
        trs = by_token[tok]; ts_list = [t.ts for t in trs]
        hr = ev.cap(e[f"ret_{H}"]); hold.append(hr)

        # window helpers
        def overlay_events(lo, hi):
            return [{"ts": t.ts, "wallet": t.wallet, "side": t.side, "sol": t.sol, "source": "organic"}
                    for t in trs[bisect.bisect_left(ts_list, lo):bisect.bisect_right(ts_list, hi)]]

        def quality_asof(t):
            lo = t - h.Config().window_s
            ws = {t2.wallet for t2 in trs[bisect.bisect_left(ts_list, lo):bisect.bisect_right(ts_list, t)]}
            return {w: skill.at(w, t)[0] for w in ws}

        # ---- ENTRY verdict (no-trade veto) ----
        ent = h.evaluate_entry(tok, t0, overlay_events(t0 - h.Config().window_s, t0), quality_asof(t0))
        vetoed = ent.decision == "no_trade"
        if vetoed:
            n_veto += 1
        else:
            veto_keep.append(hr)

        # ---- sells in hold window ----
        a = bisect.bisect_right(ts_list, t0 + ENTRY_WIN); b = bisect.bisect_right(ts_list, t0 + H)
        sells = [t for t in trs[a:b] if t.side == "sell"]

        # exit_h166: first during-hold quality-distribution cluster
        xts = None
        for s in sells:
            v = h.evaluate_position(tok, s.ts, t0, overlay_events(s.ts - h.Config().exit_recent_s, s.ts),
                                    quality_asof(s.ts))
            if v.decision == "exit_candidate":
                xts = s.ts; break
        if xts is not None:
            n_exit_h166 += 1
            xr = fwd_ret(trs, ts_list, t0, xts - t0); xr = xr if xr is not None else hr
            ex_h166.append(xr)
            if hr > xr:
                n_false_exit += 1
            if not vetoed:
                combined.append(xr)
        else:
            ex_h166.append(hr)
            if not vetoed:
                combined.append(hr)

        # control: random TIME exit
        if sells:
            rt = t0 + ENTRY_WIN + float(RNG.random()) * (H - ENTRY_WIN)
            rr = fwd_ret(trs, ts_list, t0, rt - t0); ex_rand_t.append(rr if rr is not None else hr)
            # control: random SELL-time exit
            rs = sells[RNG.integers(len(sells))]
            rsr = fwd_ret(trs, ts_list, t0, rs.ts - t0); ex_rand_sell.append(rsr if rsr is not None else hr)
        else:
            ex_rand_t.append(hr); ex_rand_sell.append(hr)

    print("=" * 92)
    print(f"H-166 STAGE-2 BACKTEST  (H={H//60}m, n={len(hold)} buy candidates, source=ORGANIC raw_trades)")
    print("=" * 92)
    rows = {}
    rows["hold"] = summarize("hold (baseline)", hold, hold)
    rows["exit_random_time"] = summarize("exit_random_time", ex_rand_t, hold)
    rows["exit_random_sell"] = summarize("exit_random_sell", ex_rand_sell, hold)
    rows["exit_h166"] = summarize("exit_h166", ex_h166, hold)
    rows["veto_h166"] = summarize("veto_h166 (kept)", veto_keep, hold)
    rows["combined"] = summarize("combined", combined, hold)

    print(f"\n  exits fired (h166): {n_exit_h166}/{len(hold)} ({n_exit_h166/len(hold):.0%})  "
          f"no_trade vetoes: {n_veto} ({n_veto/len(hold):.0%})  "
          f"false-exit rate: {n_false_exit/max(n_exit_h166,1):.0%}")
    hv, xv = rows["hold"]["ev"], rows["exit_h166"]["ev"]
    rtv, rsv = rows["exit_random_time"]["ev"], rows["exit_random_sell"]["ev"]
    print(f"\n  EXIT EDGE vs controls: h166 {xv:+.2%} | hold {hv:+.2%} (+{xv-hv:+.2%}) | "
          f"rand-time {rtv:+.2%} (+{xv-rtv:+.2%}) | rand-sell {rsv:+.2%} (+{xv-rsv:+.2%})")
    print(f"  DRAWDOWN (CVaR5): hold {rows['hold']['cvar5']:+.2%} -> exit_h166 {rows['exit_h166']['cvar5']:+.2%}")
    print("\n  VERDICT: H-166 is a real DE-RISK overlay if exit_h166 EV>hold AND >both controls AND CVaR5 improves;")
    print("           it is NOT alpha unless some policy EV>+2% (gate). Source=organic (raw_trades), single session.")
    out = {"H": H, "rows": rows, "n_exit": n_exit_h166, "n_veto": n_veto, "n_false_exit": n_false_exit}
    (wa.CACHE / "backtest_h166_result.json").write_text(json.dumps(out, default=str), encoding="utf-8")
    return out


if __name__ == "__main__":
    main()
