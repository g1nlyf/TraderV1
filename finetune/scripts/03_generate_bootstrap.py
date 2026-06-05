"""
Script 03: Generate synthetic bootstrap examples for fine-tuning.

These examples ONLY teach FORMAT and tool call sequence — NOT trading strategy.
They ensure the fine-tuned model always:
  1. Calls wallet_profile_history first
  2. Calls token_get_profile second
  3. Always calls agent_record_trading_decision
  4. Has correct JSON schema for tool calls

We generate clear-cut cases: obviously bad (no_trade) and obviously good (signal).
The nuanced strategy gets learned from real data (teacher service outputs + outcomes).

Usage:
  python scripts/03_generate_bootstrap.py --count 100
  python scripts/03_generate_bootstrap.py --count 50 --only-format
"""
from __future__ import annotations

import json
import random
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SESSIONS_DIR = ROOT / "finetune" / "data" / "sessions"
TOOLS_FILE = ROOT / "finetune" / "config" / "tools.json"
PROMPTS_DIR = ROOT / "finetune" / "prompts"

TOOLS = json.loads(TOOLS_FILE.read_text(encoding="utf-8"))
SYSTEM_PROMPT = (PROMPTS_DIR / "teacher_system.md").read_text(encoding="utf-8")

# Scenario templates
SCENARIOS = [
    # (name, wallet_config, token_config, decision_type, reasoning_template)

    # Clear NO_TRADE scenarios
    ("insufficient_data", {
        "win_rate": 0.55, "trade_count": 3, "pnl": 450, "data_sufficiency": "insufficient",
        "quality_flags": ["insufficient_trade_history"]
    }, {
        "liquidity": 45000, "market_cap": 850000, "quality_flags": [],
    }, "no_trade",
     "Wallet has only {trade_count} trades — insufficient history to evaluate edge. "
     "Data sufficiency is 'insufficient'. Conservative no_trade."),

    ("low_win_rate", {
        "win_rate": 0.28, "trade_count": 12, "pnl": -1200, "data_sufficiency": "sufficient",
        "quality_flags": []
    }, {
        "liquidity": 65000, "market_cap": 2100000, "quality_flags": [],
    }, "no_trade",
     "Wallet win rate is {win_rate:.0%} across {trade_count} trades with negative net P&L. "
     "Below 40% threshold. No_trade."),

    ("stale_signal", {
        "win_rate": 0.61, "trade_count": 18, "pnl": 8400, "data_sufficiency": "sufficient",
        "quality_flags": []
    }, {
        "liquidity": 55000, "market_cap": 1500000, "quality_flags": [],
    }, "no_trade",
     "Wallet quality is good (61% win rate, 18 trades), but signal is {age_minutes} minutes old. "
     "Above 4-hour stale threshold. Price has likely moved. No_trade."),

    ("critical_quality_flags", {
        "win_rate": 0.68, "trade_count": 22, "pnl": 15000, "data_sufficiency": "sufficient",
        "quality_flags": []
    }, {
        "liquidity": 78000, "market_cap": 900000, "quality_flags": ["freeze_authority_active", "mutable_supply"],
    }, "no_trade",
     "Token has critical quality flags: freeze_authority_active, mutable_supply. "
     "Wallet is strong but token risk is unacceptable. No_trade."),

    ("low_liquidity", {
        "win_rate": 0.57, "trade_count": 14, "pnl": 5200, "data_sufficiency": "partial",
        "quality_flags": []
    }, {
        "liquidity": 8500, "market_cap": 180000, "quality_flags": ["low_liquidity_absolute"],
    }, "no_trade",
     "Token liquidity is only ${liquidity:,.0f} — below $15k minimum. "
     "Can't execute without extreme slippage. No_trade."),

    ("bot_wallet", {
        "win_rate": 0.85, "trade_count": 340, "pnl": 45000, "data_sufficiency": "sufficient",
        "quality_flags": ["bot_pattern", "high_frequency_trading"]
    }, {
        "liquidity": 120000, "market_cap": 3500000, "quality_flags": [],
    }, "no_trade",
     "Wallet shows bot pattern flags despite high win rate. "
     "Bot-like wallets are not copyable — they trade at machine speed. No_trade."),

    ("small_sample_borderline", {
        "win_rate": 0.43, "trade_count": 7, "pnl": 320, "data_sufficiency": "partial",
        "quality_flags": []
    }, {
        "liquidity": 38000, "market_cap": 720000, "quality_flags": [],
    }, "no_trade",
     "Wallet has {trade_count} trades at {win_rate:.0%} win rate — borderline with small sample. "
     "Insufficient evidence for confident signal. No_trade."),

    # Clear SIGNAL scenarios
    ("strong_wallet_good_token", {
        "win_rate": 0.64, "trade_count": 21, "pnl": 18500, "data_sufficiency": "sufficient",
        "quality_flags": []
    }, {
        "liquidity": 145000, "market_cap": 2800000, "quality_flags": [],
    }, "signal",
     "Wallet shows 64% win rate across 21 trades with $18,500 net P&L — strong evidence. "
     "Token has $145k liquidity, no quality flags, signal is {age_minutes} minutes old. "
     "Good entry conditions. Creating signal with medium confidence."),

    ("solid_track_record", {
        "win_rate": 0.71, "trade_count": 35, "pnl": 32000, "data_sufficiency": "sufficient",
        "quality_flags": []
    }, {
        "liquidity": 210000, "market_cap": 5200000, "quality_flags": [],
    }, "signal",
     "Wallet has 71% win rate on 35 trades — excellent track record. "
     "Token liquidity $210k, signal fresh at {age_minutes} minutes. High confidence signal."),

    ("good_wallet_decent_token", {
        "win_rate": 0.55, "trade_count": 12, "pnl": 6800, "data_sufficiency": "sufficient",
        "quality_flags": []
    }, {
        "liquidity": 52000, "market_cap": 1100000, "quality_flags": [],
    }, "signal",
     "Wallet: 55% win rate, 12 trades, positive P&L — meets minimum criteria. "
     "Token: $52k liquidity, no flags, signal {age_minutes} minutes old. "
     "Medium confidence signal given adequate but not exceptional wallet."),
]


