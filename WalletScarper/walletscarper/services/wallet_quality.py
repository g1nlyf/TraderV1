from __future__ import annotations

from dataclasses import dataclass, field
from statistics import median
from typing import Any


def clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))


@dataclass(slots=True)
class WalletQuality:
    copyability_score: float
    bot_score: float
    human_score: float
    sample_score: float
    risk_penalty: float
    decision_band: str
    confidence: str
    median_buy_usd: float
    total_volume_usd: float
    one_token_pnl_share: float
    tx_per_token_median: float
    fast_trade_pct: float
    consistency_score: float
    reason: dict[str, Any] = field(default_factory=dict)


class WalletQualityScorer:
    def score(self, wallet: str, results: list[dict[str, Any]]) -> WalletQuality:
        unique_tokens = len(results)
        total_trades = sum(int(r.get("buys_count", 0) + r.get("sells_count", 0)) for r in results)
        closed_positions = sum(1 for r in results if int(r.get("sells_count", 0)) > 0 and float(r.get("realized_cost_usd", 0)) > 0)
        wins = [r for r in results if float(r.get("realized_pnl_usd", 0)) > 0 and float(r.get("roi", 0)) > 0]
        total_pnl = sum(float(r.get("realized_pnl_usd", 0)) for r in results)
        positive_pnl = sum(max(0.0, float(r.get("realized_pnl_usd", 0))) for r in results)
        total_volume = sum(float(r.get("buy_usd_total", 0)) + float(r.get("sell_usd_total", 0)) for r in results)
        buy_sizes = [float(v) for r in results for v in r.get("buy_sizes_usd", []) if float(v) > 0]
        median_buy = median(buy_sizes) if buy_sizes else 0.0
        rois = [float(r.get("roi", 0)) for r in results]
        median_roi = median(rois) if rois else 0.0
        hold_values = [float(r.get("holding_time_minutes", 0)) for r in results if float(r.get("holding_time_minutes", 0)) > 0]
        median_hold = median(hold_values) if hold_values else 0.0
        tx_counts = [int(r.get("buys_count", 0) + r.get("sells_count", 0)) for r in results]
        tx_per_token_median = median(tx_counts) if tx_counts else 0.0
        side_flips = sum(int(r.get("side_flip_count", 0)) for r in results)
        flip_ratio = side_flips / max(total_trades - unique_tokens, 1)
        fast_trade_pct = sum(1 for v in hold_values if v < 5) / max(len(hold_values), 1)
        one_token_share = max((max(0.0, float(r.get("realized_pnl_usd", 0))) for r in results), default=0.0) / max(positive_pnl, 1.0)
        winrate = len(wins) / max(unique_tokens, 1)
        pnl_per_trade = total_pnl / max(total_trades, 1)

        sample_score = self._sample_score(unique_tokens, closed_positions, total_trades)
        position_score = self._position_size_score(median_buy, total_volume)
        holding_score = self._holding_score(median_hold)
        winrate_score = self._winrate_score(winrate, unique_tokens)
        pnl_score = clamp(50 + total_pnl / 250 * 50)
        roi_score = clamp(median_roi * 250)
        consistency_score = self._consistency_score(results)
        bot_score, bot_flags = self._bot_score(
            unique_tokens=unique_tokens,
            total_trades=total_trades,
            median_buy=median_buy,
            median_hold=median_hold,
            winrate=winrate,
            tx_per_token_median=tx_per_token_median,
            flip_ratio=flip_ratio,
            fast_trade_pct=fast_trade_pct,
            one_token_share=one_token_share,
            pnl_per_trade=pnl_per_trade,
        )
        human_score = clamp(sample_score * 0.22 + position_score * 0.20 + holding_score * 0.20 + winrate_score * 0.16 + consistency_score * 0.12 + clamp(100 - bot_score) * 0.10)
        penalties, reject_reason = self._penalties(
            unique_tokens=unique_tokens,
            closed_positions=closed_positions,
            total_volume=total_volume,
            median_buy=median_buy,
            median_hold=median_hold,
            winrate=winrate,
            total_pnl=total_pnl,
            one_token_share=one_token_share,
            tx_per_token_median=tx_per_token_median,
            bot_score=bot_score,
        )
        copyability = clamp(pnl_score * 0.18 + winrate_score * 0.14 + sample_score * 0.16 + holding_score * 0.16 + position_score * 0.12 + consistency_score * 0.09 + human_score * 0.15 - penalties)
        decision_band, confidence = self._decision(copyability, bot_score, sample_score, reject_reason)
        reason = {
            "flags": bot_flags,
            "reject_reason": reject_reason,
            "closed_positions": closed_positions,
            "position_score": round(position_score, 2),
            "holding_score": round(holding_score, 2),
            "winrate_score": round(winrate_score, 2),
            "pnl_score": round(pnl_score, 2),
            "roi_score": round(roi_score, 2),
            "flip_ratio": round(flip_ratio, 4),
            "fast_trade_pct": round(fast_trade_pct, 4),
            "pnl_per_trade": round(pnl_per_trade, 4),
            "target_profile": "manual_or_semi_manual_mid_hold_100usd_plus",
        }
        return WalletQuality(copyability, bot_score, human_score, sample_score, penalties, decision_band, confidence, median_buy, total_volume, one_token_share, tx_per_token_median, fast_trade_pct, consistency_score, reason)

    def _sample_score(self, unique_tokens: int, closed_positions: int, total_trades: int) -> float:
        token_part = clamp(unique_tokens / 8 * 100)
        closed_part = clamp(closed_positions / 10 * 100)
        trade_part = 100 if 8 <= total_trades <= 80 else clamp(total_trades / 8 * 100) if total_trades < 8 else clamp(100 - (total_trades - 80) * 0.8)
        return token_part * 0.38 + closed_part * 0.42 + trade_part * 0.20

    def _position_size_score(self, median_buy: float, total_volume: float) -> float:
        if median_buy >= 100:
            size = 100
        elif median_buy >= 50:
            size = 75
        elif median_buy >= 25:
            size = 45
        elif median_buy >= 10:
            size = 20
        else:
            size = 0
        volume = clamp(total_volume / 1500 * 100)
        return size * 0.75 + volume * 0.25

    def _holding_score(self, median_hold: float) -> float:
        if 15 <= median_hold <= 180:
            return 100
        if 5 <= median_hold < 15:
            return 65 + (median_hold - 5) / 10 * 25
        if 180 < median_hold <= 360:
            return 80 - (median_hold - 180) / 180 * 30
        if 0 < median_hold < 5:
            return median_hold / 5 * 35
        return 15

    def _winrate_score(self, winrate: float, unique_tokens: int) -> float:
        if unique_tokens < 3 and winrate >= 0.95:
            return 35
        if 0.45 <= winrate <= 0.75:
            return 100
        if 0.75 < winrate <= 0.90:
            return 88
        if 0.35 <= winrate < 0.45:
            return 65
        if 0.90 < winrate < 0.98:
            return 65
        if winrate >= 0.98:
            return 45
        return 25

    def _consistency_score(self, results: list[dict[str, Any]]) -> float:
        if not results:
            return 0
        positive = sum(1 for r in results if float(r.get("realized_pnl_usd", 0)) > 0)
        base = positive / len(results) * 100
        pnl_values = [float(r.get("realized_pnl_usd", 0)) for r in results]
        total_positive = sum(max(0.0, v) for v in pnl_values)
        one_share = max((max(0.0, v) for v in pnl_values), default=0.0) / max(total_positive, 1.0)
        return clamp(base - max(0, one_share - 0.45) * 80)

    def _bot_score(self, **m: Any) -> tuple[float, list[str]]:
        score = 0.0
        flags: list[str] = []
        if m["median_buy"] < 25:
            score += 30
            flags.append("micro_position_size")
        elif m["median_buy"] < 100:
            score += 10
            flags.append("sub_100_median_buy")
        if m["tx_per_token_median"] > 8:
            score += min(30, (m["tx_per_token_median"] - 8) * 4)
            flags.append("too_many_transactions_per_token")
        if m["flip_ratio"] > 0.55:
            score += min(25, (m["flip_ratio"] - 0.55) * 80)
            flags.append("frequent_buy_sell_flips")
        if m["fast_trade_pct"] > 0.35:
            score += min(25, m["fast_trade_pct"] * 45)
            flags.append("many_fast_round_trips")
        if m["one_token_share"] > 0.60:
            score += min(25, (m["one_token_share"] - 0.60) * 70)
            flags.append("one_token_profit_concentration")
        if m["winrate"] >= 0.95 and m["unique_tokens"] < 6:
            score += 18
            flags.append("suspicious_perfect_winrate_small_sample")
        if m["pnl_per_trade"] < 2 and m["total_trades"] > 20:
            score += 15
            flags.append("low_profit_per_trade")
        if m["median_hold"] and m["median_hold"] < 5:
            score += 30
            flags.append("too_fast_to_copy")
        return clamp(score), flags

    def _penalties(self, **m: Any) -> tuple[float, str]:
        penalties = 0.0
        reject = ""
        if m["median_buy"] < 25:
            penalties += 30
            reject = reject or "micro_position_size"
        elif m["median_buy"] < 100:
            penalties += 8
        if m["unique_tokens"] < 3:
            penalties += 10
            reject = reject or "too_few_tokens"
        if m["closed_positions"] < 3:
            penalties += 8
            reject = reject or "too_few_closed_positions"
        if m["total_volume"] < 150:
            penalties += 25
            reject = reject or "too_low_volume"
        if m["total_pnl"] <= 0:
            penalties += 22
            reject = reject or "negative_pnl"
        if m["one_token_share"] > 0.55:
            penalties += min(18, (m["one_token_share"] - 0.55) * 45)
            reject = reject or "one_token_winner"
        if m["tx_per_token_median"] > 10:
            penalties += min(30, (m["tx_per_token_median"] - 10) * 5)
            reject = reject or "too_many_same_token_transactions"
        if 0 < m["median_hold"] < 5:
            penalties += 35
            reject = reject or "paperhand_too_fast"
        if m["bot_score"] > 65:
            penalties += 35
            reject = reject or "bot_like"
        if m["winrate"] >= 0.98 and m["unique_tokens"] < 6:
            penalties += 18
            reject = reject or "suspicious_perfect_winrate"
        return penalties, reject

    def _decision(self, score: float, bot_score: float, sample_score: float, reject_reason: str) -> tuple[str, str]:
        if reject_reason:
            if reject_reason in {"bot_like", "too_many_same_token_transactions"} or bot_score > 65:
                return "rejected_bot", "medium"
            if reject_reason == "micro_position_size":
                return "rejected_micro", "medium"
            if reject_reason == "one_token_winner":
                return "rejected_one_token", "medium"
            return "store", "low"
        confidence = "high" if sample_score >= 75 and bot_score < 30 else "medium" if sample_score >= 45 else "low"
        if score >= 80 and bot_score < 35 and confidence in {"medium", "high"}:
            return "active", confidence
        if score >= 70 and bot_score < 50:
            return "probation", confidence
        if score >= 55:
            return "watch", confidence
        return "store", confidence
