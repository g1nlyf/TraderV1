"""
Copyability classifier (#3) — separate copyable wallets from un-copyable ones.

Core thesis: we CANNOT win the latency race vs Trojan/Photon. So we must only
follow wallets whose edge is NOT speed-based. A sniper that buys in block 0-2 and
dumps in seconds is un-copyable — copying it makes us exit liquidity. A swing
wallet holding minutes-hours is copyable even at our latency.

Archetype heuristic (v1; refine later with on-chain launch-timing):
  sniper   : very short hold + extreme payoff   -> UN-COPYABLE (speed/info edge)
  scalper  : short hold (<30m)                  -> copyable only with low latency
  swing    : hold >= 30m                        -> COPYABLE (latency-insensitive) ** our target **
  bot/micro: tiny volume / 1 token              -> ignore

Priority for OUR system (no latency edge): SWING > scalper >> sniper(avoid).

Output: tags each leaderboard wallet + writes the copyable target set.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore

ROOT = Path(__file__).resolve().parents[2]
LB = ROOT / "finetune" / "data" / "wallet_leaderboard.json"
OUT = ROOT / "finetune" / "data" / "copyable_wallets.json"


def classify(w: dict) -> dict:
    hold = w.get("avg_hold_sec", 0) or 0
    payoff = w.get("payoff_ratio", 0) or 0
    pnl = w.get("realized_pnl_sol", 0) or 0
    win = w.get("win_rate", 0) or 0
    tokens = w.get("n_tokens", 0) or 0
    vol = w.get("sol_volume", 0) or 0

    if tokens <= 2 or vol < 0.5:
        arch, copyable, why = "micro/bot", False, "too few tokens / tiny volume"
    elif hold < 120 and payoff > 15:
        arch, copyable, why = "sniper", False, "block-0 speed/info edge — un-copyable"
    elif hold < 1800:
        arch, copyable, why = "scalper", True, "short hold — copyable with low latency"
    else:
        arch, copyable, why = "swing", True, "multi-min/hour hold — latency-insensitive (BEST)"

    # quality gate for the target set
    quality = (pnl > 0 and win >= 0.5 and payoff >= 1.5 and tokens >= 5)
    target = copyable and quality and arch in ("swing", "scalper")
    # priority: swing first
    prio = (2 if arch == "swing" else 1 if arch == "scalper" else 0) * (1 if target else 0)
    return {**w, "archetype": arch, "copyable": copyable, "is_target": target,
            "priority": prio, "why": why}


def main():
    if not LB.exists():
        print("no leaderboard"); return
    lb = json.loads(LB.read_text(encoding="utf-8"))
    tagged = [classify(w) for w in lb]

    from collections import Counter
    print(f"[copyability] {len(tagged)} wallets")
    print("  archetypes:", dict(Counter(t["archetype"] for t in tagged)))
    targets = sorted([t for t in tagged if t["is_target"]],
                     key=lambda t: (t["priority"], t["score"]), reverse=True)
    print(f"  COPYABLE TARGETS (quality + copyable): {len(targets)}")
    print(f"  of which SWING (latency-insensitive, best): {sum(1 for t in targets if t['archetype']=='swing')}")

    OUT.write_text(json.dumps(targets, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n=== TOP COPYABLE TARGETS -> {OUT.name} ===")
    for t in targets[:12]:
        print(f"  {t['wallet'][:20]} [{t['archetype']:7s}] score={t['score']} "
              f"pnl={t['realized_pnl_sol']:+.1f} win={t['win_rate']:.0%} "
              f"payoff={t['payoff_ratio']} hold={t['avg_hold_sec']/60:.0f}m")

    # who we EXCLUDE (snipers) — important: these would make us exit liquidity
    snipers = [t for t in tagged if t["archetype"] == "sniper"]
    if snipers:
        print(f"\n  EXCLUDED snipers (un-copyable, would dump on us): {len(snipers)}")
        for s in snipers[:5]:
            print(f"    {s['wallet'][:18]} pnl={s['realized_pnl_sol']:+.1f} payoff={s['payoff_ratio']} hold={s['avg_hold_sec']:.0f}s")


if __name__ == "__main__":
    main()
