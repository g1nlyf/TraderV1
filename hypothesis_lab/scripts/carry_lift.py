"""
H-031 / H-049 / H-036 / H-051 — carry-book refinements (Session 3).
Reuses funding_harvest engines + the offline panel loader. All offline, deterministic.

Goal honesty: parallel uncorrelated sleeves AVERAGE APR and RAISE Sharpe (Session 2 finding),
so these refinements lift Sharpe (the leverage enabler), not unlevered APR past +2%. We measure
exactly that, and whether the negative-funding sleeve is a genuinely uncorrelated 3rd component.

Run: py hypothesis_lab/scripts/carry_lift.py
"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "finetune" / "pipeline"))
sys.path.insert(0, str(ROOT / "hypothesis_lab" / "scripts"))
import funding_harvest as fh          # noqa: E402
import h013_tradeable_carry as h13    # noqa: E402
sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore
MAKER = 0.0001; PPY = fh.PERIODS_PER_YEAR


def slice_panel(p, idx):
    br = p.get("basis_ret")
    return {"times": p["times"], "kept": [p["kept"][i] for i in idx], "binance": p["binance"][:, idx],
            "bybit": p["bybit"][:, idx], "btc": p["btc"], "basis_ret": br[:, idx] if br is not None else None}


def m_test(s, cut):
    mm = fh.metrics(s[cut:]); lo, hi = fh.block_bootstrap_ci(s[cut:])
    return mm["apr"], mm["sharpe"], mm["maxdd"], (lo * PPY, hi * PPY)


def main():
    panel, spot, _ = h13.load_offline_panel()
    tp = fh.filter_tradeable(panel, min_cov=0.90)
    fb, br, btc = tp["binance"], tp["basis_ret"], tp["btc"]
    T, N = fb.shape; cut = int(T * fh.TRAIN_FRAC)
    print("=" * 78); print("CARRY REFINEMENTS — H-031/049/036/051 (tradeable-29, OOS)"); print("=" * 78)

    # baseline: level-fixed top-10 (H-021), tuned span
    lvl = np.array([np.nanmean(fb[:cut, j]) for j in range(N)])
    top_lvl = np.argsort(-lvl)[:10]
    ev = fh.evaluate(slice_panel(tp, list(top_lvl)), "single", MAKER, use_basis=True)
    span = ev["ewma_span"]; b = ev["test"]
    print(f"\nBASELINE level-fixed top-10 (span={span}): apr={b['apr']:+.2%} sharpe={b['sharpe']:+.2f} "
          f"maxDD={b['maxdd']:+.2%}")

    # per-name carry pnl at the tuned span
    P = np.array([fh.carry_single(fb[:, j], span, MAKER, br[:, j]) for j in range(N)])
    ew = P[top_lvl].mean(0)

    # --- H-049: carry-to-vol selection (per-name carry Sharpe on train) ---
    csh = np.array([fh.metrics(P[j][:cut])["sharpe"] for j in range(N)])
    top_c = np.argsort(-csh)[:10]
    ev49 = fh.evaluate(slice_panel(tp, list(top_c)), "single", MAKER, use_basis=True)
    print(f"\nH-049 carry-to-vol selection: apr={ev49['test']['apr']:+.2%} "
          f"sharpe={ev49['test']['sharpe']:+.2f} maxDD={ev49['test']['maxdd']:+.2%}  "
          f"names={','.join(tp['kept'][j] for j in top_c)}")

    # --- H-031: risk-parity (1/funding-vol) on the level-top-10 ---
    fv = np.array([np.nanstd(fb[:cut, j][np.isfinite(fb[:cut, j])]) for j in top_lvl])
    w = np.where(fv > 0, 1.0 / fv, 0.0); w = w / w.sum()
    rp = (w[:, None] * P[top_lvl]).sum(0)
    a, s, dd, ci = m_test(rp, cut)
    print(f"\nH-031 risk-parity (1/funding-vol): apr={a:+.2%} sharpe={s:+.2f} maxDD={dd:+.2%} "
          f"CI95=[{ci[0]:+.2%},{ci[1]:+.2%}]  (vs EW sharpe {b['sharpe']:+.2f})")

    # --- H-036: BTC-beta neutralize the EW level book ---
    btcret = np.full(T, np.nan); btcret[1:] = btc[1:] / btc[:-1] - 1.0
    msk = np.isfinite(ew) & np.isfinite(btcret)
    tr = msk.copy(); tr[cut:] = False
    if tr.sum() > 20 and np.nanvar(btcret[tr]) > 0:
        beta = np.cov(ew[tr], btcret[tr])[0, 1] / np.var(btcret[tr])
    else:
        beta = 0.0
    hedged = ew - beta * np.nan_to_num(btcret) - 0.000055 * abs(beta) * np.abs(np.nan_to_num(btcret))
    a0, s0, d0, _ = m_test(ew, cut); a1, s1, d1, _ = m_test(hedged, cut)
    print(f"\nH-036 beta-hedge (beta={beta:+.2f}): EW apr={a0:+.2%} sh={s0:+.2f} maxDD={d0:+.2%} "
          f"-> hedged apr={a1:+.2%} sh={s1:+.2f} maxDD={d1:+.2%}")

    # --- H-051: negative-funding sleeve (long-perp/short-spot) ---
    def neg_pnl(j):
        sgn = fh._ewma_sign_prev(fb[:, j], span); pos = (sgn < 0).astype(float)
        out = np.zeros(T); prev = 0.0
        for i in range(T):
            f = fb[i, j] if np.isfinite(fb[i, j]) else 0.0
            bb = br[i, j] if np.isfinite(br[i, j]) else 0.0
            out[i] = pos[i] * (-f - bb) - MAKER * 2.0 * abs(pos[i] - prev); prev = pos[i]
        return out
    neg_top = np.argsort(lvl)[:10]          # most-negative mean train funding
    NEG = np.array([neg_pnl(j) for j in neg_top])
    neg_book = NEG.mean(0)
    a2, s2, d2, ci2 = m_test(neg_book, cut)
    corr = float(np.corrcoef(ew[cut:], neg_book[cut:])[0, 1])
    print(f"\nH-051 neg-funding sleeve: apr={a2:+.2%} sharpe={s2:+.2f} maxDD={d2:+.2%} "
          f"CI95=[{ci2[0]:+.2%},{ci2[1]:+.2%}]  corr_to_pos={corr:+.2f}")
    print("  per-name (train_fundAPR / test_fundAPR / test_sleeveAPR) — persistence + concentration:")
    contribs = []
    for ji, j in enumerate(neg_top):
        trf = np.nanmean(fb[:cut, j]) * PPY; tef = np.nanmean(fb[cut:, j]) * PPY
        sl = fh.metrics(NEG[ji][cut:])["apr"]; contribs.append(sl)
        flip = "" if (trf < 0 and tef < 0) else "  <-- sign FLIPPED train->test"
        print(f"    {tp['kept'][j]:<6} {trf:+6.1%} / {tef:+6.1%} / {sl:+6.1%}{flip}")
    contribs = np.array(contribs)
    print(f"  concentration: top-1 name = {contribs.max()/contribs.sum():.0%} of total sleeve APR; "
          f"{int((contribs>0).sum())}/10 names positive")

    # --- best book + 3-sleeve stack (incl xvenue from carry_leads logic) ---
    import carry_leads as cl  # reuse _best_span_series for xvenue
    xv, xcut, _ = cl._best_span_series(panel, "xvenue", MAKER, False)
    best_single = rp if s > b['sharpe'] else ew
    sleeves = {"pos(best)": best_single[cut:], "xvenue": xv[cut:], "neg": neg_book[cut:]}
    print("\n--- STACK (equal-capital across sleeves; APR averages, Sharpe diversifies) ---")
    for combo in (["pos(best)", "xvenue"], ["pos(best)", "xvenue", "neg"]):
        arr = np.mean([sleeves[k] for k in combo], axis=0)
        mm = fh.metrics(arr); lo, hi = fh.block_bootstrap_ci(arr)
        print(f"  {'+'.join(combo):<28} apr={mm['apr']:+.2%} sharpe={mm['sharpe']:+.2f} "
              f"maxDD={mm['maxdd']:+.2%} CI95=[{lo*PPY:+.2%},{hi*PPY:+.2%}]")
    print("\n" + "=" * 78)


if __name__ == "__main__":
    main()
