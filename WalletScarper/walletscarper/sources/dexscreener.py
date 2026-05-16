from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from walletscarper.config import settings
from walletscarper.http_client import HttpClient
from walletscarper.models import TokenCandidate


class DexScreenerSource:
    def __init__(self) -> None:
        self.http = HttpClient("dexscreener")

    async def discover(self) -> list[TokenCandidate]:
        profiles = await self.http.get_json("https://api.dexscreener.com/token-profiles/latest/v1", ttl_seconds=60) or []
        boosts = await self.http.get_json("https://api.dexscreener.com/token-boosts/latest/v1", ttl_seconds=60) or []
        addresses = []
        for item in list(profiles)[: settings.max_discovery_profiles] + list(boosts)[: settings.max_discovery_profiles]:
            if str(item.get("chainId", "")).lower() == "solana" and item.get("tokenAddress"):
                addresses.append(str(item["tokenAddress"]))
        candidates: list[TokenCandidate] = []
        for chunk in self._chunks(list(dict.fromkeys(addresses)), 30):
            payload = await self.http.get_json(f"https://api.dexscreener.com/latest/dex/tokens/{','.join(chunk)}", ttl_seconds=45)
            for pair in (payload or {}).get("pairs", []) or []:
                if str(pair.get("chainId", "")).lower() != "solana":
                    continue
                candidate = self._pair_to_candidate(pair)
                if candidate:
                    candidates.append(candidate)
        return candidates

    def _pair_to_candidate(self, pair: dict[str, Any]) -> TokenCandidate | None:
        base = pair.get("baseToken") or {}
        mint = str(base.get("address") or "")
        pool = str(pair.get("pairAddress") or "")
        if not mint or not pool:
            return None
        created_ms = pair.get("pairCreatedAt")
        age = None
        created_at = None
        if created_ms:
            created = datetime.fromtimestamp(float(created_ms) / 1000, tz=timezone.utc)
            created_at = created.isoformat()
            age = (datetime.now(timezone.utc) - created).total_seconds() / 60
        txns = pair.get("txns") or {}
        buys_1h = int((txns.get("h1") or {}).get("buys") or 0)
        sells_1h = int((txns.get("h1") or {}).get("sells") or 0)
        volume = pair.get("volume") or {}
        liquidity = pair.get("liquidity") or {}
        return TokenCandidate(
            token_mint=mint,
            pool_address=pool,
            symbol=str(base.get("symbol") or ""),
            name=str(base.get("name") or ""),
            dex_id=str(pair.get("dexId") or ""),
            quote_mint=str((pair.get("quoteToken") or {}).get("address") or ""),
            pair_created_at=created_at,
            pair_age_minutes=age,
            price_usd=self._float(pair.get("priceUsd")),
            liquidity_usd=self._float(liquidity.get("usd")),
            volume_5m=self._float(volume.get("m5")),
            volume_1h=self._float(volume.get("h1")),
            volume_6h=self._float(volume.get("h6")),
            volume_24h=self._float(volume.get("h24")),
            txns_5m=int((txns.get("m5") or {}).get("buys") or 0) + int((txns.get("m5") or {}).get("sells") or 0),
            txns_1h=buys_1h + sells_1h,
            buys_1h=buys_1h,
            sells_1h=sells_1h,
            fdv=self._float(pair.get("fdv")),
            market_cap=self._float(pair.get("marketCap")),
            source="dexscreener",
            confidence="medium",
            raw=pair,
        )

    def _chunks(self, values: list[str], size: int) -> list[list[str]]:
        return [values[i : i + size] for i in range(0, len(values), size)]

    def _float(self, value: Any) -> float:
        try:
            return float(value or 0)
        except Exception:
            return 0.0
