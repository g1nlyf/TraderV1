# H-162 Day-Level Persistence — Status (Sprint 7, 2026-06-06)

**Question:** does the H-162 quality-wallet distribution signal persist across calendar DAYS/regimes?

## Status: STILL UNRESOLVED (cross-day untestable on current data)
- Organic on-chain data remains effectively **one session** (raw_trades = 2026-05-14, 5.5h). Intra-session
  persistence HOLDS (walk-forward +7.7% over base, perm 0.000 — see H162_PERSISTENCE_REPORT.md), but that
  cannot separate cross-sectional skill from a single down-regime.
- The free firehose (`firehose_collector.py`) is built and verified, but at current settings yields
  **~0.5 sell-cluster events/day** (GeckoTerminal free: ~40 pools/tick, heavy token overlap across ticks).
  The day-level gate needs **≥100 independent sell-cluster events/day across ≥14 days**. → not met, not close.

## Why GeckoTerminal free is too thin (operational truth)
The May-14 reference firehose (Bitquery Corecast) captured **803K trades / 12,318 tokens / 5.5h** → ~975
sell-clusters. GeckoTerminal free new+trending pools surface only tens of fresh tokens per tick with large
overlap → orders of magnitude fewer unique tokens/day. It proves the collector works and can seed a few
multi-day signals, but it is **not** a volume path to a day-level n>100 gate.

## The volume path (free, already wired — future-optional execution)
`WalletScarper/walletscarper/sources/bitquery_corecast.py` is the gRPC firehose that produced raw_trades;
the Ory token is configured (free tier). Streaming it into the SAME `firehose_trades` schema for ≥14 days is
the realistic route to day-level n. This sprint does NOT start a live stream (paper/research only, and to
avoid burning free quota without supervision) — it is documented as the exact next operational step.

## Collection target (the unblock contract)
| axis | need | have |
|------|------|------|
| distinct calendar days | ≥14 (≥30 ideal) | 1 (May-14) + partial 2026-06-06 firehose POC |
| independent sell-cluster events / day | ≥100 | ~0.5 (GT free) / ~975 (corecast reference) |
| source | organic on-chain | raw_trades=organic; firehose=organic; fixtures=excluded |

## Decision
H-162 cross-day persistence = **OPEN**. H-166 already demoted by the random-sell control independent of
persistence (H166_RISK_ENGINE_REPORT.md). The single experiment that resolves H-162 is **H-163**: run the
corecast firehose ≥14 days → rebuild per-day events → day-level walk-forward of the wq-sell increment. Until
then, no wallet distribution signal is sized; the intra-session result stays a lead, not a fact.
