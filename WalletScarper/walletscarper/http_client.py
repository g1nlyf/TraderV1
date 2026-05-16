from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from walletscarper.config import settings
from walletscarper.db import db
from walletscarper.models import utc_now

log = logging.getLogger(__name__)


class HttpClient:
    def __init__(self, source: str, timeout: float = 25.0):
        self.source = source
        self.timeout = timeout

    async def get_json(self, url: str, params: dict[str, Any] | None = None, ttl_seconds: int = 30) -> Any:
        cache_key = self._cache_key("GET", url, params)
        cached = await self._read_cache(cache_key)
        if cached is not None:
            return cached
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(url, params=params)
            if resp.status_code == 429:
                await self._mark("cooldown", resp.text[:300])
                return None
            resp.raise_for_status()
            payload = resp.json()
            await self._write_cache(cache_key, resp.status_code, payload, ttl_seconds)
            await self._mark("healthy", None)
            return payload
        except Exception as exc:
            await self._mark("degraded", self._redact(str(exc)))
            log.warning("source %s error: %s", self.source, self._redact(str(exc)))
            return None

    async def post_json(self, url: str, payload: dict[str, Any], headers: dict[str, str] | None = None) -> Any:
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(url, json=payload, headers=headers)
            if resp.status_code == 429:
                await self._mark("cooldown", resp.text[:300])
                return None
            resp.raise_for_status()
            await self._mark("healthy", None)
            return resp.json()
        except Exception as exc:
            await self._mark("degraded", self._redact(str(exc)))
            log.warning("source %s error: %s", self.source, self._redact(str(exc)))
            return None

    def _cache_key(self, method: str, url: str, params: dict[str, Any] | None) -> str:
        raw = json.dumps({"method": method, "url": url, "params": params or {}}, sort_keys=True)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    async def _read_cache(self, cache_key: str) -> Any | None:
        row = await db.fetchone("SELECT payload, expires_at FROM api_cache WHERE cache_key=?", (cache_key,))
        if not row:
            return None
        if datetime.fromisoformat(row["expires_at"]) < datetime.now(timezone.utc):
            return None
        try:
            return json.loads(row["payload"])
        except Exception:
            return None

    async def _write_cache(self, cache_key: str, status_code: int, payload: Any, ttl_seconds: int) -> None:
        expires = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
        await db.execute(
            """
            INSERT OR REPLACE INTO api_cache(cache_key, source, created_at, expires_at, status_code, payload)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (cache_key, self.source, utc_now(), expires.isoformat(), status_code, json.dumps(payload, ensure_ascii=False, default=str)),
        )

    async def _mark(self, status: str, error: str | None) -> None:
        await db.execute(
            """
            INSERT INTO source_health(source, status, updated_at, last_success_at, last_error_at, last_error_message, confidence)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source) DO UPDATE SET status=excluded.status, updated_at=excluded.updated_at,
              last_success_at=COALESCE(excluded.last_success_at, source_health.last_success_at),
              last_error_at=excluded.last_error_at, last_error_message=excluded.last_error_message,
              confidence=excluded.confidence
            """,
            (self.source, status, utc_now(), utc_now() if status == "healthy" else None, utc_now() if error else None, error, "medium" if status == "healthy" else "low"),
        )

    def _redact(self, value: str) -> str:
        for secret in (settings.telegram_bot_token, settings.openrouter_api_key, settings.bitquery_api_token, settings.helius_api_key):
            if secret:
                value = value.replace(secret, "<redacted>")
        return value
