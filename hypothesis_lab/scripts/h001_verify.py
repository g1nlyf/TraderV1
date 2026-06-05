"""
H-001 verification — is the mean-reversion "champion" a real edge or a measurement artifact?

Rebuilds the entry events DIRECTLY from token_ohlcv (the source build_momentum_v3 reads),
because the shipped holdout file (holdout_mom3_eval.jsonl) discarded two things we need:
  1. the continuous triple-barrier payoff (it kept only token_outcome_is_winner = net>0)
  2. the entry timestamp (so an honest within-OOS temporal split is impossible from the file)

We replicate build_momentum_v3's feature + triple-barrier + temporal-split logic EXACTLY,
then evaluate the LIVE meanrev rule (meanrev_strategy.decide with calibrate() thresholds)
under the CONSTRAINTS.md standard:
  - realized mean net payoff (not win-rate-implied)
  - permutation null: rule-fired mean vs 20,000 random same-size subsets
  - block-bootstrap CI95 on the rule's per-trade payoff
  - within-OOS temporal split (first half vs second half by entry time)

It also reproduces the pipeline's win-rate-implied EV so the gap (Defect 3) is explicit.

Run:  python hypothesis_lab/scripts/h001_verify.py
"""
from __future__ import annotations

import json
import sqlite3
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from finetune.pipeline.eval_stats import permutation_p, block_bootstrap_ci  # noqa: E402
DB = ROOT / "WalletScarper" / "data" / "stage2_foundation.sqlite3"
SRC = "geckoterminal:hour1"

# Constants copied verbatim from finetune/scripts/build_momentum_v3.py
UP, DN, VERT, COST = 0.20, 0.12, 6, 0.018
STEP, MINLEN, T_PCT = 3, 30, 0.72
# permutation/bootstrap stats live in finetune.pipeline.eval_stats (seeded, deterministic)


def _tsnum(s):
    """Best-effort numeric epoch for temporal sub-split (display + ordering)."""
    if isinstance(s, (int, float)):
        return float(s)
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00")).timestamp()
    except Exception:
        try:
            return float(s)
        except Exception:
            return None


def load():
    con = sqlite3.connect(str(DB)); con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT token_mint, ts, open, high, low, close, volume FROM token_ohlcv "
        "WHERE source=? ORDER BY token_mint, ts", (SRC,)).fetchall()
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
    win = closes[-25:]
    hi, lo = max(win), min(win)
    vol_mean = (sum(vols) / len(vols)) if vols else 0
    vol6 = vols[-6:]; vol24 = vols
    def cpos(b):
        rng = b[2] - b[3]
        return (b[4] - b[3]) / rng if rng > 0 else 0.5
    dd = round(c / hi - 1, 4) if hi > 0 else 0.0
    vsurge = round(v / vol_mean, 3) if vol_mean > 0 else None
    return {
        "drawdown_from_high": dd,
        "buy_pressure_6": round(statistics.mean([cpos(b) for b in bars[max(0, i - 5):i + 1]]), 3),
        "range_pct": round((h - l) / c, 4) if c > 0 else None,
    }


def triple_barrier(bars, i):
    entry = bars[i][4]
    up, dn = entry * (1 + UP), entry * (1 - DN)
    fut = bars[i + 1:i + 1 + VERT]
    if not fut:
        return None
    for b in fut:
        if b[3] <= dn:
            return "no_trade", -DN - COST, "n/a"
        if b[2] >= up:
            return "signal", UP - COST, "high"
    fr = fut[-1][4] / entry - 1 - COST
    return ("signal", fr, "low") if fr > 0 else ("no_trade", fr, "n/a")


