from __future__ import annotations

import asyncio
import logging
from typing import Any

from walletscarper.config import settings
from walletscarper.http_client import HttpClient

log = logging.getLogger(__name__)

_WSOL_MINT = "So11111111111111111111111111111111111111112"


class SolanaRpcSource:
    def __init__(self) -> None:
        self.http = HttpClient("solana_rpc", timeout=30)

    async def call(self, method: str, params: list[Any]) -> Any:
        payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
        result = await self.http.post_json(settings.rpc_url, payload)
        if isinstance(result, dict):
            return result.get("result")
        return None

    async def health(self) -> bool:
        result = await self.call("getHealth", [])
        return result == "ok"

    async def get_signatures_for_address(self, address: str, *, limit: int = 50, until: str | None = None) -> list[dict[str, Any]]:
        """Return recent transaction signatures for an address, newest first.

        Each dict has: signature, slot, blockTime, err, memo.
        Stops at `until` signature (exclusive) — useful for incremental polling.
        """
        opts: dict[str, Any] = {"limit": min(limit, 1000)}
        if until:
            opts["until"] = until
        result = await self.call("getSignaturesForAddress", [address, opts])
        if isinstance(result, list):
            return result
        return []

    async def get_transactions_batch(self, signatures: list[str], *, max_concurrent: int = 5) -> list[dict[str, Any] | None]:
        """Fetch multiple transactions in parallel, respecting max_concurrent RPC calls."""
        sem = asyncio.Semaphore(max_concurrent)

        async def fetch_one(sig: str) -> dict[str, Any] | None:
            async with sem:
                return await self.call("getTransaction", [sig, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}])

        return await asyncio.gather(*[fetch_one(s) for s in signatures])

    async def infer_signer_and_token_buy(self, signature: str) -> tuple[str, str, str, str | None]:
        result = await self.call("getTransaction", [signature, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}])
        if not isinstance(result, dict):
            return "", "", "", None
        tx = result.get("transaction") or {}
        message = tx.get("message") or {}
        account_keys = message.get("accountKeys") or []
        signer = ""
        for account in account_keys:
            if isinstance(account, dict) and account.get("signer"):
                signer = str(account.get("pubkey") or "")
                break
        block_time = result.get("blockTime")
        return signer, "", "", str(block_time) if block_time else None

    async def parse_wallet_swap(self, signature: str) -> dict[str, Any] | None:
        """Parse a single transaction into a swap event dict.

        Returns dict with: signature, wallet, token_mint, side, token_amount,
        quote_amount, price_usd, block_time — or None if not a parseable swap.
        """
        result = await self.call("getTransaction", [signature, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}])
        return _parse_swap_from_tx(signature, result)

    async def get_asset(self, mint_address: str) -> dict[str, Any] | None:
        """Helius DAS getAsset — returns token metadata including mint/freeze authority.

        Requires Helius RPC endpoint (helius_das_url). Returns None if unavailable.
        """
        if not settings.helius_das_url:
            return None
        payload = {"jsonrpc": "2.0", "id": 1, "method": "getAsset", "params": {"id": mint_address}}
        try:
            result = await self.http.post_json(settings.helius_das_url, payload)
            if isinstance(result, dict):
                return result.get("result")
        except Exception as exc:
            log.debug("get_asset failed for %s: %s", mint_address[:8], exc)
        return None


def _parse_swap_from_tx(signature: str, result: Any) -> dict[str, Any] | None:
    """Extract swap fields from a jsonParsed getTransaction result."""
    if not isinstance(result, dict):
        return None

    tx = result.get("transaction") or {}
    message = tx.get("message") or {}
    account_keys = message.get("accountKeys") or []
    meta = result.get("meta") or {}
    block_time = result.get("blockTime")

    # Signer = fee payer (first signer in accountKeys)
    wallet = ""
    for acc in account_keys:
        if isinstance(acc, dict) and acc.get("signer"):
            wallet = str(acc.get("pubkey") or "")
            break
    if not wallet:
        return None

    # Build index: accountIndex -> pubkey
    idx_to_pubkey: dict[int, str] = {}
    for i, acc in enumerate(account_keys):
        if isinstance(acc, dict):
            idx_to_pubkey[i] = str(acc.get("pubkey") or "")
        elif isinstance(acc, str):
            idx_to_pubkey[i] = acc

    pre_token = {b.get("accountIndex"): b for b in (meta.get("preTokenBalances") or [])}
    post_token = {b.get("accountIndex"): b for b in (meta.get("postTokenBalances") or [])}

    # Find non-WSOL token with largest absolute balance change owned by wallet
    best_mint: str | None = None
    best_delta = 0.0
    all_indices = set(list(pre_token.keys()) + list(post_token.keys()))

    for idx in all_indices:
        pre = pre_token.get(idx) or {}
        post = post_token.get(idx) or {}
        owner = (post or pre).get("owner", "")
        if owner != wallet:
            continue
        mint = (post or pre).get("mint", "")
        if not mint or mint == _WSOL_MINT:
            continue
        pre_amt = float(((pre.get("uiTokenAmount") or {}).get("uiAmount")) or 0)
        post_amt = float(((post.get("uiTokenAmount") or {}).get("uiAmount")) or 0)
        delta = post_amt - pre_amt
        if abs(delta) > abs(best_delta):
            best_delta = delta
            best_mint = mint

    if not best_mint or best_delta == 0:
        return None

    side = "buy" if best_delta > 0 else "sell"

    # Estimate SOL cost from wallet's native balance change
    pre_sol_balances = meta.get("preBalances") or []
    post_sol_balances = meta.get("postBalances") or []
    wallet_idx = next((i for i, pk in idx_to_pubkey.items() if pk == wallet), None)

    sol_delta_lamports = 0
    if wallet_idx is not None and wallet_idx < len(pre_sol_balances) and wallet_idx < len(post_sol_balances):
        sol_delta_lamports = post_sol_balances[wallet_idx] - pre_sol_balances[wallet_idx]

    sol_amount = abs(sol_delta_lamports) / 1e9
    quote_amount = sol_amount * settings.sol_usd_estimate
    token_amount = abs(best_delta)
    price_usd = (quote_amount / token_amount) if token_amount > 0 else 0.0

    return {
        "signature": signature,
        "wallet": wallet,
        "token_mint": best_mint,
        "side": side,
        "token_amount": token_amount,
        "quote_amount": quote_amount,
        "price_usd": price_usd,
        "block_time": str(block_time) if block_time else None,
    }
