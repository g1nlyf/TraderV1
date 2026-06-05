"""
Generate 20 synthetic "high confidence" training sessions with outcome_label="excellent".

These sessions represent ELITE wallet + perfect timing scenarios — the gold standard
for the model to learn HIGH confidence signals (composite >= 0.72).

They are hand-crafted with realistic but slightly idealized parameters:
  - Wallets: elite track record (WR 65-72%, payoff 3.5-6x, net PnL +$15k-$80k, 80-250 trades)
  - Tokens: solid liquidity ($60k-$200k), good mcap ($1M-$12M), clean flags
  - Timing: fresh signals (2-15min old), early momentum (+5-18% 1h), dominant buys (8:1+)

All 20 sessions follow the FULL tool sequence:
  wallet_profile_history → token_get_profile → market_get_token_snapshot
  → agent_record_trading_decision → signal_create → risk_check_entry
  → paper_create_order → paper_simulate_fill

Written to finetune/data/sessions/synth_YYYYMMDD_HHMMSS_NNN.json
with outcome_label = "excellent"

Usage:
  python finetune/scripts/generate_synthetic_high_conf.py
  python finetune/scripts/generate_synthetic_high_conf.py --count 20 --output-dir finetune/data/sessions/
"""
from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]

ROOT = Path(__file__).resolve().parents[2]
SESSIONS_DIR = ROOT / "finetune" / "data" / "sessions"
PROMPTS_DIR = ROOT / "finetune" / "prompts"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_call_id() -> str:
    return "call_" + uuid.uuid4().hex[:8]


def make_uuid() -> str:
    return str(uuid.uuid4())


def load_system_prompt() -> str:
    path = PROMPTS_DIR / "teacher_system.md"
    if not path.exists():
        print(f"[synth] WARNING: teacher_system.md not found at {path}. Using placeholder.")
        return "# Teacher Model System Prompt\n\nYou are an autonomous signal reviewer for TraderV1."
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 20 hand-crafted scenario parameters
#
# Fields:
#   wallet_addr, token_mint, token_symbol,
#   win_rate, payoff, trade_count, net_pnl,
#   liquidity, market_cap, price_1h_pct, price_5m_pct,
#   buys_5m, sells_5m, signal_age_min,
#   price_usd, wallet_score, token_score, timing_score
#
# Composite = 0.40 * wallet + 0.35 * token + 0.25 * timing  -- must be >= 0.72
# ---------------------------------------------------------------------------

