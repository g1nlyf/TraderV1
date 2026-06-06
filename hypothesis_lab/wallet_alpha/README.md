# wallet_alpha — Wallet Intelligence Alpha Engine (Sprint 5)

First honest, leakage-controlled test of on-chain wallet alpha on the `raw_trades` cross-section.
Replaces the in-sample/survivorship `finetune/pipeline/copy_engine.py` premise with a point-in-time pipeline.

## Pipeline
```
profile_dbs.py      PHASE 1  regenerate the data audit (knowledge/DATA_AUDIT.md)
build_events.py     PHASE 2  point-in-time token-disjoint cluster events + forward labels  -> _cache/events_{side}.json
wa_common.py                 shared loaders (block_time parse, price_sol = quote/token, COST)
wa_eval.py          PHASE 5  validation harness wired to finetune/pipeline/eval_stats.py (the gate)
test_h160_consensus.py       H-160  wallet-consensus quality        (FAIL/DEAD)
test_h161_archetype.py       H-161  archetype mix (KMeans)          (FAIL/DEAD)
test_h162_sells.py           H-162  distribution-sell down-signal   (REAL, not capturable)
SYNTHESIS.md        PHASE 6  alive/dead ranking + next hypotheses
```

## Run
```
py hypothesis_lab/wallet_alpha/build_events.py --k 4 --window-min 15 --side buy
py hypothesis_lab/wallet_alpha/build_events.py --k 4 --window-min 15 --side sell
py hypothesis_lab/wallet_alpha/test_h160_consensus.py
py hypothesis_lab/wallet_alpha/test_h161_archetype.py
py hypothesis_lab/wallet_alpha/test_h162_sells.py
```
Interpreter: `py` (Python 3.14 + numpy/pandas/scikit-learn). `_cache/` is gitignored (regenerable).

## Leakage rules (binding — see knowledge/DATA_AUDIT.md)
1. Features only from `block_time < event_t`.
2. Wallet skill recomputed point-in-time from pre-t completed round-trips; NEVER wallet_scores/leaderboard/
   wallet_token_pnl/GMGN (all full-history look-ahead).
3. Entry = post-signal public VWAP; label = forward VWAP, cost-adjusted, capped to [-1,+1].
4. Temporal OOS split; wallet/token overlap reported. Baselines mandatory: naive-copy + token-only.

## Headline result
No capturable wallet LONG alpha (naive copy −17%; quality anti-helps via survivorship; token context
predicts relative-badness only). One real SHORT/avoid signal (H-162 coordinated quality-sells) that
gate-clears statistically but is not promotable (no short venue + single-session regime risk). Full
write-up in SYNTHESIS.md.
