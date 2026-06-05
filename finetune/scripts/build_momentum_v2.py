"""
Momentum dataset v2 — TRUSTWORTHY eval. Integrates ideas #61/#67/#63.

Fixes the eval-integrity bottleneck (regime leakage in token-disjoint split):

  #61 TEMPORAL holdout: one global time T. Train = entries whose label window ends
      <= T. Holdout = entries starting after T. => test is the FUTURE of train.
      The only leak-free backtest (no lookahead, regime-honest).

  #67 PURGE/EMBARGO: drop entries whose label window straddles T (no train/test
      overlap through shared future candles).

  #63 TRIPLE-BARRIER labels: upper(+take-profit) / lower(-stop) / vertical(time).
      signal = upper touched before lower within the window. Proper financial-ML
      labeling; less noise than naive stop-or-horizon.

Survivorship: entries sampled uniformly along each token's history (incl. dead
periods). Audit reported ~30% of tokens died >=85% — downside is represented.

Price-only (close) features for now; volume/order-flow = next cycle (#65, re-harvest).

Output: train_mom2.jsonl, val_mom2.jsonl, holdout_mom2_eval.jsonl (future period)
"""
from __future__ import annotations

import json, random, sqlite3, statistics, sys
from collections import Counter
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore

ROOT = Path(__file__).resolve().parents[2]
DB = ROOT / "WalletScarper" / "data" / "stage2_foundation.sqlite3"
OUT = ROOT / "finetune" / "data" / "training"
SRC = "geckoterminal:hour"     # consistent granularity

SYS_PROMPT = (
    "You are an entry-timing analyst for Solana memecoins. Given a token's recent "
    "price-momentum features, decide whether NOW is a good entry (signal) or not "
    "(no_trade). Output JSON: decision_type, confidence, pre_action_reasoning."
)

# triple-barrier
UP = 0.20         # take-profit barrier
DN = 0.12         # stop barrier
VERT = 6          # vertical (candles, ~6h)
COST = 0.018
STEP = 3
MINLEN = 30
T_PCT = 0.72      # global temporal split percentile
EMBARGO = VERT    # candles
random.seed(2026)


def _ts(s):
    try: return datetime.fromisoformat(str(s).replace("Z", "+00:00")).timestamp()
    except Exception: return None


def load():
    con = sqlite3.connect(str(DB)); con.row_factory = sqlite3.Row
    rows = con.execute(
        f"SELECT token_mint, observed_at, price_usd FROM token_price_paths "
        f"WHERE source=? ORDER BY token_mint, observed_at", (SRC,)).fetchall()
    con.close()
    ser = {}
    for r in rows:
        t = _ts(r["observed_at"])
        if t: ser.setdefault(r["token_mint"], []).append((t, float(r["price_usd"])))
    return {k: v for k, v in ser.items() if len(v) >= MINLEN}


def feats(prices, i):
    p = prices[i]
    def ret(k): return round(p/prices[i-k]-1, 4) if i-k >= 0 and prices[i-k] > 0 else None
    win = prices[max(0, i-24):i+1]
    rets = [win[j]/win[j-1]-1 for j in range(1, len(win)) if win[j-1] > 0]
    hi, lo = max(win), min(win)
    return {"ret_1h": ret(1), "ret_6h": ret(6), "ret_24h": ret(24),
            "volatility_24h": round(statistics.pstdev(rets), 4) if len(rets) >= 2 else None,
            "drawdown_from_high": round(p/hi-1, 4) if hi > 0 else None,
            "rise_from_low": round(p/lo-1, 4) if lo > 0 else None,
            "above_ma24": bool(p > sum(win)/len(win)),
            "age_candles": i}


def triple_barrier(prices, i):
    entry = prices[i]
    up, dn = entry*(1+UP), entry*(1-DN)
    fut = prices[i+1:i+1+VERT]
    if not fut: return None
    for px in fut:
        if px >= up: return "signal", UP-COST, "high"
        if px <= dn: return "no_trade", -DN-COST, "n/a"
    fr = fut[-1]/entry-1-COST
    return ("signal", fr, "low") if fr > 0 else ("no_trade", fr, "n/a")


