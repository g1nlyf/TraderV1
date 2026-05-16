from __future__ import annotations

import asyncio
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from walletscarper.config import settings
from walletscarper.db import db
from walletscarper.models import utc_now
from walletscarper.services.trade_store import RawTrade, TradeStore

log = logging.getLogger(__name__)

PUMP_PROGRAM = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
CPMM_PROGRAM = "CPMMoo8L3F4NbTegBCKVNunggL7H1ZpdTHKxQB5qKP1C"
AMM_V4_PROGRAM = "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8"
CLMM_PROGRAM = "CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK"
WHIRLPOOL_PROGRAM = "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc"
QUOTE_MINTS = {
    "",
    "11111111111111111111111111111111",
    "So11111111111111111111111111111111111111112",
    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
    "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",
}


class BitqueryCoreCastSource:
    def __init__(self) -> None:
        self.trade_store = TradeStore()
        self._stream_lock = asyncio.Lock()

    async def check_graphql_access(self) -> tuple[bool, str]:
        if not settings.bitquery_api_token:
            return False, "missing token"
        import httpx

        headers = {"Authorization": f"Bearer {settings.bitquery_api_token}"}
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                resp = await client.post(settings.bitquery_graphql_url, json={"query": "{ __typename }"}, headers=headers)
            if resp.status_code == 200:
                return True, "ok"
            return False, f"{resp.status_code} {resp.text[:200]}"
        except Exception as exc:
            return False, str(exc)

    async def stream_dex_trades(self, seconds: int = 60, program_addresses: list[str] | None = None) -> int:
        if self._stream_lock.locked():
            log.info("Bitquery CoreCast stream already running; skipping overlapping tick")
            return 0
        async with self._stream_lock:
            return await self._stream_dex_trades_locked(seconds=seconds, program_addresses=program_addresses)

    async def _stream_dex_trades_locked(self, seconds: int = 60, program_addresses: list[str] | None = None) -> int:
        if not settings.bitquery_configured:
            await self._mark("disabled", "missing or disabled Bitquery token")
            return 0
        try:
            import grpc

            corecast_pb2_grpc, request_pb2 = self._imports()
        except Exception as exc:
            await self._mark("degraded", f"CoreCast imports failed: {exc}")
            return 0
        addresses = program_addresses or [PUMP_PROGRAM, CPMM_PROGRAM, AMM_V4_PROGRAM, CLMM_PROGRAM, WHIRLPOOL_PROGRAM]
        request = request_pb2.SubscribeTradesRequest(program=request_pb2.AddressFilter(addresses=addresses))
        metadata = [("authorization", settings.bitquery_api_token)]
        run_id = f"bitquery-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
        await self._start_run(run_id)
        try:
            trades = await asyncio.to_thread(self._collect_stream, grpc, corecast_pb2_grpc, request, metadata, seconds, run_id)
            count = await self.trade_store.store_many(trades)
            await self._finish_run(run_id, "ok", count)
            await self._mark("healthy", None)
            return count
        except grpc.RpcError as exc:
            message = f"{exc.code().name}: {exc.details()}"
            await self._finish_run(run_id, "failed", 0, message)
            await self._mark("degraded", message)
            return 0

    def _collect_stream(self, grpc: Any, corecast_pb2_grpc: Any, request: Any, metadata: list[tuple[str, str]], seconds: int, run_id: str) -> list[RawTrade]:
        deadline = datetime.now(timezone.utc).timestamp() + seconds
        trades: list[RawTrade] = []
        with grpc.secure_channel(settings.bitquery_grpc_address, grpc.ssl_channel_credentials()) as channel:
            stub = corecast_pb2_grpc.CoreCastStub(channel)
            for message in stub.DexTrades(request, metadata=metadata, timeout=seconds + 10):
                trade = self._message_to_trade(message, run_id)
                if trade:
                    trades.append(trade)
                if datetime.now(timezone.utc).timestamp() >= deadline:
                    break
        return trades

    def _message_to_trade(self, message: Any, run_id: str) -> RawTrade | None:
        trade = getattr(message, "Trade", None)
        tx = getattr(message, "Transaction", None)
        block = getattr(message, "Block", None)
        if not trade or not tx:
            return None
        signature = self._bytes_to_addr(getattr(tx, "Signature", b""))
        buy = getattr(trade, "Buy", None)
        sell = getattr(trade, "Sell", None)
        market = getattr(trade, "Market", None)
        dex = getattr(trade, "Dex", None)
        buy_mint = self._currency_mint(getattr(buy, "Currency", None))
        sell_mint = self._currency_mint(getattr(sell, "Currency", None))
        token_mint = self._preferred_token_mint(buy_mint, sell_mint)
        if not signature or not token_mint:
            return None
        wallet = self._side_owner(buy) or self._side_owner(sell) or self._bytes_to_addr(getattr(getattr(tx, "Header", None), "FeePayer", b""))
        side = "buy" if buy_mint == token_mint else "sell"
        token_side = buy if side == "buy" else sell
        quote_side = sell if side == "buy" else buy
        quote_mint = sell_mint if side == "buy" else buy_mint
        slot = int(getattr(block, "Slot", 0) or 0)
        return RawTrade(
            signature=signature,
            wallet=wallet,
            token_mint=token_mint,
            pool_address=self._bytes_to_addr(getattr(market, "MarketAddress", b"")),
            dex_id=str(getattr(dex, "ProtocolName", "") or getattr(dex, "ProtocolFamily", "") or "corecast"),
            side=side,
            token_amount=self._side_amount(token_side),
            quote_amount=self._quote_amount_usd(quote_side, quote_mint),
            block_time=utc_now(),
            slot=slot,
            source="bitquery_corecast",
            confidence="medium",
            ingestion_run_id=run_id,
            raw={"signature": signature, "slot": slot, "source": "bitquery_corecast", "quote_mint": quote_mint},
        )

    def _imports(self) -> tuple[Any, Any]:
        candidate = Path(sys.prefix) / "Lib" / "site-packages" / "bitquery_corecast_proto"
        if candidate.exists() and str(candidate) not in sys.path:
            sys.path.append(str(candidate))
        import corecast_pb2_grpc  # type: ignore
        import request_pb2  # type: ignore

        return corecast_pb2_grpc, request_pb2

    def _currency_mint(self, currency: Any) -> str:
        if not currency:
            return ""
        return self._bytes_to_addr(getattr(currency, "MintAddress", b"")) or str(getattr(currency, "Symbol", "") or "")

    def _side_amount(self, side: Any) -> float:
        amount = float(getattr(side, "Amount", 0) or 0)
        currency = getattr(side, "Currency", None)
        decimals = int(getattr(currency, "Decimals", 0) or 0) if currency else 0
        return amount / (10**decimals) if decimals > 0 else amount

    def _quote_amount_usd(self, side: Any, quote_mint: str) -> float:
        amount = self._side_amount(side)
        if quote_mint in {"11111111111111111111111111111111", "So11111111111111111111111111111111111111112"}:
            return amount * settings.sol_usd_estimate
        return amount

    def _preferred_token_mint(self, buy_mint: str, sell_mint: str) -> str:
        if buy_mint not in QUOTE_MINTS:
            return buy_mint
        if sell_mint not in QUOTE_MINTS:
            return sell_mint
        return ""

    def _side_owner(self, side: Any) -> str:
        account = getattr(side, "Account", None)
        token = getattr(account, "Token", None)
        return self._bytes_to_addr(getattr(token, "Owner", b"")) or self._bytes_to_addr(getattr(account, "Address", b""))

    def _bytes_to_addr(self, value: Any) -> str:
        if isinstance(value, bytes):
            try:
                import base58

                return base58.b58encode(value).decode("ascii")
            except Exception:
                return value.hex()
        return str(value or "")

    async def _mark(self, status: str, error: str | None) -> None:
        await db.execute(
            """
            INSERT INTO source_health(source, status, updated_at, last_success_at, last_error_at, last_error_message, confidence)
            VALUES ('bitquery_corecast', ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source) DO UPDATE SET status=excluded.status, updated_at=excluded.updated_at,
              last_success_at=COALESCE(excluded.last_success_at, source_health.last_success_at),
              last_error_at=excluded.last_error_at, last_error_message=excluded.last_error_message,
              confidence=excluded.confidence
            """,
            (status, utc_now(), utc_now() if status == "healthy" else None, utc_now() if error else None, error, "medium" if status == "healthy" else "low"),
        )

    async def _start_run(self, run_id: str) -> None:
        await db.execute(
            "INSERT OR REPLACE INTO ingestion_runs(id, source, mode, started_at, status) VALUES (?, 'bitquery_corecast', 'stream', ?, 'running')",
            (run_id, utc_now()),
        )

    async def _finish_run(self, run_id: str, status: str, count: int, error: str | None = None) -> None:
        stats = await db.fetchone(
            "SELECT COUNT(DISTINCT token_mint) AS tokens_seen, COUNT(DISTINCT wallet) AS wallets_seen FROM raw_trades WHERE ingestion_run_id=?",
            (run_id,),
        )
        await db.execute(
            """
            UPDATE ingestion_runs
            SET finished_at=?, status=?, trades_ingested=?, tokens_seen=?, wallets_seen=?, error_message=?
            WHERE id=?
            """,
            (utc_now(), status, count, (stats or {}).get("tokens_seen", 0), (stats or {}).get("wallets_seen", 0), error, run_id),
        )
