from __future__ import annotations

import json
from typing import Any

from walletscarper.config import settings
from walletscarper.http_client import HttpClient


class OpenRouterSource:
    def __init__(self) -> None:
        self.http = HttpClient("openrouter", timeout=45)

    async def explain_wallet(self, facts: dict[str, Any]) -> dict[str, Any] | None:
        if not settings.openrouter_configured:
            return None
        headers = {
            "Authorization": f"Bearer {settings.openrouter_api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "http://localhost",
            "X-Title": "WalletScarper",
        }
        prompt = (
            "You are a Solana wallet analyst. Use only the supplied metrics. "
            "Do not make trading decisions. Return strict JSON with summary, flags, recommendation, confidence."
        )
        body = {
            "model": settings.openrouter_model,
            "messages": [
                {"role": "system", "content": prompt},
                {"role": "user", "content": json.dumps(facts, ensure_ascii=False, default=str)},
            ],
            "temperature": 0.2,
            "max_tokens": 500,
            "response_format": {"type": "json_object"},
        }
        data = await self.http.post_json("https://openrouter.ai/api/v1/chat/completions", body, headers=headers)
        try:
            content = data["choices"][0]["message"]["content"]
            return json.loads(content)
        except Exception:
            return None
