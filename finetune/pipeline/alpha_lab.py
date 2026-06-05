"""
Alpha Lab — multi-factor entry-condition research (learn the wallets' DECISION MODEL).

Reframe (per the mandate): don't copy trades. Learn what CONDITIONS are present when
good wallets enter AND win. Then detect those conditions ourselves in real-time on any
token -> no copy-latency. The wallet is a teacher that labels good-entry conditions.

Method:
  1. Reconstruct every clean (non-sniper) wallet's full round-trips (buy -> sell, FIFO).
  2. At each entry, compute TOKEN-CONTEXT features from the whole cohort's activity on
     that token BEFORE the entry (momentum, prior consensus, net flow, age, acceleration,
     time-of-day, wallet quality).
  3. Label = the wallet's realized return on that round-trip (their full cycle).
  4. Multi-factor analysis: single features + best 2-way COMBINATIONS that maximize
     win-rate -> the alpha condition profile.

This is 10 research directions in one dataset: lifecycle, pre-entry token state, meta
factor combinations, temporal, wallet behavior. Spearman + win-rate buckets, robust to
memecoin outliers.
"""
from __future__ import annotations

import json
import math
import statistics
import sys
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore

ROOT = Path(__file__).resolve().parents[2]
TAPES = ROOT / "finetune" / "data" / "wallet_tapes.json"
LB = ROOT / "finetune" / "data" / "wallet_leaderboard.json"
CLEAN = ROOT / "finetune" / "data" / "clean_wallets.json"

from finetune.pipeline.helius_client import SwapEvent

WIN = 0.10   # round-trip return > +10% = win label


def load():
    tapes = {w: [SwapEvent(**e) for e in evs]
             for w, evs in json.loads(TAPES.read_text(encoding="utf-8")).items()}
    scores = {w["wallet"]: w["score"] for w in json.loads(LB.read_text(encoding="utf-8"))}
    clean = {w["wallet"] for w in json.loads(CLEAN.read_text(encoding="utf-8"))} if CLEAN.exists() else set(tapes)
    return {w: e for w, e in tapes.items() if w in clean}, scores


def token_context(token_trades, entry_ts):
    """Order-flow microstructure features from cohort activity BEFORE entry_ts."""
    before = [x for x in token_trades if x[0] < entry_ts]
    if not before:
        return None
    first_ts = before[0][0]
    last_hour = [x for x in before if entry_ts - x[0] <= 3600]
    last_15 = [x for x in before if entry_ts - x[0] <= 900]
    buys_1h = [x for x in last_hour if x[1] == "buy"]
    sells_1h = [x for x in last_hour if x[1] == "sell"]
    buys_15 = [x for x in last_15 if x[1] == "buy"]
    prices_1h = [x[2] for x in last_hour if x[2] > 0]
    cur = before[-1][2]
    vol_buy = sum(x[3] for x in buys_1h)
    vol_sell = sum(x[3] for x in sells_1h)
    return {
        "token_age_min": (entry_ts - first_ts) / 60,
        "prior_buys_1h": len(buys_1h),
        "net_flow_1h": len(buys_1h) - len(sells_1h),
        "unique_buyers_1h": len({x[4] for x in buys_1h}),          # distinct buyer breadth
        "vol_flow_1h": vol_buy - vol_sell,                         # net SOL flow (magnitude)
        "buyer_accel": len({x[4] for x in buys_15}) / max(1, len({x[4] for x in buys_1h})),
        "buy_accel": (len(buys_15) / max(1, len(buys_1h))),
        "mom_1h": (cur / statistics.median(prices_1h) - 1) if len(prices_1h) >= 2 else 0.0,
    }


