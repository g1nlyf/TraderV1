"""
Copy-trade engine — cluster detection + copy backtest. The core of the system.

Pipeline:
  1. Load the wallet leaderboard, take the top-N smart wallets (score + positive PnL).
  2. Pull each top wallet's full on-chain tape (Helius), cache it.
  3. CLUSTER DETECTION: find tokens that >= K distinct top wallets BOUGHT within a
     time window W. A cluster = smart-money consensus = the entry signal.
  4. COPY BACKTEST: simulate entering when the cluster forms, and compare exit rules:
       - follow_lead     : exit when the highest-scored wallet in the cluster sells
       - follow_majority : exit when >= half the cluster wallets have sold
       - target_stop     : exit at +TP / -SL
     Report realized PnL per rule -> pick the best exit empirically.

This answers the user's vision directly: track best wallets, find tokens 5+ of them
bought, use their exact on-chain entry/exit prices, learn the pattern. No candle
guessing — entries/exits are real fills from chain.

SECURITY: Helius keys via env only.

Run (after wallet_leaderboard.py has produced a leaderboard):
  python -m finetune.pipeline.copy_engine --top 25 --k 2 --window-min 60
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from dataclasses import asdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore

ROOT = Path(__file__).resolve().parents[2]
LB = ROOT / "finetune" / "data" / "wallet_leaderboard.json"
TAPES = ROOT / "finetune" / "data" / "wallet_tapes.json"

from finetune.pipeline.helius_client import wallet_swaps, SwapEvent

COST = 0.018  # entry+exit fees+slippage estimate (SOL DEX ~0.9% each side)


def top_wallets(n: int, min_pnl: float = 0.05) -> list[dict]:
    lb = json.loads(LB.read_text(encoding="utf-8"))
    good = [w for w in lb if w["realized_pnl_sol"] >= min_pnl and w["score"] >= 0.4]
    return sorted(good, key=lambda w: w["score"], reverse=True)[:n]


def get_tapes(wallets: list[str], pages: int = 3) -> dict[str, list[SwapEvent]]:
    cache = {}
    if TAPES.exists():
        raw = json.loads(TAPES.read_text(encoding="utf-8"))
        for w, evs in raw.items():
            cache[w] = [SwapEvent(**e) for e in evs]
    out = {}
    for w in wallets:
        if w in cache:
            out[w] = cache[w]; continue
        try:
            out[w] = wallet_swaps(w, pages=pages)
        except Exception as e:
            print(f"  tape fail {w[:12]}: {str(e)[:50]}"); out[w] = []
    # persist cache
    TAPES.write_text(json.dumps({w: [asdict(s) for s in evs] for w, evs in {**cache, **out}.items()},
                                ensure_ascii=False), encoding="utf-8")
    return out


def find_clusters(tapes: dict[str, list[SwapEvent]], scores: dict[str, float],
                  k: int, window_sec: int) -> list[dict]:
    """Token -> [buy events by top wallets]; cluster if >=k distinct wallets buy in window."""
    buys_by_token: dict[str, list[tuple]] = defaultdict(list)
    for w, evs in tapes.items():
        for s in evs:
            if s.side == "buy":
                buys_by_token[s.token_mint].append((s.ts, w, s.price_sol))
    clusters = []
    for token, buys in buys_by_token.items():
        buys.sort()
        # sliding window over buy timestamps
        i = 0
        for j in range(len(buys)):
            while buys[j][0] - buys[i][0] > window_sec:
                i += 1
            window = buys[i:j + 1]
            wallets_in = {b[1] for b in window}
            if len(wallets_in) >= k:
                lead = max(wallets_in, key=lambda w: scores.get(w, 0))
                clusters.append({
                    "token": token,
                    "form_ts": window[-1][0],
                    "wallets": sorted(wallets_in),
                    "n_wallets": len(wallets_in),
                    "lead": lead,
                    "entry_price": sum(b[2] for b in window) / len(window),
                })
                break  # one cluster event per token (first formation)
    return clusters


def _exit_price(token: str, after_ts: float, tapes: dict, wallets: list[str]) -> tuple[float, str] | None:
    """First sell of `token` by any of `wallets` after `after_ts` -> (price, wallet)."""
    best = None
    for w in wallets:
        for s in tapes.get(w, []):
            if s.token_mint == token and s.side == "sell" and s.ts > after_ts:
                if best is None or s.ts < best[0]:
                    best = (s.ts, s.price_sol, w)
    return (best[1], best[2]) if best else None


def backtest(clusters: list[dict], tapes: dict, scores: dict) -> dict:
    rules = {"follow_lead": [], "follow_majority": [], "target_stop": []}
    for c in clusters:
        token, entry, form_ts = c["token"], c["entry_price"], c["form_ts"]
        wallets = c["wallets"]
        if entry <= 0:
            continue
        # follow_lead: exit when lead wallet sells
        ex = _exit_price(token, form_ts, tapes, [c["lead"]])
        if ex:
            rules["follow_lead"].append(ex[0] / entry - 1 - COST)
        # follow_majority: exit when >= half cluster wallets have a sell after entry
        sells = []
        for w in wallets:
            e = _exit_price(token, form_ts, tapes, [w])
            if e:
                sells.append(e[0])
        if len(sells) >= max(1, len(wallets) // 2):
            sells.sort()
            mprice = sells[len(wallets) // 2] if len(wallets) // 2 < len(sells) else sells[-1]
            rules["follow_majority"].append(mprice / entry - 1 - COST)
        # target_stop: +60% / -25% based on any cluster wallet's realized path
        anyex = _exit_price(token, form_ts, tapes, wallets)
        if anyex:
            r = anyex[0] / entry - 1
            r = min(0.60, max(-0.25, r))
            rules["target_stop"].append(r - COST)

    def summ(rs):
        if not rs:
            return {"trades": 0}
        wins = [r for r in rs if r > 0]
        return {"trades": len(rs), "win_rate": round(len(wins) / len(rs), 3),
                "avg_pnl": round(sum(rs) / len(rs), 4),
                "total_pnl": round(sum(rs), 3),
                "median": round(sorted(rs)[len(rs) // 2], 4)}
    return {name: summ(rs) for name, rs in rules.items()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=25)
    ap.add_argument("--k", type=int, default=2, help="min distinct top wallets for a cluster")
    ap.add_argument("--window-min", type=int, default=60)
    ap.add_argument("--pages", type=int, default=3)
    a = ap.parse_args()

    if not LB.exists():
        print("[copy] no leaderboard yet — run wallet_leaderboard.py first"); sys.exit(1)
    tw = top_wallets(a.top)
    print(f"[copy] top wallets (score>=0.4, pnl>0): {len(tw)}")
    for w in tw[:10]:
        print(f"  {w['wallet'][:20]} score={w['score']} pnl={w['realized_pnl_sol']:+.2f} "
              f"win={w['win_rate']:.0%} payoff={w['payoff_ratio']}")
    if len(tw) < 2:
        print("[copy] too few good wallets — leaderboard still scoring or pool weak"); return

    scores = {w["wallet"]: w["score"] for w in tw}
    print(f"\n[copy] pulling tapes for {len(tw)} wallets...")
    tapes = get_tapes([w["wallet"] for w in tw], pages=a.pages)
    n_sw = sum(len(v) for v in tapes.values())
    print(f"[copy] total swaps: {n_sw}")

    clusters = find_clusters(tapes, scores, k=a.k, window_sec=a.window_min * 60)
    print(f"[copy] clusters found (>= {a.k} top wallets / {a.window_min}min): {len(clusters)}")
    for c in clusters[:10]:
        print(f"  {c['token'][:16]} : {c['n_wallets']} wallets, lead={c['lead'][:10]}")

    if not clusters:
        print("[copy] no clusters — top wallets don't overlap on tokens (need more wallets or bigger window)")
        return

    res = backtest(clusters, tapes, scores)
    print(f"\n=== COPY BACKTEST (exit-rule comparison) ===")
    for rule, m in res.items():
        print(f"  {rule:16s}: {m}")
    best = max(res.items(), key=lambda kv: kv[1].get("avg_pnl", -9) if kv[1].get("trades", 0) else -9)
    print(f"\n[copy] BEST exit rule: {best[0]}  avg_pnl={best[1].get('avg_pnl')}")


if __name__ == "__main__":
    main()
