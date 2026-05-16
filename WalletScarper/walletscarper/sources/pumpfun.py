"""pump.fun token discovery source.

Fetches recently active and newly launched Solana memecoins from pump.fun's
frontend API. This is the primary launchpad for viral Solana memecoins, so
discovering tokens here early gives a meaningful timing edge.

Note: pump.fun API is unofficial/undocumented — endpoint may change.
"""
from __future__ import annotations

import logging
from typing import Any

from walletscarper.http_client import HttpClient
from walletscarper.models import TokenCandidate

log = logging.getLogger(__name__)

_PUMPFUN_API = "https://frontend-api.pump.fun"
_WSOL_MINT = "So11111111111111111111111111111111111111112"


class PumpFunSource:
    def __init__(self) -> None:
        self.http = HttpClient("pumpfun", timeout=15)

    async def discover_trending(self, limit: int = 50) -> list[TokenCandidate]:
        """Fetch recently traded tokens from pump.fun sorted by last trade.

        Returns TokenCandidate list. Tokens with usd_market_cap = 0 or
        without pool/mint data are skipped.
        """
        url = f"{_PUMPFUN_API}/coins"
        params = f"?offset=0&limit={limit}&sort=last_trade_timestamp&order=DESC&includeNsfw=false"
        try:
            data = await self.http.get_json(url + params)
        except Exception as exc:
            log.warning("pumpfun.discover_trending: request failed: %s", exc)
            return []

        if not isinstance(data, list):
            log.debug("pumpfun.discover_trending: unexpected response type %s", type(data))
            return []

        candidates: list[TokenCandidate] = []
        for item in data:
            candidate = _to_candidate(item)
            if candidate:
                candidates.append(candidate)

        log.info("pumpfun: discovered %d candidates", len(candidates))
        return candidates

    async def discover_new(self, limit: int = 50) -> list[TokenCandidate]:
        """Fetch newest token launches from pump.fun."""
        url = f"{_PUMPFUN_API}/coins"
        params = f"?offset=0&limit={limit}&sort=created_timestamp&order=DESC&includeNsfw=false"
        try:
            data = await self.http.get_json(url + params)
        except Exception as exc:
            log.warning("pumpfun.discover_new: request failed: %s", exc)
            return []

        if not isinstance(data, list):
            return []

        candidates: list[TokenCandidate] = []
        for item in data:
            candidate = _to_candidate(item)
            if candidate:
                candidates.append(candidate)

        log.info("pumpfun: new tokens discovered %d", len(candidates))
        return candidates


def _to_candidate(item: dict[str, Any]) -> TokenCandidate | None:
    mint = str(item.get("mint") or "")
    if not mint or mint == _WSOL_MINT:
        return None

    symbol = str(item.get("symbol") or "")
    name = str(item.get("name") or "")
    usd_market_cap = _float(item.get("usd_market_cap"))
    # pump.fun uses "bonding_curve" as pool address until graduation to a DEX
    pool_address = str(item.get("bonding_curve") or item.get("associated_bonding_curve") or "")
    if not pool_address:
        return None

    # Estimate liquidity from market cap (pump.fun pools are ~5-15% of mcap)
    liquidity_usd = usd_market_cap * 0.08 if usd_market_cap else 0.0

    created_timestamp = item.get("created_timestamp")
    import time

    pair_age_minutes = None
    if created_timestamp:
        try:
            age_seconds = time.time() - float(created_timestamp) / 1000
            pair_age_minutes = age_seconds / 60
        except Exception:
            pass

    return TokenCandidate(
        token_mint=mint,
        pool_address=pool_address,
        symbol=symbol,
        name=name,
        dex_id="pump_fun",
        price_usd=_float(item.get("sol_price") or item.get("last_trade_price")),
        liquidity_usd=liquidity_usd,
        market_cap=usd_market_cap,
        fdv=usd_market_cap,
        volume_1h=_float(item.get("volume") or item.get("volume_24h")),
        txns_1h=int(item.get("total_transactions") or 0),
        pair_age_minutes=pair_age_minutes,
        source="pumpfun",
    )


def _float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0
