from __future__ import annotations

import json
import logging
from dataclasses import asdict

from walletscarper.config import settings
from walletscarper.db import db
from walletscarper.models import utc_now
from walletscarper.services.backfill import BackfillService
from walletscarper.services.discovery import DiscoveryService
from walletscarper.services.scoring import ScoringService
from walletscarper.services.stage2_bridge import Stage2IngestBridge
from walletscarper.services.telegram import TelegramService
from walletscarper.services.transactions import TransactionService
from walletscarper.sources import OpenRouterSource

log = logging.getLogger(__name__)


class Pipeline:
    def __init__(self) -> None:
        self.discovery = DiscoveryService()
        self.transactions = TransactionService()
        self.scoring = ScoringService()
        self.telegram = TelegramService()
        self.llm = OpenRouterSource()
        self.backfill = BackfillService()
        self.stage2_bridge = Stage2IngestBridge()

    async def run_once(self, notify: bool = True) -> dict[str, int | str]:
        started = utc_now()
        errors = 0
        candidates = []
        deep_count = 0
        scores = []
        tracked_before = await self._tracked_count()
        try:
            candidates = await self.discovery.run()
            await self.stage2_bridge.ingest_token_candidates(candidates)
            await self.backfill.enqueue_discovered(candidates)
            high = [c for c in candidates if c.priority == "HIGH"]
            medium = [c for c in candidates if c.priority == "MEDIUM"]
            low = [c for c in candidates if c.priority == "LOW"]
            deep = (high + medium + low)[: settings.max_deep_tokens_per_run]
            for candidate in deep:
                await self.transactions.collect_for_token(candidate)
                deep_count += 1
            scores = await self.scoring.score_recent_swaps()
            llm_candidates = [s for s in scores if s.copyability_score >= 55 and s.bot_score < 50 and s.human_score >= 55]
            await self._explain_top_wallets(llm_candidates[:3])
            status = "ok"
        except Exception as exc:
            log.exception("pipeline failed")
            errors += 1
            status = f"failed: {exc}"
        tracked_after = await self._tracked_count()
        summary = {
            "status": status,
            "tokens_checked": len(candidates),
            "tokens_deep_analyzed": deep_count,
            "wallet_candidates_found": len(scores),
            "tracked_wallets_added": max(0, tracked_after - tracked_before),
            "errors_count": errors,
        }
        await db.execute(
            """
            INSERT INTO run_summaries(run_type, started_at, finished_at, status, tokens_checked,
              tokens_deep_analyzed, wallet_candidates_found, tracked_wallets_added, errors_count, summary_json)
            VALUES ('discovery', ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (started, utc_now(), status, summary["tokens_checked"], summary["tokens_deep_analyzed"], summary["wallet_candidates_found"], summary["tracked_wallets_added"], summary["errors_count"], json.dumps(summary, ensure_ascii=False)),
        )
        if notify:
            await self.telegram.send(await self.telegram.render_digest_text(), notification_type="run_digest")
        return summary

    async def _explain_top_wallets(self, scores) -> None:
        for score in scores:
            try:
                report = await self.llm.explain_wallet(asdict(score))
                if not isinstance(report, dict):
                    continue
                await db.execute(
                    """
                    INSERT INTO llm_wallet_reports(wallet, created_at, model, recommendation, confidence, summary, flags_json, raw_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        score.wallet,
                        utc_now(),
                        settings.openrouter_model,
                        str(report.get("recommendation", "investigate")),
                        str(report.get("confidence", "low")),
                        str(report.get("summary", "")),
                        json.dumps(report.get("flags", []), ensure_ascii=False),
                        json.dumps(report, ensure_ascii=False),
                    ),
                )
            except Exception:
                log.warning("LLM explanation skipped for wallet %s", score.wallet, exc_info=True)

    async def _tracked_count(self) -> int:
        row = await db.fetchone("SELECT COUNT(*) AS c FROM tracked_wallets WHERE status IN ('active','probation')")
        return int(row["c"] if row else 0)
