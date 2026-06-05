"""
Helius client — reconstruct any wallet's on-chain trade tape (ground truth).

SECURITY: no keys in this file. Reads HELIUS_API_KEY / HELIUS_RPC_URL from the
environment only. Never write keys to a repo file.

Capabilities:
  - get_signatures(wallet)  : RPC getSignaturesForAddress (paginated tx history)
  - parse(signatures)       : Helius Enhanced Transactions API (decoded swaps)
  - wallet_swaps(wallet)    : -> [SwapEvent] (token, side, sol, price, ts) per wallet

This is the foundation for: forward-validated wallet scoring, cluster detection,
and copy-trade backtests — all from real chain data, no GeckoTerminal candles.
"""
from __future__ import annotations

import json
import os
import time
import urllib.request
import urllib.error
from dataclasses import dataclass

RPC_URL = os.environ.get("HELIUS_RPC_URL", "")
API_KEY = os.environ.get("HELIUS_API_KEY", "")
PARSE_URL = f"https://api-mainnet.helius-rpc.com/v0/transactions/?api-key={API_KEY}"

WSOL = "So11111111111111111111111111111111111111112"


@dataclass
class SwapEvent:
    ts: int
    signature: str
    wallet: str
    token_mint: str
    side: str            # buy (SOL->token) | sell (token->SOL)
    sol_amount: float    # SOL in (buy) or out (sell)
    token_amount: float
    price_sol: float     # sol per token


def _post(url: str, body: dict, retries: int = 3) -> dict | list:
    data = json.dumps(body).encode()
    for i in range(retries):
        try:
            req = urllib.request.Request(url, data=data,
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=40) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(2 * (i + 1)); continue
            raise
    raise RuntimeError(f"helius post failed: {url}")


def get_signatures(wallet: str, limit: int = 100, before: str | None = None) -> list[dict]:
    params: dict = {"limit": limit}
    if before:
        params["before"] = before
    body = {"jsonrpc": "2.0", "id": "1", "method": "getSignaturesForAddress",
            "params": [wallet, params]}
    res = _post(RPC_URL, body)
    return res.get("result", []) if isinstance(res, dict) else []


def parse(signatures: list[str]) -> list[dict]:
    """Enhanced parse, max 100 sigs/call."""
    out = []
    for i in range(0, len(signatures), 100):
        chunk = signatures[i:i + 100]
        res = _post(PARSE_URL, {"transactions": chunk})
        if isinstance(res, list):
            out.extend(res)
        time.sleep(0.3)
    return out


def _extract_swap(tx: dict, wallet: str) -> SwapEvent | None:
    """Decode a swap from tokenTransfers + nativeTransfers (events.swap is empty
    for most DEX programs). Handles wrapped WSOL and native SOL legs."""
    ts = tx.get("timestamp") or 0
    sig = tx.get("signature", "")
    tt = tx.get("tokenTransfers") or []
    nt = tx.get("nativeTransfers") or []

    sol_sent = sol_recv = 0.0
    tok_sent: dict[str, float] = {}
    tok_recv: dict[str, float] = {}

    for t in tt:
        mint = t.get("mint", "")
        amt = float(t.get("tokenAmount", 0) or 0)
        frm = t.get("fromUserAccount"); to = t.get("toUserAccount")
        if mint == WSOL:
            if frm == wallet: sol_sent += amt
            if to == wallet: sol_recv += amt
        else:
            if frm == wallet and amt > 0: tok_sent[mint] = tok_sent.get(mint, 0) + amt
            if to == wallet and amt > 0: tok_recv[mint] = tok_recv.get(mint, 0) + amt
    for n in nt:
        a = float(n.get("amount", 0) or 0) / 1e9
        if n.get("fromUserAccount") == wallet: sol_sent += a
        if n.get("toUserAccount") == wallet: sol_recv += a

    # BUY: net SOL out, token in
    if sol_sent > sol_recv and tok_recv:
        mint, ta = max(tok_recv.items(), key=lambda x: x[1])
        sol = sol_sent - sol_recv
        if ta > 0 and sol > 0:
            return SwapEvent(ts, sig, wallet, mint, "buy", sol, ta, sol / ta)
    # SELL: net SOL in, token out
    if sol_recv > sol_sent and tok_sent:
        mint, ta = max(tok_sent.items(), key=lambda x: x[1])
        sol = sol_recv - sol_sent
        if ta > 0 and sol > 0:
            return SwapEvent(ts, sig, wallet, mint, "sell", sol, ta, sol / ta)
    return None


def wallet_swaps(wallet: str, pages: int = 1, per_page: int = 100) -> list[SwapEvent]:
    sigs_meta: list[dict] = []
    before = None
    for _ in range(pages):
        batch = get_signatures(wallet, limit=per_page, before=before)
        if not batch:
            break
        sigs_meta.extend(batch)
        before = batch[-1]["signature"]
    sigs = [s["signature"] for s in sigs_meta]
    parsed = parse(sigs)
    swaps = []
    for tx in parsed:
        s = _extract_swap(tx, wallet)
        if s:
            swaps.append(s)
    return swaps


if __name__ == "__main__":
    import sqlite3, sys, pathlib
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore
    if not API_KEY or not RPC_URL:
        print("ERROR: HELIUS_API_KEY / HELIUS_RPC_URL not in env"); sys.exit(1)
    DB = pathlib.Path(__file__).resolve().parents[2] / "WalletScarper" / "data" / "stage2_foundation.sqlite3"
    con = sqlite3.connect(str(DB))
    w = con.execute("SELECT wallet FROM wallet_token_outcomes "
                    "WHERE length(wallet)=44 AND wallet NOT LIKE '%fixture%' "
                    "AND wallet NOT LIKE 'acceptance%' LIMIT 1").fetchone()[0]
    con.close()
    print(f"Testing Helius on real wallet: {w}")
    sigs = get_signatures(w, limit=15)
    print(f"  signatures fetched: {len(sigs)}")
    parsed = parse([s["signature"] for s in sigs])
    from collections import Counter
    print(f"  parsed tx types: {dict(Counter(t.get('type') for t in parsed))}")
    swaps = [s for s in (_extract_swap(t, w) for t in parsed) if s]
    print(f"  swaps decoded: {len(swaps)}")
    for s in swaps[:6]:
        import datetime
        ts = datetime.datetime.utcfromtimestamp(s.ts).strftime("%Y-%m-%d %H:%M")
        print(f"    [{ts}] {s.side:4s} {s.token_amount:,.0f} {s.token_mint[:12]} for {s.sol_amount:.3f} SOL @ {s.price_sol:.2e}")
