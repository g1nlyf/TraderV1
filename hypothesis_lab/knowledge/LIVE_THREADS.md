# LIVE THREADS — what is still alive and what it needs next

> A thread is LIVE if it has a real (or plausible) edge AND a concrete next step that could move it
> toward/through the gate. Ordered by expected value. Updated 2026-06-06.

## 1. C-002 carry book — ACTIVE champion, hardening
- State: +1.49% APR unlevered, leverage-validated to ~3.4× cross-margin → +5% target.
- Alive work: (a) full 10-name intraday rerun for the basis-blowout stress haircut; (b) live funding-compression monitor; (c) forward paper to confirm OOS APR holds.
- Blocker to "production": explicit basis-tail (>33% gap) stress scenario; 8h data can't supply it.

## 2. H-042 liquidation-bounce sleeve — REAL, sub-gate, n-blocked
- State: −8%/H2 +1.46%/trade, cluster-t 2.24, n=91; market-neutral; **uncorrelated to carry (r≈0)** → genuine diversifier.
- Alive work: forward-collector is accumulating events (running). Promote the 70/30 vol-matched stack ONLY after n>100 with perm_p<0.05 ∧ CI95>0 on forward data.
- Blocker: n. Pure data/time problem.

## 3. Wallet-intelligence intraday alpha — UNPROVEN, under active test (Sprint 5)
- Hypothesis family: point-in-time wallet-consensus / quality-weighted cluster buys predict intraday forward token return better than token-only + naive-copy baselines.
- Substrate: raw_trades 5.5h cross-section (DATA_LEDGER). Builder: `wallet_alpha/build_events.py`. Tests: `wallet_alpha/test_*.py` through eval_stats.
- What would make it LIVE→promotable: OOS realized EV>2% net of cost, perm_p<0.05, CI95>0, n>100, **and** beats token-only + naive-copy. Intraday only.
- Hard blocker (already known): **persistence is untestable** on a 5.5h snapshot. Even a clean intraday pass cannot claim forward alpha half-life. Needs multi-day capture (see DATA needs).

## 4. Forward collection — INFRA, running
- forward_collector.py + cron updating forward_collector_state.jsonl (last 2026-06-06 18:40).
- This is the unblock engine for #2 and any wallet sleeve. Keep it running; it is the cheapest path to n.

## DATA NEEDS (what unlocks the next real edge — ranked)
1. **Multi-day on-chain capture** (same bitquery firehose, run daily for ≥30 days) → makes wallet persistence + archetype half-life + multi-day labels testable. *Highest leverage.*
2. **OI history + funding** (one source) → unblocks ~6 carry-timing hypotheses.
3. **L2/orderbook snapshots** → spread/maker-taker/impact hypotheses.
4. **Options/IV** → vol-carry gates.

## Operating rule
Same-data idea generation is exhausted (Sprint 4 proved it: 100 generated, 0 promoted). New edges come
from **new data**, not new variants. Spend cycles on collection + the wallet point-in-time test, not on
generating H-160+.
