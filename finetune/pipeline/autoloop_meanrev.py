"""
Walk-forward autonomous engine for the mean-reversion edge (#70).

The edge (meanrev_strategy: +1.57% EV/trade) is validated on ONE harvest regime.
Robustness requires re-validating as NEW candles form (wall-clock days). This
orchestrator runs the full cycle and logs the result with drift detection, so the
system self-maintains the edge. Designed for daily cron:

  # Daily 06:00 UTC
  0 6 * * * cd /path/TraderV1 && python -m finetune.pipeline.autoloop_meanrev >> finetune/logs/meanrev.log 2>&1

Cycle:
  1. harvest --full      (pulls fresh OHLCV; new candles accrue over time)
  2. build_momentum_v3   (temporal split + triple-barrier)
  3. feature_audit       (GATE: abort if features become noise, max|d|<0.30)
  4. calibrate + validate meanrev rule on the fresh temporal holdout
  5. append result to meanrev_log.jsonl + flag regime drift vs last run

No Vertex slot, no endpoint throttling — pure data + deterministic rule.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore

ROOT = Path(__file__).resolve().parents[2]
PY = sys.executable
LOG = ROOT / "finetune" / "data" / "meanrev_log.jsonl"
DRIFT_EV_DROP = 0.010   # flag if rule EV/trade drops >1pp vs last run


def _run(args, timeout=900):
    print(f"[loop] $ {' '.join(str(a) for a in args)}", flush=True)
    r = subprocess.run([PY, *args], cwd=str(ROOT), capture_output=True, text=True, timeout=timeout)
    sys.stdout.write(r.stdout[-2000:])
    return r.returncode, r.stdout


def _last_log():
    if not LOG.exists():
        return None
    lines = [l for l in LOG.read_text(encoding="utf-8").splitlines() if l.strip()]
    return json.loads(lines[-1]) if lines else None


def validate():
    """Calibrate + backtest the rule on the fresh holdout. Returns metrics dict.

    H-001 fix (2026-06-04): rule_ev is now the REALIZED mean net payoff, gated by a
    permutation null + block-bootstrap CI95 (CONSTRAINTS.md). The old win-rate-implied
    EV (assume every win=+20%/loss=-12%) is retained ONLY as a labeled diagnostic — it
    inverted the sign of the truth and manufactured a false champion. A universe
    fingerprint is logged so cross-run drift is only flagged when the token set matches.
    """
    import hashlib
    sys.path.insert(0, str(ROOT))
    from finetune.pipeline.meanrev_strategy import decide, calibrate, ev_per_trade
    from finetune.pipeline.eval_stats import permutation_p, block_bootstrap_ci
    p = calibrate()
    ho = ROOT / "finetune" / "data" / "training" / "holdout_mom3_eval.jsonl"
    rows = [json.loads(l) for l in ho.read_text(encoding="utf-8").splitlines() if l.strip()]
    base_w = sum(1 for r in rows if r["token_outcome_is_winner"]) / len(rows)
    has_net = all("net" in r for r in rows)

    fired = wins = 0
    all_nets, fired_events = [], []
    for r in rows:
        c = r["context_text"]
        f = json.loads(c[c.find("{"):c.find("}") + 1])
        net = r.get("net")
        if net is not None:
            all_nets.append(net)
        if decide(f, p)["decision_type"] == "signal":
            fired += 1
            wins += 1 if r["token_outcome_is_winner"] else 0
            if net is not None:
                fired_events.append((r.get("entry_ts"), net))
    wr = wins / fired if fired else 0.0

    toks = sorted({r.get("token_mint") for r in rows if r.get("token_mint")})
    uni_fp = hashlib.sha1("|".join(toks).encode()).hexdigest()[:12] if toks else None

    out = {"holdout_n": len(rows), "base_win": round(base_w, 3), "rule_win": round(wr, 3),
           "fires": fired, "fires_pct": round(fired / len(rows), 3),
           "n_tokens": len(toks), "universe_fp": uni_fp,
           "rule_ev_wr_implied": round(ev_per_trade(wr), 4),
           "base_ev_wr_implied": round(ev_per_trade(base_w), 4),
           "params": {"dd_max": p.dd_max, "range_min": round(p.range_min, 4),
                      "buypress_min": round(p.buypress_min, 3)}}

    if has_net and fired_events:
        rule_ev = sum(n for _, n in fired_events) / len(fired_events)
        base_ev = sum(all_nets) / len(all_nets)
        perm_p = permutation_p(all_nets, len(fired_events), rule_ev)
        fired_time_ordered = [n for _, n in sorted(fired_events, key=lambda x: (x[0] is None, x[0]))]
        ci = block_bootstrap_ci(fired_time_ordered)
        out.update({"rule_ev": round(rule_ev, 5), "base_ev": round(base_ev, 5),
                    "rule_ev_realized": round(rule_ev, 5),
                    "edge_over_base": round(rule_ev - base_ev, 5),
                    "perm_p": round(perm_p, 4), "ci95": [round(ci[0], 5), round(ci[1], 5)],
                    "validated": bool(rule_ev > 0.02 and perm_p < 0.05 and ci[0] > 0)})
    else:
        # old holdout schema lacks realized payoff — DO NOT trust win-rate-implied EV as truth
        out.update({"rule_ev": round(ev_per_trade(wr), 4), "base_ev": round(ev_per_trade(base_w), 4),
                    "realized_unavailable": True, "validated": False})
    return out


def main():
    validate_only = "--validate-only" in sys.argv
    print(f"\n[loop] ===== mean-reversion walk-forward {datetime.now(timezone.utc):%Y-%m-%d %H:%M} ====="
          + ("  (validate-only: no harvest/build)" if validate_only else ""))

    rc = 0
    if not validate_only:
        # Harvest scope is env-configurable. The original 220 tokens x 8 pages (~1760 reqs)
        # exceeds GeckoTerminal's free rate limit within any sane timeout -> it TIMED OUT every
        # scheduled run (a co-cause of the walk-forward never accruing). Smaller default fits the
        # rate limit; scale up via env when a higher-throughput key is available.
        pages = os.environ.get("MEANREV_HARVEST_PAGES", "4")
        maxtok = os.environ.get("MEANREV_HARVEST_TOKENS", "80")
        rc, _ = _run(["-m", "finetune.pipeline.harvest_token_universe", "--run", "--full",
                      "--tf", "hour", "--pages", pages, "--max-tokens", maxtok], timeout=1500)
        if rc != 0:
            print("[loop] harvest failed/partial — proceeding with whatever data accrued")

        rc, _ = _run(["finetune/scripts/build_momentum_v3.py"])
        if rc != 0:
            print("[loop] build failed — abort"); sys.exit(1)

        # GATE: feature separability
        rc, out = _run(["-m", "finetune.pipeline.feature_audit",
                        "finetune/data/training/train_mom3.jsonl"])
        if rc == 3:
            print("[loop] FEATURE AUDIT = NOISE. Edge gone this regime. Logging + abort train.")

    metrics = validate()
    metrics["ts"] = datetime.now(timezone.utc).isoformat()
    metrics["audit_noise"] = (rc == 3)

    # Drift is only meaningful when comparing the SAME token universe (H-001 fix):
    # harvest growth changes n+tokens+params at once, so cross-universe deltas are noise.
    last = _last_log()
    drift = None
    if last and last.get("universe_fp") and last.get("universe_fp") == metrics.get("universe_fp"):
        d = metrics["rule_ev"] - last.get("rule_ev", 0)
        drift = round(d, 4)
        metrics["drift_vs_last"] = drift
        if d < -DRIFT_EV_DROP:
            metrics["alert"] = "EDGE DEGRADING"
    elif last:
        metrics["note"] = "universe changed vs last run — rule_ev not comparable (no drift alert)"

    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(metrics, ensure_ascii=False) + "\n")

    print(f"[loop] RESULT: rule_win={metrics['rule_win']:.1%} "
          f"rule_ev={metrics['rule_ev']:+.2%} base_ev={metrics['base_ev']:+.2%} "
          f"fires={metrics['fires_pct']:.0%}"
          + (f" perm_p={metrics['perm_p']:.3f}" if "perm_p" in metrics else "")
          + (f" ci95=[{metrics['ci95'][0]:+.2%},{metrics['ci95'][1]:+.2%}]" if "ci95" in metrics else "")
          + (f" VALIDATED" if metrics.get("validated") else " NOT-VALIDATED")
          + (f" drift={drift:+.2%}" if drift is not None else "")
          + (f"  ** {metrics['alert']} **" if metrics.get("alert") else ""))
    print("[loop] logged ->", LOG.relative_to(ROOT))


if __name__ == "__main__":
    main()
