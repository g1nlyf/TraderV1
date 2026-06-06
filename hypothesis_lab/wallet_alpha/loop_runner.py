"""loop_runner — the continuous Alpha Factory loop.

Runs repeated tournament cycles, optionally polling GMGN for fresh data between cycles. Resume-safe (the
ledger persists across runs), schedulable (Task Scheduler / cron), needs NO chat memory — it reads code +
ledger. Each cycle: [optional GMGN collect] -> tournament.run_all (walk-forward TEST-ONLY gate, all
registered candidates + controls) -> append ledger -> regenerate report -> summarize -> sleep.

Run: py loop_runner.py                       (3 cycles, no sleep, no collect)
     py loop_runner.py --cycles 0 --interval 1800 --collect   (forever, 30-min cadence, GMGN poll each cycle)
     py loop_runner.py --cycles 1            (single cycle = one tournament pass)
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone

import wa_common as wa
import tournament as T

LEDGER = wa.CACHE / "tournament_ledger.jsonl"


def _arg(flag, default):
    return type(default)(sys.argv[sys.argv.index(flag) + 1]) if flag in sys.argv else default


def _ledger_summary():
    """Best gated candidate + any promotions across the most recent run in the ledger."""
    if not LEDGER.exists():
        return
    rows = [json.loads(l) for l in LEDGER.read_text(encoding="utf-8").splitlines() if l.strip()]
    if not rows:
        return
    last_ts = rows[-1]["ts"]
    run = [r for r in rows if r.get("ts") == last_ts and r.get("k")]
    promoted = [r for r in run if r.get("verdict") == "PASS"]
    real = [r for r in run if "random" not in r["label"] and r.get("edge_over_base") is not None]
    real.sort(key=lambda r: -r["edge_over_base"])
    print(f"  [ledger] run={last_ts} candidates={len(run)} promoted={len(promoted)}")
    for r in real[:4]:
        print(f"    {r['label']:30s} edge={r['edge_over_base']:+.2%} perm={r['perm_p']:.3f} "
              f"EV={r['rule_ev']:+.2%} {r['verdict']}")
    print(f"  [ledger] total historical rows={len(rows)}")
    return promoted


def main():
    cycles = _arg("--cycles", 3)            # 0 = infinite
    interval = _arg("--interval", 0)
    collect = "--collect" in sys.argv
    k = _arg("--folds", 3)
    i = 0
    while True:
        i += 1
        print(f"\n{'='*70}\n[loop_runner] CYCLE {i} @ {datetime.now(timezone.utc).isoformat()} "
              f"(collect={collect}, folds={k})\n{'='*70}")
        if collect:
            try:
                import gmgn_adapter
                gmgn_adapter.poll_once("smartmoney", 200)
            except Exception as e:
                print(f"  [collect] GMGN poll failed (non-fatal): {e}")
        try:
            T.run_all(k=k)
        except Exception as e:
            print(f"  [cycle] tournament error: {e}")
        promoted = _ledger_summary()
        if promoted:
            print(f"\n[loop_runner] STOP CONDITION MET: {len(promoted)} candidate(s) PROMOTED -> {[p['label'] for p in promoted]}")
            break
        if cycles and i >= cycles:
            print(f"\n[loop_runner] ran {i} cycle(s); ledger persisted. Re-run to continue (resume-safe).")
            break
        if interval:
            print(f"[loop_runner] sleeping {interval}s ...")
            time.sleep(interval)


if __name__ == "__main__":
    main()
