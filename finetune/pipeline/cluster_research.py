"""
Cluster Research — parallel hypothesis mining on the cached cohort tapes.

Instead of testing one signal serially (slow), build a feature-rich dataset of EVERY
historical consensus cluster across the 86 cached wallet tapes, attach a forward
outcome (follow-cohort-out return), and test MANY competing hypotheses at once:

  H1 breadth        : # distinct wallets in the cluster
  H2 avg_quality    : mean leaderboard score of the cluster wallets
  H3 max_quality    : best wallet's score
  H4 lead_quality   : first buyer's score (the alpha source)
  H5 speed_sec      : time span of the cluster buys (tight = fast conviction)
  H6 avg_buy_sol    : average SOL size (conviction)
  H7 breadth>=3     : the prior consensus threshold

Outcome = follow-cohort-out: first cohort sell after formation / entry price (capped).
Features are pre-formation; outcome is post -> forward-clean. Spearman rank-corr is
robust to memecoin price outliers.

Max information per unit time: one pass, all hypotheses ranked by predictive power.
"""
from __future__ import annotations

import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore

ROOT = Path(__file__).resolve().parents[2]
TAPES = ROOT / "finetune" / "data" / "wallet_tapes.json"
LB = ROOT / "finetune" / "data" / "wallet_leaderboard.json"

from finetune.pipeline.helius_client import SwapEvent

WINDOW = 90 * 60      # cluster window
COST = 0.018
CAP = 5.0             # cap returns at +500% (artifact guard)


