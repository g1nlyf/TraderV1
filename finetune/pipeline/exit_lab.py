"""
Exit Lab — test the biggest untested lever: EXIT > ENTRY (meta-conclusion).

The forward distribution is fat-tailed (median +2%, p75 +66%, winners +600%). So how
we EXIT likely matters more than which wallet we copy. This compares exit strategies
on the SAME entries:

  copy_exit    : exit when the entry wallet sells (what dumb copy bots do — baseline)
  target_50    : take profit at +50%
  trailing_30  : exit when price falls 30% from its running max after entry
  stop_25      : hard stop at -25% (else hold to last path point)
  hold_to_max  : ORACLE upper bound (perfect exit at the post-entry max)

Price path is reconstructed from ALL cached wallets' fills on the token (every
buy/sell = a real price-time sample) — no new API calls. With ~80 wallets, popular
tokens have a dense path.

Entries = vetted swing wallets' POST-T buys (forward-valid selection).
Reports median return per rule -> which exit wins.
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
CAP = 10.0  # cap returns at +1000% (filter scam-price artifacts)


def load():
    raw = json.loads(TAPES.read_text(encoding="utf-8"))
    return {w: [SwapEvent(**e) for e in evs] for w, evs in raw.items()}


def token_paths(tapes) -> dict[str, list[tuple]]:
    paths = defaultdict(list)
    for evs in tapes.values():
        for s in evs:
            if s.price_sol > 0:
                paths[s.token_mint].append((s.ts, s.price_sol))
    for t in paths:
        paths[t].sort()
    return paths


def sim_exits(entry_p: float, entry_ts: int, path: list[tuple], wallet_exit: float | None) -> dict:
    fut = [(ts, p) for ts, p in path if ts > entry_ts]
    if not fut or entry_p <= 0:
        return {}
    out = {}
    # copy_exit
    if wallet_exit and wallet_exit > 0:
        out["copy_exit"] = wallet_exit / entry_p - 1 - COST
    # target_50
    tgt = next((p for ts, p in fut if p >= entry_p * 1.5), None)
    out["target_50"] = (tgt / entry_p - 1 - COST) if tgt else (fut[-1][1] / entry_p - 1 - COST)
    # trailing_30
    mx = entry_p; exitp = fut[-1][1]
    for ts, p in fut:
        mx = max(mx, p)
        if p <= mx * 0.70:
            exitp = p; break
    out["trailing_30"] = exitp / entry_p - 1 - COST
    # stop_25
    sp = next((p for ts, p in fut if p <= entry_p * 0.75), None)
    out["stop_25"] = (sp / entry_p - 1 - COST) if sp else (fut[-1][1] / entry_p - 1 - COST)
    # hold_to_max (oracle)
    out["hold_to_max"] = max(p for ts, p in fut) / entry_p - 1 - COST
    return {k: max(-1.0, min(CAP, v)) for k, v in out.items()}


def main(t_pct: float = 0.6):
    tapes = load()
    copyable = {w["wallet"] for w in json.loads(COPYABLE.read_text(encoding="utf-8"))} \
        if COPYABLE.exists() else set(tapes)
    tapes_c = {w: e for w, e in tapes.items() if w in copyable} or tapes
    all_ts = sorted(s.ts for evs in tapes.values() for s in evs)
    T = all_ts[int(len(all_ts) * t_pct)]
    paths = token_paths(tapes)   # path from ALL wallets (dense)

    # vetted selection: profitable pre-T
    selected = []
    for w, evs in tapes_c.items():
        sc = reconstruct_pnl([s for s in evs if s.ts <= T])
        if sc and sc.realized_pnl_sol > 0 and sc.win_rate >= 0.5:
            selected.append(w)
    print(f"[exit] vetted wallets={len(selected)}  tokens_with_path={len(paths)}")

    rules = defaultdict(list)
    n = 0
    for w in selected:
        # first sell per token (the wallet's own exit)
        sells = {}
        for s in tapes[w]:
            if s.side == "sell" and s.token_mint not in sells:
                sells[s.token_mint] = s.ts, s.price_sol
        for s in tapes[w]:
            if s.side == "buy" and s.ts > T:
                wexit = None
                if s.token_mint in sells and sells[s.token_mint][0] > s.ts:
                    wexit = sells[s.token_mint][1]
                r = sim_exits(s.price_sol, s.ts, paths.get(s.token_mint, []), wexit)
                if r:
                    n += 1
                    for k, v in r.items():
                        rules[k].append(v)

    print(f"[exit] simulated entries: {n}\n")
    print(f"=== EXIT-RULE COMPARISON (median return per trade, vetted entries) ===")
    base = statistics.median(rules.get("copy_exit", [0])) if rules.get("copy_exit") else None
    for k in ["copy_exit", "target_50", "trailing_30", "stop_25", "hold_to_max"]:
        rs = rules.get(k, [])
        if not rs:
            continue
        med = statistics.median(rs); win = sum(1 for r in rs if r > 0) / len(rs)
        mean = statistics.mean(rs)
        tag = ""
        if base is not None and k != "copy_exit":
            tag = f"  vs copy: {med - base:+.1%}"
        print(f"  {k:12s}: n={len(rs):3d} win={win:.0%} median={med:+.2%} mean={mean:+.2%}{tag}")
    print("\n[exit] hold_to_max = oracle ceiling (unreachable). Gap copy_exit->hold_to_max = exit alpha available.")


if __name__ == "__main__":
    main()
