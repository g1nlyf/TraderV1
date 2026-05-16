from __future__ import annotations

from typing import Any

from walletscarper.config import settings
from walletscarper.http_client import HttpClient


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
