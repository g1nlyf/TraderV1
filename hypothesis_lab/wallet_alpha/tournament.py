"""Alpha Factory — reusable hypothesis TOURNAMENT harness (Sprint 9).

Fixes the Sprint-8 validation bug (gate was given full-sample all_nets while firing test-only selections ->
contaminated base/permutation). Here the gate ALWAYS runs on the TEST-ONLY universe, pooled across
expanding-window walk-forward folds. Reusable: register candidates, run, get a leaderboard + persistent
ledger. Every candidate competes against base, token-only, and random controls on the SAME folds.

Gate semantics (canonical, via eval_stats):
  * walk-forward: expanding window. fold i trains on rows[0:start_i), tests on rows[start_i:end_i).
  * a candidate fn(ds, train_rows, test_rows) -> bool[len(test_rows)] (OOS: fit on train, fire on test).
  * pool the per-fold TEST nets + fired masks -> ev.gate(pooled_test_nets, pooled_fired) => base = mean of
    pooled TEST nets, perm draws k from pooled TEST only, bootstrap CI on fired TEST nets. NO train leakage.
  * promotion verdict = eval_stats gate (EV>+2%, perm<0.05, CI95>0, n>100).

Run: py hypothesis_lab/wallet_alpha/tournament.py            (runs all registered datasets+candidates)
     py hypothesis_lab/wallet_alpha/tournament.py --quick     (1 fold, fast smoke)
"""
from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable

import numpy as np

import wa_common as wa
import wa_eval as ev
import token_lifecycle as tl

wa.ensure_utf8()
RNG = np.random.default_rng(2026)
LEDGER = wa.CACHE / "tournament_ledger.jsonl"
REPORT = wa.ROOT / "hypothesis_lab" / "wallet_alpha" / "TOURNAMENT_REPORT.md"


@dataclass
class Dataset:
    name: str
    rows: list                       # time-ordered list of dict; each has 'net' (capped) + features
    feat_sets: dict                  # name -> [feature keys]
    source: str = "organic"          # provenance label; non_organic excluded from real claims