def generate_wallet_address() -> str:
    chars = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
    return "".join(random.choices(chars, k=44))


def generate_token_address() -> str:
    chars = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
    return "".join(random.choices(chars, k=44))


def build_wallet_profile_result(wallet: str, wc: dict, age_minutes: int) -> dict:
    return {
        "tool": "wallet.profile_history",
        "ok": True,
        "artifact_id": f"wms_{uuid.uuid4().hex[:16]}",
        "confidence": "medium" if wc.get("data_sufficiency") == "sufficient" else "low",
        "quality_flags": wc.get("quality_flags", []),
        "profile": {
            "wallet": wallet,
            "win_rate_estimate": wc["win_rate"],
            "trade_count": wc["trade_count"],
            "closed_trade_count": max(1, wc["trade_count"] - 2),
            "net_pnl_estimate": wc["pnl"],
            "realized_pnl_estimate": wc["pnl"] * 0.9,
            "payoff_ratio": round(random.uniform(1.5, 3.5), 2),
            "average_win": round(wc["pnl"] / max(1, wc["trade_count"] * wc["win_rate"]) * 1.1, 0),
            "average_loss": round(abs(wc["pnl"]) / max(1, wc["trade_count"] * (1 - wc["win_rate"])) * 0.7, 0),
            "sample_size": wc["trade_count"],
            "data_sufficiency": wc.get("data_sufficiency", "partial"),
            "quality_flags": wc.get("quality_flags", []),
        },
        "data_as_of": "2026-01-15T10:00:00Z",
        "next_suggested_tools": ["token_get_profile"],
    }


def build_token_profile_result(token_mint: str, tc: dict) -> dict:
    return {
        "tool": "token.get_profile",
        "ok": True,
        "artifact_id": f"tp_{uuid.uuid4().hex[:16]}",
        "confidence": "medium",
        "quality_flags": tc.get("quality_flags", []),
        "profile": {
            "token_mint": token_mint,
            "market_cap": tc["market_cap"],
            "liquidity_usd": tc["liquidity"],
            "volume_24h": tc["liquidity"] * random.uniform(0.8, 4.0),
            "txns_1h": random.randint(15, 120),
            "holder_count": random.randint(200, 2000),
            "top_holder_concentration": round(random.uniform(0.05, 0.25), 3),
            "quality_flags": tc.get("quality_flags", []),
            "evidence_quality": "partial" if tc.get("quality_flags") else "good",
            "data_sufficiency": "partial",
            "source_freshness": "2026-01-15T09:55:00Z",
        },
        "data_as_of": "2026-01-15T09:55:00Z",
        "next_suggested_tools": ["agent_record_trading_decision"],
    }


