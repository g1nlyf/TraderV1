from __future__ import annotations

import json
import logging
from collections import defaultdict
from datetime import datetime, timezone
from statistics import median
from typing import Any

from walletscarper.db import db
from walletscarper.models import WalletScore, utc_now
from walletscarper.services.wallet_quality import WalletQualityScorer

log = logging.getLogger(__name__)

TRACKED_STATUSES = {"active", "probation"}


class ScoringService:
    def __init__(self) -> None:
        self.quality = WalletQualityScorer()

    async def score_recent_swaps(self) -> list[WalletScore]:
        rows = await db.fetchall(
            """
            SELECT wallet, token_mint, side, token_amount, quote_amount, price_usd, block_time
            FROM pool_transactions
            WHERE wallet IS NOT NULL AND side IN ('buy', 'sell')
            ORDER BY block_time
            """
        )
        grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            grouped[(row["wallet"], row["token_mint"])].append(row)

        wallet_token_results: list[dict[str, Any]] = []
        for (wallet, token), swaps in grouped.items():
            result = self._token_pnl(wallet, token, swaps)
            if result:
                wallet_token_results.append(result)
        await self._store_wallet_token_pnl_many(wallet_token_results)

        by_wallet: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for result in wallet_token_results:
            by_wallet[result["wallet"]].append(result)

        scores: list[WalletScore] = []
        for wallet, results in by_wallet.items():
            score = self._wallet_score(wallet, results)
            scores.append(score)
        await self._store_wallet_scores_many(scores)
        await self._sync_tracked_wallets(scores)
        await self.rebuild_leaderboard()
        log.info("scored %s wallets with quality layer", len(scores))
        return sorted(scores, key=lambda s: s.copyability_score, reverse=True)

    def _token_pnl(self, wallet: str, token: str, swaps: list[dict[str, Any]]) -> dict[str, Any] | None:
        swaps = sorted(swaps, key=lambda r: self._parse_time(r.get("block_time")) or datetime.min.replace(tzinfo=timezone.utc))
        buys: list[dict[str, Any]] = []
        realized_cost = 0.0
        proceeds = 0.0
        buy_count = sell_count = 0
        buy_sizes: list[float] = []
        hold_minutes: list[float] = []
        side_sequence: list[str] = []
        first_buy_at: datetime | None = None
        last_sell_at: datetime | None = None
        for row in swaps:
            side = str(row.get("side") or "")
            amount = abs(float(row.get("token_amount") or 0))
            quote = abs(float(row.get("quote_amount") or 0))
            if quote == 0 and row.get("price_usd") and amount:
                quote = amount * float(row["price_usd"])
            event_time = self._parse_time(row.get("block_time"))
            if side in {"buy", "sell"}:
                side_sequence.append(side)
            if side == "buy" and amount > 0:
                buys.append({"amount": amount, "cost": quote, "time": event_time})
                buy_sizes.append(quote)
                buy_count += 1
                first_buy_at = first_buy_at or event_time
            elif side == "sell" and amount > 0:
                sell_count += 1
                proceeds += quote
                last_sell_at = event_time or last_sell_at
                remaining = amount
                while remaining > 0 and buys:
                    lot = buys[0]
                    lot_amount = float(lot["amount"])
                    lot_cost = float(lot["cost"])
                    take = min(lot_amount, remaining)
                    cost = lot_cost * (take / lot_amount) if lot_amount else 0
                    realized_cost += cost
                    if event_time and lot.get("time"):
                        hold_minutes.append(max(0.0, (event_time - lot["time"]).total_seconds() / 60))
                    lot["amount"] = lot_amount - take
                    lot["cost"] = lot_cost - cost
                    remaining -= take
                    if lot["amount"] <= 1e-12:
                        buys.pop(0)
        if buy_count == 0:
            return None
        realized_pnl = proceeds - realized_cost
        if sell_count == 0 and realized_pnl == 0:
            return None
        roi = realized_pnl / realized_cost if realized_cost > 0 else 0.0
        side_flip_count = sum(1 for left, right in zip(side_sequence, side_sequence[1:]) if left != right)
        return {
            "wallet": wallet,
            "token_mint": token,
            "realized_pnl_usd": realized_pnl,
            "realized_cost_usd": realized_cost,
            "roi": roi,
            "buys_count": buy_count,
            "sells_count": sell_count,
            "buy_usd_total": sum(buy_sizes),
            "sell_usd_total": proceeds,
            "buy_sizes_usd": buy_sizes,
            "side_flip_count": side_flip_count,
            "holding_time_minutes": median(hold_minutes) if hold_minutes else self._fallback_hold_minutes(first_buy_at, last_sell_at),
            "first_buy_at": first_buy_at.isoformat() if first_buy_at else None,
            "last_sell_at": last_sell_at.isoformat() if last_sell_at else None,
        }

    def _wallet_score(self, wallet: str, results: list[dict[str, Any]]) -> WalletScore:
        quality = self.quality.score(wallet, results)
        wins = [r for r in results if float(r["realized_pnl_usd"]) > 0 and float(r["roi"]) > 0]
        total_pnl = sum(float(r["realized_pnl_usd"]) for r in results)
        rois = [float(r["roi"]) for r in results]
        hold_values = [float(r.get("holding_time_minutes") or 0) for r in results if float(r.get("holding_time_minutes") or 0) > 0]
        return WalletScore(
            wallet=wallet,
            copyability_score=quality.copyability_score,
            confidence=quality.confidence,
            status=quality.decision_band,
            realized_pnl_usd=total_pnl,
            winrate=len(wins) / max(len(results), 1),
            median_roi=median(rois) if rois else 0.0,
            median_holding_minutes=median(hold_values) if hold_values else 0.0,
            total_trades=sum(int(r["buys_count"] + r["sells_count"]) for r in results),
            unique_tokens=len(results),
            risk_penalty=quality.risk_penalty,
            bot_score=quality.bot_score,
            human_score=quality.human_score,
            sample_score=quality.sample_score,
            median_buy_usd=quality.median_buy_usd,
            total_volume_usd=quality.total_volume_usd,
            one_token_pnl_share=quality.one_token_pnl_share,
            tx_per_token_median=quality.tx_per_token_median,
            reason=quality.reason,
        )

    async def _store_wallet_token_pnl_many(self, results: list[dict[str, Any]]) -> None:
        if not results:
            return
        now = utc_now()
        conn = await db.connect()
        try:
            await conn.executemany(
                """
                INSERT OR REPLACE INTO wallet_token_pnl(wallet, token_mint, calculated_at, realized_pnl_usd,
                  roi, buys_count, sells_count, holding_time_minutes, method)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'fifo_quality_v2')
                """,
                [
                    (
                        r["wallet"],
                        r["token_mint"],
                        now,
                        r["realized_pnl_usd"],
                        r["roi"],
                        r["buys_count"],
                        r["sells_count"],
                        r["holding_time_minutes"],
                    )
                    for r in results
                ],
            )
            await conn.commit()
        finally:
            await conn.close()

    async def _store_wallet_scores_many(self, scores: list[WalletScore]) -> None:
        if not scores:
            return
        now = utc_now()
        conn = await db.connect()
        try:
            await conn.executemany(
                """
                INSERT OR REPLACE INTO wallet_scores(wallet, calculated_at, total_trades, unique_tokens, realized_pnl_usd,
                  winrate, median_roi, median_holding_minutes, fast_trade_pct, consistency_score, copyability_score,
                  risk_penalty, confidence, decision_band, bot_score, human_score, sample_score, median_buy_usd,
                  total_volume_usd, one_token_pnl_share, tx_per_token_median, reason_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        s.wallet,
                        now,
                        s.total_trades,
                        s.unique_tokens,
                        s.realized_pnl_usd,
                        s.winrate,
                        s.median_roi,
                        s.median_holding_minutes,
                        s.reason.get("fast_trade_pct", 0),
                        s.sample_score,
                        s.copyability_score,
                        s.risk_penalty,
                        s.confidence,
                        s.status,
                        s.bot_score,
                        s.human_score,
                        s.sample_score,
                        s.median_buy_usd,
                        s.total_volume_usd,
                        s.one_token_pnl_share,
                        s.tx_per_token_median,
                        json.dumps(s.reason, ensure_ascii=False),
                    )
                    for s in scores
                ],
            )
            await conn.commit()
        finally:
            await conn.close()

    async def _sync_tracked_wallets(self, scores: list[WalletScore]) -> None:
        if not scores:
            return
        now = utc_now()
        promotions = [
            (s.wallet, s.status, now, now, s.copyability_score, s.confidence)
            for s in scores
            if s.status in TRACKED_STATUSES
        ]
        demotions = [
            (now, s.copyability_score, s.confidence, s.status, s.wallet)
            for s in scores
            if s.status in {"rejected_bot", "rejected_micro", "rejected_one_token"}
        ]
        conn = await db.connect()
        try:
            if promotions:
                await conn.executemany(
                    """
                    INSERT INTO tracked_wallets(wallet, status, added_at, updated_at, copyability_score, confidence, stale_reason)
                    VALUES (?, ?, ?, ?, ?, ?, NULL)
                    ON CONFLICT(wallet) DO UPDATE SET status=excluded.status, updated_at=excluded.updated_at,
                      copyability_score=excluded.copyability_score, confidence=excluded.confidence, stale_reason=NULL
                    """,
                    promotions,
                )
            if demotions:
                await conn.executemany(
                    """
                    UPDATE tracked_wallets
                    SET status='stale', updated_at=?, copyability_score=?, confidence=?, stale_reason=?
                    WHERE wallet=? AND status IN ('active', 'probation')
                    """,
                    demotions,
                )
            await conn.commit()
        finally:
            await conn.close()

    async def _store_wallet_token_pnl(self, r: dict[str, Any]) -> None:
        await db.execute(
            """
            INSERT OR REPLACE INTO wallet_token_pnl(wallet, token_mint, calculated_at, realized_pnl_usd,
              roi, buys_count, sells_count, holding_time_minutes, method)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'fifo_quality_v2')
            """,
            (r["wallet"], r["token_mint"], utc_now(), r["realized_pnl_usd"], r["roi"], r["buys_count"], r["sells_count"], r["holding_time_minutes"]),
        )

    async def _store_wallet_score(self, s: WalletScore) -> None:
        await db.execute(
            """
            INSERT OR REPLACE INTO wallet_scores(wallet, calculated_at, total_trades, unique_tokens, realized_pnl_usd,
              winrate, median_roi, median_holding_minutes, fast_trade_pct, consistency_score, copyability_score,
              risk_penalty, confidence, decision_band, bot_score, human_score, sample_score, median_buy_usd,
              total_volume_usd, one_token_pnl_share, tx_per_token_median, reason_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                s.wallet,
                utc_now(),
                s.total_trades,
                s.unique_tokens,
                s.realized_pnl_usd,
                s.winrate,
                s.median_roi,
                s.median_holding_minutes,
                s.reason.get("fast_trade_pct", 0),
                s.sample_score,
                s.copyability_score,
                s.risk_penalty,
                s.confidence,
                s.status,
                s.bot_score,
                s.human_score,
                s.sample_score,
                s.median_buy_usd,
                s.total_volume_usd,
                s.one_token_pnl_share,
                s.tx_per_token_median,
                json.dumps(s.reason, ensure_ascii=False),
            ),
        )

    async def _promote(self, s: WalletScore) -> None:
        await db.execute(
            """
            INSERT INTO tracked_wallets(wallet, status, added_at, updated_at, copyability_score, confidence, stale_reason)
            VALUES (?, ?, ?, ?, ?, ?, NULL)
            ON CONFLICT(wallet) DO UPDATE SET status=excluded.status, updated_at=excluded.updated_at,
              copyability_score=excluded.copyability_score, confidence=excluded.confidence, stale_reason=NULL
            """,
            (s.wallet, s.status, utc_now(), utc_now(), s.copyability_score, s.confidence),
        )

    async def _demote_if_tracked(self, s: WalletScore) -> None:
        if s.status in {"rejected_bot", "rejected_micro", "rejected_one_token"}:
            await db.execute(
                """
                UPDATE tracked_wallets
                SET status='stale', updated_at=?, copyability_score=?, confidence=?, stale_reason=?
                WHERE wallet=? AND status IN ('active', 'probation')
                """,
                (utc_now(), s.copyability_score, s.confidence, s.status, s.wallet),
            )

    async def rebuild_leaderboard(self) -> None:
        old_ranks = {row["wallet"]: row["rank"] for row in await db.fetchall("SELECT wallet, rank FROM wallet_leaderboard")}
        rows = await db.fetchall(
            """
            SELECT wallet, copyability_score, confidence, decision_band AS status, reason_json
            FROM wallet_scores
            WHERE decision_band NOT IN ('stale', 'rejected_bot', 'rejected_micro', 'rejected_one_token')
            ORDER BY copyability_score DESC
            LIMIT 100
            """
        )
        now = utc_now()
        leaderboard_rows = []
        history_rows = []
        for i, row in enumerate(rows, start=1):
            reason = self._json_or_default(row.get("reason_json"), {"source": "wallet_scores_quality_v2"})
            reason_json = json.dumps(reason, ensure_ascii=False)
            leaderboard_rows.append(
                (row["wallet"], i, old_ranks.get(row["wallet"]), now, row["copyability_score"], row["copyability_score"], 0, row["confidence"], row["status"], reason_json)
            )
            history_rows.append((row["wallet"], i, row["copyability_score"], now, reason_json))
        conn = await db.connect()
        try:
            await conn.execute("DELETE FROM wallet_leaderboard")
            if leaderboard_rows:
                await conn.executemany(
                    """
                    INSERT OR REPLACE INTO wallet_leaderboard(wallet, rank, previous_rank, calculated_at, composite_score,
                      copyability_score, forward_score, confidence, status, reason_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    leaderboard_rows,
                )
            if history_rows:
                await conn.executemany(
                    "INSERT INTO wallet_rank_history(wallet, rank, composite_score, captured_at, reason_json) VALUES (?, ?, ?, ?, ?)",
                    history_rows,
                )
            await conn.commit()
        finally:
            await conn.close()

    def _fallback_hold_minutes(self, first_buy_at: datetime | None, last_sell_at: datetime | None) -> float:
        if first_buy_at and last_sell_at:
            return max(0.0, (last_sell_at - first_buy_at).total_seconds() / 60)
        return 0.0

    def _parse_time(self, value: Any) -> datetime | None:
        if not value:
            return None
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value, tz=timezone.utc)
        text = str(value)
        try:
            if text.isdigit():
                return datetime.fromtimestamp(int(text), tz=timezone.utc)
            return datetime.fromisoformat(text.replace("Z", "+00:00"))
        except Exception:
            return None

    def _json_or_default(self, raw: str | None, default: dict[str, Any]) -> dict[str, Any]:
        if not raw:
            return default
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else default
        except Exception:
            return default
