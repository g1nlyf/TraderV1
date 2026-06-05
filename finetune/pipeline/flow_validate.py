"""
Full-token ORDER-FLOW IMBALANCE validator — the strong, self-contained test.

The cohort net_flow signal (86-wallet sample) was the ONE regime-stable survivor but weak
(rho +0.06-0.15) because it samples a tiny slice of true flow. This measures the FULL flow
(every trader on the pool) and tests the real hypothesis directly and self-containedly:

    Does net order-flow imbalance over [T-W, T] predict forward price return over [T, T+H]?

Self-contained = pool swaps give BOTH the imbalance signal AND the forward price path, so we
need no cohort labels. Every point in a token's life is a sample -> big N from few tokens.

Honesty guards:
  - forward return uses prices STRICTLY after T (no look-ahead).
  - temporal 70/30 split per token-stream -> is the sign stable across regime?
  - decorrelate samples (stride) so overlapping windows don't inflate N.

Active pools discovered via Dexscreener public API (no key). Helius keys: ENV ONLY.
Run:  python flow_validate.py [n_pools] [pages] [W_sec] [H_sec]
"""
from __future__ import annotations

import statistics
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import requests
from finetune.pipeline.helius_client import get_signatures, parse, WSOL

SOL_MINT = "So11111111111111111111111111111111111111112"
GT = "https://api.geckoterminal.com/api/v2/networks/solana"


def active_solana_pools(n: int) -> list[tuple[str, str, str]]:
    """Return [(pool, base_mint, symbol)] of active SOL-quoted pools (GeckoTerminal).

    Target the testable band: enough flow to have many swaps, but moderate reserve so
    price actually MOVES on order flow (memecoin microstructure, not a deep blue-chip).
    """
    seen, cand = set(), []
    for ep in ("trending_pools", "pools"):
        try:
            r = requests.get(f"{GT}/{ep}", params={"page": 1},
                             headers={"accept": "application/json"}, timeout=20)
            if r.status_code != 200:
                continue
            for d in r.json().get("data", []):
                a = d.get("attributes", {}); rel = d.get("relationships", {})
                base = (((rel.get("base_token") or {}).get("data") or {}).get("id") or "").replace("solana_", "")
                quote = (((rel.get("quote_token") or {}).get("data") or {}).get("id") or "").replace("solana_", "")
                pool = a.get("address")
                volh1 = float(((a.get("volume_usd") or {}).get("h1")) or 0)
                resv = float(a.get("reserve_in_usd") or 0)
                sym = (a.get("name") or "?").split(" / ")[0]
                if quote != SOL_MINT or not pool or not base or pool in seen:
                    continue
                # testable band: active flow + price-sensitive reserve
                if not (20_000 <= volh1 and 10_000 <= resv <= 400_000):
                    continue
                seen.add(pool)
                cand.append((pool, base, sym, volh1))
        except Exception:
            continue
    cand.sort(key=lambda x: -x[3])  # by 1h volume
    return [(p, m, s) for p, m, s, _ in cand[:n]]


def pool_flow(pool: str, mint: str, pages: int) -> list[tuple]:
    """[(ts, side, sol, trader, price)] for every swap on the pool. price = sol/token."""
    sigs, before = [], None
    for _ in range(pages):
        batch = get_signatures(pool, limit=100, before=before)
        if not batch:
            break
        sigs += [s["signature"] for s in batch]
        before = batch[-1]["signature"]
    parsed = parse(sigs)
    out = []
    for tx in parsed:
        ts = tx.get("timestamp") or 0
        payer = tx.get("feePayer", "")
        sol_in = sol_out = tok_in = tok_out = 0.0
        for t in tx.get("tokenTransfers") or []:
            m = t.get("mint"); amt = float(t.get("tokenAmount", 0) or 0)
            frm, to = t.get("fromUserAccount"), t.get("toUserAccount")
            if m == WSOL:
                if frm == payer: sol_out += amt
                if to == payer: sol_in += amt
            elif m == mint:
                if to == payer: tok_in += amt
                if frm == payer: tok_out += amt
        for n in tx.get("nativeTransfers") or []:
            a = float(n.get("amount", 0) or 0) / 1e9
            if n.get("fromUserAccount") == payer: sol_out += a
            if n.get("toUserAccount") == payer: sol_in += a
        if tok_in > 0 and sol_out > 0:
            out.append((ts, "buy", sol_out, payer, sol_out / tok_in))
        elif tok_out > 0 and sol_in > 0:
            out.append((ts, "sell", sol_in, payer, sol_in / tok_out))
    out.sort()
    return out


def _price_win(flow, lo, hi):
    near = [f[4] for f in flow if lo <= f[0] <= hi and f[4] > 0]
    return statistics.median(near) if near else None


