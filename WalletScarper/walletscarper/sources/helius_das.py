"""Helius Digital Asset Standard (DAS) API source.

Provides on-chain token metadata: mint authority, freeze authority, supply,
decimals, holder count. Used for token validation before trading.
"""
from __future__ import annotations

import logging
from typing import Any

from walletscarper.config import settings
from walletscarper.http_client import HttpClient

log = logging.getLogger(__name__)


class HeliusDASSource:
    def __init__(self) -> None:
        self.http = HttpClient("helius_das", timeout=15)

    async def get_token_metadata(self, mint_address: str) -> dict[str, Any] | None:
        """Fetch on-chain token metadata via Helius DAS getAsset.

        Returns dict with: mint_authority, freeze_authority, supply, decimals,
        token_program — or None if unavailable / Helius not configured.
        """
        if not settings.helius_configured:
            return None
        url = settings.helius_das_url
        payload = {"jsonrpc": "2.0", "id": 1, "method": "getAsset", "params": {"id": mint_address}}
        try:
            result = await self.http.post_json(url, payload)
            if not isinstance(result, dict):
                return None
            asset = result.get("result")
            if not isinstance(asset, dict):
                return None
            token_info = asset.get("token_info") or {}
            return {
                "mint": mint_address,
                "mint_authority": token_info.get("mint_authority"),
                "freeze_authority": token_info.get("freeze_authority"),
                "supply": token_info.get("supply"),
                "decimals": token_info.get("decimals"),
                "token_program": token_info.get("token_program"),
                "holder_count": (asset.get("ownership") or {}).get("owner_count"),
                "interface": asset.get("interface"),
            }
        except Exception as exc:
            log.debug("helius_das: get_token_metadata failed for %s: %s", mint_address[:8], exc)
            return None

    async def get_token_metadata_batch(self, mint_addresses: list[str]) -> dict[str, dict[str, Any]]:
        """Fetch metadata for multiple mints. Returns {mint: metadata_dict}."""
        import asyncio

        results: dict[str, dict[str, Any]] = {}

        async def fetch_one(mint: str) -> None:
            meta = await self.get_token_metadata(mint)
            if meta:
                results[mint] = meta

        await asyncio.gather(*[fetch_one(m) for m in mint_addresses])
        return results
