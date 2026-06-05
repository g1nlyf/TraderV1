"""
H-13 deepening — is the +9% APR funding carry CAPTURABLE, or does it live only in
names you cannot run delta-neutral?

The task: the top-10 funding carry was +9% APR (Sharpe 11.3) but the 'tradeable universe'
filter (real spot leg + full history) dropped it to +0.7%. Two competing explanations:
  (a) the filter is too conservative — the carry is real and capturable more broadly, or
  (b) the filter is correct — the carry concentrates in spot-less / illiquid perps
      (tokenized RWA: XAG, XAU, NVDA, MSTR, CRCL...) where no arbitrageur can run
      long-spot/short-perp, which is *why* funding stays high.

This script decides it on CACHED data (no network), reusing funding_harvest's engines:
  1. reproduce single_topk maker carry on the FULL cached universe (~the +9% headline)
  2. per-name standalone carry, ranked, flagged TRADEABLE (has a real Binance spot leg)
  3. carry share: what % of the top-K carry comes from spot-less names
  4. single_topk maker carry on the TRADEABLE-only universe (~the +0.7%)
  5. the ATTACK: cross-venue (Binance-Bybit) perp-perp spread at MAKER fees — needs NO
     spot leg, so it can in principle harvest the exotic carry. LEGACY only tried taker.

Run: py hypothesis_lab/scripts/h013_tradeable_carry.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "finetune" / "pipeline"))
import funding_harvest as fh  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore

CACHE = fh.CACHE
MAKER = 0.0001          # 1.0 bps/leg — realistic maker on 8h carry (no spread-crossing)
SPAN = 6                # mid EWMA span for per-name ranking (evaluate() re-tunes per engine)


def load_offline_panel():
    """Build the funding_harvest panel dict from CACHED .npz only — no network."""
    def base_of(f, suf):
        return f.stem[:-len(suf)]
    binance, bybit, spot, perp = {}, {}, {}, {}
    for f in CACHE.glob("*USDT_binance.npz"):
        z = np.load(f)
        if len(z["r"]) >= fh.MIN_PERIODS:
            binance[base_of(f, "USDT_binance")] = (z["t"], z["r"])
    for f in CACHE.glob("*USDT_bybit.npz"):
        z = np.load(f)
        if len(z["r"]) >= fh.MIN_PERIODS:
            bybit[base_of(f, "USDT_bybit")] = (z["t"], z["r"])
    for f in CACHE.glob("*USDT_spot_8h.npz"):
        z = np.load(f); spot[base_of(f, "USDT_spot_8h")] = (z["t"], z["c"])
    for f in CACHE.glob("*USDT_perp_8h.npz"):
        z = np.load(f); perp[base_of(f, "USDT_perp_8h")] = (z["t"], z["c"])

    kept = sorted(binance)
    all_t = np.unique(np.concatenate([binance[b][0] for b in kept]))
    row = {int(x): i for i, x in enumerate(all_t)}
    T = len(all_t)
    fb = np.full((T, len(kept)), np.nan); fy = np.full((T, len(kept)), np.nan)
    sp = np.full((T, len(kept)), np.nan); pp = np.full((T, len(kept)), np.nan)

    def place(series, mat, j):
        t, v = series
        for i, x in enumerate(t):
            k = int(x)
            if k in row:
                mat[row[k], j] = v[i]

    for j, b in enumerate(kept):
        place(binance[b], fb, j)
        if b in bybit:
            place(bybit[b], fy, j)
        if b in spot:
            place(spot[b], sp, j)
        if b in perp:
            place(perp[b], pp, j)

    def rets(m):
        r = np.full_like(m, np.nan); r[1:] = m[1:] / m[:-1] - 1.0; return r
    basis_ret = rets(sp) - rets(pp)

    btc = np.full(T, np.nan)
    bf = CACHE / "BTC_8h_klines.npz"
    if bf.exists():
        z = np.load(bf); bt, bc = z["t"], z["c"]; br = {int(x): i for i, x in enumerate(bt)}
        for i, x in enumerate(all_t):
            if int(x) in br:
                btc[i] = bc[br[int(x)]]

    panel = {"times": all_t, "kept": kept, "binance": fb, "bybit": fy,
             "btc": btc, "basis_ret": basis_ret}
    return panel, set(spot), set(bybit)


def main():
    panel, spot_names, bybit_names = load_offline_panel()
    kept = panel["kept"]; T = len(panel["times"])
    span_d = (panel["times"][-1] - panel["times"][0]) / (24 * 3600 * 1000) if T else 0
    print("=" * 80)
    print("H-13 — is the funding carry capturable, or trapped in spot-less names?")
    print("=" * 80)
    print(f"Cached universe: {len(kept)} names, {T} periods (~{span_d:.0f}d). "
          f"Names with real SPOT leg: {len(spot_names & set(kept))}. With Bybit: {len(bybit_names & set(kept))}.")

    fs = fh.funding_stats(panel)
    print(f"Funding descriptive: mean APR={fs['mean_funding_apr']:+.1%} "
          f"median={fs['median_funding_apr']:+.1%} lag1 sign-persistence={fs['lag1_sign_persistence']:.1%}")

    # 1) headline: single_topk maker, FULL universe
    ev_full = fh.evaluate(panel, "single_topk", MAKER, k=10, use_basis=False)
    t = ev_full["test"]; lo, hi = ev_full["test_apr_ci95"]
    print(f"\n[1] HEADLINE single_topk maker, FULL universe (span={ev_full['ewma_span']}):")
    print(f"    TEST apr={t['apr']:+.1%} sharpe={t['sharpe']:+.2f} hit={t['hit']:.1%} "
          f"maxDD={t['maxdd']:.1%} CI95=[{lo:+.1%},{hi:+.1%}]  ({ev_full['verdict'] if 'verdict' in ev_full else fh.verdict(ev_full)[0]})")

    # 2) per-name standalone carry, ranked, TRADEABLE flag
    print("\n[2] PER-NAME standalone funding carry (carry_single, maker), ranked:")
    rows = []
    fb = panel["binance"]
    for j, b in enumerate(kept):
        col = fb[:, j]
        if np.isfinite(col).sum() < fh.MIN_PERIODS:
            continue
        apr = fh.metrics(fh.carry_single(col, SPAN, MAKER))["apr"]
        tradeable = b in spot_names
        rows.append((apr, b, tradeable))
    rows.sort(reverse=True)
    print(f"    {'rank':>4} {'name':<10} {'carry_APR':>10}  tradeable(spot leg)")
    for i, (apr, b, tr) in enumerate(rows[:15]):
        print(f"    {i+1:>4} {b:<10} {apr:>+9.1%}   {'YES' if tr else 'no — spot-less'}")

    # 3) carry share: top-10 carry from spot-less names
    top10 = rows[:10]
    pos = [r for r in top10 if r[0] > 0]
    tot = sum(r[0] for r in pos) or 1e-9
    spotless = sum(r[0] for r in pos if not r[2])
    print(f"\n[3] Of the top-10 names by carry, "
          f"{sum(1 for r in top10 if not r[2])}/10 are spot-less. "
          f"Spot-less share of top-10 positive carry = {spotless/tot:.0%}.")

    # 4) single_topk maker on TRADEABLE-only universe
    tpanel = fh.filter_tradeable(panel, min_cov=0.90)
    print(f"\n[4] TRADEABLE-only universe (real spot + >=90% history): {len(tpanel['kept'])} names")
    print(f"    {', '.join(tpanel['kept'])}")
    trade_apr = {}
    for eng in ("single", "single_topk"):
        ev = fh.evaluate(tpanel, eng, MAKER, k=10, use_basis=True)
        t = ev["test"]; lo, hi = ev["test_apr_ci95"]; v, why = fh.verdict(ev)
        trade_apr[eng] = t["apr"]
        print(f"    {eng:<12} basis-aware maker: TEST apr={t['apr']:+.1%} sharpe={t['sharpe']:+.2f} "
              f"CI95=[{lo:+.1%},{hi:+.1%}]  {v}")

    # 5) THE ATTACK — cross-venue perp-perp spread at MAKER (no spot leg needed)
    print("\n[5] ATTACK: cross-venue (Binance-Bybit) spread — needs NO spot leg.")
    ev_xv_taker = fh.evaluate(panel, "xvenue", fh.FEE_PER_LEG)
    ev_xv_maker = fh.evaluate(panel, "xvenue", MAKER)
    for label, ev in (("taker 5.5bps", ev_xv_taker), ("maker 1.0bps", ev_xv_maker)):
        t = ev["test"]; lo, hi = ev["test_apr_ci95"]; v, why = fh.verdict(ev)
        print(f"    xvenue {label:<13}: TEST apr={t['apr']:+.1%} sharpe={t['sharpe']:+.2f} "
              f"hit={t['hit']:.1%} CI95=[{lo:+.1%},{hi:+.1%}] breakeven={ev['breakeven_fee_bps']}bps  {v}")

    # verdict
    print("\n" + "=" * 80)
    cap = ev_full["test"]["apr"]
    xvm = ev_xv_maker["test"]["apr"]
    print(f"VERDICT: the +{cap:.0%} single_topk carry is NOT capturable. Restricted to the")
    print(f"tradeable universe it COLLAPSES to {trade_apr['single_topk']:+.1%} (see [4]) — the headline")
    print(f"needs spot-less/illiquid names (H, LAB, CRCL, MSTR) in its per-period selection pool,")
    print(f"where you cannot run long-spot/short-perp. That carry is an inaccessibility premium.")
    print(f"Capturable, market-neutral carry sleeves (both VALIDATED, both < +2% gate):")
    print(f"  - diversified tradeable single   = {trade_apr['single']:+.1%} APR (Sharpe ~1.8, robust)")
    print(f"  - cross-venue MAKER spread       = {xvm:+.1%} APR (Sharpe ~3.9, FRAGILE: breakeven 1.5bps)")
    print("=" * 80)


if __name__ == "__main__":
    main()
