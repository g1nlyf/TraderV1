from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime
from statistics import mean
from typing import Any

from walletscarper.stage2.clock import Clock, SystemClock, isoformat_utc
from walletscarper.stage2.db import Stage2Database
from walletscarper.stage2.db.json import dumps_json
from walletscarper.stage2.ids import new_id


class WalletIntelligenceService:
    def __init__(self, database: Stage2Database, clock: Clock | None = None):
        self.database = database
        self.clock = clock or SystemClock()

    async def reconstruct_wallet_trade_from_raw_event(self, raw_source_event_id: str) -> str:
        event = await self.database.fetchone("SELECT * FROM raw_source_events WHERE raw_source_event_id = ?", (raw_source_event_id,))
        if not event:
            raise ValueError(f"raw source event not found: {raw_source_event_id}")
        payload = _loads_dict(event["payload_json"])
        metadata = _loads_dict(event["quality_metadata_json"])
        attrs = payload.get("attributes") if isinstance(payload.get("attributes"), dict) else payload
        market = await self.database.fetchone(
            "SELECT * FROM market_snapshots WHERE raw_source_event_id = ? ORDER BY created_at DESC LIMIT 1",
            (raw_source_event_id,),
        )
        wallet = _text(attrs.get("wallet") or attrs.get("maker") or attrs.get("trader") or attrs.get("user") or attrs.get("sender") or attrs.get("owner"))
        token_mint = _text(attrs.get("token_mint") or attrs.get("token") or attrs.get("token_0") or (market or {}).get("token_mint"))
        pool_address = _text(attrs.get("pool_address") or attrs.get("pool") or attrs.get("pair_address") or (market or {}).get("pool_address"))
        side = _side(attrs.get("side") or attrs.get("type") or attrs.get("kind"))
        token_amount = _float(attrs.get("token_amount") or attrs.get("base_amount") or attrs.get("amount") or attrs.get("amount_0"))
        quote_amount = _float(attrs.get("quote_amount") or attrs.get("quote_volume") or attrs.get("amount_usd") or attrs.get("volume_usd"))
        price_usd = _float(attrs.get("price_usd") or attrs.get("price") or attrs.get("price_0_usd") or (market or {}).get("price_usd"))
        flags = _unique(list(_loads_list(metadata.get("quality_flags"))) + list(_loads_list((market or {}).get("quality_flags_json"))))
        if not wallet:
            flags.append("missing_wallet")
        if not token_mint:
            flags.append("missing_token_mint")
        if not side:
            flags.append("uncertain_side")
        if token_amount is None:
            flags.append("missing_token_amount")
        if price_usd is None:
            flags.append("missing_price_usd")
        if "missing_observed_at" in flags:
            flags.append("weak_trade_timestamp")
        confidence = _confidence(str(event.get("confidence") or "unknown"), flags)
        eligible = confidence in {"high", "medium"} and not (set(flags) & {"missing_wallet", "uncertain_side", "missing_token_amount", "missing_price_usd", "weak_trade_timestamp"})
        trade_id = new_id("wallet_trade")
        await self.database.execute(
            """
            INSERT INTO wallet_trades(
              wallet_trade_id, wallet, token_mint, pool_address, side, token_amount,
              quote_amount, price_usd, observed_at, source_name, raw_source_event_id,
              market_snapshot_id, fees_estimate, confidence, quality_flags_json,
              reconstruction_method, eligible_for_high_confidence_evaluation, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                trade_id,
                wallet,
                token_mint,
                pool_address,
                side,
                token_amount,
                quote_amount,
                price_usd,
                event["observed_at"],
                event["source_name"],
                raw_source_event_id,
                (market or {}).get("market_snapshot_id"),
                _float(attrs.get("fees") or attrs.get("fee_usd")),
                confidence,
                dumps_json(_unique(flags)),
                "stage2_raw_event_observed_trade_reconstruction",
                1 if eligible else 0,
                isoformat_utc(self.clock.now()),
            ),
        )
        return trade_id

    async def calculate_wallet_metrics(self, wallet: str) -> str:
        stage2_trades = await self.database.fetchall(
            "SELECT * FROM wallet_trades WHERE wallet = ? ORDER BY observed_at, created_at, wallet_trade_id",
            (wallet,),
        )
        legacy_trades = []
        if not stage2_trades:
            legacy_trades = await _fetch_legacy_wallet_trades(wallet)
        trades = [_metric_trade_from_stage2(row) for row in stage2_trades] + [
            _metric_trade_from_legacy(row) for row in legacy_trades
        ]
        flags: list[str] = []
        source_refs = [row["source_ref"] for row in trades if row.get("source_ref")]
        if not trades:
            flags.append("no_reconstructed_trades")
        lots: dict[str, list[dict[str, Any]]] = defaultdict(list)
        closed_results: list[float] = []
        holding_seconds: list[float] = []
        position_sizes: list[float] = []
        for trade in trades:
            row_flags = list(trade.get("quality_flags") or [])
            flags.extend(str(flag) for flag in row_flags)
            token = trade.get("token_mint")
            side = trade.get("side")
            amount = _float(trade.get("token_amount"))
            price = _float(trade.get("price_usd"))
            if not token or not side or amount is None:
                flags.append("incomplete_trade_excluded_from_pnl_estimate")
                continue
            notional = _trade_notional(trade, amount=amount, price=price)
            if notional is None:
                flags.append("missing_price_or_notional")
                continue
            position_sizes.append(notional)
            observed_at = _parse_time(trade.get("observed_at"))
            if side == "buy":
                lots[token].append({"amount": amount, "cost": notional, "time": observed_at})
            elif side == "sell":
                remaining = amount
                proceeds = notional
                cost_basis = 0.0
                while remaining > 0 and lots[token]:
                    lot = lots[token][0]
                    take = min(float(lot["amount"]), remaining)
                    lot_cost = float(lot["cost"]) * (take / float(lot["amount"])) if float(lot["amount"]) else 0
                    cost_basis += lot_cost
                    lot["amount"] = float(lot["amount"]) - take
                    lot["cost"] = float(lot["cost"]) - lot_cost
                    remaining -= take
                    if observed_at and lot.get("time"):
                        holding_seconds.append(max(0, (observed_at - lot["time"]).total_seconds()))
                    if float(lot["amount"]) <= 1e-12:
                        lots[token].pop(0)
                if cost_basis == 0:
                    flags.append("sell_without_observed_entry")
                else:
                    closed_results.append(proceeds - cost_basis)
        wins = [value for value in closed_results if value > 0]
        losses = [abs(value) for value in closed_results if value < 0]
        realized = sum(closed_results) if closed_results else None
        avg_win = mean(wins) if wins else None
        avg_loss = mean(losses) if losses else None
        quality = _metric_quality(flags, trade_count=len(trades), closed_count=len(closed_results))
        now = self.clock.now()
        latest_trade_time = max((_parse_time(row["observed_at"]) for row in trades), default=None)
        metric_id = new_id("wallet_metric")
        await self.database.execute(
            """
            INSERT INTO wallet_metric_snapshots(
              wallet_metric_snapshot_id, wallet, calculated_at, trade_count, closed_trade_count,
              realized_pnl_estimate, unrealized_inventory_json, net_pnl_estimate, win_rate_estimate,
              expectancy_estimate, payoff_ratio, average_win, average_loss, holding_time_summary_json,
              position_sizing_summary_json, sample_size, recency_seconds, evidence_quality, confidence,
              quality_flags_json, source_refs_json, candidate_evidence_only, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
            """,
            (
                metric_id,
                wallet,
                isoformat_utc(now),
                len(trades),
                len(closed_results),
                realized,
                dumps_json({token: lots[token] for token in lots}),
                realized,
                len(wins) / len(closed_results) if closed_results else None,
                mean(closed_results) if closed_results else None,
                (avg_win / avg_loss) if avg_win is not None and avg_loss not in {None, 0} else None,
                avg_win,
                avg_loss,
                dumps_json({"count": len(holding_seconds), "average_seconds": mean(holding_seconds) if holding_seconds else None}),
                dumps_json({"count": len(position_sizes), "average_usd": mean(position_sizes) if position_sizes else None}),
                len(trades),
                (now - latest_trade_time).total_seconds() if latest_trade_time else None,
                quality,
                "medium" if quality == "medium" else "low",
                dumps_json(_unique(flags)),
                dumps_json(_unique(source_refs)),
                isoformat_utc(now),
            ),
        )
        return metric_id

    async def create_wallet_profile(self, wallet: str, metrics_snapshot_id: str | None = None) -> str:
        metric_id = metrics_snapshot_id or await self.calculate_wallet_metrics(wallet)
        metric = await self.database.fetchone("SELECT * FROM wallet_metric_snapshots WHERE wallet_metric_snapshot_id = ?", (metric_id,))
        if not metric:
            raise ValueError(f"wallet metric snapshot not found: {metric_id}")
        flags = list(_loads_list(metric["quality_flags_json"]))
        sample_size = int(metric["sample_size"] or 0)
        win_rate = _float(metric.get("win_rate_estimate"))
        net = _float(metric.get("net_pnl_estimate"))
        label = "unknown_insufficient_evidence"
        label_confidence = "low"
        included: list[str] = []
        excluded: list[str] = []
        candidate_score = None
        if sample_size < 3 or metric["evidence_quality"] == "low":
            excluded.append("insufficient reconstructed high-quality trade sample")
        elif win_rate is not None and net is not None and net > 0:
            label = "smart_money_candidate"
            label_confidence = "medium"
            candidate_score = min(1.0, max(0.0, win_rate * min(sample_size / 20, 1)))
            included.append("positive reconstructed candidate evidence")
        else:
            label = "noisy_wallet"
            label_confidence = "medium"
            excluded.append("candidate evidence does not show repeatable positive reconstructed outcomes")
        profile_id = new_id("wallet_profile")
        now = isoformat_utc(self.clock.now())
        await self.database.execute(
            """
            INSERT INTO wallet_profiles(
              wallet_profile_id, wallet, metrics_snapshot_id, label, label_confidence,
              candidate_score, evidence_quality, degradation_status, sample_size, recency_seconds,
              source_refs_json, explanation_json, included_reasons_json, excluded_reasons_json,
              last_updated_at, candidate_evidence_only, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
            """,
            (
                profile_id,
                wallet,
                metric_id,
                label,
                label_confidence,
                candidate_score,
                metric["evidence_quality"],
                "degraded" if flags else "normal",
                sample_size,
                metric.get("recency_seconds"),
                metric["source_refs_json"],
                dumps_json({"historical_metrics_are_candidate_evidence_only": True}),
                dumps_json(included),
                dumps_json(excluded),
                now,
                now,
            ),
        )
        return profile_id

    async def create_wallet_cluster(
        self,
        *,
        wallets: list[str],
        relation_type: str,
        evidence_refs: list[str],
        confidence: str,
        token_mint: str | None = None,
        flags: list[str] | None = None,
        quality_flags: list[str] | None = None,
    ) -> str:
        cluster_id = new_id("wallet_cluster")
        await self.database.execute(
            """
            INSERT INTO wallet_clusters(
              wallet_cluster_id, relation_type, wallets_json, token_mint, evidence_refs_json,
              confidence, quality_flags_json, flags_json, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                cluster_id,
                relation_type,
                dumps_json(_unique(wallets)),
                token_mint,
                dumps_json(_unique(evidence_refs)),
                confidence,
                dumps_json(_unique(quality_flags or [])),
                dumps_json(_unique(flags or [relation_type])),
                isoformat_utc(self.clock.now()),
            ),
        )
        return cluster_id

    async def calculate_wallet_token_outcomes(self, token_trade_corpus_id: str) -> dict[str, Any]:
        corpus = await self.database.fetchone(
            "SELECT * FROM token_trade_corpora WHERE token_trade_corpus_id = ?",
            (token_trade_corpus_id,),
        )
        if not corpus:
            raise ValueError(f"token trade corpus not found: {token_trade_corpus_id}")
        stage2_trades = await _fetch_outcome_stage2_trades(
            self.database,
            token_mint=str(corpus["token_mint"]),
            pool_address=corpus.get("pool_address"),
            window_start=corpus.get("window_start"),
            window_end=corpus.get("window_end"),
        )
        legacy_trades = []
        if not stage2_trades:
            legacy_trades = await _fetch_outcome_legacy_trades(
                token_mint=str(corpus["token_mint"]),
                pool_address=corpus.get("pool_address"),
                window_start=corpus.get("window_start"),
                window_end=corpus.get("window_end"),
            )
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in stage2_trades:
            wallet = row.get("wallet")
            if wallet:
                grouped[str(wallet)].append(_normalized_trade(row, legacy=False))
        for row in legacy_trades:
            wallet = row.get("wallet")
            if wallet:
                grouped[str(wallet)].append(_normalized_trade(row, legacy=True))
        outcome_ids: list[str] = []
        outcomes: list[dict[str, Any]] = []
        for wallet, trades in sorted(grouped.items()):
            calculated = _calculate_wallet_token_outcome(wallet=wallet, trades=trades)
            outcome_id = new_id("wallet_token_outcome")
            await self.database.execute(
                """
                INSERT INTO wallet_token_outcomes(
                  wallet_token_outcome_id, token_trade_corpus_id, wallet, token_mint, pool_address,
                  buy_count, sell_count, realized_pnl_estimate, roi_estimate, roi_bucket, notional_usd,
                  entry_time, exit_time, holding_seconds, data_sufficiency, source_refs_json,
                  quality_flags_json, eligible_for_agent_review, calculated_by_service, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    outcome_id,
                    token_trade_corpus_id,
                    wallet,
                    corpus["token_mint"],
                    corpus.get("pool_address"),
                    calculated["buy_count"],
                    calculated["sell_count"],
                    calculated["realized_pnl_estimate"],
                    calculated["roi_estimate"],
                    calculated["roi_bucket"],
                    calculated["notional_usd"],
                    calculated["entry_time"],
                    calculated["exit_time"],
                    calculated["holding_seconds"],
                    calculated["data_sufficiency"],
                    dumps_json(calculated["source_refs"]),
                    dumps_json(calculated["quality_flags"]),
                    1 if calculated["eligible_for_agent_review"] else 0,
                    "wallet_token_outcome_service",
                    isoformat_utc(self.clock.now()),
                ),
            )
            outcome_ids.append(outcome_id)
            outcomes.append({"wallet_token_outcome_id": outcome_id, **calculated})
        quality_flags = list(_loads_list(corpus.get("quality_flags_json")))
        if legacy_trades:
            quality_flags.append("legacy_adapter_source")
        if not outcomes:
            quality_flags.append("no_wallet_outcomes_calculated")
        return {
            "token_trade_corpus_id": token_trade_corpus_id,
            "token_mint": corpus["token_mint"],
            "pool_address": corpus.get("pool_address"),
            "wallet_token_outcome_ids": outcome_ids,
            "outcomes": outcomes,
            "quality_flags": _unique(quality_flags),
            "data_sufficiency": corpus.get("data_sufficiency") or "insufficient",
        }

    async def profile_wallet_history_v2(self, wallet: str) -> dict[str, Any]:
        if not wallet:
            raise ValueError("wallet is required")
        metric_id = await self.calculate_wallet_metrics(wallet)
        metric = await self.database.fetchone(
            "SELECT * FROM wallet_metric_snapshots WHERE wallet_metric_snapshot_id = ?",
            (metric_id,),
        )
        if not metric:
            raise ValueError(f"wallet metric snapshot not found: {metric_id}")
        stage2_trades = await self.database.fetchall(
            "SELECT * FROM wallet_trades WHERE wallet = ? ORDER BY observed_at, created_at, wallet_trade_id",
            (wallet,),
        )
        legacy_trades = []
        if not stage2_trades:
            legacy_trades = await _fetch_legacy_wallet_trades(wallet)
        trades = [_metric_trade_from_stage2(row) for row in stage2_trades] + [
            _metric_trade_from_legacy(row) for row in legacy_trades
        ]
        flags = list(_loads_list(metric.get("quality_flags_json")))
        token_notional: dict[str, float] = defaultdict(float)
        for trade in trades:
            token = trade.get("token_mint")
            amount = _float(trade.get("token_amount"))
            price = _float(trade.get("price_usd"))
            quote = _float(trade.get("quote_amount"))
            notional = quote if quote is not None else ((amount or 0) * price if amount is not None and price is not None else None)
            if token and notional is not None:
                token_notional[str(token)] += notional
        total_notional = sum(token_notional.values())
        one_token_concentration = (max(token_notional.values()) / total_notional) if token_notional and total_notional > 0 else None
        closed_count = int(metric.get("closed_trade_count") or 0)
        trade_count = int(metric.get("trade_count") or 0)
        data_sufficiency = _wallet_history_sufficiency(
            trade_count=trade_count,
            closed_count=closed_count,
            evidence_quality=str(metric.get("evidence_quality") or "unknown"),
        )
        if one_token_concentration is not None and one_token_concentration > 0.75:
            flags.append("one_token_concentration")
        if trade_count > 0 and closed_count == 0:
            flags.append("no_closed_trade_sample")
        bot_like_flags = _bot_like_flags(metric, trade_count=trade_count, one_token_concentration=one_token_concentration)
        copyability_flags = _copyability_flags(metric, data_sufficiency=data_sufficiency, one_token_concentration=one_token_concentration)
        observed_behavior = {
            "trade_count": trade_count,
            "closed_trade_count": closed_count,
            "net_pnl_estimate": metric.get("net_pnl_estimate"),
            "win_rate_estimate": metric.get("win_rate_estimate"),
            "average_win": metric.get("average_win"),
            "average_loss": metric.get("average_loss"),
            "payoff_ratio": metric.get("payoff_ratio"),
            "holding_time_summary": _loads_dict(metric.get("holding_time_summary_json")),
            "position_sizing_summary": _loads_dict(metric.get("position_sizing_summary_json")),
            "one_token_concentration": one_token_concentration,
            "bot_like_flags": bot_like_flags,
            "copyability_flags": copyability_flags,
        }
        inferred_behavior: dict[str, Any] = {}
        if data_sufficiency == "sufficient":
            inferred_behavior = {
                "low_confidence_summary": "repeat behavior can be reviewed from the observed sample; historical edge is not proof of future edge"
            }
        elif data_sufficiency == "partial":
            inferred_behavior = {
                "low_confidence_summary": "wallet has some closed history, but source coverage is partial and should not be treated as a stable personality"
            }
        unknowns = []
        if data_sufficiency == "insufficient":
            unknowns.append("interesting wallet, insufficient data")
        if "sell_without_observed_entry" in flags:
            unknowns.append("entries missing for at least one observed sell")
        return {
            "wallet": wallet,
            "metrics_snapshot_id": metric_id,
            "total_pnl_estimate": metric.get("net_pnl_estimate"),
            "win_rate_estimate": metric.get("win_rate_estimate"),
            "closed_trade_count": closed_count,
            "average_win": metric.get("average_win"),
            "average_loss": metric.get("average_loss"),
            "payoff_ratio": metric.get("payoff_ratio"),
            "holding_time_distribution": _loads_dict(metric.get("holding_time_summary_json")),
            "position_size_distribution": _loads_dict(metric.get("position_sizing_summary_json")),
            "one_token_concentration": one_token_concentration,
            "bot_like_flags": bot_like_flags,
            "copyability_flags": copyability_flags,
            "source_quality": metric.get("evidence_quality"),
            "data_sufficiency": data_sufficiency,
            "quality_flags": _unique(flags),
            "source_refs": _loads_list(metric.get("source_refs_json")),
            "observed_behavior": observed_behavior,
            "inferred_behavior": inferred_behavior,
            "unknowns": _unique(unknowns),
        }

    async def record_agent_wallet_review(
        self,
        *,
        wallet: str,
        decision: str,
        created_by_agent: str,
        metrics_snapshot_id: str | None = None,
        agent_rating: float | None = None,
        copyability_rating: float | None = None,
        pnl_quality: str = "unknown",
        winrate_quality: str = "unknown",
        behavior_profile: dict[str, Any] | None = None,
        why_yes: list[str] | None = None,
        why_no: list[str] | None = None,
        demotion_triggers: list[str] | None = None,
        data_sufficiency: str = "insufficient",
        observed_behavior: dict[str, Any] | None = None,
        inferred_behavior: dict[str, Any] | None = None,
        unknowns: list[str] | None = None,
        evidence_refs: list[str] | None = None,
    ) -> str:
        if decision not in {"elite", "probation", "watch", "reject", "archive"}:
            raise ValueError(f"unsupported agent wallet review decision: {decision}")
        if data_sufficiency not in {"sufficient", "partial", "insufficient"}:
            raise ValueError(f"unsupported data sufficiency: {data_sufficiency}")
        review_unknowns = list(unknowns or [])
        review_inferred = dict(inferred_behavior or {})
        if data_sufficiency == "insufficient":
            if not review_unknowns:
                review_unknowns.append("interesting wallet, insufficient data")
            review_inferred = {}
        if metrics_snapshot_id:
            metric = await self.database.fetchone(
                "SELECT * FROM wallet_metric_snapshots WHERE wallet_metric_snapshot_id = ?",
                (metrics_snapshot_id,),
            )
            if not metric:
                raise ValueError(f"wallet metric snapshot not found: {metrics_snapshot_id}")
        review_id = new_id("agent_wallet_review")
        await self.database.execute(
            """
            INSERT INTO agent_wallet_reviews(
              agent_wallet_review_id, wallet, metrics_snapshot_id, decision, agent_rating,
              copyability_rating, pnl_quality, winrate_quality, behavior_profile_json,
              why_yes_json, why_no_json, demotion_triggers_json, data_sufficiency,
              observed_behavior_json, inferred_behavior_json, unknowns_json,
              evidence_refs_json, created_by_agent, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                review_id,
                wallet,
                metrics_snapshot_id,
                decision,
                agent_rating,
                copyability_rating,
                pnl_quality,
                winrate_quality,
                dumps_json(behavior_profile or {}),
                dumps_json(why_yes or []),
                dumps_json(why_no or []),
                dumps_json(demotion_triggers or []),
                data_sufficiency,
                dumps_json(observed_behavior or {}),
                dumps_json(review_inferred),
                dumps_json(_unique(review_unknowns)),
                dumps_json(_unique(evidence_refs or [])),
                created_by_agent,
                isoformat_utc(self.clock.now()),
            ),
        )
        return review_id

    async def create_wallet_forward_contribution_placeholder(
        self,
        *,
        wallet: str,
        strategy_version_id: str | None = None,
        window_start: str | None = None,
        window_end: str | None = None,
    ) -> str:
        contribution_id = new_id("wallet_forward_contribution")
        now = isoformat_utc(self.clock.now())
        await self.database.execute(
            """
            INSERT INTO wallet_forward_contributions(
              wallet_forward_contribution_id, wallet, strategy_version_id, window_start, window_end,
              signal_count, paper_trade_count, net_pnl, expectancy, win_rate, max_drawdown,
              quality_flags_json, calculated_by_service, calculated_at
            )
            VALUES (?, ?, ?, ?, ?, 0, 0, NULL, NULL, NULL, NULL, ?, ?, ?)
            """,
            (
                contribution_id,
                wallet,
                strategy_version_id,
                window_start,
                window_end,
                dumps_json(["placeholder_no_forward_paper_results", "sprint1_no_forward_metrics_fabricated"]),
                "wallet_forward_contribution_placeholder_service",
                now,
            ),
        )
        return contribution_id


def _loads_dict(raw: Any) -> dict[str, Any]:
    if not raw:
        return {}
    parsed = json.loads(raw) if isinstance(raw, str) else raw
    return parsed if isinstance(parsed, dict) else {}


def _loads_list(raw: Any) -> list[Any]:
    if not raw:
        return []
    parsed = json.loads(raw) if isinstance(raw, str) else raw
    return parsed if isinstance(parsed, list) else []


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None


def _float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return abs(float(value))
    except (TypeError, ValueError):
        return None


def _side(value: Any) -> str | None:
    text = str(value or "").lower()
    if text in {"buy", "sell"}:
        return text
    if "buy" in text:
        return "buy"
    if "sell" in text:
        return "sell"
    return None


def _unique(values: list[Any]) -> list[str]:
    result: list[str] = []
    for value in values:
        text = str(value)
        if text and text not in result:
            result.append(text)
    return result


def _confidence(confidence: str, flags: list[str]) -> str:
    if set(flags) & {"missing_wallet", "uncertain_side", "missing_token_amount", "missing_price_usd", "weak_trade_timestamp"}:
        return "low"
    return confidence if confidence in {"high", "medium"} else "unknown"


def _parse_time(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _metric_quality(flags: list[str], *, trade_count: int, closed_count: int) -> str:
    if trade_count == 0 or closed_count == 0:
        return "low"
    if set(flags) & {"missing_price_usd", "missing_token_amount", "uncertain_side", "sell_without_observed_entry"}:
        return "low"
    return "medium"


def _metric_trade_from_stage2(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "token_mint": row.get("token_mint"),
        "side": row.get("side"),
        "token_amount": row.get("token_amount"),
        "quote_amount": row.get("quote_amount"),
        "price_usd": row.get("price_usd"),
        "observed_at": row.get("observed_at"),
        "quality_flags": _loads_list(row.get("quality_flags_json")),
        "source_ref": row.get("raw_source_event_id"),
    }


def _metric_trade_from_legacy(row: dict[str, Any]) -> dict[str, Any]:
    flags = ["legacy_adapter_source"]
    if not row.get("price_usd") and not row.get("quote_amount"):
        flags.append("missing_price_or_notional")
    return {
        "token_mint": row.get("token_mint"),
        "side": row.get("side"),
        "token_amount": row.get("token_amount"),
        "quote_amount": row.get("quote_amount"),
        "price_usd": row.get("price_usd"),
        "observed_at": row.get("block_time"),
        "quality_flags": flags,
        "source_ref": f"legacy_pool_transaction:{row.get('signature')}" if row.get("signature") else None,
    }


def _trade_notional(trade: dict[str, Any], *, amount: float, price: float | None) -> float | None:
    quote = _float(trade.get("quote_amount"))
    if quote is not None:
        return quote
    if price is not None:
        return amount * price
    return None


async def _fetch_outcome_stage2_trades(
    database: Stage2Database,
    *,
    token_mint: str,
    pool_address: str | None,
    window_start: str | None,
    window_end: str | None,
) -> list[dict[str, Any]]:
    return await database.fetchall(
        """
        SELECT *
        FROM wallet_trades
        WHERE token_mint = ?
          AND (? IS NULL OR pool_address = ?)
          AND (? IS NULL OR observed_at >= ?)
          AND (? IS NULL OR observed_at <= ?)
        ORDER BY observed_at, created_at, wallet_trade_id
        """,
        (token_mint, pool_address, pool_address, window_start, window_start, window_end, window_end),
    )


async def _fetch_outcome_legacy_trades(
    *,
    token_mint: str,
    pool_address: str | None,
    window_start: str | None,
    window_end: str | None,
) -> list[dict[str, Any]]:
    try:
        from walletscarper.db import db as legacy_db

        return await legacy_db.fetchall(
            """
            SELECT signature, pool_address, token_mint, wallet, side, token_amount, quote_amount,
                   price_usd, block_time, source, source_confidence, completeness, raw_json
            FROM pool_transactions
            WHERE token_mint = ?
              AND (? IS NULL OR pool_address = ?)
              AND (? IS NULL OR block_time >= ?)
              AND (? IS NULL OR block_time <= ?)
            ORDER BY block_time, signature
            """,
            (token_mint, pool_address, pool_address, window_start, window_start, window_end, window_end),
        )
    except Exception:
        return []


async def _fetch_legacy_wallet_trades(wallet: str) -> list[dict[str, Any]]:
    try:
        from walletscarper.db import db as legacy_db

        return await legacy_db.fetchall(
            """
            SELECT signature, pool_address, token_mint, wallet, side, token_amount, quote_amount,
                   price_usd, block_time, source, source_confidence, completeness, raw_json
            FROM pool_transactions
            WHERE wallet = ?
              AND side IN ('buy', 'sell')
            ORDER BY block_time, signature
            LIMIT 5000
            """,
            (wallet,),
        )
    except Exception:
        return []


def _normalized_trade(row: dict[str, Any], *, legacy: bool) -> dict[str, Any]:
    amount = _float(row.get("token_amount"))
    quote = _float(row.get("quote_amount"))
    price = _float(row.get("price_usd"))
    flags = [str(flag) for flag in _loads_list(row.get("quality_flags_json"))]
    source_refs: list[str] = []
    if legacy:
        flags.append("legacy_adapter_source")
        if row.get("signature"):
            source_refs.append(f"legacy_pool_transaction:{row.get('signature')}")
        observed_at = row.get("block_time")
    else:
        if row.get("wallet_trade_id"):
            source_refs.append(f"wallet_trade:{row.get('wallet_trade_id')}")
        if row.get("raw_source_event_id"):
            source_refs.append(str(row.get("raw_source_event_id")))
        observed_at = row.get("observed_at")
    side = _side(row.get("side"))
    if side is None:
        flags.append("uncertain_side")
    if amount is None:
        flags.append("missing_token_amount")
    if quote is None and (amount is None or price is None):
        flags.append("missing_price_or_notional")
    notional = quote if quote is not None else (amount * price if amount is not None and price is not None else None)
    return {
        "wallet": row.get("wallet"),
        "side": side,
        "amount": amount,
        "price": price,
        "notional": notional,
        "observed_at": observed_at,
        "source_refs": source_refs,
        "quality_flags": flags,
    }


def _calculate_wallet_token_outcome(*, wallet: str, trades: list[dict[str, Any]]) -> dict[str, Any]:
    lots: list[dict[str, Any]] = []
    flags: list[str] = []
    source_refs: list[str] = []
    buy_count = 0
    sell_count = 0
    buy_notional = 0.0
    matched_cost_basis = 0.0
    realized_pnl = 0.0
    matched_sell_seen = False
    holding_seconds: list[float] = []
    entry_times: list[str] = []
    exit_times: list[str] = []
    for trade in trades:
        flags.extend(trade.get("quality_flags") or [])
        source_refs.extend(trade.get("source_refs") or [])
        side = trade.get("side")
        amount = trade.get("amount")
        notional = trade.get("notional")
        observed = str(trade.get("observed_at") or "")
        observed_dt = _parse_time(observed) if observed else None
        if side not in {"buy", "sell"} or amount is None or notional is None:
            flags.append("incomplete_trade_excluded_from_token_outcome")
            continue
        if side == "buy":
            buy_count += 1
            buy_notional += float(notional)
            if observed:
                entry_times.append(observed)
            lots.append({"amount": float(amount), "cost": float(notional), "time": observed_dt})
            continue
        sell_count += 1
        if observed:
            exit_times.append(observed)
        remaining = float(amount)
        proceeds = float(notional)
        while remaining > 0 and lots:
            lot = lots[0]
            lot_amount = float(lot["amount"])
            if lot_amount <= 0:
                lots.pop(0)
                continue
            take = min(lot_amount, remaining)
            proceed_part = proceeds * (take / float(amount)) if float(amount) else 0
            cost_part = float(lot["cost"]) * (take / lot_amount) if lot_amount else 0
            realized_pnl += proceed_part - cost_part
            matched_cost_basis += cost_part
            matched_sell_seen = True
            if observed_dt and lot.get("time"):
                holding_seconds.append(max(0, (observed_dt - lot["time"]).total_seconds()))
            lot["amount"] = lot_amount - take
            lot["cost"] = float(lot["cost"]) - cost_part
            remaining -= take
            if float(lot["amount"]) <= 1e-12:
                lots.pop(0)
        if remaining > 1e-12:
            flags.append("sell_without_observed_entry")
    if buy_count == 0 or sell_count == 0:
        flags.append("incomplete_buy_sell_path")
    if buy_count + sell_count < 2:
        flags.append("small_token_trade_sample")
    realized = realized_pnl if matched_sell_seen else None
    roi = (realized / matched_cost_basis) if realized is not None and matched_cost_basis > 0 else None
    data_sufficiency = _token_outcome_sufficiency(
        buy_count=buy_count,
        sell_count=sell_count,
        matched_cost_basis=matched_cost_basis,
        flags=flags,
        trade_count=len(trades),
    )
    eligible = bool(
        data_sufficiency == "sufficient"
        and roi is not None
        and roi >= 0.2
        and matched_cost_basis > 0
        and not (set(flags) & {"sell_without_observed_entry", "missing_price_or_notional", "uncertain_side"})
    )
    return {
        "wallet": wallet,
        "buy_count": buy_count,
        "sell_count": sell_count,
        "realized_pnl_estimate": realized,
        "roi_estimate": roi,
        "roi_bucket": _roi_bucket(roi),
        "notional_usd": matched_cost_basis if matched_cost_basis > 0 else (buy_notional or None),
        "entry_time": min(entry_times) if entry_times else None,
        "exit_time": max(exit_times) if exit_times else None,
        "holding_seconds": mean(holding_seconds) if holding_seconds else None,
        "data_sufficiency": data_sufficiency,
        "source_refs": _unique(source_refs),
        "quality_flags": _unique(flags),
        "eligible_for_agent_review": eligible,
    }


def _roi_bucket(roi: float | None) -> str | None:
    if roi is None or roi < 0.2:
        return None
    if roi < 0.5:
        return "20_50"
    if roi < 1.0:
        return "50_100"
    if roi < 2.0:
        return "100_200"
    return "200_plus"


def _token_outcome_sufficiency(
    *,
    buy_count: int,
    sell_count: int,
    matched_cost_basis: float,
    flags: list[str],
    trade_count: int,
) -> str:
    if not trade_count:
        return "insufficient"
    hard_gaps = {"missing_price_or_notional", "uncertain_side", "sell_without_observed_entry"}
    if buy_count > 0 and sell_count > 0 and matched_cost_basis > 0 and not (hard_gaps & set(flags)):
        return "sufficient"
    if buy_count > 0 or sell_count > 0:
        return "partial"
    return "insufficient"


def _wallet_history_sufficiency(*, trade_count: int, closed_count: int, evidence_quality: str) -> str:
    if trade_count >= 10 and closed_count >= 5 and evidence_quality != "low":
        return "sufficient"
    if trade_count > 0 and closed_count > 0:
        return "partial"
    return "insufficient"


def _bot_like_flags(metric: dict[str, Any], *, trade_count: int, one_token_concentration: float | None) -> list[str]:
    flags: list[str] = []
    holding = _loads_dict(metric.get("holding_time_summary_json"))
    average_holding = _float(holding.get("average_seconds"))
    if average_holding is not None and average_holding < 30:
        flags.append("very_short_average_holding")
    if trade_count >= 30 and one_token_concentration is not None and one_token_concentration > 0.9:
        flags.append("high_repetition_one_token")
    return flags


def _copyability_flags(metric: dict[str, Any], *, data_sufficiency: str, one_token_concentration: float | None) -> list[str]:
    flags: list[str] = []
    net = _signed_float(metric.get("net_pnl_estimate"))
    win_rate = _float(metric.get("win_rate_estimate"))
    if data_sufficiency == "insufficient":
        flags.append("insufficient_history_for_copyability")
    if net is not None and net > 0:
        flags.append("positive_observed_pnl")
    if win_rate is not None and win_rate > 0.5:
        flags.append("positive_observed_win_rate")
    if one_token_concentration is not None and one_token_concentration > 0.75:
        flags.append("one_token_concentration_limits_copyability")
    flags.append("historical_wallet_pnl_is_not_future_edge_proof")
    return _unique(flags)


def _signed_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
