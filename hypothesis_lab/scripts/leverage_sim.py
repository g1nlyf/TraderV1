"""
LEVERAGE SIM — the real gate to +5%. Replaces the 8h-close maxDD TRAP with intra-8h 1m paths.

Champion-candidate carry book = long spot / short perp, delta-neutral, +1.49% APR unlevered (Sh~3.5).
To reach the +5% target needs ~3.4x leverage. The 8h-close maxDD (−0.24%) cannot see what actually
kills levered carry: an intra-8h UP spike liquidates the isolated short-perp leg before the spot leg's
gain is realized on the (separately-margined) spot exchange.

Model (honest, conservative = isolated margin):
  * Position per name: short perp at leverage L (notional = L × equity_slice). Long spot hedge.
  * Liquidation when the perp's adverse (UP) move within an 8h funding period exceeds the maintenance
    threshold d_liq(L) = 1/L − mmr  (mmr≈0.4%). Measured from 1m HIGHS (worst intra-bar excursion).
  * Funding (the carry) scales with notional → levered carry APR ≈ L × base_apr (minus liq drag).
  * max_safe_L = highest L with expected liquidations < 1 / year. Levered APR there = the answer.

CAVEAT baked into output: 180d may not contain a true flash/basis-blowout. The safe-L is for
NORMAL conditions; a tail event is un-sampled → treat the levered APR as an upper bound and keep a
stress haircut. This is still vastly more honest than the 8h-close maxDD.

Run: py hypothesis_lab/scripts/leverage_sim.py
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

DATA = ROOT / "finetune" / "data" / "intraday_1m"
MMR = 0.004                  # maintenance margin rate (~0.4%)
PERIOD_MS = 8 * 3600 * 1000  # 8h funding period
BASE_APR = 0.0149            # champion-candidate unlevered (risk-parity level-fixed, H-031)


def load_1m(name, venue):
    p = DATA / f"{name}_{venue}_1m.npz"
    if not p.exists():
        return None
    z = np.load(p)
    return z["open_time"], z["high"], z["low"], z["close"]


def period_excursions(name):
    """Per 8h period, the worst-case ADVERSE intra-period excursion for long-spot/short-perp:
       (a) perp-absolute up-move  = ISOLATED-margin liquidation risk (conservative),
       (b) basis (perp/spot) widening = CROSS-margin risk (realistic for a pro carry desk).
       Returns (perp_abs_up[], basis_adv[]) or None."""
    dp, ds = load_1m(name, "perp"), load_1m(name, "spot")
    if dp is None:
        return None
    otp, hp, lp, cp = dp
    pid = (otp // PERIOD_MS).astype(np.int64)
    perp_abs, basis_adv = [], []
    # align spot to perp minutes for the basis path
    sclose = None
    if ds is not None:
        ots, _, _, cs = ds
        idx = {int(t): i for i, t in enumerate(ots)}
        sclose = np.array([cs[idx[int(t)]] if int(t) in idx else np.nan for t in otp])
    for p in np.unique(pid):
        m = pid == p
        if m.sum() < 60:
            continue
        entry = cp[m][0]
        if not np.isfinite(entry) or entry <= 0:
            continue
        perp_abs.append(hp[m].max() / entry - 1.0)
        if sclose is not None:
            basis = cp[m] / sclose[m]                 # perp/spot path
            b0 = basis[np.isfinite(basis)]
            if len(b0) > 30 and np.isfinite(b0[0]) and b0[0] > 0:
                basis_adv.append(np.nanmax(basis) / b0[0] - 1.0)   # basis widening hurts short-perp
    return np.array(perp_abs), np.array(basis_adv)


def main():
    files = sorted(DATA.glob("*_perp_1m.npz"))
    names = [f.stem[:-len("_perp_1m")] for f in files]
    if not names:
        print("No 1m data yet in", DATA); return
    print("=" * 84)
    print(f"LEVERAGE SIM — champion-candidate carry book, intra-8h liquidation from 1m paths")
    print("=" * 84)
    print(f"Names with 1m perp data: {len(names)} {names}")

    perp_all, basis_all = [], []
    for n in names:
        ex = period_excursions(n)
        if ex is None or len(ex[0]) == 0:
            continue
        pa, ba = ex
        perp_all.append(pa)
        if len(ba):
            basis_all.append(ba)
        bstr = (f"basis p99={np.percentile(ba,99):+.2%} max={ba.max():+.2%}" if len(ba) else "basis: (spot pending)")
        print(f"  {n:>6}: periods={len(pa):4d}  perp-abs p99={np.percentile(pa,99):+.2%} max={pa.max():+.2%}  | {bstr}")
    perp = np.concatenate(perp_all)
    years = len(perp) * PERIOD_MS / (365.25 * 24 * 3600 * 1000)
    nN = len(names)
    loss_per_liq = 1.0 / nN     # one blown leg ≈ 1/N of book equity

    def table(ex, years, label):
        print(f"\n[{label}]  (each liquidation ≈ loses 1/{nN} of book = {loss_per_liq:.0%}; net = L·base − liq/yr·loss)")
        print(f"  {'L':>3} {'d_liq':>7} {'liq':>5} {'liq/yr':>8} {'gross_APR':>10} {'net_APR':>9}  note")
        safe = 1
        for L in (1, 2, 3, 4, 5, 6, 8, 10):
            d = 1.0 / L - MMR
            liq = int((ex > d).sum()); lyr = liq / years if years > 0 else np.nan
            gross = L * BASE_APR; net = gross - lyr * loss_per_liq
            note = "safe" if lyr < 0.2 else ("marginal" if lyr < 1 else "UNSAFE")
            if lyr < 0.2:
                safe = max(safe, L)
            print(f"  {L:>3} {d:>7.1%} {liq:>5} {lyr:>8.2f} {gross:>9.1%} {net:>+8.1%}  {note}")
        return safe

    print(f"\nname-periods: perp={len(perp)} basis={sum(len(b) for b in basis_all)}  (~{years:.2f} name-years)")
    s_iso = table(perp, years, "ISOLATED margin — perp absolute move (conservative; the naive setup)")
    if basis_all:
        basis = np.concatenate(basis_all)
        s_cross = table(basis, years, "CROSS margin — perp/spot BASIS widening (realistic pro carry desk)")
    else:
        s_cross = None
    print("\n" + "=" * 84)
    print(f"ISOLATED safe_L≈{s_iso}x (one +N% spike liquidates a leg — net APR collapses).")
    if s_cross:
        print(f"CROSS-MARGIN safe_L≈{s_cross}x → levered carry APR ≈ {s_cross*BASE_APR:+.1%} "
              f"({'REACHES +5%' if s_cross*BASE_APR >= 0.05 else 'short of +5%'}). This is the realistic desk setup.")
    print("CAVEAT: 180d, few names — no sampled flash/basis-blowout. The basis tail is the real killer and is")
    print("UNDER-sampled here; treat safe_L as an upper bound and keep a stress haircut. NOT mission-complete on this alone.")
    print("=" * 84)


if __name__ == "__main__":
    main()
