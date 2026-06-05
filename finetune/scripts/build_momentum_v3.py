"""
Momentum dataset v3 — the real edge hunt. Volume/order-flow + mean-reversion.

Why: feature audit proved price-only features ~0 separation (Cohen's d <0.07).
The only weak signals were drawdown/volatility => MEAN-REVERSION, not momentum,
and memecoin direction lives in VOLUME, not price shape. So:

  - Reads token_ohlcv (full OHLCV+volume from harvest --full).
  - VOLUME features: vol_surge (vs 24h mean), vol_trend, volume@drawdown (capitulation).
  - ORDER-FLOW proxy: close-position-in-range (where price closed in the bar) = buy/sell pressure.
  - MEAN-REVERSION: drawdown_from_high, rise_from_low, oversold interactions.
  - ACCURATE triple-barrier using intrabar HIGH/LOW (not close-only).
  - TEMPORAL split + embargo (leak-free), same as v2.

Then feature_audit gates it: train only if max|Cohen's d| >= 0.30.

Output: train_mom3.jsonl, val_mom3.jsonl, holdout_mom3_eval.jsonl
"""
from __future__ import annotations

import json, random, sqlite3, statistics, sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore

ROOT = Path(__file__).resolve().parents[2]
DB = ROOT / "WalletScarper" / "data" / "stage2_foundation.sqlite3"
OUT = ROOT / "finetune" / "data" / "training"
SRC = "geckoterminal:hour1"

SYS_PROMPT = (
    "You are an entry-timing analyst for Solana memecoins. Given a token's recent "
    "volume and price-action features, decide whether NOW is a good entry (signal) "
    "or not (no_trade). Output JSON: decision_type, confidence, pre_action_reasoning."
)

UP, DN, VERT, COST = 0.20, 0.12, 6, 0.018
STEP, MINLEN, T_PCT = 3, 30, 0.72
random.seed(2026)


def _ts(s):
    try: return datetime.fromisoformat(str(s).replace("Z", "+00:00")).timestamp()
    except Exception: return None


def load():
    con = sqlite3.connect(str(DB)); con.row_factory = sqlite3.Row
    try:
        rows = con.execute(
            "SELECT token_mint, ts, open, high, low, close, volume FROM token_ohlcv "
            "WHERE source=? ORDER BY token_mint, ts", (SRC,)).fetchall()
    except sqlite3.OperationalError:
        print("[mom3] token_ohlcv not found — run harvest --full first."); return {}
    con.close()
    ser = {}
    for r in rows:
        ser.setdefault(r["token_mint"], []).append(
            (r["ts"], r["open"], r["high"], r["low"], r["close"], r["volume"]))
    return {k: v for k, v in ser.items() if len(v) >= MINLEN}


def feats(bars, i):
    o, h, l, c, v = (lambda b: (b[1], b[2], b[3], b[4], b[5]))(bars[i])
    closes = [b[4] for b in bars[:i + 1]]
    vols = [b[5] for b in bars[max(0, i - 24):i + 1]]
    def ret(k): return round(c / closes[-1 - k] - 1, 4) if len(closes) > k and closes[-1 - k] > 0 else None
    win = closes[-25:]
    hi, lo = max(win), min(win)
    vol_mean = (sum(vols) / len(vols)) if vols else 0
    vol6 = vols[-6:]; vol24 = vols
    def cpos(b):  # close position in bar: 1=closed at high (buy), 0=at low (sell)
        rng = b[2] - b[3]
        return (b[4] - b[3]) / rng if rng > 0 else 0.5
    dd = round(c / hi - 1, 4) if hi > 0 else 0.0
    vsurge = round(v / vol_mean, 3) if vol_mean > 0 else None
    return {
        "ret_6h": ret(6), "ret_24h": ret(24),
        "drawdown_from_high": dd,
        "rise_from_low": round(c / lo - 1, 4) if lo > 0 else None,
        "vol_surge": vsurge,
        "vol_trend_6_24": round((sum(vol6) / len(vol6)) / (sum(vol24) / len(vol24)), 3)
                          if vol6 and vol24 and sum(vol24) > 0 else None,
        "close_pos_in_range": round(cpos(bars[i]), 3),
        "buy_pressure_6": round(statistics.mean([cpos(b) for b in bars[max(0, i - 5):i + 1]]), 3),
        "range_pct": round((h - l) / c, 4) if c > 0 else None,
        # interaction: high volume during a drawdown = capitulation buy candidate
        "capitulation": round((vsurge or 0) * max(0.0, -dd), 3),
    }