def build_decision_result(signal_id: str, decision_type: str) -> dict:
    decision_id = f"atd_{uuid.uuid4().hex[:16]}"
    return {
        "tool": "agent.record_trading_decision",
        "ok": True,
        "artifact_id": decision_id,
        "confidence": "medium",
        "quality_flags": [],
        "agent_trading_decision": {
            "agent_trading_decision_id": decision_id,
            "decision_type": decision_type,
            "linked_tracked_wallet_signal_event_id": signal_id,
        },
        "next_suggested_tools": ["signal_create"] if decision_type == "signal" else [],
        "data_as_of": "2026-01-15T10:01:00Z",
    }


def build_signal_result(decision_id: str) -> dict:
    signal_id = f"sig_{uuid.uuid4().hex[:16]}"
    return {
        "tool": "signal.create",
        "ok": True,
        "artifact_id": signal_id,
        "signal_id": signal_id,
        "confidence": "medium",
        "quality_flags": [],
        "next_suggested_tools": ["risk_check_entry"],
        "data_as_of": "2026-01-15T10:01:30Z",
    }


def build_risk_result(signal_id: str, passed: bool = True) -> dict:
    risk_id = f"rc_{uuid.uuid4().hex[:16]}"
    return {
        "tool": "risk.check_entry",
        "ok": True,
        "artifact_id": risk_id,
        "confidence": "high",
        "quality_flags": [] if passed else ["entry_risk_vetoed"],
        "blocked_reason": None if passed else "position_limit_reached",
        "risk_check": {"risk_check_id": risk_id, "passed": 1 if passed else 0},
        "next_suggested_tools": ["paper_create_order"] if passed else [],
        "data_as_of": "2026-01-15T10:01:45Z",
    }


def build_order_result(signal_id: str, risk_id: str) -> dict:
    order_id = f"po_{uuid.uuid4().hex[:16]}"
    return {
        "tool": "paper.create_order",
        "ok": True,
        "artifact_id": order_id,
        "confidence": "high",
        "quality_flags": [],
        "next_suggested_tools": ["paper_simulate_fill"],
        "data_as_of": "2026-01-15T10:01:50Z",
    }


def build_fill_result(order_id: str) -> dict:
    fill_id = f"pf_{uuid.uuid4().hex[:16]}"
    position_id = f"pp_{uuid.uuid4().hex[:16]}"
    return {
        "tool": "paper.simulate_fill",
        "ok": True,
        "artifact_id": fill_id,
        "paper_position_id": position_id,
        "confidence": "high",
        "quality_flags": [],
        "next_suggested_tools": [],
        "data_as_of": "2026-01-15T10:02:00Z",
    }


