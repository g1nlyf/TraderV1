# Alpha Factory — Loop Operating Manual (resume / restart)

The research engine is a **loop with persistent state**. Any session (or scheduled agent) resumes by reading
this file + the ledgers, then continues. Nothing here needs the previous chat's memory.

## State (persistent, on disk)
| file | role |
|------|------|
| `HYPOTHESIS_QUEUE.md` | backlog: candidates tagged test-now / collect / dead / later |
| `tournament.py` | reusable harness: candidate registry → walk-forward TEST-ONLY gate → ledger + report |
| `_cache/tournament_ledger.jsonl` | append-only results, timestamped per run (every cycle accumulates) |
| `TOURNAMENT_REPORT.md` | latest leaderboard (regenerated each run) |
| `_data/firehose.sqlite3` | collected trades (GeckoTerminal + Corecast, same schema, deduped) |
| `VALIDATION_AUDIT.md` | gate-correctness record (test-only walk-forward; how contamination was fixed) |

## The loop (one cycle)
```
# 1. orient
cat hypothesis_lab/wallet_alpha/HYPOTHESIS_QUEUE.md         # what's test-now
cat hypothesis_lab/wallet_alpha/TOURNAMENT_REPORT.md        # current leaderboard

# 2. (optional) add a new candidate: edit tournament.py -> lifecycle_candidates()/cluster_candidates()
#    signature: fn(ds, train_rows, test_rows) -> bool[len(test_rows)]   (fit on train, fire on test)

# 3. run a cycle (walk-forward, TEST-ONLY gate, controls auto-included; ledger appends)
PYTHONPATH=hypothesis_lab/wallet_alpha py hypothesis_lab/wallet_alpha/tournament.py

# 4. read verdicts -> update HYPOTHESIS_QUEUE.md statuses + INDEX/DEAD_TRACKS; commit
```
Promotion = realized net EV>+2% ∧ perm<0.05 ∧ CI95>0 ∧ n>100 (eval_stats). Controls (random/token-only/base)
auto-run every cycle; a candidate must beat them all AND the previous best.

## The data flywheel (unblocks the only hard blocker: single regime)
```
py hypothesis_lab/wallet_alpha/corecast_adapter.py --selftest   # verify mapping (no network)
# one config change starts high-volume collection:
set BITQUERY_TOKEN=<free Bitquery Ory token>                     # https://account.bitquery.io (free tier)
py hypothesis_lab/wallet_alpha/corecast_adapter.py --stream      # resume-safe; writes -> firehose.sqlite3
py hypothesis_lab/wallet_alpha/corecast_adapter.py --status      # daily event volume / collection target
# thin fallback (no token): py firehose_collector.py --loop      (GeckoTerminal, ~0.5 clusters/day)
```
Run the stream (or schedule it) for ≥14 distinct calendar days → rebuild events per day → re-run the
tournament at DAY level (H-163/H-191). That is the experiment that can flip promoted=0 → promoted≥1, because
it is the first time the gate sees a non-dump regime.

## Continuous operation (scheduled agent)
```
# Windows Task Scheduler, every 30 min (collection) + daily tournament:
schtasks /Create /SC MINUTE /MO 30 /TN fh_corecast /TR "py .../corecast_adapter.py --stream"
schtasks /Create /SC DAILY /TN alpha_tournament /TR "py .../tournament.py"
```

## Stop conditions (per the mission)
- ✅ a candidate clears the promotion gate → promote to STACK, size in paper/shadow.
- ✅ collector flywheel built + launched → accumulate, re-enter loop at day level.   ← **we are here** (Corecast
  adapter built + tested; one token starts it).
- ✅ a full tournament killed/demoted all current free-data-testable families → generate next batch (queue has 12 live).
- ✅ real external blocker with exact unblock path documented → BITQUERY_TOKEN + 14-day accrual (documented above).

## Current standing (2026-06-06, after Sprint-9 cycles 1–2)
- promoted = 0. Every selection EV<0 on the May-14 down-regime (the wall).
- Robust under corrected walk-forward gate: token_gbm (perm 0.044), neutral-state (0.002), token+wallet
  (+1.78% over token-only, 0.000, CI upper +2.14% via token+wq), **H-184 rug-skip filter (+4.73%, 0.000)**.
- Corrected: naive avoidance filter is n.s. (0.117) — superseded by H-184.
- Next cycles (test-now, no new data needed): H-183 continuation/reversal, H-180 archetype-consensus,
  H-182 wallet-token fit, H-190 sizing overlay, H-185 transitions, H-187 co-buy cluster (intra).
- Binding blocker: REGIME DIVERSITY → Corecast flywheel (one token + 14 days).
