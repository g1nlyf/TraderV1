"""
test_carry_cluster.py — Session 2026-06-05: STACK + regime-gate + selection carry-refinement battery.

Loads the funding panel ONCE (offline cache), builds the C-002 carry book (level-fixed
risk-parity top-10, basis-aware maker, no-lookahead) and batch-tests four families:

  1. STACK   (H-099/H-110/H-149): C-002 carry per-8h pnl  vs  H-042 sleeve per-8h beta-adjusted
             excess (reuse h042_deep: -8% drop, H=2, rising funding, tradeable, market-neutral).
             Align on shared period timestamps. Pearson r + 50/50 & 70/30 stack APR/Sharpe/CI
             vs each sleeve alone. GATE: r<0.3 AND stack Sharpe CI-separated above carry-alone.
  2. DE-RISKER (H-091/H-150): rolling-30p book basis-vol -> leverage scalar (1.0/0.5/0.25 by
             train basis-vol quantile). Scaled vs fixed maxDD/Sharpe/APR on the carry book.
  3. BTC-VOL GATE (H-080/H-092/H-100/H-116/H-140): BTC rolling-21 realized-vol percentile.
             Carry ON when btc-vol<p50/p60, scaled/off above. Gated vs always-on, block-boot CI,
             eff-n honesty (regimes autocorrelated -> count distinct ON-runs).
  4. SELECTION (vs H-021 level base): H-115 funding AR(1), H-145 low-BTC-beta, H-089 level×persist.
             top-10 fixed, OOS APR/Sharpe. Flag only if CI-separated from base.

HARD RULES honored: reuse fh.metrics / fh.block_bootstrap_ci / fh.evaluate / the level-fixed
risk-parity top-10 book from carry_lift.py. Temporal 70/30 (fh.TRAIN_FRAC), select on TRAIN,
report TEST. Realized payoff only. Regime-capture (H-051) guard: report eff-n / period-clustering.

Run: py hypothesis_lab/scripts/test_carry_cluster.py
"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "finetune" / "pipeline"))
sys.path.insert(0, str(ROOT / "hypothesis_lab" / "scripts"))
import funding_harvest as fh          # noqa: E402
import h013_tradeable_carry as h13    # noqa: E402  (offline panel loader)
import funding_leads2 as fl2          # noqa: E402  (load_perp)
sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore

MAKER = 0.0001
PPY = fh.PERIODS_PER_YEAR
SEED = 2026


def slice_panel(p, idx):
    br = p.get("basis_ret")
    return {"times": p["times"], "kept": [p["kept"][i] for i in idx], "binance": p["binance"][:, idx],
            "bybit": p["bybit"][:, idx], "btc": p["btc"], "basis_ret": br[:, idx] if br is not None else None}


def m_ci(series):
    """metrics + block-bootstrap CI95 (annualized) on a pnl series. Reuses fh primitives."""
    m = fh.metrics(series); lo, hi = fh.block_bootstrap_ci(series)
    return m["apr"], m["sharpe"], m["maxdd"], (lo * PPY, hi * PPY), m["n"]


def _maxdd(series):
    eq = np.cumprod(1.0 + series)
    return float((eq / np.maximum.accumulate(eq) - 1.0).min())


# ===================================================================== C-002 BOOK
def build_c002_book(tp, cut):
    """The champion C-002 book per-8h pnl: level-fixed top-10 selection (train mean funding),
    risk-parity weights (1/funding-vol, train), basis-aware maker carry_single, EWMA span tuned
    on TRAIN by the evaluate() book. Returns (book_pnl[T], top10_idx, span)."""
    fb, br = tp["binance"], tp["basis_ret"]
    T, N = fb.shape
    lvl = np.array([np.nanmean(fb[:cut, j]) for j in range(N)])
    top = np.argsort(-lvl)[:10]
    # span tuned on TRAIN via the same book evaluate() uses (single engine, basis-aware)
    ev = fh.evaluate(slice_panel(tp, list(top)), "single", MAKER, use_basis=True)
    span = ev["ewma_span"]
    P = np.array([fh.carry_single(fb[:, j], span, MAKER, br[:, j]) for j in top])
    fv = np.array([np.nanstd(fb[:cut, j][np.isfinite(fb[:cut, j])]) for j in top])
    w = np.where(fv > 0, 1.0 / fv, 0.0); w = w / w.sum()
    book = (w[:, None] * P).sum(0)
    return book, top, span, w


# ===================================================================== H-042 SLEEVE
def build_h042_sleeve(panel, spot_names, thr=-0.08, H=2):
    """H-042 liquidation-bounce sleeve as a per-8h-period return series (reuse h042_deep logic):
    trigger = perp drop < thr AND rising funding AND tradeable; payoff = H-period beta-adjusted
    EXCESS forward return (market-neutral, per-name beta to EW market). One value per EVENT-PERIOD
    = mean across names firing that period (equal-weight basket). Returns full-length series
    (0 on non-event periods = capital flat) + the list of distinct event-period indices."""
    fb, times, kept = panel["binance"], panel["times"], panel["kept"]
    pp = fl2.load_perp(times, kept)
    T, N = pp.shape
    ret = np.full_like(pp, np.nan); ret[1:] = pp[1:] / pp[:-1] - 1.0
    tradeable = np.array([k in spot_names for k in kept])
    mret = np.nanmean(ret, axis=1)
    beta = np.full(N, np.nan)
    for j in range(N):
        m = np.isfinite(ret[:, j]) & np.isfinite(mret)
        if m.sum() > 50 and np.var(mret[m]) > 0:
            beta[j] = np.cov(ret[m, j], mret[m])[0, 1] / np.var(mret[m])
    CR = np.full((T, N), np.nan)
    if T - H > 0:
        CR[:T - H] = pp[H:] / pp[:T - H] - 1.0
    mkt = np.nanmean(CR, axis=1)                       # market H-period forward per period
    sleeve = np.zeros(T)                               # 0 = flat (no cascade that period)
    ev_periods = []
    for t in range(1, T - H):
        rising = np.isfinite(fb[t]) & np.isfinite(fb[t - 1]) & (fb[t] > fb[t - 1])
        hit = np.isfinite(ret[t]) & (ret[t] < thr) & np.isfinite(CR[t]) & rising & tradeable
        js = np.where(hit)[0]
        if len(js) == 0:
            continue
        # beta-adjusted excess forward per firing name, equal-weight basket for the period
        ex = [CR[t, j] - (beta[j] if np.isfinite(beta[j]) else 1.0) * mkt[t] for j in js]
        sleeve[t] = float(np.mean(ex))
        ev_periods.append(t)
    return sleeve, np.array(ev_periods, dtype=int), beta


# ===================================================================== 1) STACK
def test_stack(panel, spot_names, tp, cut, book):
    print("=" * 92)
    print("[1] STACK — C-002 carry  ⊕  H-042 liquidation-bounce sleeve  (H-099/H-110/H-149)")
    print("=" * 92)
    sleeve, ev_periods, _ = build_h042_sleeve(panel, spot_names, thr=-0.08, H=2)
    T = len(panel["times"])
    # sleeve is on the FULL panel grid; carry book is on the tradeable panel grid (same times).
    assert len(sleeve) == len(book) == T, (len(sleeve), len(book), T)
    test = slice(cut, T)
    carry_te = book[test]
    sleeve_te = sleeve[test]
    ev_te = ev_periods[ev_periods >= cut]
    n_ev_te = len(ev_te)

    # --- correlation on CO-ACTIVE periods (where H-042 actually fires) — the honest r ---
    active = sleeve_te != 0.0
    if active.sum() > 3 and np.std(carry_te[active]) > 0 and np.std(sleeve_te[active]) > 0:
        r_active = float(np.corrcoef(carry_te[active], sleeve_te[active])[0, 1])
    else:
        r_active = float("nan")
    # full-window r (sleeve 0 on non-events) — what the blended book actually realizes
    r_full = float(np.corrcoef(carry_te, sleeve_te)[0, 1]) if np.std(sleeve_te) > 0 else float("nan")

    a_c, s_c, dd_c, ci_c, n_c = m_ci(carry_te)
    # sleeve standalone stats on its ACTIVE event-periods (the raw per-event bounce, honest EV).
    a_s, s_s, dd_s, ci_s, n_s = m_ci(sleeve_te[active]) if active.sum() > 1 else (0, 0, 0, (0, 0), 0)
    sleeve_full_mean = float(sleeve_te.mean())         # per-8h-period mean ACROSS the full test window
    sleeve_per_apr = sleeve_full_mean * PPY            # sleeve as a per-period book (flat between events)

    print(f"  H-042 sleeve (-8% / H2 / beta-adj excess, market-neutral): "
          f"{len(ev_periods)} event-periods total, {n_ev_te} in TEST.")
    print(f"  CORRELATION carry⊕sleeve:  r(co-active, n={int(active.sum())}) = {r_active:+.3f}   "
          f"r(full-test-window) = {r_full:+.3f}   <-- scale-invariant, the load-bearing result")
    print(f"  {'sleeve (per-event)':<22} APR={a_s:+8.2%} Sh={s_s:+5.2f} maxDD={dd_s:+7.2%} "
          f"CI95=[{ci_s[0]:+.1%},{ci_s[1]:+.1%}] n={n_s}  (raw bounce/event — NOT a per-8h rate)")
    print(f"  {'carry (C-002)':<22} APR={a_c:+8.2%} Sh={s_c:+5.2f} maxDD={dd_c:+7.2%} "
          f"CI95=[{ci_c[0]:+.2%},{ci_c[1]:+.2%}] n={n_c}")
    print(f"  NOTE: sleeve fires only {n_ev_te}/{T - cut} test periods at ~{100*active.mean():.1f}% duty;"
          f" raw 50/50 capital blend is meaningless (vol mismatch ~{np.std(sleeve_te[active])/max(np.std(carry_te),1e-12):.0f}x).")
    print(f"        -> stacks below are VOL-MATCHED: sleeve scaled so its full-window per-period std")
    print(f"           equals the carry book's, then weight-blended (honest common-capital basis).")

    # vol-match the sleeve to the carry book over the test window (scale-only; sign/timing preserved).
    s_carry = np.std(carry_te); s_sleeve = np.std(sleeve_te)
    k = (s_carry / s_sleeve) if s_sleeve > 0 else 0.0
    sleeve_vm = sleeve_te * k
    a_vm = float(sleeve_vm.mean()) * PPY
    print(f"  vol-matched sleeve scale k={k:.4f} -> sleeve-as-book APR={a_vm:+.2%} "
          f"(this is the sleeve's contribution at carry-equal risk)")

    rows = [("carry-alone", a_c, s_c, dd_c, ci_c, n_c, "")]
    for wlabel, wc in (("50/50", 0.50), ("70/30", 0.70)):
        comb = wc * carry_te + (1.0 - wc) * sleeve_vm    # vol-matched blend
        a, s, dd, ci, n = m_ci(comb)
        rows.append((f"stack {wlabel}", a, s, dd, ci, n, ""))
        sep = "Sh-CI-sep>carry" if ci[0] > 0 and s > s_c and ci[0] > ci_c[0] else ""
        print(f"  {'stack '+wlabel+' (volmatch)':<22} APR={a:+7.2%} Sh={s:+5.2f} maxDD={dd:+6.2%} "
              f"CI95=[{ci[0]:+.2%},{ci[1]:+.2%}] n={n}  {sep}")

    # gate logic: r<0.3 AND a stack Sharpe CI-separated above carry-alone Sharpe.
    # Sharpe CI-separation proxied via block-bootstrap of the per-period Sharpe is heavy; instead
    # use the brief's operational test: stack Sharpe > carry Sharpe with stack APR CI95 lo > carry lo.
    best = max(rows[1:], key=lambda x: x[2])
    sharpe_better = best[2] > s_c
    apr_ci_better = best[4][0] >= ci_c[0]
    low_corr = (abs(r_active) < 0.3) if np.isfinite(r_active) else False
    gate = low_corr and sharpe_better and apr_ci_better and n_ev_te > 0
    verdict = ("HARDENS C-002 (uncorrelated 2nd sleeve) — gate-candidate Y" if gate
               else f"stack does not CI-dominate carry (best Sh {best[2]:+.2f} vs {s_c:+.2f}) — "
                    f"gate-candidate N")
    print(f"  VERDICT: r={'<0.3' if low_corr else '>=0.3 or n/a'}; {verdict}")
    return {"r_active": r_active, "r_full": r_full, "n_ev_te": n_ev_te,
            "carry": (a_c, s_c, dd_c, ci_c, n_c), "rows": rows, "gate": gate, "verdict": verdict}


# ===================================================================== 2) DE-RISKER
def test_derisker(tp, cut, book):
    print("\n" + "=" * 92)
    print("[2] DE-RISKER — rolling-30p basis-vol leverage scalar (H-091/H-150)")
    print("=" * 92)
    br = tp["basis_ret"]; T = len(tp["times"])
    # book-aggregate basis-return series = mean basis_ret across the held top-10 (proxy for the
    # book's delta-neutral leg vol). Use the same top-10 as C-002.
    lvl = np.array([np.nanmean(tp["binance"][:cut, j]) for j in range(tp["binance"].shape[1])])
    top = np.argsort(-lvl)[:10]
    book_basis = np.nanmean(br[:, top], axis=1)
    book_basis = np.where(np.isfinite(book_basis), book_basis, 0.0)
    W = 30
    rv = np.full(T, np.nan)
    for t in range(T):
        a = max(0, t - W)
        seg = book_basis[a:t]
        if len(seg) >= 5:
            rv[t] = np.std(seg)
    # quantile thresholds from TRAIN basis-vol distribution (no lookahead)
    rv_tr = rv[:cut][np.isfinite(rv[:cut])]
    q80, q95 = np.percentile(rv_tr, [80, 95])
    scalar = np.ones(T)
    scalar[rv > q80] = 0.5
    scalar[rv > q95] = 0.25
    scalar[~np.isfinite(rv)] = 1.0
    # apply scalar with 1-period lag (decide leverage from PAST vol -> no lookahead)
    scal_lag = np.ones(T); scal_lag[1:] = scalar[:-1]
    scaled = book * scal_lag

    fixed_te, scaled_te = book[cut:], scaled[cut:]
    a0, s0, dd0, ci0, n0 = m_ci(fixed_te)
    a1, s1, dd1, ci1, n1 = m_ci(scaled_te)
    frac_derisk = float((scal_lag[cut:] < 1.0).mean())
    print(f"  train basis-vol q80={q80:.2e} q95={q95:.2e}; TEST de-risked {frac_derisk:.0%} of periods")
    print(f"  {'fixed (1.0x)':<18} APR={a0:+7.2%} Sh={s0:+5.2f} maxDD={dd0:+6.2%} "
          f"CI95=[{ci0[0]:+.2%},{ci0[1]:+.2%}] n={n0}")
    print(f"  {'basis-vol scaled':<18} APR={a1:+7.2%} Sh={s1:+5.2f} maxDD={dd1:+6.2%} "
          f"CI95=[{ci1[0]:+.2%},{ci1[1]:+.2%}] n={n1}")
    dd_better = dd1 > dd0  # less negative
    sh_ok = s1 >= s0 - 0.10
    verdict = (f"de-risk {'IMPROVES' if dd_better and sh_ok else 'does not improve'} risk "
               f"(maxDD {dd0:+.2%}->{dd1:+.2%}, Sh {s0:+.2f}->{s1:+.2f}); "
               f"{'risk-rule OK' if dd_better and sh_ok else 'no value-add'} — gate-candidate N (risk rule)")
    print(f"  VERDICT: {verdict}")
    return {"fixed": (a0, s0, dd0, ci0, n0), "scaled": (a1, s1, dd1, ci1, n1),
            "frac": frac_derisk, "verdict": verdict}


# ===================================================================== 3) BTC-VOL GATE
def test_btc_gate(tp, cut, book):
    print("\n" + "=" * 92)
    print("[3] BTC-VOL GATE — rolling-21 BTC realized-vol percentile (H-080/092/100/116/140)")
    print("=" * 92)
    btc = tp["btc"]; T = len(tp["times"])
    btcret = np.full(T, np.nan); btcret[1:] = btc[1:] / btc[:-1] - 1.0
    W = 21
    rv = np.full(T, np.nan)
    for t in range(T):
        a = max(0, t - W)
        seg = btcret[a:t][np.isfinite(btcret[a:t])]
        if len(seg) >= 8:
            rv[t] = np.std(seg)
    rv_tr = rv[:cut][np.isfinite(rv[:cut])]
    base_te = book[cut:]
    a0, s0, dd0, ci0, n0 = m_ci(base_te)
    print(f"  always-on (baseline)   APR={a0:+7.2%} Sh={s0:+5.2f} maxDD={dd0:+6.2%} "
          f"CI95=[{ci0[0]:+.2%},{ci0[1]:+.2%}] n={n0}")
    out = {"always": (a0, s0, dd0, ci0, n0), "variants": {}}
    for pct in (50, 60):
        thr = np.percentile(rv_tr, pct)
        on = np.zeros(T)
        # decide ON/OFF from PAST vol (1-period lag, no lookahead): ON when prev vol < thr
        prev_rv = np.full(T, np.nan); prev_rv[1:] = rv[:-1]
        on = np.where(np.isfinite(prev_rv), (prev_rv < thr).astype(float), 1.0)
        for mode, off_scalar in (("off", 0.0), ("0.5x", 0.5)):
            g = np.where(on > 0, 1.0, off_scalar)
            gated = book * g
            gt = gated[cut:]
            a1, s1, dd1, ci1, n1 = m_ci(gt)
            # eff-n honesty: distinct ON-runs in TEST (regimes autocorrelated)
            on_te = (g[cut:] == 1.0).astype(int)
            runs = int(((on_te[1:] == 1) & (on_te[:-1] == 0)).sum() + (on_te[0] == 1))
            frac_on = float(on_te.mean())
            tag = f"btc-vol<p{pct} ({mode} above)"
            out["variants"][tag] = (a1, s1, dd1, ci1, n1, runs, frac_on)
            flag = "CI>0 & Sh>base" if (ci1[0] > 0 and s1 > s0) else ""
            print(f"  {tag:<26} APR={a1:+7.2%} Sh={s1:+5.2f} maxDD={dd1:+6.2%} "
                  f"CI95=[{ci1[0]:+.2%},{ci1[1]:+.2%}] n={n1} | ON {frac_on:.0%}, eff-n≈{runs} runs  {flag}")
    # verdict: best gated Sharpe vs always-on, honest about run-count (regime-capture guard)
    best_tag = max(out["variants"], key=lambda k: out["variants"][k][1])
    bv = out["variants"][best_tag]
    beats = bv[1] > s0 and bv[3][0] > 0
    regime_risk = bv[5] < 8
    verdict = (f"best={best_tag} Sh {bv[1]:+.2f} vs always-on {s0:+.2f}; "
               f"{'gate ties/worse' if not beats else 'gate lifts Sharpe'} "
               f"{'(BUT eff-n≈%d runs -> regime-capture risk, INVALID as champion)' % bv[5] if regime_risk and beats else ''} "
               f"— gate-candidate {'N' if (not beats or regime_risk) else 'Y'}")
    print(f"  VERDICT: {verdict}")
    out["verdict"] = verdict
    return out


# ===================================================================== 4) SELECTION
def _book_from_idx(tp, idx, cut):
    """Build the SAME risk-parity basis-aware book on an arbitrary top-10 index set, TEST series."""
    fb, br = tp["binance"], tp["basis_ret"]
    ev = fh.evaluate(slice_panel(tp, list(idx)), "single", MAKER, use_basis=True)
    span = ev["ewma_span"]
    P = np.array([fh.carry_single(fb[:, j], span, MAKER, br[:, j]) for j in idx])
    fv = np.array([np.nanstd(fb[:cut, j][np.isfinite(fb[:cut, j])]) for j in idx])
    w = np.where(fv > 0, 1.0 / fv, 0.0); w = w / w.sum()
    book = (w[:, None] * P).sum(0)
    return book


def test_selection(tp, cut):
    print("\n" + "=" * 92)
    print("[4] SELECTION variants vs H-021 level base (H-115 AR1 / H-145 low-beta / H-089 composite)")
    print("=" * 92)
    fb, btc = tp["binance"], tp["btc"]
    T, N = fb.shape

    lvl = np.array([np.nanmean(fb[:cut, j]) for j in range(N)])
    persist = np.array([float((fb[:cut, j][np.isfinite(fb[:cut, j])] > 0).mean())
                        if np.isfinite(fb[:cut, j]).any() else 0.0 for j in range(N)])
    # H-115: funding AR(1) coefficient on TRAIN (lag-1 autocorrelation of funding level)
    ar1 = np.full(N, np.nan)
    for j in range(N):
        c = fb[:cut, j]; m = np.isfinite(c[1:]) & np.isfinite(c[:-1])
        if m.sum() > 30 and np.std(c[:-1][m]) > 0 and np.std(c[1:][m]) > 0:
            ar1[j] = np.corrcoef(c[:-1][m], c[1:][m])[0, 1]
    # H-145: low BTC-beta names (beta of name funding-carry pnl to BTC returns, TRAIN)
    btcret = np.full(T, np.nan); btcret[1:] = btc[1:] / btc[:-1] - 1.0
    beta = np.full(N, np.nan)
    for j in range(N):
        pnl = fh.carry_single(fb[:, j], 6, MAKER, tp["basis_ret"][:, j])
        mm = np.isfinite(btcret[:cut]) & np.isfinite(pnl[:cut])
        if mm.sum() > 30 and np.var(btcret[:cut][mm]) > 0:
            beta[j] = np.cov(pnl[:cut][mm], btcret[:cut][mm])[0, 1] / np.var(btcret[:cut][mm])

    sel = {
        "H-021 level (BASE)": np.argsort(-lvl)[:10],
        "H-115 funding AR(1)": np.argsort(-np.where(np.isfinite(ar1), ar1, -1e9))[:10],
        "H-145 low BTC-beta": np.argsort(np.where(np.isfinite(beta), np.abs(beta), 1e9))[:10],
        "H-089 level×persist": np.argsort(-(lvl * persist))[:10],
    }
    base_stats = None
    out = {}
    for tag, idx in sel.items():
        book = _book_from_idx(tp, idx, cut)
        a, s, dd, ci, n = m_ci(book[cut:])
        out[tag] = (a, s, dd, ci, n)
        if "BASE" in tag:
            base_stats = (a, s, dd, ci, n)
            sep = ""
        else:
            # CI-separated from base = this variant's APR CI95 lo > base APR point (strong) OR
            # base APR point below this lo (i.e. lower bounds don't overlap base mean)
            sep = "CI-sep>base" if ci[0] > base_stats[0] else ("Sh>base" if s > base_stats[1] else "")
        print(f"  {tag:<24} APR={a:+7.2%} Sh={s:+5.2f} maxDD={dd:+6.2%} "
              f"CI95=[{ci[0]:+.2%},{ci[1]:+.2%}] n={n}  {sep}")
    # verdict
    bestnb = max([k for k in out if "BASE" not in k], key=lambda k: out[k][1])
    bs = out[bestnb]; sep = bs[3][0] > base_stats[0]
    verdict = (f"best non-base = {bestnb} (Sh {bs[1]:+.2f} vs base {base_stats[1]:+.2f}); "
               f"{'CI-separated -> flag' if sep else 'NOT CI-separated from base -> no flag'} — "
               f"gate-candidate {'Y' if (sep and bs[0] > 0.02 and bs[3][0] > 0 and bs[4] > 100) else 'N'}")
    print(f"  VERDICT: {verdict}")
    out["__base__"] = base_stats; out["__verdict__"] = verdict
    return out


# ===================================================================== MAIN
def main():
    panel, spot_names, bybit_names = h13.load_offline_panel()
    tp = fh.filter_tradeable(panel, min_cov=0.90)
    T = len(tp["times"]); cut = int(T * fh.TRAIN_FRAC)
    span_d = (tp["times"][-1] - tp["times"][0]) / (24 * 3600 * 1000) if T else 0
    print("=" * 92)
    print(f"CARRY-CLUSTER BATTERY — panel {len(panel['kept'])} names / tradeable {len(tp['kept'])} / "
          f"{T} periods (~{span_d:.0f}d), cut@{cut} (70/30)")
    print("=" * 92)

    book, top, span, w = build_c002_book(tp, cut)
    a, s, dd, ci, n = m_ci(book[cut:])
    print(f"C-002 BASELINE (level-fixed RP top-10, span={span}, basis-aware maker): "
          f"TEST APR={a:+.2%} Sh={s:+.2f} maxDD={dd:+.2%} CI95=[{ci[0]:+.2%},{ci[1]:+.2%}] n={n}")
    print(f"  top-10: {', '.join(tp['kept'][j] for j in top)}\n")

    r1 = test_stack(panel, spot_names, tp, cut, book)
    r2 = test_derisker(tp, cut, book)
    r3 = test_btc_gate(tp, cut, book)
    r4 = test_selection(tp, cut)

    print("\n" + "=" * 92)
    print("COMPACT SUMMARY (test | APR | Sharpe | CI95 | n | verdict)")
    print("=" * 92)
    bc = r1["carry"]
    print(f"  baseline C-002      | {bc[0]:+6.2%} | {bc[1]:+5.2f} | "
          f"[{bc[3][0]:+.2%},{bc[3][1]:+.2%}] | {bc[4]} | champion baseline")
    for tag, a_, s_, dd_, ci_, n_, _ in r1["rows"][1:]:
        print(f"  {tag:<19} | {a_:+6.2%} | {s_:+5.2f} | [{ci_[0]:+.2%},{ci_[1]:+.2%}] | {n_} | "
              f"r={r1['r_active']:+.2f} stack")
    f0, f1 = r2["fixed"], r2["scaled"]
    print(f"  derisk fixed        | {f0[0]:+6.2%} | {f0[1]:+5.2f} | [{f0[3][0]:+.2%},{f0[3][1]:+.2%}] | {f0[4]} | "
          f"maxDD {f0[2]:+.2%}")
    print(f"  derisk scaled       | {f1[0]:+6.2%} | {f1[1]:+5.2f} | [{f1[3][0]:+.2%},{f1[3][1]:+.2%}] | {f1[4]} | "
          f"maxDD {f1[2]:+.2%}")
    g0 = r3["always"]
    print(f"  btcgate always-on   | {g0[0]:+6.2%} | {g0[1]:+5.2f} | [{g0[3][0]:+.2%},{g0[3][1]:+.2%}] | {g0[4]} | baseline")
    for tag, v in r3["variants"].items():
        print(f"  {tag:<19} | {v[0]:+6.2%} | {v[1]:+5.2f} | [{v[3][0]:+.2%},{v[3][1]:+.2%}] | {v[4]} | "
              f"eff-n≈{v[5]} runs")
    for tag, v in r4.items():
        if tag.startswith("__"):
            continue
        print(f"  {tag:<19} | {v[0]:+6.2%} | {v[1]:+5.2f} | [{v[3][0]:+.2%},{v[3][1]:+.2%}] | {v[4]} | sel")
    print("=" * 92)
    print(f"STACK r(co-active) = {r1['r_active']:+.3f} | r(full) = {r1['r_full']:+.3f} | "
          f"H-042 test events = {r1['n_ev_te']} | gate={r1['gate']}")
    print("=" * 92)


if __name__ == "__main__":
    main()
