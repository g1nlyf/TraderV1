"""
Entry-timing (momentum) dataset from the harvested token universe.

Breaks the 6-token ceiling: hundreds of real tokens x ~15 sampled entries each =
thousands of diverse real records. Features are price-derived (trailing returns,
volatility, drawdown-from-high) — thin but real; many diverse tokens >> rich
features on 6 tokens.

TOKEN-DISJOINT split (the honest-eval fix): ~15% of TOKENS are held out entirely.
Holdout = true out-of-sample generalization to unseen tokens (the live question).

Survivorship guard: entries sampled UNIFORMLY along each token's full history,
including the dumps — not just current winners.

Label: realistic-exit over next 4h (stop -20% else horizon) net of costs.

Output: train_momentum.jsonl, val_momentum.jsonl, holdout_momentum.jsonl
        + holdout_eval.jsonl  (EvalExample format for backtest_harness --eval-file)
"""
from __future__ import annotations

import json
import random
import sqlite3
import statistics
import sys
from collections import Counter
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore

ROOT = Path(__file__).resolve().parents[2]
DB = ROOT / "WalletScarper" / "data" / "stage2_foundation.sqlite3"
OUT = ROOT / "finetune" / "data" / "training"
PROMPTS = ROOT / "finetune" / "prompts"
SYS_PROMPT = (
    "You are an entry-timing analyst for Solana memecoins. Given a token's recent "
    "price-momentum features, decide whether NOW is a good entry (signal) or not "
    "(no_trade). Output JSON: decision_type, confidence, pre_action_reasoning."
)

COST = 0.018          # fee + slippage round-trip
STOP = 0.20           # invalidation
HOLD = 4              # hourly candles (4h)
STEP = 4              # sample an entry every STEP candles
MIN_CANDLES = 34      # need 24 trailing + HOLD + buffer
HOLDOUT_FRAC = 0.15
VAL_FRAC = 0.12
random.seed(2026)


def tokens_with_paths() -> dict[str, list[tuple[str, float]]]:
    con = sqlite3.connect(str(DB)); con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT token_mint, observed_at, price_usd FROM token_price_paths "
        "WHERE source LIKE 'geckoterminal%' ORDER BY token_mint, observed_at ASC"
    ).fetchall()
    con.close()
    series: dict[str, list[tuple[str, float]]] = {}
    for r in rows:
        series.setdefault(r["token_mint"], []).append((r["observed_at"], float(r["price_usd"])))
    return series


def features(prices: list[float], i: int) -> dict:
    p = prices[i]
    def ret(k): return round((p / prices[i - k] - 1.0), 4) if i - k >= 0 and prices[i - k] > 0 else None
    win = prices[max(0, i - 24): i + 1]
    rets = [(win[j] / win[j - 1] - 1.0) for j in range(1, len(win)) if win[j - 1] > 0]
    vol = round(statistics.pstdev(rets), 4) if len(rets) >= 2 else None
    hi = max(win); lo = min(win)
    return {
        "ret_1h": ret(1), "ret_6h": ret(6), "ret_24h": ret(24),
        "volatility_24h": vol,
        "drawdown_from_high": round((p / hi - 1.0), 4) if hi > 0 else None,
        "rise_from_low": round((p / lo - 1.0), 4) if lo > 0 else None,
        "above_ma24": bool(p > (sum(win) / len(win))) if win else None,
    }


def label(prices: list[float], i: int) -> tuple[str, float, str]:
    entry = prices[i]
    future = prices[i + 1: i + 1 + HOLD]
    if not future or entry <= 0:
        return "no_trade", 0.0, "no_future"
    stop = entry * (1 - STOP)
    exit_px = None; reason = "horizon"
    for px in future:
        if px <= stop:
            exit_px = stop; reason = "stop"; break
    if exit_px is None:
        exit_px = future[-1]
    net = (exit_px / entry - 1.0) - COST
    if net > 0:
        tier = "high" if net >= 0.20 else "medium" if net >= 0.08 else "low"
        return "signal", net, tier
    return "no_trade", net, "n/a"


