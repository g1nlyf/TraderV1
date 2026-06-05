"""
Wallet PnL reconstruction + scoring — from real on-chain tapes (Helius).

Turns a wallet's swap tape into a rankable profile: realized PnL (SOL), win rate,
payoff ratio, hold time, trade count. This is the foundation of the
forward-validated smart-money leaderboard (the real copy-trade alpha).

FIFO matching per token: each sell closes the oldest open buy lots. Realized PnL
in SOL. Open lots (still holding) are reported separately, not counted as wins.

Forward-validation: pass `since_ts` to score ONLY trades after a discovery cutoff
(kills survivorship — a wallet's pre-discovery luck cannot inflate its score).

SECURITY: keys via env only (helius_client reads them).
"""
from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, asdict

from finetune.pipeline.helius_client import SwapEvent, wallet_swaps


@dataclass
class WalletScore:
    wallet: str
    realized_pnl_sol: float
    closed_trades: int          # closed round-trips (token fully or partly sold)
    win_rate: float             # winning closed-tokens / closed-tokens
    payoff_ratio: float         # avg win / avg loss (SOL)
    avg_hold_sec: float
    n_tokens: int
    sol_volume: float
    still_holding: int
    score: float                # 0..1 composite (for ranking)


def reconstruct_pnl(swaps: list[SwapEvent], since_ts: int = 0) -> WalletScore | None:
    if not swaps:
        return None
    wallet = swaps[0].wallet
    swaps = sorted([s for s in swaps if s.ts >= since_ts], key=lambda s: s.ts)
    lots: dict[str, deque] = defaultdict(deque)   # token -> deque[(sol_cost, qty, ts)]
    per_token_pnl: dict[str, float] = defaultdict(float)
    hold_times: list[float] = []
    vol = 0.0
    closed = 0

    for s in swaps:
        vol += s.sol_amount
        if s.side == "buy":
            lots[s.token_mint].append([s.sol_amount, s.token_amount, s.ts])
        else:  # sell — match FIFO against open buy lots
            qty = s.token_amount
            proceeds_per = s.price_sol
            dq = lots[s.token_mint]
            matched_any = False
            while qty > 1e-12 and dq:
                lot = dq[0]
                cost_sol, lot_qty, lot_ts = lot
                take = min(qty, lot_qty)
                cost_per = (cost_sol / lot_qty) if lot_qty else 0
                per_token_pnl[s.token_mint] += take * (proceeds_per - cost_per)
                hold_times.append(max(0, s.ts - lot_ts))
                lot[1] -= take; lot[0] -= take * cost_per; qty -= take
                matched_any = True
                if lot[1] <= 1e-12:
                    dq.popleft()
            if matched_any:
                closed += 1

    closed_tokens = {t: p for t, p in per_token_pnl.items() if abs(p) > 1e-9}
    wins = [p for p in closed_tokens.values() if p > 0]
    losses = [-p for p in closed_tokens.values() if p < 0]
    realized = sum(per_token_pnl.values())
    win_rate = len(wins) / len(closed_tokens) if closed_tokens else 0.0
    avg_win = (sum(wins) / len(wins)) if wins else 0.0
    avg_loss = (sum(losses) / len(losses)) if losses else 0.0
    payoff = (avg_win / avg_loss) if avg_loss > 0 else (avg_win and 5.0 or 0.0)
    still = sum(1 for dq in lots.values() if any(l[1] > 1e-9 for l in dq))

    # composite score: profitable + good win/payoff + enough trades
    pnl_s = max(0.0, min(1.0, 0.5 + realized / 5.0))   # +5 SOL -> ~1.0
    wr_s = max(0.0, min(1.0, (win_rate - 0.3) / 0.4))
    payoff_s = min(1.0, payoff / 3.0)
    depth_s = min(1.0, len(closed_tokens) / 20.0)
    score = 0.35 * pnl_s + 0.25 * wr_s + 0.25 * payoff_s + 0.15 * depth_s

    return WalletScore(
        wallet=wallet, realized_pnl_sol=round(realized, 4), closed_trades=closed,
        win_rate=round(win_rate, 3), payoff_ratio=round(payoff, 2),
        avg_hold_sec=round(sum(hold_times) / len(hold_times), 1) if hold_times else 0.0,
        n_tokens=len(per_token_pnl), sol_volume=round(vol, 3), still_holding=still,
        score=round(score, 3),
    )


def score_wallet(wallet: str, pages: int = 3, since_ts: int = 0) -> WalletScore | None:
    swaps = wallet_swaps(wallet, pages=pages)
    return reconstruct_pnl(swaps, since_ts=since_ts)


if __name__ == "__main__":
    import sqlite3, sys, pathlib, json
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore
    DB = pathlib.Path(__file__).resolve().parents[2] / "WalletScarper" / "data" / "stage2_foundation.sqlite3"
    con = sqlite3.connect(str(DB))
    wallets = [r[0] for r in con.execute(
        "SELECT DISTINCT wallet FROM wallet_token_outcomes WHERE length(wallet)=44 "
        "AND wallet NOT LIKE '%fixture%' AND wallet NOT LIKE 'acceptance%' LIMIT 4").fetchall()]
    con.close()
    print(f"Scoring {len(wallets)} real wallets from chain (Helius)...\n")
    for w in wallets:
        try:
            sc = score_wallet(w, pages=2)
            if sc:
                print(f"{w[:20]}  pnl={sc.realized_pnl_sol:+.3f} SOL  win={sc.win_rate:.0%}  "
                      f"payoff={sc.payoff_ratio}  tokens={sc.n_tokens}  hold={sc.avg_hold_sec:.0f}s  "
                      f"vol={sc.sol_volume:.2f}  score={sc.score}")
            else:
                print(f"{w[:20]}  no swaps")
        except Exception as e:
            print(f"{w[:20]}  ERROR {str(e)[:80]}")
