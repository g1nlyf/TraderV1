"""
Phase 2: reads current paper trading balance and drawdown state from stage2 DB.
Used to inject budget context into model prompts so the model trades with real weight.
"""
from __future__ import annotations

import aiosqlite
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "WalletScarper" / "data" / "stage2_foundation.sqlite3"

STARTING_BUDGET_USD = 500.0
CIRCUIT_BREAKER_DRAWDOWN = 0.30  # halt at 30% drawdown from peak


async def get_budget_state() -> dict:
    """
    Returns current paper trading state:
      balance_usd       - current paper balance
      peak_balance_usd  - highest ever balance (for drawdown calc)
      drawdown_pct      - (peak - current) / peak
      open_positions    - count of open paper orders
      circuit_broken    - True if drawdown >= threshold
      position_size_usd - 5% of current balance (0 if circuit broken)
    """
    async with aiosqlite.connect(str(DB_PATH)) as db:
        db.row_factory = aiosqlite.Row

        # Sum all closed P&L to get realized gains/losses
        row = await db.execute_fetchall(
            """
            SELECT
                COALESCE(SUM(pnl_usd), 0) AS realized_pnl,
                COUNT(*) AS closed_count
            FROM paper_positions
            WHERE status = 'closed'
            """
        )
        realized_pnl = float(row[0]["realized_pnl"]) if row else 0.0

        # Sum unrealized from open positions (mark-to-market not available, use cost basis)
        open_row = await db.execute_fetchall(
            """
            SELECT COUNT(*) AS open_count,
                   COALESCE(SUM(size_usd), 0) AS open_exposure
            FROM paper_positions
            WHERE status = 'open'
            """
        )
        open_count = int(open_row[0]["open_count"]) if open_row else 0
        open_exposure = float(open_row[0]["open_exposure"]) if open_row else 0.0

    balance = STARTING_BUDGET_USD + realized_pnl
    peak = max(STARTING_BUDGET_USD, balance)  # simplified: peak = max of starting or current
    drawdown = (peak - balance) / peak if peak > 0 else 0.0
    circuit_broken = drawdown >= CIRCUIT_BREAKER_DRAWDOWN

    return {
        "balance_usd": round(balance, 2),
        "starting_budget_usd": STARTING_BUDGET_USD,
        "realized_pnl_usd": round(realized_pnl, 2),
        "peak_balance_usd": round(peak, 2),
        "drawdown_pct": round(drawdown * 100, 1),
        "open_positions": open_count,
        "open_exposure_usd": round(open_exposure, 2),
        "circuit_broken": circuit_broken,
        "position_size_usd": 0.0 if circuit_broken else round(balance * 0.05, 2),
    }


def format_budget_context(state: dict) -> str:
    """Format budget state as a context block injected into model prompt."""
    circuit_note = ""
    if state["circuit_broken"]:
        circuit_note = (
            f"\n⛔ CIRCUIT BREAKER ACTIVE — drawdown {state['drawdown_pct']}% exceeds 30% threshold. "
            "Record no_trade for ALL signals until balance recovers above circuit breaker level."
        )

    return (
        f"PAPER TRADING BUDGET STATE:\n"
        f"  Balance: ${state['balance_usd']:.2f} (started: ${state['starting_budget_usd']:.2f})\n"
        f"  P&L: ${state['realized_pnl_usd']:+.2f} | Drawdown: {state['drawdown_pct']}% from peak\n"
        f"  Open positions: {state['open_positions']} (${state['open_exposure_usd']:.2f} exposure)\n"
        f"  Position size per trade: ${state['position_size_usd']:.2f} (5% of balance)"
        f"{circuit_note}"
    )