def example(f, dec, tier):
    user = ("ENTRY-TIMING REVIEW\n\nMOMENTUM FEATURES:\n" + json.dumps(f, ensure_ascii=False)
            + "\n\nDecide entry. Output JSON: decision_type, confidence, pre_action_reasoning.")
    reason = (f"ret_6h={f['ret_6h']}, dd_from_high={f['drawdown_from_high']}, vol={f['volatility_24h']}. "
              + ("Favorable momentum, upside barrier reachable -> entry."
                 if dec == "signal" else "Reversal/stop risk dominates -> skip."))
    model = json.dumps({"decision_type": dec, "confidence": tier if dec == "signal" else None,
                        "pre_action_reasoning": reason}, ensure_ascii=False)
    return {"systemInstruction": {"parts": [{"text": SYS_PROMPT}]},
            "contents": [{"role": "user", "parts": [{"text": user}]},
                         {"role": "model", "parts": [{"text": model}]}]}


def main():
    ser = load()
    print(f"[mom2] tokens >= {MINLEN} candles: {len(ser)}")
    if len(ser) < 8:
        print("[mom2] too few — wait for harvest."); return

    all_ts = sorted(t for v in ser.values() for t, _ in v)
    T = all_ts[int(len(all_ts)*T_PCT)]
    print(f"[mom2] temporal split T={datetime.utcfromtimestamp(T):%Y-%m-%d %H:%M} "
          f"({T_PCT:.0%}); embargo={EMBARGO} candles")

    train, holdout = [], []
    for t, series in ser.items():
        ts = [x[0] for x in series]; pr = [x[1] for x in series]
        for i in range(24, len(pr)-VERT, STEP):
            lab = triple_barrier(pr, i)
            if not lab: continue
            dec, net, tier = lab
            ex = example(feats(pr, i), dec, tier)
            entry_t = ts[i]; window_end_t = ts[min(i+VERT, len(ts)-1)]
            if window_end_t <= T:
                train.append((ex, dec, net))
            elif entry_t > T:   # embargo gap = straddling entries dropped
                holdout.append((ex, dec, net))

    print(f"[mom2] raw train={len(train)} holdout={len(holdout)}")
    print(f"[mom2] train labels: {dict(Counter(d for _,d,_ in train))}")
    print(f"[mom2] holdout labels: {dict(Counter(d for _,d,_ in holdout))}")
    if not train or not holdout:
        print("[mom2] empty split — adjust T_PCT."); return

    # balance train
    sig = [r for r in train if r[1] == "signal"]; notr = [r for r in train if r[1] != "signal"]
    random.shuffle(notr); notr = notr[:max(20, int(len(sig)*1.2))]
    pool = sig+notr; random.shuffle(pool)
    val_n = max(10, int(len(pool)*0.12)); val, tr = pool[:val_n], pool[val_n:]

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT/"train_mom2.jsonl").write_text("\n".join(json.dumps(e, ensure_ascii=False) for e,_,_ in tr), "utf-8")
    (OUT/"val_mom2.jsonl").write_text("\n".join(json.dumps(e, ensure_ascii=False) for e,_,_ in val), "utf-8")
    eval_rows = [{"context_text": e["contents"][0]["parts"][0]["text"], "recorded_decision": d,
                 "recorded_confidence": None,
                 "outcome_label": ("good" if n >= 0.08 else "marginal" if n >= 0 else "loss"),
                 "token_outcome_is_winner": bool(n > 0)} for e, d, n in holdout]
    (OUT/"holdout_mom2_eval.jsonl").write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in eval_rows), "utf-8")

    base = sum(1 for _,_,n in holdout if n > 0)/len(holdout)
    print(f"[mom2] TRAIN={len(tr)} VAL={len(val)} HOLDOUT={len(holdout)}")
    print(f"[mom2] train balanced: {dict(Counter(d for _,d,_ in tr))}")
    print(f"[mom2] holdout base win-rate (always-signal): {base:.1%}  <- model must beat this")


if __name__ == "__main__":
    main()
