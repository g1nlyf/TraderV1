"""
CLI tool: show full context for a signal event.
Usage:
  python tools/review_context.py --list
  python tools/review_context.py --signal <id>
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "finetune"))

from tools.db_context import get_pending_signals, get_signal_full_context


def fmt_float(v: object, decimals: int = 2) -> str:
    if v is None:
        return "—"
    try:
        return f"{float(v):.{decimals}f}"
    except (TypeError, ValueError):
        return str(v)


def fmt_pct(v: object) -> str:
    if v is None:
        return "—"
    try:
        return f"{float(v) * 100:.1f}%"
    except (TypeError, ValueError):
        return str(v)


async def show_list() -> None:
    signals = await get_pending_signals(limit=30)
    if not signals:
        print("No pending signals.")
        return

    print(f"\n{'ID':<40} {'WALLET':<12} {'TOKEN':<12} {'SIDE':<5} {'AGE':>8} {'SUFFICIENCY'}")
    print("-" * 95)
    for s in signals:
        sid = str(s.get("tracked_wallet_signal_event_id") or "")[:38]
        wallet = str(s.get("wallet") or "")[:10] + ".."
        token = str(s.get("token_mint") or "")[:10] + ".."
        side = str(s.get("side") or "")
        age = s.get("age_minutes")
        age_str = f"{age:.0f}m" if age is not None else "?"
        suf = str(s.get("data_sufficiency") or "?")
        print(f"{sid:<40} {wallet:<12} {token:<12} {side:<5} {age_str:>8} {suf}")

    print(f"\nTotal pending: {len(signals)}")


async def show_signal(signal_id: str) -> None:
    ctx = await get_signal_full_context(signal_id)
    if "error" in ctx:
        print(f"[ERROR] {ctx['error']}")
        return

    event = ctx.get("signal_event") or {}
    wm = ctx.get("wallet_metrics") or {}
    wr = ctx.get("wallet_review") or {}
    tp = ctx.get("token_profile") or {}
    ps = ctx.get("portfolio_state") or {}
    rwd = ctx.get("recent_wallet_decisions") or []

    wallet = str(event.get("wallet") or "")
    token = str(event.get("token_mint") or "")

    print("\n" + "=" * 70)
    print("SIGNAL EVENT")
    print("=" * 70)
    print(f"  ID:          {event.get('tracked_wallet_signal_event_id')}")
    print(f"  Wallet:      {wallet}")
    print(f"  Token:       {token}")
    print(f"  Side:        {event.get('side')}")
    print(f"  Observed at: {event.get('observed_at')}")
    print(f"  Source:      {event.get('source_name')}")
    print(f"  Sufficiency: {event.get('data_sufficiency')}")

    print("\n" + "-" * 70)
    print("WALLET METRICS")
    print("-" * 70)
    if wm:
        print(f"  Win rate:    {fmt_pct(wm.get('win_rate_estimate'))}")
        print(f"  Trade count: {wm.get('trade_count')} (closed: {wm.get('closed_trade_count')})")
        print(f"  Net P&L est: ${fmt_float(wm.get('net_pnl_estimate'), 0)}")
        print(f"  Payoff ratio:{fmt_float(wm.get('payoff_ratio'))}")
        print(f"  Avg win:     ${fmt_float(wm.get('average_win'), 0)}")
        print(f"  Avg loss:    ${fmt_float(wm.get('average_loss'), 0)}")
        print(f"  Sample size: {wm.get('sample_size')}")
        print(f"  Sufficiency: {wm.get('data_sufficiency') or wm.get('evidence_quality')}")
        qf = wm.get("quality_flags") or []
        if qf:
            print(f"  Flags:       {', '.join(str(f) for f in qf)}")
    else:
        print("  (no metrics snapshot found)")

    if wr:
        print(f"\n  Agent review: {wr.get('decision')} | rating={fmt_float(wr.get('agent_rating'))}")
        why_yes = wr.get("why_yes") or []
        why_no = wr.get("why_no") or []
        if why_yes:
            print(f"  Why yes:  {why_yes[:2]}")
        if why_no:
            print(f"  Why no:   {why_no[:2]}")

    print("\n" + "-" * 70)
    print("TOKEN PROFILE")
    print("-" * 70)
    if tp:
        print(f"  Market cap:  ${fmt_float(tp.get('market_cap'), 0)}")
        print(f"  Liquidity:   ${fmt_float(tp.get('liquidity_usd'), 0)}")
        print(f"  Volume 24h:  ${fmt_float(tp.get('volume_24h'), 0)}")
        print(f"  Txns 1h:     {tp.get('txns_1h')}")
        print(f"  Holders:     {tp.get('holder_count')}")
        print(f"  Top conc:    {fmt_pct(tp.get('top_holder_concentration'))}")
        print(f"  Evidence:    {tp.get('evidence_quality')}")
        print(f"  Last seen:   {tp.get('latest_observed_at')}")
        qf = tp.get("quality_flags") or []
        if qf:
            print(f"  Flags:       {', '.join(str(f) for f in qf)}")
        else:
            print("  Flags:       none")
    else:
        print("  (no token profile found)")

    print("\n" + "-" * 70)
    print("PORTFOLIO STATE")
    print("-" * 70)
    print(f"  Open positions:    {ps.get('open_positions')}")
    print(f"  Decisions (last h):{ps.get('decisions_last_hour')}")

    if rwd:
        print("\n" + "-" * 70)
        print("RECENT DECISIONS ON THIS WALLET")
        print("-" * 70)
        for d in rwd:
            print(f"  [{d.get('created_at', '')[:16]}] {d.get('decision_type')}")
            r = str(d.get("pre_action_reasoning") or "")
            if r:
                print(f"    {r[:120]}")

    print("\n" + "=" * 70)


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Show signal context")
    parser.add_argument("--list", action="store_true", help="List all pending signals")
    parser.add_argument("--signal", help="Show full context for signal ID")
    args = parser.parse_args()

    if args.list:
        asyncio.run(show_list())
    elif args.signal:
        asyncio.run(show_signal(args.signal))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
