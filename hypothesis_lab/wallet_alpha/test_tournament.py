"""Tests for the tournament harness + lifecycle sampling (Sprint 9). No network. Run: py test_tournament.py

Critical test: GATE TEST-ONLY ISOLATION — proves the Sprint-8 contamination bug is fixed (the gate base /
permutation universe must be the TEST fold only, never train+test).
"""
from __future__ import annotations

import numpy as np

import wa_common as wa
import token_lifecycle as tl
import tournament as T


def _mk_trades(n, t0=1000.0, dt=10.0, price0=1.0, drift=0.0, side="buy"):
    out = []
    for i in range(n):
        out.append(wa.Trade(ts=t0 + i * dt, wallet=f"w{i%7}", token="TOK", side=side,
                            sol=1.0, qty=1.0, price=price0 * (1.0 + drift) ** i))
    return out


def test_folds_walkforward_disjoint():
    fs = T.folds(100, k=3, min_train_frac=0.4)
    assert len(fs) == 3
    prev_hi = None
    for tr, te in fs:
        assert tr[0] == 0 and tr[-1] == te[0] - 1          # expanding window: train ends where test starts
        assert te[0] < te[-1] + 1
        if prev_hi is not None:
            assert te[0] == prev_hi                          # test folds are contiguous, disjoint
        prev_hi = te[-1] + 1
    assert fs[-1][1][-1] == 99                               # folds cover the tail
    print("  folds_walkforward_disjoint: OK")


def test_gate_test_only_isolation():
    # train region strongly NEGATIVE, test region strongly POSITIVE. A contaminated gate would report
    # base ~ -0.1 (full mean); the correct test-only gate must report base = +0.5 (test mean).
    rows = [{"net": -0.5, "t": i} for i in range(60)] + [{"net": +0.5, "t": 60 + i} for i in range(40)]
    ds = T.Dataset("synth", rows, {})
    fire_all = lambda ds, tr, te: np.ones(len(te), bool)
    r = T.run_candidate(ds, "fire_all", fire_all, k=1)       # folds(100,1,0.4): train[0:40) ... but k=1
    # with k=1, min_train_frac=0.4 -> start=40, test=[40,100): mean = (-0.5*20 + 0.5*40)/60 = +0.1667
    assert abs(r["base_ev"] - np.mean([x["net"] for x in rows[40:]])) < 1e-6, r["base_ev"]
    assert r["base_ev"] > 0, f"contaminated? base={r['base_ev']:+.3f} (full-sample would be -0.10)"
    print(f"  gate_test_only_isolation: OK (base={r['base_ev']:+.3f} = test-only mean, not full-sample)")


def test_gate_subset_selection():
    rows = [{"net": -0.5} for _ in range(50)] + [{"net": +1.0} for _ in range(20)] + [{"net": -1.0} for _ in range(20)]
    ds = T.Dataset("synth2", rows, {})
    # fire only the +1.0 block in the test region
    def fire_winners(ds, tr, te):
        return np.array([r["net"] > 0 for r in te], bool)
    r = T.run_candidate(ds, "winners", fire_winners, k=1)
    assert r["rule_ev"] > r["base_ev"], (r["rule_ev"], r["base_ev"])
    assert r["k"] >= 1
    print(f"  gate_subset_selection: OK (rule {r['rule_ev']:+.2f} > base {r['base_ev']:+.2f})")


def test_point_in_time_no_leak():
    trs = _mk_trades(20, drift=0.01)
    ts_list = [x.ts for x in trs]
    t = trs[-1].ts + 5.0
    f1 = tl.tok_features(trs, ts_list, t)
    # add a FUTURE trade after t that would change prior_ret/peak if leaked
    trs2 = trs + [wa.Trade(ts=t + 10, wallet="wX", token="TOK", side="buy", sol=99.0, qty=1.0, price=100.0)]
    ts2 = [x.ts for x in trs2]
    f2 = tl.tok_features(trs2, ts2, t)
    assert f1 is not None and f2 is not None
    assert abs(f1["prior_ret"] - f2["prior_ret"]) < 1e-9, "FUTURE trade leaked into features!"
    assert abs(f1["cum_sol"] - f2["cum_sol"]) < 1e-9
    print("  point_in_time_no_leak: OK (post-t trade ignored)")


def test_nonoverlap_sampling():
    # one long-lived token -> decision points must be spaced >= H
    trs = _mk_trades(400, t0=0.0, dt=20.0, drift=0.001)   # spans 8000s
    rows = tl.build_lifecycle_sample(trs)
    ts = sorted(r["t"] for r in rows)
    for a, b in zip(ts, ts[1:]):
        assert b - a >= tl.H - 1e-6, f"overlap: {b-a} < H={tl.H}"
    assert len(rows) <= tl.MAX_PTS
    print(f"  nonoverlap_sampling: OK ({len(rows)} pts, all spaced >= {tl.H}s)")


def test_classifier_determinism_and_cases():
    base = {"dd_from_peak": -0.05, "prior_ret": 0.0, "recent_ret": 0.0, "recent_imb": 0.0,
            "age_s": 2000, "accel": 0.5}
    assert tl.classify({**base, "dd_from_peak": -0.9}) == "rug_dead"
    assert tl.classify({**base, "dd_from_peak": -0.3, "recent_imb": -0.5}) == "distribution"
    assert tl.classify({**base, "dd_from_peak": -0.3, "recent_imb": 0.0}) == "decay"
    assert tl.classify({**base, "prior_ret": 1.0, "recent_ret": 0.0}) == "crowded_top"
    assert tl.classify({**base, "recent_ret": 0.5, "accel": 2.0}) == "acceleration"
    assert tl.classify({**base, "age_s": 200}) == "ignition"
    assert tl.classify(base) == "neutral"
    # determinism
    assert tl.classify({**base, "dd_from_peak": -0.9}) == tl.classify({**base, "dd_from_peak": -0.9})
    print("  classifier_determinism_and_cases: OK (7 states)")


def test_random_control_fires_frac():
    rows = [{"net": 0.0} for _ in range(1000)]
    ds = T.Dataset("s", rows, {})
    fn = T.random_topk(0.30)
    fired = fn(ds, [], rows)
    assert 0.25 < fired.mean() < 0.35, fired.mean()
    print(f"  random_control_fires_frac: OK ({fired.mean():.2f})")


if __name__ == "__main__":
    for fn in [test_folds_walkforward_disjoint, test_gate_test_only_isolation, test_gate_subset_selection,
               test_point_in_time_no_leak, test_nonoverlap_sampling, test_classifier_determinism_and_cases,
               test_random_control_fires_frac]:
        fn()
    print("tournament + lifecycle tests: ALL PASS")