def build_events():
    """Returns (train_events, holdout_events). Each event = dict(ts, tsnum, net, feats)."""
    ser = load()
    all_ts = sorted(b[0] for v in ser.values() for b in v)
    T = all_ts[int(len(all_ts) * T_PCT)]           # same split rule as build_momentum_v3
    train, hold = [], []
    for t, bars in ser.items():
        for i in range(24, len(bars) - VERT, STEP):
            lab = triple_barrier(bars, i)
            if not lab:
                continue
            dec, net, tier = lab
            et = bars[i][0]
            wend = bars[min(i + VERT, len(bars) - 1)][0]
            ev = {"ts": et, "tsnum": _tsnum(et), "net": net, "feats": feats(bars, i)}
            if wend <= T:
                train.append(ev)
            elif et > T:
                hold.append(ev)
    return train, hold, len(ser), T


def wr_implied_ev(win_rate):
    return win_rate * UP - (1 - win_rate) * DN - COST


def evaluate(hold, decide, params, label=""):
    all_nets = [e["net"] for e in hold]
    fired = [e for e in hold if decide(e["feats"], params)["decision_type"] == "signal"]
    fired_nets = [e["net"] for e in fired]
    n, k = len(hold), len(fired)
    base_ev = sum(all_nets) / n
    base_win = sum(1 for x in all_nets if x > 0) / n
    if k == 0:
        return {"label": label, "n": n, "k": 0}
    rule_ev = sum(fired_nets) / k
    rule_win = sum(1 for x in fired_nets if x > 0) / k

    def decomp(nets):
        w = [x for x in nets if x > 0]; loss = [x for x in nets if x <= 0]
        return (sum(w) / len(w) if w else 0.0, sum(loss) / len(loss) if loss else 0.0)
    rwm, rlm = decomp(fired_nets)
    bwm, blm = decomp(all_nets)
    # order fired by time for block bootstrap
    fired_sorted = [e["net"] for e in sorted(fired, key=lambda e: (e["tsnum"] is None, e["tsnum"]))]
    ci = block_bootstrap_ci(fired_sorted)
    perm_p = permutation_p(all_nets, k, rule_ev)
    return {
        "label": label, "n": n, "k": k, "fires_pct": k / n,
        "base_ev_realized": base_ev, "base_win": base_win,
        "rule_ev_realized": rule_ev, "rule_win": rule_win,
        "rule_ev_wr_implied": wr_implied_ev(rule_win),
        "base_ev_wr_implied": wr_implied_ev(base_win),
        "edge_over_base_realized": rule_ev - base_ev,
        "ci95": ci, "perm_p": perm_p,
        "rule_win_mean": rwm, "rule_loss_mean": rlm,
        "base_win_mean": bwm, "base_loss_mean": blm,
    }


