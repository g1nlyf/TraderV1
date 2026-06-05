"""
eval_stats — the ONE honest way to score a selection rule. Shared by the walk-forward
loop and the hypothesis lab so a number can never again mean two different things.

Why this exists (H-001, 2026-06-04): the mean-reversion "champion" was promoted on a
WIN-RATE-IMPLIED EV (assume every win = +20%, every loss = -12%). Realized payoffs tell
the opposite story — the rule's losers slam the -12% stop, so realized EV is NEGATIVE
even though win-rate is higher than base. Lesson, encoded here:

  * EV must be the REALIZED mean of per-event net payoffs, never a win-rate reconstruction.
  * A selection rule is only "validated" if realized EV clears the bar AND it beats a
    permutation null AND its block-bootstrap CI95 excludes zero (CONSTRAINTS.md gate).

All functions are pure stdlib and deterministic given `seed`.
"""
from __future__ import annotations

import random
from typing import Sequence


def realized_ev(nets: Sequence[float]) -> float:
    """Mean realized net payoff. The only EV that counts."""
    return sum(nets) / len(nets) if nets else 0.0


def win_rate(nets: Sequence[float]) -> float:
    return sum(1 for x in nets if x > 0) / len(nets) if nets else 0.0


def tail_decomp(nets: Sequence[float]) -> dict:
    """Conditional means — exposes a fat left tail that win-rate alone hides."""
    w = [x for x in nets if x > 0]
    loss = [x for x in nets if x <= 0]
    return {"avg_win": (sum(w) / len(w) if w else 0.0),
            "avg_loss": (sum(loss) / len(loss) if loss else 0.0),
            "win_rate": (len(w) / len(nets) if nets else 0.0)}


def block_bootstrap_ci(vals: Sequence[float], n_boot: int = 10_000,
                       block: int = 10, alpha: float = 0.05, seed: int = 2026):
    """Block-bootstrap CI for the mean (preserves local autocorrelation).
    `vals` should be ordered in time so blocks are contiguous in time."""
    vals = list(vals)
    n = len(vals)
    if n < 2:
        return (float("nan"), float("nan"))
    rng = random.Random(seed)
    nblocks = (n + block - 1) // block
    means = []
    for _ in range(n_boot):
        sample = []
        for _ in range(nblocks):
            start = rng.randint(0, n - 1)
            sample.extend(vals[start:start + block])
        sample = sample[:n]
        means.append(sum(sample) / len(sample))
    means.sort()
    lo = means[int((alpha / 2) * n_boot)]
    hi = means[int((1 - alpha / 2) * n_boot)]
    return (lo, hi)


def permutation_p(all_nets: Sequence[float], k: int, observed_mean: float,
                  n_perm: int = 20_000, seed: int = 2026) -> float:
    """One-sided permutation p: P(mean of a random size-k subset >= observed rule mean).
    Tests whether the rule SELECTS higher-payoff events than chance. k must be > 0."""
    if k <= 0 or k > len(all_nets):
        return 1.0
    rng = random.Random(seed)
    N = len(all_nets)
    idx = list(range(N))
    ge = 0
    for _ in range(n_perm):
        s = rng.sample(idx, k)
        if (sum(all_nets[j] for j in s) / k) >= observed_mean:
            ge += 1
    return (ge + 1) / (n_perm + 1)


def evaluate_selection(all_nets: Sequence[float], fired_mask: Sequence[bool],
                       fired_nets_time_ordered: Sequence[float] | None = None,
                       ev_gate: float = 0.02, n_perm: int = 20_000,
                       n_boot: int = 10_000) -> dict:
    """Full CONSTRAINTS.md verdict for a selection rule.

    all_nets               : realized net payoff of EVERY candidate event (the base set)
    fired_mask             : bool per candidate — did the rule fire?
    fired_nets_time_ordered: fired payoffs sorted by entry time (for block bootstrap).
                             If None, uses fired order from all_nets/fired_mask.
    Returns realized EV, base EV, edge, win rates, tail decomposition, perm_p, CI95, verdict.
    """
    fired = [x for x, m in zip(all_nets, fired_mask) if m]
    k, n = len(fired), len(all_nets)
    base_ev = realized_ev(all_nets)
    if k == 0:
        return {"n": n, "k": 0, "base_ev": base_ev, "verdict": "FAIL", "reason": "no fires"}
    rule_ev = realized_ev(fired)
    ci = block_bootstrap_ci(fired_nets_time_ordered if fired_nets_time_ordered is not None else fired,
                            n_boot=n_boot)
    perm_p = permutation_p(all_nets, k, rule_ev, n_perm=n_perm)
    gate_ev = rule_ev > ev_gate
    gate_perm = perm_p < 0.05
    gate_ci = ci[0] > 0
    return {
        "n": n, "k": k, "fires_pct": k / n,
        "rule_ev": rule_ev, "base_ev": base_ev, "edge_over_base": rule_ev - base_ev,
        "rule_tail": tail_decomp(fired), "base_tail": tail_decomp(all_nets),
        "perm_p": perm_p, "ci95": ci,
        "gates": {"ev>{:.0%}".format(ev_gate): gate_ev, "perm_p<0.05": gate_perm, "ci95>0": gate_ci},
        "verdict": "PASS" if (gate_ev and gate_perm and gate_ci) else "FAIL",
    }


if __name__ == "__main__":
    # self-test: a known-positive selector must PASS; a random selector must FAIL.
    rng = random.Random(1)
    base = [rng.gauss(0, 0.1) for _ in range(1000)]
    # planted edge: fire on events we secretly boosted by +5%
    boosted = list(base)
    fired_mask = [False] * 1000
    for i in range(150):
        boosted[i] += 0.05
        fired_mask[i] = True
    pos = evaluate_selection(boosted, fired_mask)
    rand_mask = [i < 150 for i in rng.sample(range(1000), 1000)]
    neg = evaluate_selection(base, [True if j < 150 else False for j in range(1000)])
    print("planted-edge verdict:", pos["verdict"], "EV", round(pos["rule_ev"], 4),
          "perm_p", round(pos["perm_p"], 4))
    print("null-selector verdict:", neg["verdict"], "EV", round(neg["rule_ev"], 4),
          "perm_p", round(neg["perm_p"], 4))
    assert pos["verdict"] == "PASS", "planted edge should PASS"
    print("eval_stats self-test OK")