def make_example(feat: dict, decision: str, tier: str, net: float) -> dict:
    user = ("ENTRY-TIMING REVIEW\n\nMOMENTUM FEATURES:\n"
            + json.dumps(feat, ensure_ascii=False)
            + "\n\nDecide entry. Output JSON: decision_type, confidence, pre_action_reasoning.")
    reason = (f"Trailing ret_1h={feat['ret_1h']}, ret_6h={feat['ret_6h']}, "
              f"dd_from_high={feat['drawdown_from_high']}. "
              + ("Momentum favorable -> entry." if decision == "signal"
                 else "Momentum unfavorable / reversal risk -> skip."))
    model = json.dumps({"decision_type": decision,
                        "confidence": tier if decision == "signal" else None,
                        "pre_action_reasoning": reason}, ensure_ascii=False)
    return {"systemInstruction": {"parts": [{"text": SYS_PROMPT}]},
            "contents": [{"role": "user", "parts": [{"text": user}]},
                         {"role": "model", "parts": [{"text": model}]}]}


def main():
    series = tokens_with_paths()
    toks = [t for t, s in series.items() if len(s) >= MIN_CANDLES]
    print(f"[mom] tokens with >= {MIN_CANDLES} candles: {len(toks)} (of {len(series)})")
    if len(toks) < 5:
        print("[mom] too few tokens — wait for harvest to finish."); return

    random.shuffle(toks)
    n_hold = max(2, int(len(toks) * HOLDOUT_FRAC))
    holdout_toks = set(toks[:n_hold])
    train_toks = toks[n_hold:]
    print(f"[mom] token-disjoint: train_tokens={len(train_toks)} holdout_tokens={len(holdout_toks)}")

    def build(tok_list):
        recs = []
        for t in tok_list:
            prices = [p for _, p in series[t]]
            for i in range(24, len(prices) - HOLD, STEP):
                feat = features(prices, i)
                dec, net, tier = label(prices, i)
                recs.append((make_example(feat, dec, tier, net), dec, net))
        return recs

    train_recs = build(train_toks)
    hold_recs = build(holdout_toks)
    print(f"[mom] raw train recs={len(train_recs)} holdout recs={len(hold_recs)}")
    print(f"[mom] train decisions: {dict(Counter(d for _, d, _ in train_recs))}")

    # balance train: cap no_trade to 1.2x signal
    sig = [r for r in train_recs if r[1] == "signal"]
    notr = [r for r in train_recs if r[1] != "signal"]
    random.shuffle(notr)
    notr = notr[: max(20, int(len(sig) * 1.2))]
    pool = sig + notr
    random.shuffle(pool)
    val_n = max(10, int(len(pool) * VAL_FRAC))
    val = pool[:val_n]; train = pool[val_n:]

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "train_momentum.jsonl").write_text(
        "\n".join(json.dumps(e, ensure_ascii=False) for e, _, _ in train), encoding="utf-8")
    (OUT / "val_momentum.jsonl").write_text(
        "\n".join(json.dumps(e, ensure_ascii=False) for e, _, _ in val), encoding="utf-8")
    (OUT / "holdout_momentum.jsonl").write_text(
        "\n".join(json.dumps(e, ensure_ascii=False) for e, _, _ in hold_recs), encoding="utf-8")

    # EvalExample format for the harness (--eval-file)
    eval_rows = []
    for e, dec, net in hold_recs:
        eval_rows.append({
            "context_text": e["contents"][0]["parts"][0]["text"],
            "recorded_decision": dec,
            "recorded_confidence": None,
            "outcome_label": ("good" if net >= 0.08 else "marginal" if net >= 0 else "loss"),
            "token_outcome_is_winner": bool(net > 0),
        })
    (OUT / "holdout_eval.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in eval_rows), encoding="utf-8")

    print(f"[mom] TRAIN={len(train)} VAL={len(val)} HOLDOUT={len(hold_recs)}")
    print(f"[mom] train balanced: {dict(Counter(d for _, d, _ in train))}")
    print(f"[mom] holdout winners: {sum(1 for _,_,n in hold_recs if n>0)}/{len(hold_recs)}")


if __name__ == "__main__":
    main()