def main():
    tapes, scores = load()
    # cohort trades per token (all clean wallets): (ts, side, price, sol, wallet)
    token_trades = defaultdict(list)
    for w, evs in tapes.items():
        for s in evs:
            if s.price_sol > 0:
                token_trades[s.token_mint].append((s.ts, s.side, s.price_sol, s.sol_amount, w))
    for t in token_trades:
        token_trades[t].sort()

    rows = []   # (features, ret, win)
    for w, evs in tapes.items():
        lots = defaultdict(deque)
        for s in sorted(evs, key=lambda x: x.ts):
            if s.side == "buy":
                lots[s.token_mint].append(s)
            else:  # sell closes oldest buy -> round trip
                if lots[s.token_mint]:
                    b = lots[s.token_mint].popleft()
                    if b.price_sol > 0 and s.price_sol > 0:
                        ret = s.price_sol / b.price_sol - 1
                        ret = max(-1.0, min(10.0, ret))
                        ctx = token_context(token_trades[s.token_mint], b.ts)
                        if ctx:
                            ctx["wallet_score"] = scores.get(w, 0)   # LEAKY: for reference only
                            ctx["hour"] = datetime.fromtimestamp(b.ts, timezone.utc).hour
                            ctx["_ts"] = b.ts
                            rows.append((ctx, ret, 1 if ret > WIN else 0))

    print(f"[alpha] round-trips analyzed: {len(rows)}")
    if len(rows) < 30:
        print("[alpha] too few"); return
    base_win = sum(w for _, _, w in rows) / len(rows)
    print(f"[alpha] base win-rate (ret>+10%): {base_win:.0%}  median ret={statistics.median([r for _,r,_ in rows]):+.1%}\n")

    feats = ["token_age_min", "prior_buys_1h", "net_flow_1h", "buy_accel", "mom_1h",
             "wallet_score", "hour", "hold_min"]

    def spear(f):
        xs = [r[0].get(f, 0) for r in rows]; ys = [r[1] for r in rows]
        n = len(xs)
        def rk(v):
            o = sorted(range(len(v)), key=lambda i: v[i]); r = [0]*len(v)
            for p, i in enumerate(o): r[i] = p
            return r
        rx, ry = rk(xs), rk(ys); mx, my = sum(rx)/n, sum(ry)/n
        cov = sum((a-mx)*(b-my) for a, b in zip(rx, ry))
        sx = (sum((a-mx)**2 for a in rx))**.5; sy = (sum((b-my)**2 for b in ry))**.5
        return cov/(sx*sy) if sx and sy else 0

    print("=== SINGLE-FACTOR (Spearman vs return) ===")
    sf = sorted([(f, spear(f)) for f in feats], key=lambda x: -abs(x[1]))
    for f, rho in sf:
        print(f"  {f:16s}: rho={rho:+.3f} {'<-- signal' if abs(rho)>0.08 else ''}")

    # META on CLEAN pre-entry features only (drop leaky wallet_score, look-ahead hold_min).
    # Temporal holdout: derive combo on first 70% of time, VALIDATE win-rate on last 30%.
    clean_feats = ["token_age_min", "prior_buys_1h", "net_flow_1h", "buy_accel", "mom_1h", "hour"]
    rows.sort(key=lambda r: r[0]["_ts"])
    split = int(len(rows) * 0.7)
    train, test = rows[:split], rows[split:]

    # FACTOR STABILITY: is each factor's direction stable across the regime shift?
    def spear_sub(sub, f):
        xs = [r[0].get(f, 0) for r in sub]; ys = [r[1] for r in sub]
        n = len(xs)
        if n < 10:
            return 0.0
        def rk(v):
            o = sorted(range(len(v)), key=lambda i: v[i]); rr = [0]*len(v)
            for p, i in enumerate(o): rr[i] = p
            return rr
        rx, ry = rk(xs), rk(ys); mx, my = sum(rx)/n, sum(ry)/n
        cov = sum((a-mx)*(b-my) for a, b in zip(rx, ry))
        sx = (sum((a-mx)**2 for a in rx))**.5; sy = (sum((b-my)**2 for b in ry))**.5
        return cov/(sx*sy) if sx and sy else 0
    print(f"\n=== FACTOR STABILITY (Spearman: train | test) — does direction survive regime shift? ===")
    for f in ["net_flow_1h","vol_flow_1h","unique_buyers_1h","buyer_accel","buy_accel","prior_buys_1h","mom_1h","token_age_min"]:
        rt, re = spear_sub(train, f), spear_sub(test, f)
        tag = "STABLE" if (rt*re > 0 and abs(re) > 0.05) else "decayed/flip" if rt*re < 0 else "weak"
        print(f"  {f:16s}: train={rt:+.3f}  test={re:+.3f}  -> {tag}")
    meds = {f: statistics.median([r[0].get(f, 0) for r in train]) for f in clean_feats}
    base_test = sum(w for _, _, w in test) / len(test)
    print(f"\n=== META (clean pre-entry features, TEMPORAL holdout) ===")
    print(f"  train n={len(train)}  test n={len(test)}  test base-win={base_test:.0%}")

    combos = []
    for i, fa in enumerate(clean_feats):
        for fb in clean_feats[i+1:]:
            for da in (1, -1):
                for db in (1, -1):
                    def match(r, f, d):
                        return (r[0].get(f, 0) >= meds[f]) == (d > 0)
                    tr = [r for r in train if match(r, fa, da) and match(r, fb, db)]
                    if len(tr) >= 30:
                        wr_tr = sum(w for _, _, w in tr) / len(tr)
                        te = [r for r in test if match(r, fa, da) and match(r, fb, db)]
                        wr_te = (sum(w for _, _, w in te) / len(te)) if len(te) >= 10 else None
                        med_te = statistics.median([r for _, r, _ in te]) if len(te) >= 10 else None
                        combos.append((wr_tr, len(tr), wr_te, len(te), med_te,
                                       f"{fa}={'hi' if da>0 else 'lo'} & {fb}={'hi' if db>0 else 'lo'}"))
    # rank by TRAIN win-rate, show TEST (out-of-sample) result = the honest number
    combos.sort(key=lambda x: -x[0])
    print("  combo (train->test):")
    for wr_tr, ntr, wr_te, nte, med_te, label in combos[:8]:
        te_str = f"TEST win={wr_te:.0%} med={med_te:+.0%} (n={nte})" if wr_te is not None else "TEST n/a"
        print(f"    {label:34s} train={wr_tr:.0%}(n={ntr}) -> {te_str}")


if __name__ == "__main__":
    main()
