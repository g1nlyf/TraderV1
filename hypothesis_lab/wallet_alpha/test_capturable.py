"""PHASE 4 — capturable conversion of the H-162 distribution signal.

Shorting microcaps is not capturable. Test long-only / avoidance / exit conversions that ARE:
  (A) AVOIDANCE VETO  — among buy candidates, veto tokens under concurrent distribution; does the vetoed
                        set underperform the kept set (a real no-trade filter for Stage-2 reject)?
  (B) EXIT OVERLAY    — buy the (losing) cluster book, but exit early if a distribution signal appears in
                        the hold window; does exit-on-distribution beat hold-to-horizon?
  (C) ROTATION        — when wallets sell token A, do they buy token B within 1h, and does B beat a random
                        buy-cluster? (capturable: you buy B.)

All returns capped [-1,+1], cost 1.8% RT (frontier-tested in H-162). Gate via finetune/pipeline/eval_stats.
Run: py hypothesis_lab/wallet_alpha/test_capturable.py
"""
from __future__ import annotations

import bisect
import json
import sys
from collections import defaultdict

import numpy as np

import wa_common as wa
import wa_eval as ev

sys.path.insert(0, str(wa.ROOT / "finetune" / "pipeline"))
import eval_stats as es  # noqa: E402

wa.ensure_utf8()
ENTRY_WIN = 300
H_DEF = 1800


def build_index():
    trades = wa.load_raw_trades(session_only=True, min_sol=0.05)
    by_token = defaultdict(list)
    by_wallet = defaultdict(list)
    for t in trades:
        by_token[t.token].append(t)
        by_wallet[t.wallet].append(t)
    for d in (by_token, by_wallet):
        for k in d:
            d[k].sort(key=lambda x: x.ts)
    t1 = trades[-1].ts
    return by_token, by_wallet, t1


def _vwap(trs):
    s = sum(t.sol for t in trs)
    return (sum(t.price * t.sol for t in trs) / s) if s > 0 else None


def fwd_ret(by_token, token, t0, H, entry_win=ENTRY_WIN):
    """Realistic capturable return: entry VWAP in (t0,t0+entry_win], exit = last<=3 prints up to t0+H."""
    trs = by_token.get(token)
    if not trs:
        return None
    ts = [t.ts for t in trs]
    lo = bisect.bisect_right(ts, t0); hi = bisect.bisect_right(ts, t0 + entry_win)
    entry = _vwap(trs[lo:hi])
    if not entry or entry <= 0:
        return None
    b = bisect.bisect_right(ts, t0 + H)
    seg = trs[hi:b]
    exv = _vwap(seg[-3:]) if seg else None
    if not exv or exv <= 0:
        return None
    return ev.cap(exv / entry - 1.0 - wa.COST_RT)


def distribution_pre_t(by_token, token, t0, lookback=900, k=3):
    """Pre-t distribution signal: >=k distinct sellers in (t0-lookback, t0] AND sell_sol > buy_sol."""
    trs = by_token.get(token, [])
    ts = [t.ts for t in trs]
    a = bisect.bisect_right(ts, t0 - lookback); b = bisect.bisect_right(ts, t0)
    win = trs[a:b]
    sellers = {t.wallet for t in win if t.side == "sell"}
    sell_sol = sum(t.sol for t in win if t.side == "sell")
    buy_sol = sum(t.sol for t in win if t.side == "buy")
    return (len(sellers) >= k) and (sell_sol > buy_sol)


def distribution_in_hold(by_token, token, t0, H, k=3, win=300):
    """First time in (t0+entry, t0+H] that >=k distinct sellers cluster in a `win` window -> exit ts."""
    trs = by_token.get(token, [])
    ts = [t.ts for t in trs]
    a = bisect.bisect_right(ts, t0 + ENTRY_WIN); b = bisect.bisect_right(ts, t0 + H)
    seg = trs[a:b]
    sells = [t for t in seg if t.side == "sell"]
    i = 0                                   # running left pointer (sliding window)
    for j in range(len(sells)):
        while sells[j].ts - sells[i].ts > win:
            i += 1
        if len({s.wallet for s in sells[i:j + 1]}) >= k:
            return sells[j].ts
    return None