def main():
    from finetune.pipeline.meanrev_strategy import decide, calibrate
    params = calibrate()
    print("=" * 78)
    print("H-001 VERIFICATION — realized EV / permutation / bootstrap on the LIVE rule")
    print("=" * 78)
    print(f"DB: {DB.relative_to(ROOT)}  source={SRC}")
    print(f"Calibrated params: dd<{params.dd_max}  range>{params.range_min:.4f}  "
          f"buypress>{params.buypress_min:.3f}")

    train, hold, ntok, T = build_events()
    Tnum = _tsnum(T)
    Tdisp = datetime.fromtimestamp(Tnum, timezone.utc).strftime("%Y-%m-%d %H:%M") if Tnum else str(T)
    print(f"Universe: {ntok} tokens (>= {MINLEN} candles).  "
          f"Temporal split T={Tdisp}  train_events={len(train)}  holdout_events={len(hold)}")

    res = evaluate(hold, decide, params, "FULL OOS HOLDOUT")
    print("\n--- " + res["label"] + " ---")
    print(f"  holdout n={res['n']}  rule fires k={res['k']} ({res['fires_pct']:.1%})")
    print(f"  REALIZED   base_ev={res['base_ev_realized']:+.4%}  rule_ev={res['rule_ev_realized']:+.4%}"
          f"   edge_over_base={res['edge_over_base_realized']:+.4%}")
    print(f"  WR-IMPLIED base_ev={res['base_ev_wr_implied']:+.4%}  rule_ev={res['rule_ev_wr_implied']:+.4%}"
          f"   <-- THIS is what the pipeline logs")
    print(f"  win rates  base={res['base_win']:.3f}  rule={res['rule_win']:.3f}  "
          f"(rule fires on HIGHER win-rate setups)")
    print(f"  LEFT-TAIL  base: avg win {res['base_win_mean']:+.3%} / avg loss {res['base_loss_mean']:+.3%}")
    print(f"             rule: avg win {res['rule_win_mean']:+.3%} / avg loss {res['rule_loss_mean']:+.3%}"
          f"  <-- rule's losers are fatter => realized EV worse despite higher win rate")
    print(f"  CI95 (block-bootstrap, realized) = [{res['ci95'][0]:+.4%}, {res['ci95'][1]:+.4%}]")
    print(f"  permutation-null perm_p = {res['perm_p']:.4f}  "
          f"({'PASS <0.05' if res['perm_p'] < 0.05 else 'FAIL >=0.05'})")

    # honest within-OOS temporal split
    htime = sorted([e for e in hold if e["tsnum"] is not None], key=lambda e: e["tsnum"])
    if len(htime) >= 20:
        mid = len(htime) // 2
        first, second = htime[:mid], htime[mid:]
        for name, sub in (("OOS FIRST HALF (earlier)", first), ("OOS SECOND HALF (later)", second)):
            r = evaluate(sub, decide, params, name)
            if r.get("k", 0) == 0:
                print(f"\n--- {name} --- (rule fired 0x)")
                continue
            t0 = datetime.fromtimestamp(sub[0]["tsnum"], timezone.utc).strftime("%m-%d %H:%M")
            t1 = datetime.fromtimestamp(sub[-1]["tsnum"], timezone.utc).strftime("%m-%d %H:%M")
            print(f"\n--- {name}  [{t0} .. {t1}] ---")
            print(f"  n={r['n']} k={r['k']}  REALIZED base_ev={r['base_ev_realized']:+.4%} "
                  f"rule_ev={r['rule_ev_realized']:+.4%} edge={r['edge_over_base_realized']:+.4%}  "
                  f"perm_p={r['perm_p']:.3f}")

    # verdict block
    print("\n" + "=" * 78)
    gate_perm = res["perm_p"] < 0.05
    gate_ci = res["ci95"][0] > 0
    gate_ev = res["rule_ev_realized"] > 0.02
    print("PROMOTION GATE (CONSTRAINTS.md): EV>+2% AND perm_p<0.05 AND CI95>0")
    print(f"  realized EV>+2% : {'YES' if gate_ev else 'NO'}  ({res['rule_ev_realized']:+.4%})")
    print(f"  perm_p<0.05     : {'YES' if gate_perm else 'NO'}  ({res['perm_p']:.4f})")
    print(f"  CI95 excl. zero : {'YES' if gate_ci else 'NO'}  [{res['ci95'][0]:+.4%}, {res['ci95'][1]:+.4%}]")
    verdict = "PASS" if (gate_perm and gate_ci and gate_ev) else "FAIL"
    print(f"  VERDICT: {verdict}")
    print("=" * 78)

    # machine-readable for the session log
    out = {"ts": datetime.now(timezone.utc).isoformat(), "tokens": ntok,
           "holdout_n": res["n"], "fires": res["k"],
           "rule_ev_realized": round(res["rule_ev_realized"], 5),
           "rule_ev_wr_implied": round(res["rule_ev_wr_implied"], 5),
           "base_ev_realized": round(res["base_ev_realized"], 5),
           "edge_over_base": round(res["edge_over_base_realized"], 5),
           "perm_p": round(res["perm_p"], 4),
           "ci95": [round(res["ci95"][0], 5), round(res["ci95"][1], 5)],
           "verdict": verdict}
    print("\nJSON " + json.dumps(out))


if __name__ == "__main__":
    main()
