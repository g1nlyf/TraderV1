"""
Live paper-trader — the only CLEAN forward validation.

Offline backtests are exhausted: skill doesn't persist (corr ~0), consensus is
sparse in history, reconstructed prices are corrupt. The honest path is to measure
FORWARD on live data.

Logic (real-time consensus, NOT past-PnL selection):
  - Poll a watchlist of wallets every CYCLE seconds (Helius).
  - When >= K watchlist wallets BUY the same token within WINDOW -> open a paper
    position at the latest buy price (real-time cohort consensus = the signal).
  - Exit when >= half the entrants SELL (follow cohort out), or +TP / -SL, or timeout.
  - Log every closed paper-trade with REAL entry/exit prices from chain.

This bypasses the falsified "rank by past PnL" — consensus is event-driven. Skill
persistence is irrelevant; we react to live convergence.

State persisted to live_paper_state.json (restart-safe). Trades -> live_paper_trades.jsonl.
SECURITY: Helius keys via env only.

Run (daemon):
  python -m finetune.pipeline.live_paper --cycle 120 --k 2 --window-min 60
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore

ROOT = Path(__file__).resolve().parents[2]
LB = ROOT / "finetune" / "data" / "wallet_leaderboard.json"
STATE = ROOT / "finetune" / "data" / "live_paper_state.json"
TRADES = ROOT / "finetune" / "data" / "live_paper_trades.jsonl"

from finetune.pipeline.helius_client import get_signatures, parse, _extract_swap

# Asymmetric exit (data-driven: cut losers fast, ride the fat right tail):
SL = 0.15            # tight hard stop -15% (was -30%; left tail p25 was -32%)
TRAIL = 0.35         # trailing stop: exit if price falls 35% from peak...
TRAIL_ARM = 1.20     # ...once the position is up >= +20% (lock profit, ride winners)
TIMEOUT_H, COST = 12, 0.018


def watchlist(n: int) -> list[str]:
    lb = json.loads(LB.read_text(encoding="utf-8"))
    good = [w for w in lb if w["realized_pnl_sol"] > 0 and w["score"] >= 0.45]
    return [w["wallet"] for w in sorted(good, key=lambda w: w["score"], reverse=True)[:n]]


def _load_state() -> dict:
    if STATE.exists():
        try:
            return json.loads(STATE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"last_sig": {}, "open": {}, "recent_buys": []}


def _save_state(s: dict):
    STATE.write_text(json.dumps(s, ensure_ascii=False), encoding="utf-8")


def _log_trade(t: dict):
    with TRADES.open("a", encoding="utf-8") as f:
        f.write(json.dumps(t, ensure_ascii=False) + "\n")


def poll_wallet(wallet: str, last_sig: str | None) -> tuple[str | None, list]:
    """New swaps since last_sig. Returns (newest_sig, swaps). Single Helius round-trip."""
    sigs = get_signatures(wallet, limit=25)
    if not sigs:
        return last_sig, []
    newest = sigs[0]["signature"]
    new = []
    for s in sigs:
        if s["signature"] == last_sig:
            break
        new.append(s["signature"])
    if not new:
        return newest, []
    parsed = parse(new)
    swaps = [_extract_swap(t, wallet) for t in parsed]
    return newest, [s for s in swaps if s]


def cycle(wl: list[str], state: dict, k: int, window_sec: int):
    now = int(time.time())
    # 1. poll for new swaps (single round-trip per wallet)
    fresh_buys, fresh_sells = [], []
    for w in wl:
        try:
            newest, sw = poll_wallet(w, state["last_sig"].get(w))
        except Exception:
            continue
        state["last_sig"][w] = newest
        for s in sw:
            (fresh_buys if s.side == "buy" else fresh_sells).append(s)
        time.sleep(0.12)

    # 2. record recent buys, detect consensus clusters
    for s in fresh_buys:
        state["recent_buys"].append({"token": s.token_mint, "wallet": s.wallet,
                                     "ts": s.ts, "price": s.price_sol})
    state["recent_buys"] = [b for b in state["recent_buys"] if now - b["ts"] <= window_sec]
    by_token = defaultdict(list)
    for b in state["recent_buys"]:
        by_token[b["token"]].append(b)
    for token, buys in by_token.items():
        wallets = {b["wallet"] for b in buys}
        if len(wallets) >= k and token not in state["open"]:
            entry = buys[-1]["price"]
            state["open"][token] = {"entry": entry, "entry_ts": now,
                                    "wallets": sorted(wallets), "peak": entry}
            print(f"[live] OPEN {token[:14]} entry={entry:.2e} consensus={len(wallets)} wallets", flush=True)

    # 3. manage open positions — exit on cohort sells / TP / SL / timeout
    sells_by_token = defaultdict(set)
    for s in fresh_sells:
        sells_by_token[s.token_mint].add(s.wallet)
    for token in list(state["open"].keys()):
        pos = state["open"][token]
        # latest known price = any fresh buy/sell on token
        px = None
        for s in fresh_buys + fresh_sells:
            if s.token_mint == token:
                px = s.price_sol
        if px:
            pos["peak"] = max(pos["peak"], px)
        reason = None
        if token in sells_by_token and len(sells_by_token[token] & set(pos["wallets"])) >= max(1, len(pos["wallets"]) // 2):
            reason = "cohort_exit"
        elif px and px <= pos["entry"] * (1 - SL):
            reason = "stop_loss"          # tight -15%: cut losers fast
        elif px and px >= pos["entry"] * TRAIL_ARM and px <= pos["peak"] * (1 - TRAIL):
            reason = "trailing_exit"      # in profit (+20%) and reversed 35% from peak: lock gain
        elif now - pos["entry_ts"] >= TIMEOUT_H * 3600:
            reason = "timeout"
        if reason:
            exit_px = px or pos["entry"]
            pnl = exit_px / pos["entry"] - 1 - COST
            _log_trade({"token": token, "entry": pos["entry"], "exit": exit_px,
                        "pnl": round(pnl, 4), "reason": reason,
                        "n_wallets": len(pos["wallets"]), "wallets": pos["wallets"],
                        "opened": datetime.fromtimestamp(pos["entry_ts"], timezone.utc).isoformat(),
                        "closed": datetime.now(timezone.utc).isoformat()})
            print(f"[live] CLOSE {token[:14]} pnl={pnl:+.1%} ({reason})", flush=True)
            del state["open"][token]
    _save_state(state)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cycle", type=int, default=120)
    ap.add_argument("--k", type=int, default=2)
    ap.add_argument("--window-min", type=int, default=60)
    ap.add_argument("--watch", type=int, default=40)
    ap.add_argument("--max-cycles", type=int, default=0, help="0 = forever")
    a = ap.parse_args()
    wl = watchlist(a.watch)
    print(f"[live] watching {len(wl)} wallets, cycle={a.cycle}s, k={a.k}, window={a.window_min}min")
    state = _load_state()
    c = 0
    while True:
        try:
            cycle(wl, state, a.k, a.window_min * 60)
        except Exception as e:
            print(f"[live] cycle error: {str(e)[:100]}", flush=True)
        c += 1
        # report open positions count
        print(f"[live] cycle {c} done; open={len(state['open'])} "
              f"trades_logged={sum(1 for _ in TRADES.open(encoding='utf-8')) if TRADES.exists() else 0}", flush=True)
        if a.max_cycles and c >= a.max_cycles:
            break
        time.sleep(a.cycle)


if __name__ == "__main__":
    main()
