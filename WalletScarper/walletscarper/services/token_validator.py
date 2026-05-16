"""Token on-chain validation service.

Validates discovered tokens against on-chain Solana metadata before backfill.
Flags dangerous tokens (mutable supply, active freeze authority, zero decimals).
These flags are stored as quality_flags on the token_profiles / discovery candidates.
"""
from __future__ import annotations

import logging
from typing import Any

from walletscarper.config import settings
from walletscarper.sources.helius_das import HeliusDASSource

log = logging.getLogger(__name__)

# Flags that indicate potential scam / high risk
_HARD_FLAGS = {"mutable_supply", "freeze_authority_active"}


class TokenValidatorService:
    def __init__(self) -> None:
        self.das = HeliusDASSource()

    async def validate(self, token_mint: str) -> dict[str, Any]:
        """Validate a token mint on-chain. Returns:
            {
              "token_mint": str,
              "flags": list[str],          # quality flags
              "is_safe": bool,             # True if no hard flags
              "metadata": dict | None,     # raw DAS metadata
            }
        """
        if not settings.token_validation_enabled or not settings.helius_configured:
            return {"token_mint": token_mint, "flags": [], "is_safe": True, "metadata": None}

        metadata = await self.das.get_token_metadata(token_mint)
        flags = _compute_flags(metadata)
        is_safe = not bool(_HARD_FLAGS & set(flags))

        if flags:
            log.info("token_validator: %s flags=%s", token_mint[:8], flags)

        return {"token_mint": token_mint, "flags": flags, "is_safe": is_safe, "metadata": metadata}

    async def validate_batch(self, token_mints: list[str]) -> dict[str, dict[str, Any]]:
        """Validate multiple tokens. Returns {mint: validation_result}."""
        import asyncio

        results: dict[str, dict[str, Any]] = {}

        async def validate_one(mint: str) -> None:
            results[mint] = await self.validate(mint)

        await asyncio.gather(*[validate_one(m) for m in token_mints])
        return results


def _compute_flags(metadata: dict[str, Any] | None) -> list[str]:
    if not metadata:
        return ["no_onchain_metadata"]
    flags: list[str] = []
    if metadata.get("mint_authority") is not None:
        flags.append("mutable_supply")
    if metadata.get("freeze_authority") is not None:
        flags.append("freeze_authority_active")
    decimals = metadata.get("decimals")
    if decimals is not None and int(decimals) == 0:
        flags.append("zero_decimals")
    supply = metadata.get("supply")
    if supply is not None:
        try:
            if int(supply) > 10**18:
                flags.append("extreme_supply")
        except (ValueError, TypeError):
            pass
    return flags
