"""
Skill-persistence test — the make-or-break question.

Forward-copy showed +2.3% median. But is that SKILL (the wallet is good and stays
good) or just BETA (the market pumped, everyone made money)? If pre-T-good wallets
do NOT beat pre-T-bad wallets post-T, "smart money" is an illusion and selection
adds nothing.

Test: split each wallet's tape at global T. Compute pre-T score and post-T realized
PnL. If pre-T quality PREDICTS post-T PnL (positive correlation; top-half beats
bottom-half), skill persists -> selection is real alpha.

Uses cached tapes (wallet_tapes.json). No new Helius calls.
"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore

ROOT = Path(__file__).resolve().parents[2]
TAPES = ROOT / "finetune" / "data" / "wallet_tapes.json"

from finetune.pipeline.helius_client import SwapEvent
from finetune.pipeline.wallet_scoring import reconstruct_pnl


def main(t_pct: float = 0.5):
    raw = json.loads(TAPES.read_text(encoding="utf-8"))
    tapes = {w: [SwapEvent(**e) for e in evs] for w, evs in raw.items()}
    all_ts = sorted(s.ts for evs in tapes.values() for s in evs)
    T = all_ts[int(len(all_ts) * t_pct)]
    import datetime
    print(f"[skill] wallets={len(tapes)}  split T={datetime.datetime.utcfromtimestamp(T):%Y-%m-%d %H:%M}")

    pairs = []  # (pre_score, pre_pnl, post_pnl)
    for w, evs in tapes.items():
        pre = [s for s in evs if s.ts <= T]
        post = [s for s in evs if s.ts > T]
        sp = reconstruct_pnl(pre); so = reconstruct_pnl(post)
        if sp and so and sp.closed_trades >= 2 and so.closed_trades >= 2:
            pairs.append((sp.score, sp.realized_pnl_sol, so.realized_pnl_sol, w))

    print(f"[skill] wallets with >=2 closed trades both periods: {len(pairs)}")
    if len(pairs) < 6:
        print("[skill] N too small for a verdict — need the bigger leaderboard pool with cached tapes")
        for s, pre, post, w in sorted(pairs, reverse=True):
            print(f"  {w[:16]} pre_score={s:.2f} pre_pnl={pre:+.2f} post_pnl={post:+.2f}")
        return

    # Pearson correlation pre_score vs post_pnl
    xs = [p[0] for p in pairs]; ys = [p[2] for p in pairs]
    mx, my = statistics.mean(xs), statistics.mean(ys)
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sx = (sum((x - mx) ** 2 for x in xs)) ** 0.5
    sy = (sum((y - my) ** 2 for y in ys)) ** 0.5
    r = cov / (sx * sy) if sx and sy else 0.0

    # top-half vs bottom-half by pre-T score, compare post-T median PnL
    pairs.sort(key=lambda p: p[0], reverse=True)
    half = len(pairs) // 2
    top_post = [p[2] for p in pairs[:half]]
    bot_post = [p[2] for p in pairs[half:]]
    top_med = statistics.median(top_post); bot_med = statistics.median(bot_post)
    top_win = sum(1 for p in top_post if p > 0) / len(top_post)
    bot_win = sum(1 for p in bot_post if p > 0) / len(bot_post)

    print(f"\n=== SKILL PERSISTENCE ===")
    print(f"  corr(pre_score, post_pnl) = {r:+.3f}")
    print(f"  TOP-half pre-T wallets -> post-T median pnl={top_med:+.2f} SOL, win={top_win:.0%}")
    print(f"  BOT-half pre-T wallets -> post-T median pnl={bot_med:+.2f} SOL, win={bot_win:.0%}")
    verdict = ("SKILL PERSISTS — selection is real alpha" if (r > 0.15 and top_med > bot_med)
               else "WEAK/NONE — forward edge may be beta, not skill" if r < 0.05
               else "MIXED — modest persistence")
    print(f"  VERDICT: {verdict}")


if __name__ == "__main__":
    main()
