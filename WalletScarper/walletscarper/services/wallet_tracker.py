from __future__ import annotations

from walletscarper.config import settings
from walletscarper.db import db
from walletscarper.models import utc_now
from walletscarper.services.scoring import ScoringService
from walletscarper.services.telegram import TelegramService


class WalletTracker:
    def __init__(self) -> None:
        self.scoring = ScoringService()
        self.telegram = TelegramService()

    async def run_daily(self, notify: bool = True) -> None:
        await self.scoring.score_recent_swaps()
        await db.execute(
            """
            UPDATE tracked_wallets
            SET status='stale', updated_at=?, stale_reason='score_below_threshold'
            WHERE status IN ('active','probation') AND COALESCE(copyability_score, 0) < ?
            """,
            (utc_now(), settings.stale_tracked_wallet_score),
        )
        if notify:
            await self.telegram.send(await self.telegram.render_tracked_wallets(limit=20), notification_type="daily_wallet_tracker")