def spearman(xs, ys):
    n = len(xs)
    if n < 5:
        return None
    def rank(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        r = [0] * len(v)
        for pos, i in enumerate(order):
            r[i] = pos
        return r
    rx, ry = rank(xs), rank(ys)
    mx, my = sum(rx) / n, sum(ry) / n
    cov = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    sx = (sum((a - mx) ** 2 for a in rx)) ** 0.5
    sy = (sum((b - my) ** 2 for b in ry)) ** 0.5
    return cov / (sx * sy) if sx and sy else None


def main():
    tapes = {w: [SwapEvent(**e) for e in evs]
             for w, evs in json.loads(TAPES.read_text(encoding="utf-8")).items()}
    scores = {w["wallet"]: w["score"] for w in json.loads(LB.read_text(encoding="utf-8"))}

    # EXCLUDE snipers (uncopyable) — clean_wallets.json from sniper_filter.py
    clean_f = ROOT / "finetune" / "data" / "clean_wallets.json"
    if clean_f.exists():
        clean = {w["wallet"] for w in json.loads(clean_f.read_text(encoding="utf-8"))}
        before = len(tapes)
        tapes = {w: e for w, e in tapes.items() if w in clean}
        print(f"[research] sniper-filtered wallets: {before} -> {len(tapes)} clean")

    # per-token: buys (ts,wallet,price,sol) and all trades (ts,price) for the path
    buys = defaultdict(list)
    path = defaultdict(list)
    sells = defaultdict(list)
    for w, evs in tapes.items():
        for s in evs:
            if s.price_sol <= 0:
                continue
            path[s.token_mint].append((s.ts, s.price_sol))
            if s.side == "buy":
                buys[s.token_mint].append((s.ts, w, s.price_sol, s.sol_amount, s.token_amount))
            else:
                sells[s.token_mint].append((s.ts, w, s.price_sol))
    for t in path:
        path[t].sort()
        sells[t].sort()

    rows = []   # (features dict, outcome)
    for token, bs in buys.items():
        bs.sort()
        # first cluster: sliding window k>=2
        i = 0
        for j in range(len(bs)):
            while bs[j][0] - bs[i][0] > WINDOW:
                i += 1
            window = bs[i:j + 1]
            wals = {b[1] for b in window}
            if len(wals) >= 2:
                entry = window[-1][2]            # wallet's own buy price (a feature)
                form_ts = window[-1][0]
                # COPYABLE entry = price WE'd pay with REALISTIC detection+execution lag:
                # a real copier sees the cluster only AFTER it forms, enters 5-20min later
                # (not at the cohort's early launch-low fill). This is the honest copier price.
                we_ref = [p for ts, p in path[token] if form_ts + 300 <= ts <= form_ts + 1200]
                we_pay = statistics.median(we_ref) if we_ref else None
                if we_pay is None:
                    break   # no realistic post-signal price -> can't copy
                # outcome: first cohort sell after formation
                ex = next((p for ts, w2, p in sells[token] if ts > form_ts and w2 in wals), None)
                if ex is None:
                    ex = next((p for ts, p in path[token] if ts > form_ts + 300), None)
                if ex is None or we_pay <= 0:
                    break
                ret = max(-1.0, min(CAP, ex / we_pay - 1 - COST))   # OUR copyable return
                slip = (we_pay / entry - 1) if entry > 0 else 0     # how far above wallet we enter
                qs = [scores.get(b[1], 0) for b in window]
                import math
                feats = {
                    "breadth": len(wals),
                    "avg_quality": sum(qs) / len(qs),
                    "lead_quality": scores.get(window[0][1], 0),
                    "speed_sec": form_ts - window[0][0],
                    "avg_buy_sol": sum(b[3] for b in window) / len(window),
                    "entry_price": entry,
                    "log_price": math.log10(entry) if entry > 0 else -20,
                    "avg_token_qty": sum(b[4] for b in window) / len(window),
                    "total_buy_sol": sum(b[3] for b in window),
                    "copy_slippage": slip,
                }
                rows.append((feats, ret))
                break

    print(f"[research] clusters with outcomes: {len(rows)}")
    if len(rows) < 10:
        print("[research] too few"); return
    rets = [r for _, r in rows]
    print(f"[research] overall: median={statistics.median(rets):+.1%} "
          f"mean={statistics.mean(rets):+.1%} win={sum(1 for r in rets if r>0)/len(rets):.0%}\n")

    print("=== HYPOTHESIS RANKING (Spearman corr of feature vs forward return) ===")
    feat_names = ["breadth", "avg_quality", "lead_quality", "speed_sec", "avg_buy_sol",
                  "entry_price", "log_price", "avg_token_qty", "total_buy_sol", "copy_slippage"]
    results = []
    for f in feat_names:
        xs = [row[0][f] for row in rows]
        rho = spearman(xs, rets)
        results.append((f, rho))
    for f, rho in sorted(results, key=lambda x: -(abs(x[1]) if x[1] else 0)):
        if rho is not None:
            arrow = "↑profit" if rho > 0 else "↓profit"
            print(f"  {f:14s}: rho={rho:+.3f}  {arrow if abs(rho)>0.05 else '(noise)'}")

    # bucket the strongest feature
    best = max((r for r in results if r[1] is not None), key=lambda x: abs(x[1]))
    f = best[0]
    print(f"\n=== BUCKET ANALYSIS on strongest: {f} ===")
    rows.sort(key=lambda row: row[0][f])
    q = len(rows) // 4
    for name, sub in [("bottom25%", rows[:q]), ("mid", rows[q:3*q]), ("top25%", rows[3*q:])]:
        rs = [r for _, r in sub]
        if rs:
            print(f"  {name:9s}: n={len(rs):3d} win={sum(1 for r in rs if r>0)/len(rs):.0%} "
                  f"median={statistics.median(rs):+.1%} mean={statistics.mean(rs):+.1%}")

    # SEGMENT BY TOKEN SPEED — our lag only hurts on FAST tokens. The field we can
    # actually play = SLOW tokens (low copy_slippage = price barely moved in our 5-20min lag).
    def summ(rs, label):
        if rs:
            print(f"  {label:28s}: n={len(rs):3d} win={sum(1 for r in rs if r>0)/len(rs):.0%} "
                  f"median={statistics.median(rs):+.1%} mean={statistics.mean(rs):+.1%}")
    print(f"\n=== SEGMENT BY TOKEN SPEED (copy_slippage = price move in our lag) ===")
    slow = [r for f, r in rows if abs(f["copy_slippage"]) < 0.25]
    fast = [r for f, r in rows if abs(f["copy_slippage"]) >= 0.25]
    summ(slow, "SLOW tokens (|slip|<25%)")
    summ(fast, "FAST tokens (|slip|>=25%)")
    # within SLOW, does wallet quality help?
    if len(slow) >= 12:
        slow_rows = [(f, r) for f, r in rows if abs(f["copy_slippage"]) < 0.25]
        mq = statistics.median([f["avg_quality"] for f, _ in slow_rows])
        hi = [r for f, r in slow_rows if f["avg_quality"] >= mq]
        lo = [r for f, r in slow_rows if f["avg_quality"] < mq]
        print("  within SLOW:")
        summ(hi, "  high-quality wallets")
        summ(lo, "  low-quality wallets")


if __name__ == "__main__":
    main()
