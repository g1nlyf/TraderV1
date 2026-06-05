"""
Full-token order-flow extractor — the path to the real (stronger) stable signal.

Cohort net-flow (86 wallets) is regime-STABLE but weak (rho +0.06-0.15) because it's a
tiny sample of a token's true order flow. This pulls the FULL flow (ALL traders) on a
token's pool via Helius, so we can measure the real order-flow imbalance — which should
be a far stronger version of the one signal that survived all rigor.

get_token_flow(pool, mint) -> [(ts, side, sol_amount, trader)] for every swap on the pool.
SECURITY: Helius keys via env only.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore
ROOT = Path(__file__).resolve().parents[2]

from finetune.pipeline.helius_client import get_signatures, parse, WSOL


def _pool_swaps(parsed: list[dict], mint: str) -> list[tuple]:
    """From parsed pool txs, extract (ts, side, sol_amount, trader) for `mint`."""
    out = []
    for tx in parsed:
        ts = tx.get("timestamp") or 0
        payer = tx.get("feePayer", "")
        tt = tx.get("tokenTransfers") or []
        nt = tx.get("nativeTransfers") or []
        sol_in = sol_out = tok_in = tok_out = 0.0
        for t in tt:
            m = t.get("mint"); amt = float(t.get("tokenAmount", 0) or 0)
            frm, to = t.get("fromUserAccount"), t.get("toUserAccount")
            if m == WSOL:
                if frm == payer: sol_out += amt
                if to == payer: sol_in += amt
            elif m == mint:
                if to == payer: tok_in += amt
                if frm == payer: tok_out += amt
        for n in nt:
            a = float(n.get("amount", 0) or 0) / 1e9
            if n.get("fromUserAccount") == payer: sol_out += a
            if n.get("toUserAccount") == payer: sol_in += a
        # buy: payer spent SOL, got token ; sell: payer sent token, got SOL
        if tok_in > 0 and sol_out > 0:
            out.append((ts, "buy", sol_out, payer))
        elif tok_out > 0 and sol_in > 0:
            out.append((ts, "sell", sol_in, payer))
    return out


def get_token_flow(pool: str, mint: str, pages: int = 2) -> list[tuple]:
    sigs = []
    before = None
    for _ in range(pages):
        batch = get_signatures(pool, limit=100, before=before)
        if not batch:
            break
        sigs += [s["signature"] for s in batch]
        before = batch[-1]["signature"]
    parsed = parse(sigs)
    flow = _pool_swaps(parsed, mint)
    flow.sort()
    return flow


if __name__ == "__main__":
    import sqlite3, os, statistics
    if not os.environ.get("HELIUS_API_KEY"):
        print("HELIUS_API_KEY not in env"); sys.exit(1)
    DB = ROOT / "WalletScarper" / "data" / "stage2_foundation.sqlite3"
    con = sqlite3.connect(str(DB))
    # a token with a real pool + recent cohort activity
    row = con.execute("SELECT token_mint, pool_address FROM wallet_token_outcomes "
                      "WHERE pool_address IS NOT NULL AND pool_address NOT LIKE '%fixture%' "
                      "AND length(pool_address)=44 LIMIT 1").fetchone()
    con.close()
    if not row:
        print("no pool"); sys.exit(0)
    mint, pool = row
    print(f"Full-flow test: token={mint[:16]} pool={pool[:16]}")
    flow = get_token_flow(pool, mint, pages=2)
    buys = [f for f in flow if f[1] == "buy"]; sells = [f for f in flow if f[1] == "sell"]
    print(f"  full-token swaps: {len(flow)}  buys={len(buys)} sells={len(sells)}")
    print(f"  distinct traders: {len({f[3] for f in flow})}")
    print(f"  net flow (count): {len(buys)-len(sells)}   net SOL: {sum(f[2] for f in buys)-sum(f[2] for f in sells):+.2f}")
    if flow:
        span_min = (flow[-1][0]-flow[0][0])/60
        print(f"  span: {span_min:.0f} min  -> ~{len(flow)/max(1,span_min):.1f} swaps/min (vs cohort ~0.1/min)")
