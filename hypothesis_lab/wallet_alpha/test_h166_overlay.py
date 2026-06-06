"""Deterministic fixture tests for h166_risk_overlay (no network, no DB).

NOTE ON SOURCE PURITY: these are SYNTHETIC fixtures. Logic tests tag events source="organic" only to
exercise decision code paths — they are NOT organic proof of edge (the backtest over real raw_trades is).
One test uses source="fixture" to prove fixtures are flagged non_organic. Run: py test_h166_overlay.py
"""
from __future__ import annotations

import h166_risk_overlay as h


def ev(ts, wallet, side, sol=1.0, source="organic"):
    return {"ts": ts, "wallet": wallet, "side": side, "sol": sol, "source": source}


def quality(*wallets):
    return {w: 5.0 for w in wallets}    # positive realized PnL = quality (point-in-time)


T = 10_000  # as_of


def test_no_future_leakage():
    # 3 quality sellers AFTER as_of must be ignored (would otherwise trigger no_trade)
    events = [ev(T + 10, f"q{i}", "sell", 5) for i in range(3)] + [ev(T - 100, "b1", "buy", 1)]
    v = h.evaluate_entry("TOK", T, events, quality("q0", "q1", "q2"))
    assert v.decision == "pass", v.decision
    assert v.evidence["n_sellers"] == 0, v.evidence
    print("  no_future_leakage: OK (post-as_of events ignored)")


def test_fires_on_quality_sells():
    # 3 distinct quality sellers dumping in the recent sub-window, sell>buy -> no_trade (active)
    events = [ev(T - 100, "q0", "sell", 6), ev(T - 90, "q1", "sell", 6), ev(T - 80, "q2", "sell", 6),
              ev(T - 800, "b1", "buy", 1)]
    v = h.evaluate_entry("TOK", T, events, quality("q0", "q1", "q2"))
    assert v.decision == "no_trade", v.decision
    assert "active_quality_distribution" in v.reasons
    print(f"  fires_on_quality_sells: OK (no_trade, score={v.score})")


def test_not_on_random_sells():
    # 3 sellers but NONE are quality and sells don't dominate -> pass
    events = [ev(T - 100, "r0", "sell", 1), ev(T - 90, "r1", "sell", 1), ev(T - 80, "r2", "sell", 1),
              ev(T - 200, "b1", "buy", 10), ev(T - 210, "b2", "buy", 10)]
    v = h.evaluate_entry("TOK", T, events, quality())   # no quality wallets
    assert v.decision == "pass", (v.decision, v.reasons)
    print("  not_on_random_sells: OK (pass; no quality + buys dominate)")


def test_absorbed_distribution_watch():
    # quality distribution earlier in window but QUIET in recent sub-window -> watch (bounce candidate)
    events = [ev(T - 850, "q0", "sell", 6), ev(T - 840, "q1", "sell", 6), ev(T - 830, "q2", "sell", 6),
              ev(T - 820, "b1", "buy", 1)]
    v = h.evaluate_entry("TOK", T, events, quality("q0", "q1", "q2"))
    assert v.decision == "watch", (v.decision, v.reasons)
    assert "absorbed_distribution_bounce_candidate" in v.reasons
    print("  absorbed_distribution_watch: OK (watch, H-042 bounce structure)")


def test_position_exit_trigger():
    entry = T - 1200
    # during-hold recent quality distribution -> exit_candidate
    events = [ev(T - 100, "q0", "sell", 6), ev(T - 90, "q1", "sell", 6), ev(T - 80, "q2", "sell", 6)]
    v = h.evaluate_position("TOK", T, entry, events, quality("q0", "q1", "q2"))
    assert v.decision == "exit_candidate", (v.decision, v.reasons)
    # quiet position -> hold
    v2 = h.evaluate_position("TOK", T, entry, [ev(T - 100, "b1", "buy", 1)], quality("q0"))
    assert v2.decision == "hold", v2.decision
    print("  position_exit_trigger: OK (exit_candidate on cluster; hold when quiet)")


def test_degradation_no_quality():
    # active distribution but NO point-in-time quality supplied -> never hard-veto: no_trade downgraded to watch
    events = [ev(T - 100, "x0", "sell", 6), ev(T - 90, "x1", "sell", 6), ev(T - 80, "x2", "sell", 6),
              ev(T - 800, "b1", "buy", 1)]
    v = h.evaluate_entry("TOK", T, events, wallet_quality=None)
    assert v.confidence == "low" and v.decision == "watch", (v.confidence, v.decision)
    assert "downgraded_no_quality_data" in v.reasons
    print("  degradation_no_quality: OK (low-confidence never hard-vetoes)")


def test_source_purity():
    events = [ev(T - 100, "q0", "sell", 6, source="fixture"),
              ev(T - 90, "q1", "sell", 6), ev(T - 80, "q2", "sell", 6), ev(T - 800, "b1", "buy", 1)]
    v = h.evaluate_entry("TOK", T, events, quality("q0", "q1", "q2"))
    assert v.evidence["source_purity"] == "non_organic", v.evidence["source_purity"]
    assert "non_organic_source_present" in v.reasons
    print("  source_purity: OK (fixture source -> non_organic flag)")


def test_determinism():
    events = [ev(T - 100, "q0", "sell", 6), ev(T - 90, "q1", "sell", 6), ev(T - 80, "q2", "sell", 6)]
    a = h.evaluate_entry("TOK", T, events, quality("q0", "q1", "q2"))
    b = h.evaluate_entry("TOK", T, events, quality("q0", "q1", "q2"))
    assert a.decision == b.decision and a.score == b.score and a.to_evidence_ref() == b.to_evidence_ref()
    print("  determinism: OK (identical inputs -> identical verdict)")


if __name__ == "__main__":
    for fn in [test_no_future_leakage, test_fires_on_quality_sells, test_not_on_random_sells,
               test_absorbed_distribution_watch, test_position_exit_trigger, test_degradation_no_quality,
               test_source_purity, test_determinism]:
        fn()
    print("h166 overlay fixtures: ALL PASS")
