"""
TraderV1 ML pipeline package.

Stages (see docs/strategy/2026-05-30-hidden-gems-and-blueprint.md §D):
  decision_record   — atomic dataset unit (schema v2.0)
  wallet_features   — behavioral feature engine (A.1-A.6) from real tx metrics
  realistic_exit    — honest reward labeler (P&L under invalidation+holding, not max-price)
  replay_engine     — historical replay → Decision Records (#38, the data unlock)
  backtest_harness  — policy eval + off-policy estimate, the deploy gate (#27/#45)

All modules operate on REAL data from WalletScarper/data/stage2_foundation.sqlite3.
Point-in-time discipline: features use data <= decision time, labels use data after.
"""

SCHEMA_VERSION = "2.0"
