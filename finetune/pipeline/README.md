# TraderV1 ML Pipeline

Outcome-driven training pipeline. Implements blueprint §D
(`docs/strategy/2026-05-30-hidden-gems-and-blueprint.md`).

Operates on REAL data: `WalletScarper/data/stage2_foundation.sqlite3`.
Point-in-time discipline everywhere: features use data ≤ decision time, labels use data after.

## Modules

| Module | Role | Status |
|---|---|---|
| `decision_record.py` | Atomic dataset unit, schema v2.0 + text-to-text SFT projection | ✅ works |
| `wallet_features.py` | Behavioral engine (axes, form hot/cold, survivorship guard) | ✅ works on real wallets (92/67/66 snapshots) |
| `realistic_exit.py` | Honest reward: P&L under invalidation+holding, not max-price | ✅ works on real price paths |
| `replay_engine.py` | Historical replay → outcome-labelled Decision Records (#38) | ✅ ready, **data-starved today** |
| `backtest_harness.py` | Deploy gate: net-expectancy proxy, signal precision, off-policy | ✅ works (210 labelled) |

## Run

```bash
PY=C:/Users/hacke/AppData/Local/Python/bin/python.exe

# smoke-test modules on real DB
$PY -m finetune.pipeline.decision_record
$PY -m finetune.pipeline.wallet_features
$PY -m finetune.pipeline.realistic_exit

# replay corpus truth
$PY -m finetune.pipeline.replay_engine --report
# emit replay training data (once price paths exist)
$PY -m finetune.pipeline.replay_engine --emit-sft finetune/data/training/train_replay.jsonl

# DEPLOY GATE — score any policy
$PY -m finetune.pipeline.backtest_harness --policy recorded                      # formula baseline
$PY -m finetune.pipeline.backtest_harness --policy tuned --endpoint <ENDPOINT>   # candidate
$PY -m finetune.pipeline.backtest_harness --policy tuned --endpoint <E> --gate-baseline -0.0119
```

## Key findings (2026-05-30)

- **Formula baseline is unprofitable.** Backtest: `net_expectancy_proxy = -0.0119`,
  signal_precision = 0.377 (61 signals → 23 win / 38 loss). Training to imitate it
  (v1) inherits negative expectancy. → reward-filtered v2 drops the 33 losing signals.
- **Wallet engine catches the win-rate trap.** Wallet `GxDC9e…`: 62% WR, 4591 trades,
  but payoff 0.0002x, net −$83M → `edge=0.0`. Distinguished from `44zas…` (payoff 130x, edge=1.0).
- **Realistic-exit ≠ max-price.** Token `6veQU7…`: medium-confidence signal hits stop at
  −20% → label `loss`, not the inflated `excellent` a max-price label would give.

## BINDING CONSTRAINT (the one thing blocking scale)

Replay (the data unlock #38) needs **price paths** for the tokens in the outcome corpus.
Today: 891 outcome events have `entry_time`, but **0** have a future price path in
`market_snapshots` (only ~3 real tokens have multi-point paths).

→ **Next data action:** backfill historical prices (DexScreener/Birdeye) for the 891
outcome tokens. This is where the parallel-collection fabric (idea B.3) plugs in:
one shared price-poll per token, hundreds of tokens in parallel. Once paths exist,
`replay_engine` emits thousands of honest labels overnight → DPO/RL phases unlock.

The pipeline is built and correct. The constraint is data coverage, not modelling.

## Training ladder (S4)

1. **Ф1 SFT (bootstrap)** — `build_reward_filtered_dataset.py` → Vertex SFT. ✅ v2 shipped.
2. **Ф3 DPO** — losses saved in `data/training/losses_for_dpo.jsonl` (rejected side). Needs custom trainer (Vertex SFT lacks DPO).
3. **Ф4 offline-RL** — replay corpus once price-paths backfilled.

Every promotion gated by `backtest_harness`.
