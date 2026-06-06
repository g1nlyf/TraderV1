"""H-162 PERSISTENCE — does the distribution-sell down-signal hold across TIME, or is it one regime?

TRUE cross-day persistence needs many collection days (firehose_collector is now accruing them). Until
then, the only persistence evidence extractable from a single 5.5h session is INTRA-SESSION stability:
split the session into K equal time-blocks and walk forward — set the wq threshold on past blocks, apply to
the next block. If the wq-sell short edge keeps sign + significance block-to-block, it is at least not a
single-instant artifact. If it appears in only one block, it is fragile (regime-bound).

This is a PROXY, clearly labelled. It cannot rule out a session-wide regime (the whole May-14 window may be
one down-regime). That requires multi-day data — see FIREHOSE_RUNBOOK.md collection target.

Run: py hypothesis_lab/wallet_alpha/test_h162_persistence.py
"""
from __future__ import annotations

import json
import sys

import numpy as np

import wa_common as wa
import wa_eval as ev

sys.path.insert(0, str(wa.ROOT / "finetune" / "pipeline"))
import eval_stats as es  # noqa: E402

wa.ensure_utf8()


def short_payoff(raw_ret):
    return ev.cap(-(raw_ret + wa.COST_RT) - wa.COST_RT)


def run(H, K=5):
    print("=" * 100); print(f"H-162 INTRA-SESSION PERSISTENCE  |  H={H//60}m  |  {K} time-blocks"); print("=" * 100)
    evs = [e for e in json.loads((wa.CACHE / "events_sell.json").read_text())["events"] if e.get(f"ret_{H}") is not None]
    evs.sort(key=lambda e: e["form_ts"])
    t0, t1 = evs[0]["form_ts"], evs[-1]["form_ts"]
    short = np.array([short_payoff(e[f"ret_{H}"]) for e in evs])
    wq = np.array([float(e.get("wq_mean_pnl", 0)) for e in evs])
    edges = np.linspace(t0, t1, K + 1)
    blk = np.clip(np.digitize([e["form_ts"] for e in evs], edges[1:-1]), 0, K - 1)

    print(f"  sell events={len(evs)}  session {wa.fmt_hms(t0)}-{wa.fmt_hms(t1)}")
    print(f"\n  per-block: base short EV (all sells) vs wq-sell short EV (wq>block-median)")
    for b in range(K):
        m = blk == b
        if m.sum() < 10:
            print(f"   block{b}: n={int(m.sum())} (too few)"); continue
        sb, wb = short[m], wq[m]
        hi = wb > np.median(wb)
        base, wqe = sb.mean(), sb[hi].mean() if hi.sum() else float("nan")
        p = es.permutation_p(list(sb), int(hi.sum()), float(sb[hi].mean())) if hi.sum() else 1.0
        print(f"   block{b}: n={int(m.sum()):3d} base={base:+.2%} wq-sell={wqe:+.2%} "
              f"edge={wqe-base:+.2%} perm={p:.3f} {'sign+' if wqe>base else 'sign-'}")

    # walk-forward: threshold from past blocks -> apply to next block; aggregate OOS fired
    print(f"\n  WALK-FORWARD (wq threshold from blocks[:i] applied to block i):")
    oos_fired, oos_base = [], []
    for i in range(1, K):
        past = blk < i; cur = blk == i
        if past.sum() < 10 or cur.sum() < 10:
            continue
        thr = np.median(wq[past])
        fire = cur & (wq > thr)
        oos_fired += list(short[fire]); oos_base += list(short[cur])
    if oos_fired:
        evf, evb = np.mean(oos_fired), np.mean(oos_base)
        ci = es.block_bootstrap_ci(oos_fired)
        p = es.permutation_p(oos_base, len(oos_fired), float(evf))
        gates = {"perm<0.05": p < 0.05, "CI>0": ci[0] > 0, "n>100": len(oos_fired) > 100}
        flags = "".join("Y" if v else "." for v in gates.values())
        print(f"   OOS wq-sell SHORT: n={len(oos_fired)} EV={evf:+.2%} base={evb:+.2%} edge={evf-evb:+.2%} "
              f"perm={p:.3f} CI=[{ci[0]:+.2%},{ci[1]:+.2%}] [{flags}]")
        stable = (evf > evb) and p < 0.05
        print(f"   INTRA-SESSION VERDICT: {'edge persists across blocks (still NOT cross-day proven)' if stable else 'edge fragile across blocks'}")
        return {"H": H, "evf": evf, "evb": evb, "perm": p, "ci": ci, "n": len(oos_fired), "stable": stable}
    print("   insufficient blocks"); return None


def main():
    out = [run(1800), run(3600)]
    print("\n" + "=" * 100)
    print("PERSISTENCE NOTE: intra-session only. CROSS-DAY persistence is UNTESTABLE on a single 5.5h")
    print("session and remains the open question. firehose_collector is accruing days; target >=14 days")
    print("(>=30 ideal) before H-163 can separate cross-sectional skill from regime. See FIREHOSE_RUNBOOK.md.")
    return out


if __name__ == "__main__":
    main()