# ---------- walk-forward ----------
def folds(n: int, k: int = 3, min_train_frac: float = 0.4):
    start = int(n * min_train_frac)
    fs = max((n - start) // k, 1)
    out = []
    for i in range(k):
        lo = start + i * fs
        hi = n if i == k - 1 else start + (i + 1) * fs
        if lo >= n:
            break
        out.append((np.arange(0, lo), np.arange(lo, hi)))
    return out


def run_candidate(ds: Dataset, name: str, fn: Callable, k: int) -> dict:
    """Run a candidate through walk-forward; gate on POOLED TEST-ONLY universe."""
    pooled_nets, pooled_fired = [], []
    n = len(ds.rows)
    for tr_idx, te_idx in folds(n, k):
        tr = [ds.rows[i] for i in tr_idx]; te = [ds.rows[i] for i in te_idx]
        try:
            fired = np.asarray(fn(ds, tr, te), dtype=bool)
        except Exception as e:                       # candidate failure is a FAIL, not a crash
            return {"label": name, "error": str(e)[:120], "k": 0}
        if len(fired) != len(te):
            return {"label": name, "error": f"mask len {len(fired)}!={len(te)}", "k": 0}
        pooled_nets.extend(float(r["net"]) for r in te)
        pooled_fired.extend(fired.tolist())
    g = ev.gate(pooled_nets, pooled_fired, name)
    g["fired_frac"] = (sum(pooled_fired) / len(pooled_fired)) if pooled_fired else 0.0
    g["pooled_test_n"] = len(pooled_nets)
    return g


# ---------- candidate library (each: fn(ds, tr, te) -> bool[len(te)]) ----------
def make_gbm_topk(featset: str, frac=0.30):
    def fn(ds, tr, te):
        feats = ds.feat_sets[featset]
        Xtr = ev.matrix(tr, feats); ytr = np.array([r["net"] for r in tr])
        Xte = ev.matrix(te, feats)
        s, _ = ev.gbm_scores(Xtr, ytr, Xte)
        return ev.select_top(s, frac)
    return fn

def state_in(states: set):
    def fn(ds, tr, te):
        return np.array([r.get("state") in states for r in te], bool)
    return fn

def state_not_in(states: set):                       # no-trade filter (fire = KEEP)
    def fn(ds, tr, te):
        return np.array([r.get("state") not in states for r in te], bool)
    return fn

def random_topk(frac=0.30):
    def fn(ds, tr, te):
        return RNG.random(len(te)) < frac
    return fn

def feat_topk(feat: str, frac=0.30, sign=1.0):       # univariate baseline: top by a single raw feature
    def fn(ds, tr, te):
        v = np.array([sign * float(r.get(feat, 0.0)) for r in te])
        return ev.select_top(v, frac)
    return fn

def make_rug_skip(featset="token", frac_skip=0.30, rug_thr=-0.5):
    """H-184 rug pre-detection no-trade filter: GBM predicts P(net<rug_thr) from PRE-entry feats; KEEP the
    (1-frac_skip) lowest rug-risk (fire = trade). Rugs gap to ~0 (exit can't fix) -> avoid before entry."""
    def fn(ds, tr, te):
        feats = ds.feat_sets[featset]
        Xtr = ev.matrix(tr, feats); ytr = np.array([1.0 if r["net"] < rug_thr else 0.0 for r in tr])
        Xte = ev.matrix(te, feats)
        s, _ = ev.gbm_scores(Xtr, ytr, Xte)          # higher = more rug-risk
        thr = np.quantile(s, 1 - frac_skip)
        return s < thr                                # KEEP lower-risk
    return fn


# ---------- dataset builders ----------
def lifecycle_dataset():
    trades = wa.load_raw_trades(session_only=True, min_sol=0.05)
    rows = tl.build_lifecycle_sample(trades)
    return Dataset("lifecycle", rows, {
        "token": tl.TOK_FEATS,
        "token+state": tl.TOK_FEATS + [f"_st_{s}" for s in tl.STATES],
    })

def _augment_state_onehot(rows):
    for r in rows:
        for s in tl.STATES:
            r[f"_st_{s}"] = 1.0 if r.get("state") == s else 0.0

def cluster_dataset(H=1800):
    _, evs, capped, _ = ev.load("buy", H)
    for e, c in zip(evs, capped):
        e["net"] = float(c)
    tok = ["tok_age_s", "tok_prior_trades", "tok_prior_buyers", "tok_prior_sellers", "tok_buy_sell_imb",
           "tok_cum_sol", "tok_prior_ret", "tok_buyer_hhi"]
    wal = ["clu_n_wallets", "clu_cohesion", "clu_sol_total", "clu_mean_buy_sol", "clu_size_disp",
           "wq_mean_pnl", "wq_max_pnl", "wq_frac_profitable", "wq_mean_winrate", "wq_frac_known"]
    return Dataset("cluster_events", evs, {
        "token": tok, "wallet": wal, "token+wallet": tok + wal,
        "token+wq": tok + ["wq_mean_pnl", "wq_max_pnl", "wq_frac_profitable", "wq_mean_winrate"],
        "token+cohesion": tok + ["clu_cohesion", "clu_n_wallets", "clu_sol_total"],
    })


# ---------- registries ----------
def lifecycle_candidates():
    return {
        "random_top30": random_topk(0.30),
        "feat_prior_ret_top30": feat_topk("prior_ret", 0.30, sign=1.0),
        "token_gbm_top30": make_gbm_topk("token", 0.30),
        "token+state_gbm_top30": make_gbm_topk("token+state", 0.30),
        "neutral_only": state_in({"neutral"}),
        "avoid_rug_distrib_decay": state_not_in({"rug_dead", "distribution", "decay"}),
        "H184_rug_skip_token": make_rug_skip("token", 0.30),     # H-184 rug pre-detection no-trade filter
    }

def cluster_candidates():
    return {
        "random_top30": random_topk(0.30),
        "token_gbm_top30": make_gbm_topk("token", 0.30),
        "wallet_only_gbm_top30": make_gbm_topk("wallet", 0.30),
        "token+wallet_gbm_top30": make_gbm_topk("token+wallet", 0.30),
        "clu_cohesion_top30": feat_topk("clu_cohesion", 0.30),
        "H171b_token+wq_gbm": make_gbm_topk("token+wq", 0.30),          # ablation: does wq carry the increment?
        "H171b_token+cohesion_gbm": make_gbm_topk("token+cohesion", 0.30),  # ablation: does cohesion carry it?
    }


def run_all(k=3):
    t0 = time.time()
    results = []
    # lifecycle
    ds_l = lifecycle_dataset(); _augment_state_onehot(ds_l.rows)
    print(f"[tournament] lifecycle n={len(ds_l.rows)}  walk-forward folds={k}")
    for name, fn in lifecycle_candidates().items():
        r = run_candidate(ds_l, name, fn, k); r["dataset"] = "lifecycle"; results.append(r)
        print("  " + ev.fmt_gate(r).strip() if r.get("k") else f"  {name}: ERR {r.get('error')}")
    # cluster
    ds_c = cluster_dataset()
    print(f"\n[tournament] cluster_events n={len(ds_c.rows)}  walk-forward folds={k}")
    for name, fn in cluster_candidates().items():
        r = run_candidate(ds_c, name, fn, k); r["dataset"] = "cluster_events"; results.append(r)
        print("  " + ev.fmt_gate(r).strip() if r.get("k") else f"  {name}: ERR {r.get('error')}")
    _write_outputs(results, time.time() - t0)
    return results


def _write_outputs(results, secs):
    ts = datetime.now(timezone.utc).isoformat()
    with LEDGER.open("a", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps({"ts": ts, **{k: v for k, v in r.items() if k != "gates"}}, default=str) + "\n")
    # leaderboard markdown
    lines = [f"# Tournament Report — {ts}", "",
             f"Walk-forward, TEST-ONLY gate (Sprint-9 corrected). Runtime {secs:.0f}s. "
             f"Promotion = EV>+2% AND perm<0.05 AND CI95>0 AND n>100.", "",
             "| dataset | candidate | test n | fired% | EV | base | edge | perm | CI95 | verdict |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for r in sorted(results, key=lambda x: (x.get("dataset", ""), -(x.get("edge_over_base") or -9))):
        if not r.get("k"):
            lines.append(f"| {r.get('dataset','')} | {r['label']} | ERR | | | | | | | {r.get('error','')} |"); continue
        ci = r["ci95"]
        lines.append(f"| {r['dataset']} | {r['label']} | {r['k']} | {r['fired_frac']*100:.0f}% | "
                     f"{r['rule_ev']:+.2%} | {r['base_ev']:+.2%} | {r['edge_over_base']:+.2%} | "
                     f"{r['perm_p']:.3f} | [{ci[0]:+.2%},{ci[1]:+.2%}] | {r['verdict']} |")
    promoted = [r for r in results if r.get("verdict") == "PASS"]
    lines += ["", f"**Promoted this run: {len(promoted)}** "
              + (", ".join(r['label'] for r in promoted) if promoted else "(none — all fail the gate)"), "",
              "Interpretation: every selection on May-14 sits on a negative base (down-regime). A candidate "
              "that beats base+token-only+random but stays EV<0 is a SHADOW de-risk/ranking signal, not alpha. "
              "Promotion to alpha needs a non-dump regime (cross-day data, H-163). See HYPOTHESIS_QUEUE.md."]
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n[tournament] wrote {REPORT.name} + ledger ({len(results)} rows). promoted={len(promoted)}")


if __name__ == "__main__":
    run_all(k=1 if "--quick" in sys.argv else 3)
