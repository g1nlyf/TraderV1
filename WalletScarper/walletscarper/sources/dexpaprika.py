from __future__ import annotations

from typing import Any

from walletscarper.http_client import HttpClient


class DexPaprikaSource:
    def __init__(self) -> None:
        self.http = HttpClient("dexpaprika")

    async def pool_transactions(self, pool_address: str, limit: int = 100) -> list[dict[str, Any]]:
        variants = [
            f"https://api.dexpaprika.com/networks/solana/pools/{pool_address}/transactions",
            f"https://api.dexpaprika.com/networks/solana/pools/{pool_address}/swaps",
        ]
        for url in variants:
            payload = await self.http.get_json(url, params={"limit": limit}, ttl_seconds=30)
            if isinstance(payload, list):
                return payload[:limit]
            if isinstance(payload, dict):
                for key in ("transactions", "data", "swaps"):
                    if isinstance(payload.get(key), list):
                        return payload[key][:limit]
        return []
