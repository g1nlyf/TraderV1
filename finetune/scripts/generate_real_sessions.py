"""
Generate training sessions using REAL data from stage2-v2-tool.

Reads wallet-token pairs from finetune/data/real_pairs.json,
calls real stage2-v2-tool for each, applies teacher decision logic,
writes session JSON to finetune/data/sessions/.

Usage:
  python finetune/scripts/generate_real_sessions.py --batch 0 --batch-size 20
  python finetune/scripts/generate_real_sessions.py --all --workers 8
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

# Ensure stdout/stderr can handle Unicode on Windows (cp1252 default breaks UTF-8 symbols)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[2]
WALLETSCARPER_PYTHON = ROOT / "WalletScarper" / ".venv" / "Scripts" / "python.exe"
WALLETSCARPER_ROOT = ROOT / "WalletScarper"
SESSIONS_DIR = ROOT / "finetune" / "data" / "sessions"
PAIRS_FILE = ROOT / "finetune" / "data" / "real_pairs.json"
PROMPTS_DIR = ROOT / "finetune" / "prompts"

SYSTEM_PROMPT = (PROMPTS_DIR / "teacher_system.md").read_text(encoding="utf-8")

TOOL_NAME_MAP = {
    "wallet_profile_history": "wallet.profile_history",
    "token_get_profile": "token.get_profile",
    "market_get_token_snapshot": "market.get_token_snapshot",
    "agent_record_trading_decision": "agent.record_trading_decision",
}

_STRIP_ENV = {"PYTHONHOME", "PYTHONPATH", "PYTHONEXECUTABLE"}


def _clean_env():
    return {k: v for k, v in os.environ.items() if k not in _STRIP_ENV}


def call_tool(tool_name: str, payload: dict) -> dict:
    v2_name = TOOL_NAME_MAP.get(tool_name, tool_name)
    try:
        result = subprocess.run(
            [str(WALLETSCARPER_PYTHON), "-m", "walletscarper",
             "stage2-v2-tool", v2_name, "--payload-json", json.dumps(payload)],
            cwd=str(WALLETSCARPER_ROOT),
            capture_output=True, text=True, encoding="utf-8", timeout=60, check=False,
            env=_clean_env(),
        )
        stdout = result.stdout.strip()
        if not stdout:
            return {"ok": False, "error": f"empty output rc={result.returncode}",
                    "stderr": result.stderr[:200]}
        return json.loads(stdout, strict=False)
    except (subprocess.TimeoutExpired, json.JSONDecodeError, Exception) as exc:
        return {"ok": False, "error": str(exc)}


def slim_wallet_response(raw: dict) -> dict:
    """Extract key fields from wallet.profile_history response."""
    if not raw.get("ok"):
        return raw
    profile = raw.get("profile", {})
    obs = profile.get("observed_behavior") or profile
    return {
        "ok": True,
        "wallet": raw.get("wallet", ""),
        "profile": {
            "win_rate_estimate": obs.get("win_rate_estimate", profile.get("win_rate")),
            "trade_count": obs.get("trade_count", profile.get("trade_count")),
            "net_pnl_estimate": obs.get("net_pnl_estimate", profile.get("total_pnl_usd")),
            "payoff_ratio": obs.get("payoff_ratio", profile.get("payoff_ratio")),
            "data_sufficiency": profile.get("data_sufficiency"),
            "quality_flags": profile.get("copyability_flags", raw.get("quality_flags", [])),
        },
        "confidence": raw.get("confidence"),
        "data_as_of": raw.get("data_as_of"),
    }


def slim_token_response(raw: dict) -> dict:
    """Extract key fields from token.get_profile response."""
    if not raw.get("ok"):
        return raw
    profile = raw.get("profile", {})
    return {
        "ok": True,
        "token_mint": raw.get("token_mint") or profile.get("token_mint", ""),
        "profile": {
            "liquidity_usd": profile.get("liquidity_usd"),
            "market_cap": profile.get("market_cap"),
            "volume_24h": profile.get("volume_24h"),
            "data_sufficiency": profile.get("data_sufficiency"),
            "evidence_quality": (profile.get("tradeability_summary") or {}).get("evidence_quality"),
            "latest_observed_at": raw.get("data_as_of"),
        },
        "quality_flags": raw.get("quality_flags", []),
        "confidence": raw.get("confidence"),
        "data_as_of": raw.get("data_as_of"),
    }


def slim_market_response(raw: dict) -> dict:
    """Extract key fields from market.get_token_snapshot response."""
    if not raw.get("ok"):
        return raw
    snap = raw.get("snapshot", {})
    return {
        "ok": True,
        "token_mint": snap.get("token_mint", ""),
        "snapshot": {
            "symbol": snap.get("symbol"),
            "price_usd": snap.get("price_usd"),
            "price_change_5m": snap.get("price_change_5m"),
            "price_change_1h": snap.get("price_change_1h"),
            "price_change_24h": snap.get("price_change_24h"),
            "liquidity_usd": snap.get("liquidity_usd"),
            "market_cap": snap.get("market_cap"),
            "txns_5m_buys": snap.get("txns_5m_buys"),
            "txns_5m_sells": snap.get("txns_5m_sells"),
            "pair_created_at": snap.get("pair_created_at"),
            "dex": snap.get("dex"),
        },
        "confidence": raw.get("confidence"),
        "data_as_of": raw.get("data_as_of"),
    }


# ─── Composite scoring decision engine ───────────────────────────────────────

CRITICAL_TOKEN_FLAGS = {
    "freeze_authority_active", "mutable_supply", "rug_pattern", "low_liquidity_absolute"
}
CRITICAL_WALLET_FLAGS = {
    "bot_pattern",
    "wash_trading",
    "single_token_concentration",
    "one_token_concentration_limits_copyability",
}


def _score_wallet(win_rate: float, payoff: float, trade_count: int, net_pnl: float) -> float:
    """0.0–1.0 wallet quality. Critical flags must be checked before calling."""
    # Win rate: meaningful range 0.35 (floor) → 0.75 (ceiling)
    wr_s = max(0.0, min(1.0, (win_rate - 0.35) / 0.40))
    # Payoff ratio: 0x → 0, 5x → 1.0
    payoff_s = min(1.0, max(0.0, payoff / 5.0))
    # Track record depth: <3 = noise, 50 = confident
    count_s = min(1.0, max(0.0, (trade_count - 3) / 47.0))
    # Net PnL: >0 boosts, deep negative penalises
    if net_pnl >= 0:
        pnl_s = min(1.0, 0.5 + net_pnl / 200_000)
    else:
        pnl_s = max(0.0, 0.5 + net_pnl / 100_000)
    # Weights: payoff most predictive, then win rate, then experience, then PnL
    return 0.30 * wr_s + 0.35 * payoff_s + 0.20 * count_s + 0.15 * pnl_s


def _score_token(liquidity: float, market_cap: float, data_suff: str) -> float:
    """0.0–1.0 token quality. Critical flags must be checked before calling."""
    # Liquidity: $5k floor → $100k ceiling
    liq_s = max(0.0, min(1.0, (liquidity - 5_000) / 95_000))
    # Market cap sweet spot: $500k–$10M = peak score; too small or too big = lower
    if market_cap <= 0:
        cap_s = 0.3
    elif market_cap < 500_000:
        cap_s = 0.3 + 0.5 * (market_cap / 500_000)
    elif market_cap <= 10_000_000:
        cap_s = 0.8 + 0.2 * min(1.0, (market_cap - 500_000) / 9_500_000)
    else:
        cap_s = max(0.0, 1.0 - (market_cap - 10_000_000) / 40_000_000)
    quality_mult = {"sufficient": 1.0, "partial": 0.85}.get(data_suff, 0.65)
    return (0.65 * liq_s + 0.35 * cap_s) * quality_mult


def _score_timing(price_1h: float, price_5m: float, buys_5m: int, sells_5m: int,
                  signal_age_min: float) -> float:
    """0.0–1.0 entry timing quality."""
    # Signal freshness: 0 min → 1.0, 360 min → 0
    freshness_s = max(0.0, 1.0 - signal_age_min / 360)
    # Price movement 1h: sweet spot 5–25%; negative = bearish; >100% = missed
    if price_1h < 0:
        price_s = max(0.1, 0.5 + price_1h / 100)
    elif price_1h <= 25:
        price_s = 0.5 + price_1h / 50          # 0% → 0.5, 25% → 1.0
    else:
        price_s = max(0.0, 1.0 - (price_1h - 25) / 75)   # 25% → 1.0, 100% → 0
    # Buy/sell pressure in 5min
    total_5m = buys_5m + sells_5m
    pressure_s = (buys_5m / total_5m) if total_5m > 0 else 0.5
    return 0.40 * freshness_s + 0.35 * price_s + 0.25 * pressure_s


def _tradeoff_notes(
    ws: float, ts: float, timing_s: float,
    win_rate: float, payoff: float, net_pnl: float, trade_count: int,
    liquidity: float, price_1h: float,
    buys_5m: int, sells_5m: int, signal_age_min: float,
) -> list[str]:
    """Contextual observations explaining how factors interact."""
    notes: list[str] = []
    # Wallet tradeoffs
    if win_rate < 0.48 and payoff >= 2.5:
        notes.append(
            f"below-average accuracy ({win_rate:.0%} WR) offset by {payoff:.1f}x payoff — "
            f"captures large moves when correct"
        )
    elif win_rate >= 0.62 and net_pnl < 0:
        notes.append(
            f"high accuracy ({win_rate:.0%} WR) undermined by net P&L ${net_pnl:,.0f} — "
            f"small winners, large losers pattern"
        )
    elif win_rate >= 0.62 and 0 < payoff < 0.8:
        notes.append(
            f"good accuracy ({win_rate:.0%} WR) but {payoff:.2f}x payoff ratio limits profitability — "
            f"exits too early"
        )
    elif win_rate >= 0.65 and payoff >= 3.0:
        notes.append(
            f"elite execution: accuracy ({win_rate:.0%} WR) AND sizing ({payoff:.1f}x payoff) both strong"
        )
    if trade_count < 10:
        notes.append(
            f"thin track record ({trade_count} trades) — statistics may not generalise"
        )
    # Token tradeoffs
    if liquidity < 20_000 and ts >= 0.30:
        notes.append(
            f"thin liquidity (${liquidity:,.0f}) — size conservatively to limit slippage"
        )
    # Timing tradeoffs
    if price_1h > 40 and buys_5m >= sells_5m:
        notes.append(
            f"momentum strong (+{price_1h:.0f}% 1h) but reduces remaining upside — "
            f"tighter risk parameters warranted"
        )
    elif price_1h < 10 and buys_5m > sells_5m * 1.5:
        notes.append(
            f"early momentum (+{price_1h:.0f}% 1h, {buys_5m}:{sells_5m} buy/sell) — "
            f"favourable entry window before crowd arrives"
        )
    elif (buys_5m + sells_5m) > 5 and sells_5m > buys_5m * 1.5:
        notes.append(
            f"distribution pattern: {sells_5m} sells vs {buys_5m} buys (5min) — "
            f"smart money may be exiting"
        )
    if signal_age_min > 90:
        notes.append(
            f"signal {signal_age_min:.0f}min old — entry window narrowing"
        )
    # Cross-factor: identify weakest and strongest dimension
    dims = [("wallet", ws), ("token", ts), ("timing", timing_s)]
    weakest_name, weakest_val = min(dims, key=lambda x: x[1])
    strongest_name, _ = max(dims, key=lambda x: x[1])
    if weakest_val < 0.38:
        notes.append(
            f"{weakest_name} quality ({weakest_val:.2f}) is the primary limiting factor; "
            f"{strongest_name} is the relative strength"
        )
    return notes


def make_decision(
    wallet_resp: dict,
    token_resp: dict,
    market_resp: dict | None,
    observed_at_str: str,
) -> tuple[str, str, str]:
    """
    Composite scoring decision engine.
    Returns (decision_type, pre_action_reasoning, confidence_tier).

    Three dimensions scored 0–1, combined as weighted composite:
      wallet  40%  (win_rate, payoff_ratio, trade_count, net_pnl)
      token   35%  (liquidity, market_cap, data_quality)
      timing  25%  (signal_age, price_change_1h, buy/sell pressure)

    Thresholds: ≥0.72 high, ≥0.52 medium, ≥0.38 low, <0.38 no_trade.
    Hard vetos bypass scoring for truly disqualifying conditions.
    """
    now = datetime.now(timezone.utc)
    try:
        obs_dt = datetime.fromisoformat(observed_at_str.replace("Z", "+00:00"))
        signal_age_min = (now - obs_dt).total_seconds() / 60
    except Exception:
        signal_age_min = 9999

    # ── Extract metrics ────────────────────────────────────────────────────────
    wallet_ok = wallet_resp.get("ok", False)
    w_profile = wallet_resp.get("profile", {})
    win_rate = float(w_profile.get("win_rate_estimate") or 0.0)
    trade_count = int(w_profile.get("trade_count") or 0)
    net_pnl = float(w_profile.get("net_pnl_estimate") or 0.0)
    payoff = float(w_profile.get("payoff_ratio") or 0.0)
    data_suff_w = w_profile.get("data_sufficiency") or "insufficient"
    w_flags = set(w_profile.get("quality_flags") or [])

    token_ok = token_resp.get("ok", False)
    t_profile = token_resp.get("profile", {})
    liquidity = float(t_profile.get("liquidity_usd") or 0.0)
    market_cap = float(t_profile.get("market_cap") or 0.0)
    t_flags = set(token_resp.get("quality_flags") or [])
    data_suff_t = t_profile.get("data_sufficiency") or "insufficient"

    market_ok_flag = market_resp is not None and bool(market_resp.get("ok"))
    price_1h = price_5m = 0.0
    buys_5m = sells_5m = 0
    if market_ok_flag:
        snap = market_resp.get("snapshot", {})
        price_1h = float(snap.get("price_change_1h") or 0.0)
        price_5m = float(snap.get("price_change_5m") or 0.0)
        buys_5m = int(snap.get("txns_5m_buys") or 0)
        sells_5m = int(snap.get("txns_5m_sells") or 0)

    # ── Hard veto (truly uncrossable) ─────────────────────────────────────────
    veto: str | None = None
    if not wallet_ok:
        veto = "wallet data unavailable (ok=false)"
    elif not token_ok:
        veto = "token data unavailable (ok=false)"
    elif 0 < liquidity < 5_000:
        veto = f"token liquidity ${liquidity:,.0f} below $5k floor — rug/illiquidity risk"
    elif signal_age_min > 360:
        veto = f"signal {signal_age_min / 60:.1f}h old — stale beyond 6h threshold"
    elif market_ok_flag and price_1h > 100:
        veto = f"token already +{price_1h:.0f}% in 1h — move almost certainly over, risk/reward inverted"
    elif w_flags & CRITICAL_WALLET_FLAGS:
        veto = f"wallet disqualified: {', '.join(w_flags & CRITICAL_WALLET_FLAGS)}"
    elif t_flags & CRITICAL_TOKEN_FLAGS:
        veto = f"token disqualified: {', '.join(t_flags & CRITICAL_TOKEN_FLAGS)}"
    elif wallet_ok and trade_count >= 5 and payoff < 0.05 and net_pnl < -1_000:
        veto = (
            f"wallet payoff ratio {payoff:.4f}x with net P&L ${net_pnl:,.0f} — "
            f"catastrophically negative expected value despite {win_rate:.0%} win rate"
        )

    if veto:
        ctx: list[str] = []
        if wallet_ok and trade_count > 0:
            ctx.append(
                f"Wallet: {win_rate:.0%} WR across {trade_count} trades"
                + (f", {payoff:.1f}x payoff" if payoff else "")
                + (f", net P&L ${net_pnl:,.0f}" if net_pnl != 0 else "") + "."
            )
        if token_ok:
            ctx.append(f"Token: ${liquidity:,.0f} liquidity, ${market_cap:,.0f} mcap.")
        if market_ok_flag:
            ctx.append(
                f"Market: {price_1h:+.0f}% 1h, "
                f"{buys_5m}/{buys_5m + sells_5m} buys (5min)."
            )
        ctx.append(f"Hard veto: {veto}.")
        return "no_trade", " ".join(ctx), "n/a"

    # ── Composite scoring ──────────────────────────────────────────────────────
    ws = _score_wallet(win_rate, payoff, trade_count, net_pnl)
    ts = _score_token(liquidity, market_cap, data_suff_t)
    if market_ok_flag:
        timing_s = _score_timing(price_1h, price_5m, buys_5m, sells_5m, signal_age_min)
    else:
        # No live data: derive timing from signal freshness only, neutral pressure
        timing_s = _score_timing(0.0, 0.0, 1, 1, signal_age_min)

    composite = 0.40 * ws + 0.35 * ts + 0.25 * timing_s

    if composite >= 0.72:
        confidence: str | None = "high"
    elif composite >= 0.52:
        confidence = "medium"
    elif composite >= 0.38:
        confidence = "low"
    else:
        confidence = None

    notes = _tradeoff_notes(
        ws, ts, timing_s,
        win_rate, payoff, net_pnl, trade_count,
        liquidity, price_1h, buys_5m, sells_5m, signal_age_min,
    )

    if confidence is None:
        weakest_name = min(
            [("wallet", ws), ("token", ts), ("timing", timing_s)], key=lambda x: x[1]
        )[0]
        parts = [
            f"Composite score {composite:.2f} — below 0.38 threshold → no_trade.",
            f"Wallet ({ws:.2f}): {win_rate:.0%} WR, {trade_count} trades"
            + (f", {payoff:.1f}x payoff" if payoff else "")
            + (f", net P&L ${net_pnl:,.0f}" if net_pnl != 0 else "")
            + f" (data: {data_suff_w}).",
            f"Token ({ts:.2f}): ${liquidity:,.0f} liq, ${market_cap:,.0f} mcap (data: {data_suff_t}).",
        ]
        if market_ok_flag:
            parts.append(
                f"Timing ({timing_s:.2f}): {price_1h:+.0f}% 1h, "
                f"{buys_5m}/{buys_5m + sells_5m} buys, signal {signal_age_min:.0f}min old."
            )
        if notes:
            parts.append(" ".join(notes) + ".")
        parts.append(
            f"Primary drag: {weakest_name} dimension. "
            "Insufficient combined evidence to justify entry at this time."
        )
        return "no_trade", " ".join(parts), "n/a"

    # ── Signal ────────────────────────────────────────────────────────────────
    parts = [
        f"Composite score {composite:.2f} → {confidence} confidence signal.",
        f"Wallet ({ws:.2f}): {win_rate:.0%} WR across {trade_count} trades"
        + (f", {payoff:.1f}x payoff ratio" if payoff else "")
        + (f", net P&L ${net_pnl:,.0f}" if net_pnl != 0 else "") + ".",
        f"Token ({ts:.2f}): ${liquidity:,.0f} liquidity, ${market_cap:,.0f} market cap.",
    ]
    if market_ok_flag:
        total = buys_5m + sells_5m
        parts.append(
            f"Timing ({timing_s:.2f}): {price_1h:+.0f}% 1h, "
            f"{buys_5m}/{total} buys in 5min, signal {signal_age_min:.0f}min old."
        )
    if notes:
        parts.append(" ".join(notes) + ".")
    return "signal", " ".join(parts), confidence


def make_tool_call_id() -> str:
    return "call_" + uuid.uuid4().hex[:8]


def generate_session(pair: dict, session_index: int) -> dict | None:
    """Generate one training session for a wallet-token pair."""
    wallet = pair["wallet"]
    token_mint = pair["token_mint"]
    signal_id = f"real_{uuid.uuid4().hex[:16]}"

    # Support stale signal scenarios via signal_age_override_hours
    signal_age_override_hours: float | None = pair.get("signal_age_override_hours")
    if signal_age_override_hours is not None:
        from datetime import timedelta
        observed_at_dt = datetime.now(timezone.utc) - timedelta(hours=signal_age_override_hours)
        observed_at = observed_at_dt.isoformat()
    else:
        observed_at = datetime.now(timezone.utc).isoformat()

    # ── STEP 1: wallet_profile_history ────────────────────────────────────────
    wallet_call_id = make_tool_call_id()
    raw_wallet = call_tool("wallet_profile_history", {"wallet": wallet})
    slim_wallet = slim_wallet_response(raw_wallet)

    # ── STEP 2: token_get_profile ─────────────────────────────────────────────
    token_call_id = make_tool_call_id()
    raw_token = call_tool("token_get_profile", {"token_mint": token_mint})
    slim_token = slim_token_response(raw_token)

    # ── STEP 3: market_get_token_snapshot ─────────────────────────────────────
    market_call_id = make_tool_call_id()
    raw_market = call_tool("market_get_token_snapshot", {"token_mint": token_mint})
    slim_market = slim_market_response(raw_market)

    # ── Decision ──────────────────────────────────────────────────────────────
    decision_type, reasoning, confidence = make_decision(
        slim_wallet, slim_token, slim_market, observed_at
    )

    decision_call_id = make_tool_call_id()
    decision_id_str = str(uuid.uuid4())
    decision_args = {
        "decision_type": decision_type,
        "pre_action_reasoning": reasoning,
        "linked_tracked_wallet_signal_event_id": signal_id,
    }

    # ── Build session messages ─────────────────────────────────────────────────
    user_msg = (
        f"AUTONOMOUS SIGNAL REVIEW\n\n"
        f"Signal event:\n"
        f"  tracked_wallet_signal_event_id: {signal_id}\n"
        f"  wallet: {wallet}\n"
        f"  token_mint: {token_mint}\n"
        f"  side: buy\n"
        f"  observed_at: {observed_at}\n\n"
        f"Execute the required tool sequence and record your decision."
    )

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_msg},
        # Step 1: wallet
        {
            "role": "assistant", "content": None,
            "tool_calls": [{"id": wallet_call_id, "type": "function",
                            "function": {"name": "wallet_profile_history",
                                         "arguments": json.dumps({"wallet": wallet})}}]
        },
        {"role": "tool", "tool_call_id": wallet_call_id,
         "content": json.dumps(slim_wallet, default=str)},
        # Step 2: token
        {
            "role": "assistant", "content": None,
            "tool_calls": [{"id": token_call_id, "type": "function",
                            "function": {"name": "token_get_profile",
                                         "arguments": json.dumps({"token_mint": token_mint})}}]
        },
        {"role": "tool", "tool_call_id": token_call_id,
         "content": json.dumps(slim_token, default=str)},
        # Step 3: market snapshot
        {
            "role": "assistant", "content": None,
            "tool_calls": [{"id": market_call_id, "type": "function",
                            "function": {"name": "market_get_token_snapshot",
                                         "arguments": json.dumps({"token_mint": token_mint})}}]
        },
        {"role": "tool", "tool_call_id": market_call_id,
         "content": json.dumps(slim_market, default=str)},
        # Step 4: decision
        {
            "role": "assistant", "content": None,
            "tool_calls": [{"id": decision_call_id, "type": "function",
                            "function": {"name": "agent_record_trading_decision",
                                         "arguments": json.dumps(decision_args)}}]
        },
        {"role": "tool", "tool_call_id": decision_call_id,
         "content": json.dumps({"ok": True, "artifact_id": decision_id_str,
                                 "decision_id": decision_id_str})},
    ]

    # ── Signal execution path (only for signal decisions) ─────────────────────
    if decision_type == "signal":
        signal_create_call_id = make_tool_call_id()
        risk_call_id = make_tool_call_id()
        order_call_id = make_tool_call_id()
        fill_call_id = make_tool_call_id()

        signal_id_str = str(uuid.uuid4())
        risk_id_str = str(uuid.uuid4())
        order_id_str = str(uuid.uuid4())

        # Confidence-based parameters
        conf_params = {
            "high": {
                "invalidation": "Price drops 15% from entry or liquidity drops below $20k",
                "holding": "30-90 minutes",
                "size_pct": 0.08,
            },
            "medium": {
                "invalidation": "Price drops 20% from entry or liquidity drops below $15k",
                "holding": "1-4 hours",
                "size_pct": 0.05,
            },
            "low": {
                "invalidation": "Price drops 25% from entry or liquidity drops below $15k",
                "holding": "2-8 hours",
                "size_pct": 0.02,
            },
        }
        cp = conf_params.get(confidence, conf_params["low"])

        # Get fill price from market snapshot
        fill_price = None
        if slim_market and slim_market.get("ok"):
            fill_price = slim_market.get("snapshot", {}).get("price_usd")

        messages.extend([
            # Step 5: signal_create
            {
                "role": "assistant", "content": None,
                "tool_calls": [{"id": signal_create_call_id, "type": "function",
                                "function": {"name": "signal_create",
                                             "arguments": json.dumps({
                                                 "agent_trading_decision_id": decision_id_str,
                                                 "confidence": confidence,
                                                 "invalidation_condition": cp["invalidation"],
                                                 "expected_holding_time": cp["holding"],
                                             })}}]
            },
            {"role": "tool", "tool_call_id": signal_create_call_id,
             "content": json.dumps({"ok": True, "artifact_id": signal_id_str,
                                     "signal_id": signal_id_str})},
            # Step 6: risk_check_entry
            {
                "role": "assistant", "content": None,
                "tool_calls": [{"id": risk_call_id, "type": "function",
                                "function": {"name": "risk_check_entry",
                                             "arguments": json.dumps({
                                                 "signal_id": signal_id_str,
                                             })}}]
            },
            {"role": "tool", "tool_call_id": risk_call_id,
             "content": json.dumps({"ok": True, "passed": True, "artifact_id": risk_id_str,
                                     "risk_check_id": risk_id_str,
                                     "approved_size_pct": cp["size_pct"]})},
            # Step 7: paper_create_order
            {
                "role": "assistant", "content": None,
                "tool_calls": [{"id": order_call_id, "type": "function",
                                "function": {"name": "paper_create_order",
                                             "arguments": json.dumps({
                                                 "signal_id": signal_id_str,
                                                 "risk_check_id": risk_id_str,
                                             })}}]
            },
            {"role": "tool", "tool_call_id": order_call_id,
             "content": json.dumps({"ok": True, "artifact_id": order_id_str,
                                     "order_id": order_id_str})},
            # Step 8: paper_simulate_fill
            {
                "role": "assistant", "content": None,
                "tool_calls": [{"id": fill_call_id, "type": "function",
                                "function": {"name": "paper_simulate_fill",
                                             "arguments": json.dumps({
                                                 "paper_order_id": order_id_str,
                                             })}}]
            },
            {"role": "tool", "tool_call_id": fill_call_id,
             "content": json.dumps({"ok": True, "filled": True,
                                     "fill_price": fill_price or "market",
                                     "artifact_id": str(uuid.uuid4())})},
        ])

    session = {
        "session_id": str(uuid.uuid4()),
        "signal_id": signal_id,
        "model": "claude-teacher",
        "provider": "claude",
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "elapsed_seconds": 0.0,
        "decision_recorded": True,
        "outcome_label": None,
        "messages": messages,
    }

    # Save
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_path = SESSIONS_DIR / f"{ts}_real_{session_index:03d}.json"
    out_path.write_text(json.dumps(session, indent=2, ensure_ascii=False), encoding="utf-8")
    return session


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser()
    parser.add_argument("--batch", type=int, default=0, help="Batch index (0-based)")
    parser.add_argument("--batch-size", type=int, default=20)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--all", action="store_true", help="Process all pairs")
    args = parser.parse_args()

    pairs = json.loads(PAIRS_FILE.read_text(encoding="utf-8"))
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)

    if args.all:
        batch_pairs = pairs
        start_idx = 0
    else:
        start = args.batch * args.batch_size
        end = start + args.batch_size
        batch_pairs = pairs[start:end]
        start_idx = start

    print(f"[gen] Processing {len(batch_pairs)} pairs (batch={args.batch}, workers={args.workers})")

    done = failed = 0

    def process(item):
        i, pair = item
        try:
            session = generate_session(pair, i)
            if session:
                # Find last tool_calls in messages to show decision
                decision = "?"
                for msg in reversed(session["messages"]):
                    tcs = msg.get("tool_calls") or []
                    for tc in tcs:
                        if tc["function"]["name"] == "agent_record_trading_decision":
                            decision = json.loads(tc["function"]["arguments"]).get("decision_type", "?")
                            break
                    if decision != "?":
                        break
                print(f"  [{i:03d}] {pair['wallet'][:16]}... {pair.get('symbol','?')} -> {decision}")
                return True
        except Exception as exc:
            print(f"  [{i:03d}] ERROR {pair['wallet'][:16]}...: {exc}")
        return False

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(process, (start_idx + i, pair)): i
                   for i, pair in enumerate(batch_pairs)}
        for fut in as_completed(futures):
            if fut.result():
                done += 1
            else:
                failed += 1

    print(f"[gen] Done: {done} sessions written, {failed} failed")


if __name__ == "__main__":
    main()