SCENARIOS = [
    # wallet_addr,                               token_mint,                                          symbol,      wr,   payoff, trades, net_pnl, liq,    mcap,     p1h,  p5m,  b5m, s5m, age_min, price_usd,          w_sc, t_sc, ti_sc
    ("9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM", "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263pump", "BONK2",  0.68, 4.2,  147, 22400,  89000,  3400000,   8.0,  1.2,  19,  3,  5,   "0.0000423",          0.88, 0.74, 0.61),
    ("7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU",  "FoXyMu5xwXre99MHSrS67j4oNjeBaLYHmNMCEfXF1pump",   "PEPO",   0.71, 3.8,  112,  18900,  72000,  2100000,  11.0,  2.1,  24,  2,  3,   "0.0000187",          0.85, 0.70, 0.68),
    ("HN7cABqLq46Es1jh92dQQisAq662SmxELLLsHHe4YWrH",  "6X9o8Qs37gCdNTYfA2AEVAtBsX1Qs6BCaVA5m9PVKpump",  "MOGU",   0.65, 5.1,  203,  47300, 145000,  6200000,   5.5,  0.9,  31,  3,  7,   "0.000298",           0.90, 0.85, 0.58),
    ("BkXp7vxmGqeSmJzBq8jY28Fd67StbYrg5Zv1v2KFi8AA",  "9zBZspVHCaJ2N3vJNoz6PFi3AzRsCkH9J2dSMV7qNMpump",  "SOLCAT", 0.69, 4.6,  158,  34200, 112000,  4800000,  13.0,  1.8,  28,  2,  4,   "0.00000891",         0.87, 0.79, 0.65),
    ("3rFf6XPsyMFv9XBVDQ4yXUWmPKjNLjqFVvNDKsLyeVV",  "EHDaGybHUV8qm5tPxoFJX9jBX7H87wBbMWNEpnZ9gpump",  "WUFU",   0.67, 5.5,  89,   28700,  67000,  1900000,   7.2,  1.4,  16,  1,  9,   "0.0000671",          0.91, 0.69, 0.59),
    ("GPFXsFMQxiSMpCsXNxb44pGGQkpS2L94DZGPSzeBfAk1",  "AoXQ78mLVkzSwV7CwKNNzfXFJgBpCfZ4wRhNjX8Ypump",   "FLUFF",  0.70, 4.0,  175,  19800,  98000,  3800000,   9.5,  1.7,  22,  2,  6,   "0.000413",           0.86, 0.76, 0.63),
    ("5oNDL3swdV18YZ2NQ31b3eFDzUaLF9NKehCBQKV9sump1",  "BuMp9sJRhKcNpXhWYV3m8gGqFmw7EF5jZHnPJMR6pump",   "PUPPY",  0.66, 4.8,  221,  56100, 134000,  5500000,   6.0,  1.1,  35,  4,  2,   "0.0000145",          0.89, 0.82, 0.71),
    ("2KmVpxVfZNKRePc3uQZNUovfz2PamkSNpfJzpJJhUkiS",  "PuMpSrVhTm3NRXqwQ5dJBkY7a1oKZxLhXgV9CfZ2pump",  "MAGA2",  0.72, 3.6,  94,   15600,  78000,  2700000,  14.0,  2.3,  18,  1,  11,  "0.0000083",          0.84, 0.72, 0.60),
    ("DqNGXZD6szp3YpxgeTLbvwdktUGVHKqQX3wkqJQ7Mump",  "CaFeMoRningZBQnN9pxJxRd3sFm6zLhtXVbAkG7Vpump",   "WAGMI",  0.68, 5.3,  131,  39800,  156000, 7100000,   4.8,  0.8,  27,  3,  8,   "0.00000722",         0.92, 0.88, 0.56),
    ("eLo7KzFmQ9Wp3YxBvRjA4gNdHcSt8XuVi2nT5pJkMump", "RaMpToTheMooN8xKzQpFrG3mBhYTw6VjLNsd7Cpump",     "RAMP",   0.71, 4.1,  168,  24300,  91000,  3300000,  10.5,  1.9,  21,  2,  5,   "0.000156",           0.86, 0.75, 0.64),
    ("SoLaNaMoNkeYs7uXvBw4nHJREqQ3kLFTdZpCgMpump1X",  "KiNgDomEkZ9pXhVmQrJbT4nFwA6oYRsMuGCpump12",      "KDOM",   0.67, 4.9,  143,  32100, 118000,  4300000,   7.8,  1.5,  29,  3,  3,   "0.0000931",          0.88, 0.80, 0.69),
    ("F4QuMZ8jBRsLT9GXaePyc6hVkSnW3HdmNKoJupumpZx2",  "LiFeIsGudMrBagsToTheMoOnQpXz7Ckpump93Nw",        "LIFE",   0.70, 3.9,  186,  21500,  85000,  3100000,  12.3,  2.0,  23,  2,  7,   "0.0000218",          0.85, 0.73, 0.62),
    ("xBnHkJ7rPcVYe29qLGd4tSmWa1FKouMnZpump8TRv5",   "MeAtBaLLsAnDSaUceJKwZ9pumpXvRnLT4GhMc7o",        "SAUCY",  0.65, 5.8,  97,   44700,  162000, 8900000,   3.9,  0.7,  38,  4,  2,   "0.000047",           0.92, 0.87, 0.72),
    ("nVpZ4oWcHeS7LtRkF3yXuA8JmBqGdM9IePump2CxU1",   "ToKeNsRaInAnDSuNsHiNeJKzW9pump4VxRLnT8mGc",      "RAIN",   0.69, 4.4,  124,  27800,  74000,  2400000,   8.5,  1.6,  17,  1,  10,  "0.0000562",          0.87, 0.71, 0.60),
    ("kZ2SoLBeAmWaVe7MrPumpHjXqF5RcNoYLd3IeT9Vux4",  "BeAmS4UrFiNgFoRwArD8pJzXkm6Bpump2hQvLtNcRs",    "BEAM",   0.68, 4.7,  210,  38500, 108000,  5100000,   6.7,  1.3,  33,  3,  4,   "0.0000178",          0.88, 0.78, 0.67),
    ("mPqRx9TbV3uWoYsJeHpumpLcZdN5GaF8kI2KnXC7OA1",  "AlPhAbEtSoUpPumpXzVwK7LmN9qBhRjT4GcFe3pump",    "ALPHA",  0.71, 3.7,  155,  16900,  93000,  3600000,  11.8,  2.2,  20,  2,  6,   "0.000311",           0.84, 0.75, 0.63),
    ("rJcUm4Hy7qXvT8Bz9WsKpumpNeGd2FaL5oIPx6MVn3",   "CrYpToChAdZ6pumpYbXkV4NmRwT9qGeLhJ8FsSu1Bc",    "CHAD",   0.67, 5.0,  138,  29300, 127000,  5800000,   5.2,  1.0,  26,  2,  8,   "0.0000821",          0.89, 0.83, 0.59),
    ("tYoLpA2mV8XqBzH9UkpumpReF5GwJnS6dC4IeN3Kb7",   "dEgEnSeAsOnZ9pumpKqV3MxRwT6LyGePh4FcBs8Nj1",    "DEGEN",  0.66, 5.6,  89,   51200, 139000,  6600000,   4.1,  0.8,  32,  3,  3,   "0.0000093",          0.91, 0.84, 0.71),
    ("wQsZA5nX7kLpV3uBoPumpGcJ8MhYeF9dT2RiN6Cm4e1",  "vIbEcHeCkPumPRaTiOnQrX5Nm3LzKjA8GsF6wT9Yp",    "VIBE",   0.70, 4.3,  192,  23600,  81000,  2900000,   9.1,  1.8,  24,  2,  5,   "0.000204",           0.86, 0.73, 0.65),
    ("yHnV4bKjZ8mRuPumpXcT7GqLeS9Fo3WiAN5dpC2B6a1",  "sUpErDoGeShiBaZ4pumpVxKm9QrTwL6NjBeF3gCsH8",    "SDOG",   0.68, 4.5,  161,  30100,  99000,  4000000,   7.5,  1.4,  25,  2,  6,   "0.0000347",          0.87, 0.76, 0.63),
]