def samples(flow, W, H, stride_sec, big_thr):
    """(imb_vol, imb_cnt, imb_big, fwd_ret, t) at decorrelated entry points. No look-ahead:
    imbalance + now-price use ONLY data at/before t; forward price is strictly after t.
    imb_big = net SOL flow from CONVICTION trades only (sol >= big_thr) — a smart-money
    proxy, to test whether the edge lives in large/smart flow vs all (retail) flow."""
    if len(flow) < 20:
        return []
    rows = []
    t0, t1 = flow[0][0], flow[-1][0]
    pad = max(30, H // 4)
    t = t0 + W
    while t <= t1 - H:
        win = [f for f in flow if t - W <= f[0] < t]
        if len(win) >= 4:
            buys = [f for f in win if f[1] == "buy"]; sells = [f for f in win if f[1] == "sell"]
            imb_vol = sum(f[2] for f in buys) - sum(f[2] for f in sells)
            imb_cnt = len(buys) - len(sells)
            imb_big = (sum(f[2] for f in buys if f[2] >= big_thr)
                       - sum(f[2] for f in sells if f[2] >= big_thr))
            p_now = _price_win(flow, t - pad, t)           # look-back only
            p_fwd = _price_win(flow, t + H - pad, t + H + pad)  # forward only (H>pad)
            if p_now and p_fwd:
                ret = max(-0.9, min(3.0, p_fwd / p_now - 1))
                rows.append((imb_vol, imb_cnt, imb_big, ret, t))
        t += stride_sec
    return rows


def spearman(xs, ys):
    n = len(xs)
    if n < 8:
        return None
    def rk(v):
        o = sorted(range(len(v)), key=lambda i: v[i]); r = [0]*len(v)
        for p, i in enumerate(o): r[i] = p
        return r
    rx, ry = rk(xs), rk(ys); mx, my = sum(rx)/n, sum(ry)/n
    cov = sum((a-mx)*(b-my) for a, b in zip(rx, ry))
    sx = (sum((a-mx)**2 for a in rx))**.5; sy = (sum((b-my)**2 for b in ry))**.5
    return cov/(sx*sy) if sx and sy else None


def main():
    import os
    if not os.environ.get("HELIUS_API_KEY"):
        print("HELIUS_API_KEY not in env"); sys.exit(1)
    n_pools = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    pages = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    W = int(sys.argv[3]) if len(sys.argv) > 3 else 900
    H = int(sys.argv[4]) if len(sys.argv) > 4 else 900
    stride = max(30, W // 3)

    print(f"[flow] discovering {n_pools} active SOL pools (Dexscreener)...")
    pools = active_solana_pools(n_pools)
    if not pools:
        print("[flow] no pools matched filter"); return
    for p, m, s in pools:
        print(f"  {s:10s} pool={p[:12]} mint={m[:12]}")

    allrows = []
    for pool, mint, sym in pools:
        try:
            flow = pool_flow(pool, mint, pages)
        except Exception as e:
            print(f"  [{sym}] flow error: {e}"); continue
        if not flow:
            print(f"  [{sym}] no swaps"); continue
        span = (flow[-1][0] - flow[0][0]) / 60
        sols = sorted(f[2] for f in flow if f[2] > 0)
        med_sol = sols[len(sols)//2] if sols else 0.0
        big_thr = sols[int(len(sols)*0.9)] if sols else 0.0   # p90 trade = conviction (smart proxy)
        rows = samples(flow, W, H, stride, big_thr)
        nb = sum(1 for f in flow if f[1] == "buy"); ns = len(flow) - nb
        print(f"  [{sym}] swaps={len(flow)} (b{nb}/s{ns}) span={span:.0f}min "
              f"traders={len({f[3] for f in flow})} medSOL={med_sol:.2f} -> {len(rows)} samples")
        allrows += rows

    print(f"\n[flow] total samples: {len(allrows)}")
    if len(allrows) < 20:
        print("[flow] too few samples — raise pages or n_pools"); return

    rets = [r[3] for r in allrows]
    print(f"[flow] forward-return base: median={statistics.median(rets):+.2%}  "
          f"mean={statistics.mean(rets):+.2%}  win={sum(1 for r in rets if r>0)/len(rets):.0%}\n")

    print("=== FLOW IMBALANCE vs FORWARD RETURN (Spearman) ===")
    print(f"  imbalance_vol (ALL, net SOL): rho={spearman([r[0] for r in allrows], rets):+.3f}")
    print(f"  imbalance_cnt (ALL, net #)  : rho={spearman([r[1] for r in allrows], rets):+.3f}")
    print(f"  imbalance_BIG (conviction)  : rho={spearman([r[2] for r in allrows], rets):+.3f}  <- smart-money proxy")

    # temporal stability: split by entry time
    allrows.sort(key=lambda r: r[4])
    k = int(len(allrows) * 0.7)
    tr, te = allrows[:k], allrows[k:]
    def sp(sub, idx):
        return spearman([r[idx] for r in sub], [r[3] for r in sub])
    print(f"\n=== TEMPORAL STABILITY (train {len(tr)} | test {len(te)}) — sign survive regime? ===")
    for nm, idx in (("imbalance_vol", 0), ("imbalance_cnt", 1), ("imbalance_BIG", 2)):
        rt, re = sp(tr, idx), sp(te, idx)
        tag = "STABLE" if (rt and re and rt*re > 0 and abs(re) > 0.05) else "flip/weak"
        rts = rt if rt is None else round(rt, 3); res = re if re is None else round(re, 3)
        print(f"  {nm:14s}: train={rts}  test={res}  -> {tag}")

    # bucket by the smart proxy (conviction flow)
    allrows.sort(key=lambda r: r[2])
    q = len(allrows) // 4
    print(f"\n=== BUCKET (by imbalance_BIG = conviction flow) ===")
    for nm, sub in (("bottom25% (big net-sell)", allrows[:q]), ("top25% (big net-buy)", allrows[3*q:])):
        rs = [r[3] for r in sub]
        if rs:
            print(f"  {nm:26s}: n={len(rs)} fwd-median={statistics.median(rs):+.2%} "
                  f"win={sum(1 for r in rs if r>0)/len(rs):.0%}")


if __name__ == "__main__":
    main()
