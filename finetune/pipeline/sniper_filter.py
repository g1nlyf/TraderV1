"""
Sniper / un-copyable wallet filter — rigorous, from real tapes.

The cluster research found low entry_price predicts huge returns (rho -0.41). That is
the SNIPER ARTIFACT, not a copyable edge: snipers buy in the first block at impossibly
low prices (sometimes before the dev), the token "pumps," but you can NEVER match their
fill -> uncopyable. Must exclude these wallets before any copy analysis.

Sniper signatures (the user's description, made quantitative):
  - buy_vs_market << 1: they consistently buy FAR below where the cohort later trades
    (the decisive signal — measures "could we realistically match their price?")
  - micro buy size: tiny SOL per buy relative to their wins (lottery-ticket sniping)
  - ultra-high frequency: hundreds of tokens, seconds-held, first-buyer everywhere
  - extreme payoff + ultra-short hold (from wallet_scoring)

A wallet is UN-COPYABLE if buy_vs_market_median < 0.55 (we'd enter 80%+ higher than them)
OR (median_buy_sol < 0.03 AND high frequency). Output: clean (copyable) wallet set.
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
OUT_CLEAN = ROOT / "finetune" / "data" / "clean_wallets.json"
OUT_SNIPER = ROOT / "finetune" / "data" / "sniper_wallets.json"

from finetune.pipeline.helius_client import SwapEvent

REF_WINDOW = 3600         # measure market price within 1h after the buy
BUY_VS_MARKET_MIN = 0.72  # below this = bought far under market = uncopyable
MICRO_SOL = 0.03


def main():
    tapes = {w: [SwapEvent(**e) for e in evs]
             for w, evs in json.loads(TAPES.read_text(encoding="utf-8")).items()}
    lb = {w["wallet"]: w for w in json.loads(LB.read_text(encoding="utf-8"))}

    # cohort reference prices per token (all trades)
    token_trades = defaultdict(list)
    for evs in tapes.values():
        for s in evs:
            if s.price_sol > 0:
                token_trades[s.token_mint].append((s.ts, s.price_sol))
    for t in token_trades:
        token_trades[t].sort()

    clean, snipers = [], []
    for w, evs in tapes.items():
        buys = [s for s in evs if s.side == "buy" and s.price_sol > 0]
        if not buys:
            continue
        ratios = []
        for b in buys:
            ref = [p for ts, p in token_trades[b.token_mint]
                   if b.ts < ts <= b.ts + REF_WINDOW]
            if len(ref) >= 2:
                ratios.append(b.price_sol / statistics.median(ref))
        bvm = statistics.median(ratios) if ratios else None
        med_sol = statistics.median([b.sol_amount for b in buys if b.sol_amount > 0] or [0])
        # frequency: swaps per active hour
        span_h = max(1, (max(s.ts for s in evs) - min(s.ts for s in evs)) / 3600)
        freq = len(evs) / span_h
        hold = lb.get(w, {}).get("avg_hold_sec", 9999)

        reasons = []
        if bvm is not None and bvm < BUY_VS_MARKET_MIN:
            reasons.append(f"buys {(1-bvm)*100:.0f}% below market (uncopyable)")
        if med_sol < MICRO_SOL and freq > 8:
            reasons.append(f"micro buys {med_sol:.3f}SOL + freq {freq:.0f}/h")
        if hold is not None and hold < 90 and lb.get(w, {}).get("payoff_ratio", 0) > 15:
            reasons.append("ultra-short hold + extreme payoff")

        rec = {"wallet": w, "buy_vs_market": round(bvm, 3) if bvm is not None else None,
               "median_buy_sol": round(med_sol, 4), "freq_per_h": round(freq, 1),
               "hold_sec": hold, "score": lb.get(w, {}).get("score"),
               "pnl": lb.get(w, {}).get("realized_pnl_sol"), "reasons": reasons}
        (snipers if reasons else clean).append(rec)

    clean.sort(key=lambda r: r.get("score") or 0, reverse=True)
    OUT_CLEAN.write_text(json.dumps(clean, ensure_ascii=False, indent=2), encoding="utf-8")
    OUT_SNIPER.write_text(json.dumps(snipers, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[sniper] total={len(clean)+len(snipers)}  CLEAN(copyable)={len(clean)}  SNIPER/uncopyable={len(snipers)}")
    print("\n=== flagged SNIPERS (excluded) ===")
    for r in sorted(snipers, key=lambda r: (r.get("pnl") or 0), reverse=True)[:10]:
        print(f"  {r['wallet'][:18]} bvm={r['buy_vs_market']} buy={r['median_buy_sol']}SOL "
              f"freq={r['freq_per_h']}/h pnl={r['pnl']} :: {'; '.join(r['reasons'])}")
    print("\n=== top CLEAN (copyable) wallets ===")
    for r in clean[:10]:
        print(f"  {r['wallet'][:18]} bvm={r['buy_vs_market']} buy={r['median_buy_sol']}SOL "
              f"freq={r['freq_per_h']}/h hold={r['hold_sec']}s score={r['score']} pnl={r['pnl']}")


if __name__ == "__main__":
    main()