# ---------------------------------------------------------------------------
# Session builder
# ---------------------------------------------------------------------------

def build_session(
    scenario: tuple,
    system_prompt: str,
    ts: datetime,
    index: int,
) -> dict:
    (
        wallet_addr, token_mint, token_symbol,
        win_rate, payoff, trade_count, net_pnl,
        liquidity, market_cap, price_1h_pct, price_5m_pct,
        buys_5m, sells_5m, signal_age_min,
        price_usd, wallet_score, token_score, timing_score,
    ) = scenario

    composite = round(0.40 * wallet_score + 0.35 * token_score + 0.25 * timing_score, 2)

    session_id = make_uuid()
    signal_event_id = f"synth_{uuid.uuid4().hex[:16]}"
    ts_str = ts.strftime("%Y-%m-%dT%H:%M:%SZ")

    # Pre-compute UUIDs for artifacts
    decision_id = make_uuid()
    sig_id = make_uuid()
    risk_id = make_uuid()
    order_id = make_uuid()
    fill_id = make_uuid()

    # Call IDs
    cid_wallet = make_call_id()
    cid_token = make_call_id()
    cid_market = make_call_id()
    cid_decision = make_call_id()
    cid_signal = make_call_id()
    cid_risk = make_call_id()
    cid_order = make_call_id()
    cid_fill = make_call_id()

    # Wallet description word based on score
    wallet_tier = "elite" if wallet_score >= 0.88 else "strong"

    # Net PnL formatted
    net_pnl_str = f"+${net_pnl:,.0f}"

    # Liquidity formatted
    liq_k = liquidity / 1000
    mcap_m = market_cap / 1_000_000

    # Timing freshness description
    if signal_age_min <= 5:
        freshness_desc = "very fresh, minimal price movement"
    elif signal_age_min <= 10:
        freshness_desc = "fresh entry window, early momentum"
    else:
        freshness_desc = "early momentum, signal still actionable"

    # Reasoning
    reasoning = (
        f"Composite score {composite:.2f} → high confidence signal. "
        f"Wallet ({wallet_score:.2f}): {win_rate*100:.0f}% WR across {trade_count} trades, "
        f"{payoff:.1f}x payoff, net P&L {net_pnl_str} — {wallet_tier} execution. "
        f"Token ({token_score:.2f}): ${liq_k:.0f}k liquidity, ${mcap_m:.1f}M mcap, clean flags. "
        f"Timing ({timing_score:.2f}): +{price_1h_pct:.1f}% 1h, {buys_5m}/{buys_5m + sells_5m} buys "
        f"in 5min, signal {signal_age_min}min old — {freshness_desc}. "
        f"{'Elite wallet score drives decision.' if wallet_tier == 'elite' else 'Strong wallet combined with clean token profile and early timing.'}"
    )

    # Wallet tool response
    wallet_resp = {
        "ok": True,
        "wallet": wallet_addr,
        "profile": {
            "win_rate_estimate": win_rate,
            "trade_count": trade_count,
            "net_pnl_estimate": float(net_pnl),
            "payoff_ratio": payoff,
            "data_sufficiency": "sufficient",
            "quality_flags": ["historical_wallet_pnl_is_not_future_edge_proof"],
        },
        "confidence": "high",
        "data_as_of": ts_str,
    }

    # Token tool response
    token_resp = {
        "ok": True,
        "token_mint": token_mint,
        "profile": {
            "liquidity_usd": float(liquidity),
            "market_cap": float(market_cap),
            "volume_24h": float(market_cap * 0.08),
            "data_sufficiency": "sufficient",
            "evidence_quality": "high",
            "latest_observed_at": ts_str,
        },
        "quality_flags": [],
        "confidence": "high",
        "data_as_of": ts_str,
    }

    # Market snapshot response
    market_resp = {
        "ok": True,
        "token_mint": token_mint,
        "snapshot": {
            "symbol": token_symbol,
            "price_usd": price_usd,
            "price_change_5m": price_5m_pct,
            "price_change_1h": price_1h_pct,
            "price_change_24h": price_1h_pct * 2.1,
            "liquidity_usd": float(liquidity),
            "market_cap": float(market_cap),
            "txns_5m_buys": buys_5m,
            "txns_5m_sells": sells_5m,
            "pair_created_at": int(ts.timestamp() * 1000) - 7200000,  # 2h ago
            "dex": "pumpswap",
        },
        "confidence": "high",
        "data_as_of": ts_str,
    }

    # Decision response
    decision_resp = {
        "ok": True,
        "artifact_id": decision_id,
        "decision_id": decision_id,
    }

    # Signal create response
    signal_resp = {
        "ok": True,
        "artifact_id": sig_id,
        "signal_id": sig_id,
    }

    # Risk check response
    risk_resp = {
        "ok": True,
        "passed": True,
        "artifact_id": risk_id,
        "risk_check_id": risk_id,
        "approved_size_pct": 0.08,
        "position_limit_ok": True,
        "exposure_ok": True,
        "liquidity_ok": True,
    }

    # Paper order response
    order_resp = {
        "ok": True,
        "artifact_id": order_id,
        "order_id": order_id,
    }

    # Fill response
    fill_resp = {
        "ok": True,
        "filled": True,
        "fill_price": price_usd,
        "artifact_id": fill_id,
    }

    messages = [
        {
            "role": "system",
            "content": system_prompt,
        },
        {
            "role": "user",
            "content": (
                f"AUTONOMOUS SIGNAL REVIEW\n\n"
                f"Signal event:\n"
                f"  tracked_wallet_signal_event_id: {signal_event_id}\n"
                f"  wallet: {wallet_addr}\n"
                f"  token_mint: {token_mint}\n"
                f"  side: buy\n"
                f"  observed_at: {ts_str}\n\n"
                f"Execute the required tool sequence and record your decision."
            ),
        },
        # Step 1 — wallet_profile_history
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [{
                "id": cid_wallet,
                "type": "function",
                "function": {
                    "name": "wallet_profile_history",
                    "arguments": json.dumps({"wallet": wallet_addr}),
                },
            }],
        },
        {
            "role": "tool",
            "tool_call_id": cid_wallet,
            "content": json.dumps(wallet_resp),
        },
        # Step 2 — token_get_profile
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [{
                "id": cid_token,
                "type": "function",
                "function": {
                    "name": "token_get_profile",
                    "arguments": json.dumps({"token_mint": token_mint}),
                },
            }],
        },
        {
            "role": "tool",
            "tool_call_id": cid_token,
            "content": json.dumps(token_resp),
        },
        # Step 3 — market_get_token_snapshot
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [{
                "id": cid_market,
                "type": "function",
                "function": {
                    "name": "market_get_token_snapshot",
                    "arguments": json.dumps({"token_mint": token_mint}),
                },
            }],
        },
        {
            "role": "tool",
            "tool_call_id": cid_market,
            "content": json.dumps(market_resp),
        },
        # Step 4 — agent_record_trading_decision
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [{
                "id": cid_decision,
                "type": "function",
                "function": {
                    "name": "agent_record_trading_decision",
                    "arguments": json.dumps({
                        "decision_type": "signal",
                        "pre_action_reasoning": reasoning,
                        "linked_tracked_wallet_signal_event_id": signal_event_id,
                    }),
                },
            }],
        },
        {
            "role": "tool",
            "tool_call_id": cid_decision,
            "content": json.dumps(decision_resp),
        },
        # Step 5a — signal_create
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [{
                "id": cid_signal,
                "type": "function",
                "function": {
                    "name": "signal_create",
                    "arguments": json.dumps({
                        "agent_trading_decision_id": decision_id,
                        "confidence": "high",
                        "invalidation_condition": "Price drops 15% from entry or liquidity drops below $20k",
                        "expected_holding_time": "30-90 minutes",
                    }),
                },
            }],
        },
        {
            "role": "tool",
            "tool_call_id": cid_signal,
            "content": json.dumps(signal_resp),
        },
        # Step 5b — risk_check_entry
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [{
                "id": cid_risk,
                "type": "function",
                "function": {
                    "name": "risk_check_entry",
                    "arguments": json.dumps({"signal_id": sig_id}),
                },
            }],
        },
        {
            "role": "tool",
            "tool_call_id": cid_risk,
            "content": json.dumps(risk_resp),
        },
        # Step 5c — paper_create_order
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [{
                "id": cid_order,
                "type": "function",
                "function": {
                    "name": "paper_create_order",
                    "arguments": json.dumps({
                        "signal_id": sig_id,
                        "risk_check_id": risk_id,
                    }),
                },
            }],
        },
        {
            "role": "tool",
            "tool_call_id": cid_order,
            "content": json.dumps(order_resp),
        },
        # Step 5d — paper_simulate_fill
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [{
                "id": cid_fill,
                "type": "function",
                "function": {
                    "name": "paper_simulate_fill",
                    "arguments": json.dumps({"paper_order_id": order_id}),
                },
            }],
        },
        {
            "role": "tool",
            "tool_call_id": cid_fill,
            "content": json.dumps(fill_resp),
        },
    ]

    return {
        "session_id": session_id,
        "signal_id": signal_event_id,
        "model": "synthetic",
        "provider": "synthetic",
        "timestamp": ts_str,
        "elapsed_seconds": 0.0,
        "decision_recorded": True,
        "outcome_label": "excellent",
        "messages": messages,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def generate(count: int, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    system_prompt = load_system_prompt()

    scenarios_to_use = SCENARIOS[:count]
    if len(scenarios_to_use) < count:
        print(f"[synth] WARNING: requested {count} but only {len(SCENARIOS)} scenarios defined. Generating {len(scenarios_to_use)}.")

    ts_base = datetime.now(timezone.utc)
    date_prefix = ts_base.strftime("%Y%m%d_%H%M%S")

    written = 0
    for i, scenario in enumerate(scenarios_to_use):
        session = build_session(scenario, system_prompt, ts_base, i)
        filename = output_dir / f"synth_{date_prefix}_{i:03d}.json"
        filename.write_text(json.dumps(session, indent=2, ensure_ascii=False), encoding="utf-8")
        token_symbol = scenario[2]
        composite = round(0.40 * scenario[15] + 0.35 * scenario[16] + 0.25 * scenario[17], 2)
        print(f"[synth] [{i+1:02d}/{len(scenarios_to_use)}] {filename.name}  symbol={token_symbol}  composite={composite:.2f}  outcome=excellent")
        written += 1

    print(f"\n[synth] Done. {written} sessions written to {output_dir.relative_to(ROOT)}")
    print(f"[synth] All sessions: outcome_label=excellent, confidence=high, composite>=0.72")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate synthetic high-confidence training sessions for TraderV1 SFT",
    )
    parser.add_argument("--count", type=int, default=20, help="Number of sessions to generate (max 20)")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=SESSIONS_DIR,
        help=f"Directory to write session JSON files (default: {SESSIONS_DIR})",
    )
    args = parser.parse_args()

    if args.count < 1 or args.count > len(SCENARIOS):
        parser.error(f"--count must be between 1 and {len(SCENARIOS)}")

    print(f"[synth] Generating {args.count} synthetic high-confidence sessions...")
    print(f"[synth] Output dir: {args.output_dir}")
    generate(args.count, args.output_dir)


if __name__ == "__main__":
    main()
