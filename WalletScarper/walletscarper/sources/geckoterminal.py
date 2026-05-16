from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from walletscarper.http_client import HttpClient
from walletscarper.models import TokenCandidate


class GeckoTerminalSource:
    def __init__(self) -> None:
        self.http = HttpClient("geckoterminal")

    async def discover_new_and_trending(self, pages: int = 3) -> list[TokenCandidate]:
        candidates: list[TokenCandidate] = []
        for page in range(1, pages + 1):
            payload = await self.http.get_json(
                "https://api.geckoterminal.com/api/v2/networks/solana/new_pools",
                params={"page": page},
                ttl_seconds=90,
            )
            for item in (payload or {}).get("data", []) or []:
                c = self._pool_to_candidate(item)
                if c:
                    candidates.append(c)
        return candidates

    async def pool_trades(self, pool_address: str, limit: int = 100) -> list[dict[str, Any]]:
        payload = await self.http.get_json(
            f"https://api.geckoterminal.com/api/v2/networks/solana/pools/{pool_address}/trades",
            params={"trade_volume_in_usd_greater_than": 0},
            ttl_seconds=30,
        )
        return list((payload or {}).get("data", []) or [])[:limit]

    def _pool_to_candidate(self, item: dict[str, Any]) -> TokenCandidate | None:
        attrs = item.get("attributes") or {}
        relationships = item.get("relationships") or {}
        base = ((relationships.get("base_token") or {}).get("data") or {}).get("id") or ""
        pool = str(attrs.get("address") or item.get("id") or "").split("_")[-1]
        mint = str(base).split("_")[-1]
        if not mint or not pool:
            return None
        created_at = attrs.get("pool_created_at")
        age = None
        if created_at:
            try:
                created = datetime.fromisoformat(str(created_at).replace("Z", "+00:00"))
                age = (datetime.now(timezone.utc) - created).total_seconds() / 60
            except Exception:
                age = None
        tx = attrs.get("transactions") or {}
        h1 = tx.get("h1") or {}
        volume = attrs.get("volume_usd") or {}
        return TokenCandidate(
            token_mint=mint,
            pool_address=pool,
            symbol=str(attrs.get("name") or ""),
            name=str(attrs.get("name") or ""),
            dex_id=str(attrs.get("dex") or "geckoterminal"),
            pair_created_at=str(created_at) if created_at else None,
            pair_age_minutes=age,
            price_usd=self._float(attrs.get("base_token_price_usd")),
            liquidity_usd=self._float(attrs.get("reserve_in_usd")),
            volume_5m=self._float(volume.get("m5")),
            volume_1h=self._float(volume.get("h1")),
            volume_6h=self._float(volume.get("h6")),
            volume_24h=self._float(volume.get("h24")),
            txns_1h=int(h1.get("buys") or 0) + int(h1.get("sells") or 0),
            buys_1h=int(h1.get("buys") or 0),
            sells_1h=int(h1.get("sells") or 0),
            fdv=self._float(attrs.get("fdv_usd")),
            market_cap=self._float(attrs.get("market_cap_usd")),
            source="geckoterminal",
            confidence="medium",
            raw=item,
        )

    def _float(self, value: Any) -> float:
        try:
            return float(value or 0)
        except Exception:
            return 0.0