def report(name, fired, base_pool, capturable_note=""):
    """eval_stats-style verdict for a fired set vs a base pool (permutation = beats random base draw)."""
    fired = [float(x) for x in fired]; base_pool = [float(x) for x in base_pool]
    if len(fired) == 0:
        print(f"  {name:34s} no events"); return None
    evf = es.realized_ev(fired); evb = es.realized_ev(base_pool)
    ci = es.block_bootstrap_ci(fired)
    p = es.permutation_p(base_pool, len(fired), evf) if base_pool else 1.0
    gates = {"EV>2%": evf > 0.02, "perm<0.05": p < 0.05, "CI>0": ci[0] > 0, "n>100": len(fired) > 100}
    verdict = "PASS" if all(gates.values()) else "FAIL"
    flags = "".join("Y" if v else "." for v in gates.values())
    print(f"  {name:34s} n={len(fired):4d} EV={evf:+.2%} base={evb:+.2%} edge={evf-evb:+.2%} "
          f"perm={p:.3f} CI=[{ci[0]:+.2%},{ci[1]:+.2%}] [{flags}] {verdict}  {capturable_note}")
    return {"name": name, "n": len(fired), "ev": evf, "base": evb, "perm": p, "ci": ci, "verdict": verdict}


# ============================================================== (A) AVOIDANCE VETO
def test_avoidance(by_token, H):
    print("=" * 100); print(f"(A) AVOIDANCE VETO — distribution-veto on buy candidates  (H={H//60}m)"); print("=" * 100)
    buys = [e for e in json.loads((wa.CACHE / "events_buy.json").read_text())["events"] if e.get(f"ret_{H}") is not None]
    kept, vetoed = [], []
    for e in buys:
        r = ev.cap(e[f"ret_{H}"])
        (vetoed if distribution_pre_t(by_token, e["token"], e["form_ts"]) else kept).append(r)
    allr = kept + vetoed
    print(f"  buy candidates={len(allr)}  WITH-pre-distribution={len(vetoed)}  WITHOUT(fresh-FOMO)={len(kept)}")
    report("ALL buy candidates (base)", allr, allr)
    rw = report("WITH pre-distribution", vetoed, allr, "<- selling absorbed -> bounce (H-042 on-chain)")
    report("WITHOUT (fresh FOMO)", kept, allr, "<- fresh cluster = top -> continues down")
    # NOTE: sign is the OPPOSITE of a naive veto. Pre-absorbed selling forward-OUTPERFORMS fresh FOMO.
    if vetoed and kept:
        print(f"  SELECTION VALUE: WITH-distribution {np.mean(vetoed):+.2%} vs fresh-FOMO {np.mean(kept):+.2%} "
              f"=> preferring post-distribution buys is {np.mean(vetoed)-np.mean(kept):+.2%}/trade better "
              f"(BUT still <0 => not a long edge; relative filter only)")
    return rw


