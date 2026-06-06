"""wa_eval — shared validation harness for the wallet-alpha hypotheses (PHASE 5).

Everything routes through the canonical gate in finetune/pipeline/eval_stats.py so a "PASS" here means
exactly what it means for C-002: realized capped EV > +2%, perm_p < 0.05, block-bootstrap CI95 > 0, n > 100.

Conventions:
  * Returns are CAPPED to [-1, +1] = the capturable-return convention (a microcap +100000% print is not
    realizable at size; you lose at most 100%). Uncapped median + hit are reported for honesty.
  * Temporal OOS: events time-ordered, split by form_ts (default first 60% train / last 40% test).
  * Baselines (mandatory): naive-copy (all clusters), token-only model, random/permutation.
"""
from __future__ import annotations

import json
import sys

import numpy as np

import wa_common as wa

sys.path.insert(0, str(wa.ROOT / "finetune" / "pipeline"))
import eval_stats as es  # noqa: E402  (canonical gate)

CAP_LO, CAP_HI = -1.0, 1.0


def cap(x: float) -> float:
    return max(CAP_LO, min(CAP_HI, x))


def load(side: str = "buy", H: int = 1800):
    d = json.loads((wa.CACHE / f"events_{side}.json").read_text(encoding="utf-8"))
    evs = [e for e in d["events"] if e.get(f"ret_{H}") is not None]
    evs.sort(key=lambda e: e["form_ts"])
    capped = np.array([cap(e[f"ret_{H}"]) for e in evs], dtype=float)
    raw = np.array([e[f"ret_{H}"] for e in evs], dtype=float)
    return d["meta"], evs, capped, raw


def matrix(evs, feats):
    X = np.array([[float(e.get(f, 0.0)) for f in feats] for e in evs], dtype=float)
    return np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)


def temporal_split(n, frac=0.6):
    cut = int(n * frac)
    return np.arange(cut), np.arange(cut, n)


def spearman(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    if len(a) < 3:
        return float("nan")
    ra = np.argsort(np.argsort(a)); rb = np.argsort(np.argsort(b))
    ra = ra - ra.mean(); rb = rb - rb.mean()
    d = np.sqrt((ra ** 2).sum() * (rb ** 2).sum())
    return float((ra * rb).sum() / d) if d > 0 else float("nan")


def wallet_overlap(evs, tr_idx, te_idx):
    tr = set().union(*[set(evs[i]["wallets"]) for i in tr_idx]) if len(tr_idx) else set()
    te = set().union(*[set(evs[i]["wallets"]) for i in te_idx]) if len(te_idx) else set()
    return (len(tr & te) / len(te)) if te else 0.0


def describe(nets_capped, raw):
    nets_capped = np.asarray(nets_capped); raw = np.asarray(raw)
    return {"n": len(nets_capped), "ev_capped": float(nets_capped.mean()),
            "median_raw": float(np.median(raw)), "hit": float((raw > 0).mean())}


def gate(all_nets, fired_mask, label=""):
    """Run the canonical eval_stats gate on a selection rule. all_nets/fired_mask are time-ordered."""
    all_nets = list(map(float, all_nets))
    fired_mask = list(map(bool, fired_mask))
    fired_time = [x for x, m in zip(all_nets, fired_mask) if m]
    r = es.evaluate_selection(all_nets, fired_mask, fired_nets_time_ordered=fired_time)
    r["label"] = label
    return r


def fmt_gate(r) -> str:
    if r.get("k", 0) == 0:
        return f"  {r.get('label',''):28s} no fires"
    g = r["gates"]
    flags = "".join("Y" if v else "." for v in g.values())
    return (f"  {r['label']:28s} n={r['k']:4d} EV={r['rule_ev']:+.3%} base={r['base_ev']:+.3%} "
            f"edge={r['edge_over_base']:+.3%} perm_p={r['perm_p']:.3f} "
            f"CI95=[{r['ci95'][0]:+.3%},{r['ci95'][1]:+.3%}] gates[{flags}] {r['verdict']}")


# ---- models (interpretable + gradient boosting), trained on train fold only ----
def gbm_scores(Xtr, ytr, Xte):
    from sklearn.ensemble import HistGradientBoostingRegressor
    m = HistGradientBoostingRegressor(max_depth=3, max_iter=200, learning_rate=0.05,
                                      min_samples_leaf=20, l2_regularization=1.0,
                                      random_state=2026)
    m.fit(Xtr, ytr)
    return m.predict(Xte), m


def linear_scores(Xtr, ytr, Xte):
    """Interpretable baseline: standardized ridge regression."""
    from sklearn.linear_model import Ridge
    mu, sd = Xtr.mean(0), Xtr.std(0) + 1e-9
    m = Ridge(alpha=1.0).fit((Xtr - mu) / sd, ytr)
    return m.predict((Xte - mu) / sd), (m, mu, sd)


def select_top(scores, frac=0.5):
    """fired = top `frac` of test events by score."""
    if len(scores) == 0:
        return np.zeros(0, bool)
    thr = np.quantile(scores, 1 - frac)
    return scores >= thr