def generate_example(scenario: tuple, idx: int) -> dict:
    name, wc, tc, decision_type, reasoning_tpl = scenario
    wallet = generate_wallet_address()
    token_mint = generate_token_address()
    signal_id = f"twse_{uuid.uuid4().hex[:16]}"
    age_minutes = random.randint(5, 50) if decision_type == "signal" else random.randint(250, 400) if name == "stale_signal" else random.randint(10, 60)

    reasoning = reasoning_tpl.format(
        win_rate=wc["win_rate"],
        trade_count=wc["trade_count"],
        pnl=wc["pnl"],
        liquidity=tc["liquidity"],
        market_cap=tc["market_cap"],
        age_minutes=age_minutes,
    )

    user_msg = (
        f"AUTONOMOUS SIGNAL REVIEW\n\n"
        f"Signal event:\n"
        f"  tracked_wallet_signal_event_id: {signal_id}\n"
        f"  wallet: {wallet}\n"
        f"  token_mint: {token_mint}\n"
        f"  side: buy\n"
        f"  observed_at: 2026-01-15T{9 + idx % 8:02d}:{random.randint(0, 59):02d}:00Z\n"
        f"  source: live_monitor\n"
        f"  data_sufficiency: {wc.get('data_sufficiency', 'partial')}\n\n"
        f"Execute the required tool sequence and record your decision."
    )

    wallet_result = build_wallet_profile_result(wallet, wc, age_minutes)
    wallet_artifact_id = wallet_result["artifact_id"]

    token_result = build_token_profile_result(token_mint, tc)
    token_artifact_id = token_result["artifact_id"]

    decision_args = {
        "linked_tracked_wallet_signal_event_id": signal_id,
        "decision_type": decision_type,
        "pre_action_reasoning": reasoning,
        "evidence_refs": [wallet_artifact_id, token_artifact_id],
        "uncertainties": [],
    }
    decision_result = build_decision_result(signal_id, decision_type)
    decision_id = decision_result["artifact_id"]

    def tc_id(n: int = 0) -> str:
        return f"call_{uuid.uuid4().hex[:20]}"

    messages: list[dict] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_msg},
        {
            "role": "assistant",
            "tool_calls": [{
                "id": (cid1 := tc_id()),
                "type": "function",
                "function": {"name": "wallet_profile_history", "arguments": json.dumps({"wallet": wallet})},
            }],
        },
        {"role": "tool", "tool_call_id": cid1, "content": json.dumps(wallet_result)},
        {
            "role": "assistant",
            "tool_calls": [{
                "id": (cid2 := tc_id()),
                "type": "function",
                "function": {"name": "token_get_profile", "arguments": json.dumps({"token_mint": token_mint})},
            }],
        },
        {"role": "tool", "tool_call_id": cid2, "content": json.dumps(token_result)},
        {
            "role": "assistant",
            "tool_calls": [{
                "id": (cid3 := tc_id()),
                "type": "function",
                "function": {"name": "agent_record_trading_decision", "arguments": json.dumps(decision_args)},
            }],
        },
        {"role": "tool", "tool_call_id": cid3, "content": json.dumps(decision_result)},
    ]

    # Add signal path if decision is "signal"
    if decision_type == "signal":
        signal_result = build_signal_result(decision_id)
        sig_id = signal_result["signal_id"]
        risk_result = build_risk_result(sig_id, passed=True)
        risk_id = risk_result["artifact_id"]
        order_result = build_order_result(sig_id, risk_id)
        order_id = order_result["artifact_id"]
        fill_result = build_fill_result(order_id)

        sig_args = {"agent_trading_decision_id": decision_id, "token_id": token_mint,
                    "confidence": "medium", "invalidation_condition": "Liquidity drops below $15k",
                    "expected_holding_time": "1-4 hours"}
        risk_args = {"signal_id": sig_id}
        order_args = {"signal_id": sig_id, "risk_check_id": risk_id,
                      "agent_trading_decision_id": decision_id}
        fill_args = {"paper_order_id": order_id, "agent_trading_decision_id": decision_id}

        cid4, cid5, cid6, cid7 = tc_id(), tc_id(), tc_id(), tc_id()
        messages += [
            {"role": "assistant", "tool_calls": [{"id": cid4, "type": "function", "function": {"name": "signal_create", "arguments": json.dumps(sig_args)}}]},
            {"role": "tool", "tool_call_id": cid4, "content": json.dumps(signal_result)},
            {"role": "assistant", "tool_calls": [{"id": cid5, "type": "function", "function": {"name": "risk_check_entry", "arguments": json.dumps(risk_args)}}]},
            {"role": "tool", "tool_call_id": cid5, "content": json.dumps(risk_result)},
            {"role": "assistant", "tool_calls": [{"id": cid6, "type": "function", "function": {"name": "paper_create_order", "arguments": json.dumps(order_args)}}]},
            {"role": "tool", "tool_call_id": cid6, "content": json.dumps(order_result)},
            {"role": "assistant", "tool_calls": [{"id": cid7, "type": "function", "function": {"name": "paper_simulate_fill", "arguments": json.dumps(fill_args)}}]},
            {"role": "tool", "tool_call_id": cid7, "content": json.dumps(fill_result)},
        ]

    return {
        "messages": messages,
        "tools": TOOLS,
        "_meta": {"scenario": name, "decision_type": decision_type, "synthetic": True},
    }


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Generate bootstrap training examples")
    parser.add_argument("--count", type=int, default=100)
    args = parser.parse_args()

    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    out_file = ROOT / "finetune" / "data" / "training" / "bootstrap.jsonl"
    out_file.parent.mkdir(parents=True, exist_ok=True)

    examples = []
    for i in range(args.count):
        scenario = random.choice(SCENARIOS)
        ex = generate_example(scenario, i)
        examples.append(ex)

    # Count decision types
    signals = sum(1 for e in examples if e["_meta"]["decision_type"] == "signal")
    no_trades = sum(1 for e in examples if e["_meta"]["decision_type"] == "no_trade")

    # Strip _meta before writing (OpenAI fine-tuning rejects unknown keys)
    clean = [{"messages": e["messages"], "tools": e["tools"]} for e in examples]

    with out_file.open("w", encoding="utf-8") as f:
        for ex in clean:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")

    print(f"[bootstrap] Generated {len(examples)} examples → {out_file.relative_to(ROOT)}")
    print(f"[bootstrap] signal={signals} no_trade={no_trades}")
    print("[bootstrap] These examples teach FORMAT only — not trading strategy.")
    print("[bootstrap] Use teacher_service.py for real labeled training data.")


if __name__ == "__main__":
    main()