def triple_barrier(bars, i):
    entry = bars[i][4]
    up, dn = entry * (1 + UP), entry * (1 - DN)
    fut = bars[i + 1:i + 1 + VERT]
    if not fut: return None
    for b in fut:
        # conservative: if a bar's low breaches stop, count stop first
        if b[3] <= dn: return "no_trade", -DN - COST, "n/a"
        if b[2] >= up: return "signal", UP - COST, "high"
    fr = fut[-1][4] / entry - 1 - COST
    return ("signal", fr, "low") if fr > 0 else ("no_trade", fr, "n/a")


def example(f, dec, tier):
    user = ("ENTRY-TIMING REVIEW\n\nVOLUME+PRICE FEATURES:\n" + json.dumps(f, ensure_ascii=False)
            + "\n\nDecide entry. Output JSON: decision_type, confidence, pre_action_reasoning.")
    reason = (f"vol_surge={f['vol_surge']}, dd_from_high={f['drawdown_from_high']}, "
              f"buy_pressure={f['buy_pressure_6']}, capitulation={f['capitulation']}. "
              + ("Volume confirms reversal off lows -> entry." if dec == "signal"
                 else "No volume confirmation / euphoria risk -> skip."))
    model = json.dumps({"decision_type": dec, "confidence": tier if dec == "signal" else None,
                        "pre_action_reasoning": reason}, ensure_ascii=False)
    return {"systemInstruction": {"parts": [{"text": SYS_PROMPT}]},
            "contents": [{"role": "user", "parts": [{"text": user}]},
                         {"role": "model", "parts": [{"text": model}]}]}


def main():
    ser = load()
    print(f"[mom3] tokens >= {MINLEN} candles (ohlcv): {len(ser)}")
    if len(ser) < 8:
        print("[mom3] too few — wait for full harvest."); return
    all_ts = sorted(b[0] for v in ser.values() for b in v)
    T = all_ts[int(len(all_ts) * T_PCT)]
    print(f"[mom3] temporal T={datetime.fromtimestamp(T, timezone.utc):%Y-%m-%d %H:%M}")

    train, hold = [], []
    for t, bars in ser.items():
        for i in range(24, len(bars) - VERT, STEP):
            lab = triple_barrier(bars, i)
            if not lab: continue
            dec, net, tier = lab
            ex = example(feats(bars, i), dec, tier)
            et, wend = bars[i][0], bars[min(i + VERT, len(bars) - 1)][0]
            if wend <= T: train.append((ex, dec, net))
            elif et > T: hold.append((ex, dec, net, et, t))

    print(f"[mom3] train={len(train)} hold={len(hold)} "
          f"train_labels={dict(Counter(d for _,d,_ in train))}")
    if not train or not hold:
        print("[mom3] empty split"); return
    sig = [r for r in train if r[1] == "signal"]; notr = [r for r in train if r[1] != "signal"]
    random.shuffle(notr); notr = notr[:max(20, int(len(sig) * 1.2))]
    pool = sig + notr; random.shuffle(pool)
    val_n = max(10, int(len(pool) * 0.12)); val, tr = pool[:val_n], pool[val_n:]

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "train_mom3.jsonl").write_text("\n".join(json.dumps(e, ensure_ascii=False) for e,_,_ in tr), "utf-8")
    (OUT / "val_mom3.jsonl").write_text("\n".join(json.dumps(e, ensure_ascii=False) for e,_,_ in val), "utf-8")
    # REALIZED net payoff, entry ts, and token id are RETAINED (H-001 fix 2026-06-04):
    # win-rate alone is a deceptive metric — downstream EV/perm/CI must use realized `net`.
    er = [{"context_text": e["contents"][0]["parts"][0]["text"], "recorded_decision": d,
           "recorded_confidence": None,
           "outcome_label": ("good" if n >= 0.08 else "marginal" if n >= 0 else "loss"),
           "token_outcome_is_winner": bool(n > 0),
           "net": round(n, 6), "entry_ts": et, "token_mint": tok}
          for e, d, n, et, tok in hold]
    (OUT / "holdout_mom3_eval.jsonl").write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in er), "utf-8")
    base = sum(1 for _, _, n, _, _ in hold if n > 0) / len(hold)
    print(f"[mom3] TRAIN={len(tr)} VAL={len(val)} HOLDOUT={len(hold)} base_win={base:.1%}")
    print("[mom3] -> run: python -m finetune.pipeline.feature_audit finetune/data/training/train_mom3.jsonl")


if __name__ == "__main__":
    main()
