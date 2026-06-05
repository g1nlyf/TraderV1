"""
Forward-validated copy backtest — the HONEST number.

Kills the look-ahead/selection bias in copy_engine: there we picked wallets because
they were profitable all-time, then "tested" copying their own winning trades
(circular -> fake +2900%). Here:

  1. Restrict to COPYABLE SWING wallets (copyable_wallets.json) — drop snipers we
     can't follow (they'd dump on us).
  2. Time split at T. SELECT wallets with positive realized PnL on PRE-T trades only.
  3. Find clusters in the POST-T window among the pre-T-selected wallets.
  4. Backtest copying those POST-T clusters (follow_majority exit).
  5. Report MEDIAN (robust to memecoin outliers), win-rate, quartiles — not mean.

This is a true forward test: selection uses the past, the PnL uses the future.

Uses cached tapes (wallet_tapes.json from copy_engine). No new Helius calls.
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
COPYABLE = ROOT / "finetune" / "data" / "copyable_wallets.json"

from finetune.pipeline.helius_client import SwapEvent
from finetune.pipeline.wallet_scoring import reconstruct_pnl

COST = 0.018


def load_tapes() -> dict[str, list[SwapEvent]]:
    raw = json.loads(TAPES.read_text(encoding="utf-8"))
    return {w: [SwapEvent(**e) for e in evs] for w, evs in raw.items()}


def main(k: int = 2, window_min: int = 120, t_pct: float = 0.6):
    tapes_all = load_tapes()
    copyable = {w["wallet"] for w in json.loads(COPYABLE.read_text(encoding="utf-8"))}
    tapes = {w: evs for w, evs in tapes_all.items() if w in copyable}
    print(f"[fwd] copyable wallets with tapes: {len(tapes)}")
    if len(tapes) < 2:
        print("[fwd] too few copyable wallets with cached tapes"); return

    all_ts = sorted(s.ts for evs in tapes.values() for s in evs)
    if not all_ts:
        print("[fwd] no swaps"); return
    T = all_ts[int(len(all_ts) * t_pct)]
    import datetime
    print(f"[fwd] split T={datetime.datetime.utcfromtimestamp(T):%Y-%m-%d %H:%M}  "
          f"(pre={t_pct:.0%}/post)")

    # 1. select wallets profitable on PRE-T trades
    selected = {}
    for w, evs in tapes.items():
        pre = [s for s in evs if s.ts <= T]
        sc = reconstruct_pnl(pre)
        if sc and sc.realized_pnl_sol > 0 and sc.win_rate >= 0.5:
            selected[w] = sc.score
    print(f"[fwd] wallets profitable PRE-T (forward-valid selection): {len(selected)}")
    if len(selected) < 2:
        print("[fwd] too few pre-T-profitable wallets — need more wallets/data"); return

    # 2. clusters in POST-T among selected
    post_buys = defaultdict(list)
    for w in selected:
        for s in tapes[w]:
            if s.side == "buy" and s.ts > T:
                post_buys[s.token_mint].append((s.ts, w, s.price_sol))
    clusters = []
    for token, buys in post_buys.items():
        buys.sort()
        i = 0
        for j in range(len(buys)):
            while buys[j][0] - buys[i][0] > window_min * 60:
                i += 1
            win = buys[i:j + 1]
            ws = {b[1] for b in win}
            if len(ws) >= k:
                clusters.append({"token": token, "form_ts": win[-1][0], "wallets": sorted(ws),
                                 "entry": sum(b[2] for b in win) / len(win)})
                break
    print(f"[fwd] POST-T clusters (>= {k} selected wallets): {len(clusters)}")
    if not clusters:
        print("[fwd] no forward clusters — selected wallets don't co-buy post-T (need bigger pool)")
        return

    # 3. copy backtest: follow_majority exit
    pnls = []
    for c in clusters:
        token, entry, form = c["token"], c["entry"], c["form_ts"]
        sells = []
        for w in c["wallets"]:
            for s in tapes[w]:
                if s.token_mint == token and s.side == "sell" and s.ts > form:
                    sells.append(s.price_sol); break
        if len(sells) >= max(1, len(c["wallets"]) // 2) and entry > 0:
            sells.sort()
            mp = sells[len(sells) // 2]
            r = mp / entry - 1 - COST
            # filter price-data artifacts (scam tokens with broken prices); cap at +1000%/-100%
            if r > 10.0 or r < -1.0:
                continue
            pnls.append(r)

    if not pnls:
        print("[fwd] no closed forward copy-trades (clusters never sold post-T)"); return
    pnls.sort()
    wins = [p for p in pnls if p > 0]
    print(f"\n=== FORWARD COPY BACKTEST (honest, copyable swings, follow_majority) ===")
    print(f"  trades:    {len(pnls)}")
    print(f"  win_rate:  {len(wins)/len(pnls):.1%}")
    print(f"  MEDIAN:    {statistics.median(pnls):+.2%}   <- the honest per-trade number")
    print(f"  mean:      {statistics.mean(pnls):+.2%}   (outlier-skewed, ignore)")
    print(f"  p25/p75:   {pnls[len(pnls)//4]:+.2%} / {pnls[3*len(pnls)//4]:+.2%}")
    print(f"  best/worst:{pnls[-1]:+.1%} / {pnls[0]:+.1%}")


if __name__ == "__main__":
    main()