# ============================================================== (B) EXIT OVERLAY
def test_exit(by_token, H):
    print("=" * 100); print(f"(B) EXIT OVERLAY — exit-on-distribution vs hold-to-{H//60}m"); print("=" * 100)
    buys = [e for e in json.loads((wa.CACHE / "events_buy.json").read_text())["events"] if e.get(f"ret_{H}") is not None]
    hold, exitp = [], []
    exit_lags = []                          # lags where distribution fired (for the shuffled control)
    fired_idx = []
    for idx, e in enumerate(buys):
        hr = ev.cap(e[f"ret_{H}"]); hold.append(hr)
        xts = distribution_in_hold(by_token, e["token"], e["form_ts"], H)
        if xts is None:
            exitp.append(hr)            # no signal -> behaves like hold
        else:
            lag = xts - e["form_ts"]
            xr = fwd_ret(by_token, e["token"], e["form_ts"], lag)
            exitp.append(xr if xr is not None else hr)
            exit_lags.append(lag); fired_idx.append(idx)
    n_exit = len(fired_idx)
    print(f"  positions={len(hold)}  exited-early={n_exit} ({n_exit/max(len(hold),1):.0%})")
    report("HOLD-to-horizon (baseline)", hold, hold)
    rx = report("EXIT-on-distribution", exitp, hold, "<- capturable (sell rule on a long)")
    # CONTROL: same set of positions exit early, but at a SHUFFLED lag (same lag distribution, wrong timing).
    # If signal-timed >= shuffled, the distribution SIGNAL adds value beyond 'exit early in a dump'.
    rng = np.random.default_rng(2026); ctrl_means = []
    for _ in range(200):
        lags = rng.permutation(exit_lags)
        ctrl = list(hold)
        for k, idx in enumerate(fired_idx):
            cr = fwd_ret(by_token, buys[idx]["token"], buys[idx]["form_ts"], float(lags[k]))
            ctrl[idx] = cr if cr is not None else hold[idx]
        ctrl_means.append(np.mean(ctrl))
    ctrl_mean = float(np.mean(ctrl_means))
    sig_better = float(np.mean([np.mean(exitp) >= cm for cm in ctrl_means]))  # frac of shuffles signal beats
    print(f"  EXIT VALUE: hold {np.mean(hold):+.2%} -> signal-exit {np.mean(exitp):+.2%} "
          f"(+{np.mean(exitp)-np.mean(hold):+.2%}) vs shuffled-lag control {ctrl_mean:+.2%}")
    print(f"  SIGNAL-vs-CONTROL: signal-exit beats shuffled-timing in {sig_better:.0%} of draws "
          f"=> {'timing signal ADDS value' if sig_better>0.95 else 'NO timing edge beyond early-exit-in-dump'}")
    return rx


# ============================================================== (C) ROTATION
def test_rotation(by_token, by_wallet, H, t1):
    print("=" * 100); print(f"(C) ROTATION — wallets sell A -> buy B within 1h; does B beat random buy-cluster? (H={H//60}m)"); print("=" * 100)
    sells = json.loads((wa.CACHE / "events_sell.json").read_text())["events"]
    buy_base = [ev.cap(e[f"ret_{H}"]) for e in json.loads((wa.CACHE / "events_buy.json").read_text())["events"] if e.get(f"ret_{H}") is not None]
    targets, seen = [], set()
    for e in sells:
        A, t0 = e["token"], e["form_ts"]
        for w in e["wallets"]:
            for t in by_wallet.get(w, []):
                if t.side == "buy" and t0 < t.ts <= t0 + 3600 and t.token != A:
                    key = (t.token, round(t.ts / 300))    # dedup near-simultaneous targets
                    if key in seen:
                        continue
                    seen.add(key)
                    if t.ts + H <= t1:
                        r = fwd_ret(by_token, t.token, t.ts, H)
                        if r is not None:
                            targets.append(r)
    pool = buy_base + targets
    print(f"  rotation targets (B)={len(targets)}  random buy-cluster base n={len(buy_base)}")
    report("Random buy-cluster (base)", buy_base, pool)
    rr = report("ROTATION targets (B)", targets, pool, "<- capturable (buy B)")
    return rr


def main():
    by_token, by_wallet, t1 = build_index()
    print(f"[capturable] indexed raw_trades: tokens={len(by_token):,} wallets={len(by_wallet):,}\n")
    out = {}
    for H in (1800, 3600):
        out[f"avoid_{H}"] = test_avoidance(by_token, H)
        out[f"exit_{H}"] = test_exit(by_token, H)
        out[f"rot_{H}"] = test_rotation(by_token, by_wallet, H, t1)
        print()
    passes = [k for k, v in out.items() if v and v["verdict"] == "PASS"]
    print("=" * 100)
    print(f"CAPTURABLE SUMMARY: {len(passes)} gate-clearing capturable rule(s): {passes or 'none'}")
    print("  (No-trade/exit VALUE is reported even when long-EV stays negative — that is the Stage-2 use.)")
    return out


if __name__ == "__main__":
    main()
