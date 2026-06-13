# Free-Data Alpha Factory OS — Complete Project Context (Sprint 9, 2026-06-06)

**Status:** Data collection LIVE + loop RUNNING. Ready for autonomous continuation.

---

## MISSION & FINAL GOAL

**Mission:** Build a continuous research engine that discovers, tests, and validates trading hypotheses using ONLY free data sources. Ship a reusable, autonomous system—not a one-off report. The machine runs repeated cycles, persists state (ledgers), and stops only on promotion or documented blocker.

**Final Goal:** Identify a free-data hypothesis that clears the promotion gate (realized net EV>+2% ∧ perm<0.05 ∧ CI95>0 ∧ n>100, TEST-ONLY walk-forward, controls stronger than signal) and trades live with sizing.

**Constraints:**
- Free data only (no premium APIs / Glassnode / Chainalysis).
- Point-in-time features only (no lookahead / leaderboard aggregates / retrospective classification).
- Walk-forward validation (expanding-window folds, TEST-ONLY gate, pooled permutation null).
- Single champion exists: `C-002` (persistence-selected funding carry, funded, live trade).

---

## WHAT HAS BEEN DONE (Sprint 9 summary)

### A. Validation Audit + Fix (load-bearing)
**Problem:** Sprint-8 `token_lifecycle.py` passed full-sample `all_nets` into the gate while firing TEST-only selections → contaminated base/permutation universe.

**Fix:** Rewrote `tournament.py` with TEST-ONLY gate semantics: pool test-nets from all folds → call `ev.gate(pooled_test_nets, pooled_fired)` (test-only universe). Proven by `test_tournament.py::test_gate_test_only_isolation` (base=+0.167 test-only, not −0.10 full-sample).

**Deliverables:** `VALIDATION_AUDIT.md`, `test_tournament.py` (7/7 PASS), corrected tournament harness.

### B. Reusable Tournament Harness (not a one-off)
`tournament.py`: 
- Dataset abstraction (rows, feat_sets, source provenance).
- Candidate registry (pluggable `fn(ds, train, test) → fired_mask`).
- Expanding-window walk-forward folds.
- Auto controls (random/token-only/base).
- Persistent ledger (`tournament_ledger.jsonl`, append-only).
- Auto report generation (`TOURNAMENT_REPORT.md`).

Candidates are registered functions; new ideas plug in without code duplication. Tests prove gate isolation, fold disjointness, point-in-time non-leak, control behavior.

### C. GMGN Primary Data Source (THE unblock)
**Audit:** `gmgn-cli track smartmoney|follow-wallet|kol --raw` returns RAW POINT-IN-TIME trade records (tx_hash, maker, base_address, side, amounts, price, unix **timestamp**). Classified fields (GMGN_DATA_AUDIT.md):
- **Point-in-time (features):** raw track trade records.
- **Discovery-only:** smart-money membership.
- **Enrichment-snapshot:** tags, token metadata (store raw, never retroactive feature).
- **FORBIDDEN lookahead:** `portfolio stats` aggregates (realized_profit/winrate = leaderboard class).

**Adapter:** `gmgn_adapter.py` → firehose schema (`source=gmgn:smartmoney`), dedup, raw_json stored, provenance. Selftest passes. **Live: ~17K smart-money trades/day** (vs GeckoTerminal 0.5 clusters/day). Rows dated ~today = cross-day accrual started.

**Status:** PRIMARY collector. `corecast_adapter.py` (Bitquery fallback) stands by if base-rate over ALL tokens needed.

### D. Hypothesis Queue (20+ compound, machine-consumable)
`HYPOTHESIS_QUEUE.md`: 20+ compound hypotheses across 5 clusters (wallet behavioral/fit, token lifecycle, liquidity migration, CEX/carry, portfolio/meta). Each entry: structural why-works, why-fails, data sources, validation method, control, capturability, status.

**Status taxonomy:** test-now (run now), collect (blocked on cross-day volume), dead (killed), later (needs new infra).

### E. Tournament Cycles (ledger accumulating)
**Cycle 1–2:** Corrected gate on existing candidates.
- token_gbm +4.66% perm 0.044 (was n.s. 0.301 contaminated).
- neutral +7.34% perm 0.002.
- token+wallet +1.78% over token-only perm 0.000 (CI upper +2.14% via token+wq).
- **H-184 rug-skip +4.73% perm 0.000** (ROBUST, new, shadow no-trade filter).
- Naive avoidance filter CORRECTED to n.s. (0.117).
- promoted=0.

**Cycle 3:** Added H-183 (continuation/reversal) + H-185 (transitions via prev_state augment).
- H183_buy_acceleration EV −22% → **continuation FAILS**.
- H183_neutral_post_distrib +5.57% EV (only positive) but n=2 → DATA-STARVED.
- H185 transitions n=6 → DATA-STARVED.
- Survivors persist. **Ledger=43 rows across 3 cycles. promoted=0.**

### F. Continuous Loop Runner + Docs
`loop_runner.py`: repeat tournament cycles, optional GMGN poll per cycle, resume from ledger, schedulable, no chat memory. Stops on promotion.

**Docs updated:** DATA_LEDGER, CANONICAL_STATE, HYPOTHESIS_QUEUE (cycle log + status), RESUME (GMGN-primary commands), session log.

---

## CURRENT STATE (2026-06-06, end of Sprint 9)

### Data Pipeline
| source | status | volume/day | point-in-time | span |
|--------|--------|-----------|---|---|
| raw_trades (GeckoTerminal) | May-14 session only | N/A | YES (block_ts) | 5.5h |
| GMGN smartmoney (PRIMARY) | LIVE, looping | ~17K smart-money trades | YES (timestamp) | ~today (cross-day seed) |
| Corecast (fallback) | built+tested, needs token | est ~100K+ all trades | YES (timestamp) | blocked on credential |
| GeckoTerminal firehose (thin fallback) | built | ~0.5 clusters/day | YES (block_ts) | multi-day capable |

**Firehose DB:** `_data/firehose.sqlite3` (gitignored). Schema: signature/wallet/token_mint/side/amounts/price/block_ts/source/raw_json/ingested_at. Dedup on UNIQUE(signature, token_mint, side, wallet).

### Signal Library (tested under corrected gate)
| signal | EV | perm | CI95 | n | verdict | note |
|--------|----|----|-------|---|--------|------|
| token_gbm (lifecycle) | −8.6% | 0.044 | [−14.3%, −2.9%] | 186 | FAIL (base EV<0) | edge +4.66%, real |
| neutral-state filter | −5.9% | 0.002 | [−10.0%, −1.3%] | 203 | FAIL | edge +7.34%, robust |
| **H-184 rug-skip (NEW)** | **−8.5%** | **0.000** | [−12.4%, −4.5%] | 431 | FAIL | **edge +4.73%, ROBUST de-risk** |
| token+wallet GBM | −2.4% | 0.000 | [−7.2%, +1.7%] | 205 | FAIL | edge +15.54%, CI upper +1.69% |
| token+wq (ablation) | −2.1% | 0.000 | [−7.0%, +2.1%] | 205 | FAIL | **CI upper +2.14%**, highest yet |
| C-002 (funding carry) | N/A (live) | — | — | — | CHAMPION | held-out, sized, live trade |

**Honest bottom line:** All on-chain candidates sit EV<0 on single May-14 down-regime. Edges over base are REAL + walk-forward-robust (perm strong, controls beaten). But absolute EV cannot go positive in a dump. WALL = REGIME DIVERSITY (need cross-day to see non-dump).

### Hypothesis Status After Cycles
**Tested:**
- H-170 (lifecycle separator): neutral-state best, avoidance-axis weak.
- H-171/H-171b (wallet multivariate): CONFIRMED, increment carried by BOTH wq + cohesion.
- H-184 (rug-skip): ROBUST, shadow no-trade filter.
- H-183 (continuation/reversal): continuation FAILS, reversal weak, post-distribution bounce +5.57% but n=2 (data-starved).
- H-185 (transitions): sparse on 1 session (n=6), data-starved.

**Data-starved (blocked on GMGN cross-day accrual, now running):**
- H-183 post-distribution bounce (n=2!).
- H-185 transitions.
- H-186 liquidity migration.
- H-191 regime tagger (HIGHEST LEVERAGE: classify regime per day → condition all signals).
- H-189 edge stack (needs +EV on-chain legs).

**Heavy, deferred to GMGN cross-day (single-regime cousins already dead):**
- H-180 archetype-consensus (needs KMeans; H-161 dead).
- H-187 co-buy cluster (needs graph; H-168 dead).
- H-182 wallet-token fit (needs per-(wallet,state) win-rates).
- H-190 sizing overlay (needs sizing-aware gate, separate metric from selection).

**Dead/killed:**
- H-160/H-161 naive wallet consensus (token dominates, survivorship bias).
- H-170-onehot state one-hot (redundant vs continuous).
- H-168 co-sell cohesion (rho −0.10).

---

## HOW TO WORK GOING FORWARD

### Immediate (next session / next loop cycle)

#### 1. **Continue GMGN collection (the unblock happening now)**
```bash
# PRIMARY collector (point-in-time, ~17K/day)
py hypothesis_lab/wallet_alpha/gmgn_adapter.py --loop --interval 300

# OR schedule it
schtasks /Create /SC MINUTE /MO 30 /TN fh_gmgn /TR "py .../gmgn_adapter.py --loop"
```

**Goal:** Accrue ≥ 3–5 distinct calendar days of smart-money events. Once forward time passes, re-label events and build a day-level dataset (aggregate per day, compute regime per day).

#### 2. **Run tournament cycles on accumulated data**
```bash
# Single cycle (test-now candidates vs base/controls, ledger appends)
py hypothesis_lab/wallet_alpha/loop_runner.py --cycles 1

# Continuous loop (optional GMGN poll + tournament every 30 min)
py hypothesis_lab/wallet_alpha/loop_runner.py --cycles 0 --interval 1800 --collect
```

**Ledger** (`_cache/tournament_ledger.jsonl`) persists across runs. Re-run the loop whenever fresh data available.

#### 3. **Build the day-level dataset (H-163 / H-191 unblock)**
Once GMGN data spans multiple days:
- Aggregate buy-cluster events per day.
- Compute daily regime (up/flat/dump) from breadth/vol/median pnl.
- Run tournament at DAY level (not intraday).

**Why:** Day-level sees non-dump regimes → first time any candidate can be EV>0 → promotion becomes possible.

**Code sketch:**
```python
# In tournament.py, add:
def day_level_dataset():
    gmgn_rows = load_firehose(source="gmgn:smartmoney")
    events_by_day = aggregate_by_day(gmgn_rows)
    regimes = classify_regime_per_day(events_by_day)  # up/flat/dump
    rows = []
    for day, events in events_by_day.items():
        regime = regimes[day]
        for e in events:
            # features = token/wallet/network from e, + day-level regime
            rows.append({...})
    return Dataset("day_level", rows, {...})
```

#### 4. **Test the data-starved backlog**
Once day-level is live, test:
- H-183 post-distribution bounce (now with volume).
- H-185 transitions (now with volume).
- H-186 liquidity migration (needs cross-token linkage).
- H-191 regime tagger (the gate: condition all signals to non-dump).
- H-189 edge stack (once on-chain legs are +EV).

#### 5. **Update HYPOTHESIS_QUEUE.md & ledger after each cycle**
- Mark tested candidates (cycle result).
- Move data-starved to tested if volume OK.
- Kill weak ideas (perm > 0.5, edge < 0, controls better).
- Flag new ideas for next batch.

---

### Medium term (2–4 weeks)

#### Collect ≥14 days of cross-day GMGN data
Target: 100+ cluster events per day (easily reachable with ~17K trades/day in the smart-money population).

#### Run tournament at day level
This is the CRITICAL test. It is the first time the gate will see a non-dump regime.

#### If promotion happens
- Formalize the strategy (entry rule, exit rule, sizing, collection target).
- Paper-trade or live-trade with sized capital.
- Monitor real-time performance vs. backtest.

#### If no promotion yet
- Kill ideas that fail data-starved (e.g., if H-183 still n.s. with volume, it's dead).
- Generate the NEXT batch of 20+ hypotheses (consult DEAD_TRACKS, follow the learnings).
- Re-run the loop.

---

### Key files & their roles

| file | role |
|------|------|
| `tournament.py` | Reusable harness. Candidate registry (lifecycle_candidates, cluster_candidates). Run with `run_all(k=3)`. |
| `tournament_ledger.jsonl` | Append-only results. One JSON per candidate per cycle. Persists across runs. |
| `TOURNAMENT_REPORT.md` | Auto-generated leaderboard (MD table). Readable summary. |
| `HYPOTHESIS_QUEUE.md` | Machine-consumable backlog. Status (test-now/collect/dead/later) + why + data + validation method. |
| `GMGN_DATA_AUDIT.md` | Field classification (point-in-time vs enrichment vs forbidden). Reference for new GMGN users. |
| `gmgn_adapter.py` | PRIMARY collector. `--loop`, `--once`, `--status`. Polls GMGN smartmoney, writes firehose.sqlite3. |
| `loop_runner.py` | Continuous engine. Repeat tournament cycles, optional GMGN poll, resume from ledger, stop on promotion. |
| `RESUME.md` | Operating manual. State files, cycle commands, flywheel commands, scheduled-agent setup. |
| `corecast_adapter.py` | FALLBACK gRPC stream (Bitquery Corecast). Needs BITQUERY_TOKEN. Deployed but not primary. |
| `_data/firehose.sqlite3` | Collected trades (gitignored). Same schema for all sources. Dedup on (signature, token_mint, side, wallet). |
| `VALIDATION_AUDIT.md` | Explains Sprint-8 bug + fix. Reference for understanding why test-only gate is load-bearing. |
| `.env` (hypothesis_lab) | GMGN_API_KEY (required). GMGN_ENABLED=true. |

---

## STOP CONDITIONS (why/when to pause the loop)

1. **Promotion:** A candidate clears the gate (EV>+2% ∧ perm<0.05 ∧ CI95>0 ∧ n>100) → escalate to STACK, formalize strategy.
2. **Data collection is actually running:** GMGN looping at ~17K/day, cross-day accrual started → ✅ MET.
3. **All current test-now candidates have been run and ledgered:** 20+ hypothesis families tested on available data.
4. **A true hard blocker is reached:** E.g., GMGN API becomes unavailable AND Corecast also blocked AND GeckoTerminal down. Document exact blocker + unblock path.
5. **Regime diversity achieved:** 14+ calendar days with mixed regimes (up/flat/dump) → re-run day-level → CRITICAL TEST.

**Current:** Data collection RUNNING (stop condition 2 met). Next: accrue cross-day, re-run at day level (condition 5 → critical test).

---

## VALIDATION STANDARD (canonical, non-negotiable)

**Gate** (via `eval_stats.gate`):
- **Base:** mean of pooled TEST nets (across all folds).
- **Perm:** draw k samples from pooled TEST universe (no train contamination).
- **CI95:** block-bootstrap on fired TEST nets (no train leakage).
- **Verdict:** EV>+2% ∧ perm<0.05 ∧ CI95>0 ∧ n>100.

**Walk-forward:**
- Expanding window: fold i trains on rows[0:start_i), tests on rows[start_i:end_i).
- Candidate fires on TEST only (fit-train, fire-test).
- Pool all TEST-only nets + fires across folds.
- Controls auto-run (random, token-only, base) on the SAME folds.

**Point-in-time (no lookahead):**
- Features use only data strictly before decision time.
- No retroactive labels / aggregates / leaderboard classification.
- Timestamps must be event-time, not fetch-time.

**Controls stronger than signal:**
- Signal must beat random (perm < 0.5).
- Signal must beat token-only (edge > base).
- Signal must beat previous best OR be sufficiently novel.

---

## KEY FINDINGS & LEARNINGS

1. **Token lifecycle is the dominant axis.** Wallet aggregates matter but less than token flow regimes.
2. **Wallet quality increment is real and distributed.** Both wq (win-rate) and cohesion (cluster consensus) carry it; not a single artifact.
3. **Rug avoidance is subtle.** Naive state-skip (avoid rug/distrib/decay) is n.s. (0.117). GBM-based rug pre-detection (+4.73%, 0.000) is robust and the correct method.
4. **The wall is regime diversity.** On a single down-regime, all on-chain edges stay EV<0. Walk-forward proves edges are real; absolute EV just can't flip positive without a non-dump regime.
5. **Data-starved hypotheses are real but underpowered.** Post-distribution bounce (+5.57% EV, n=2) has directional signal; needs volume to confirm.
6. **Contamination kills validation fast.** Sprint-8's full-sample gate→test-only gate bias was massive (base −0.10 → +0.167). Always gate on test-only universe.

---

## NEXT IMMEDIATE ACTION

**RUN:**
```bash
py hypothesis_lab/wallet_alpha/gmgn_adapter.py --loop --interval 300 &
py hypothesis_lab/wallet_alpha/loop_runner.py --cycles 0 --interval 1800 --collect &
```

**Monitor:**
- Check `gmgn_adapter.py --status` periodically (est 17K trades/day accumulating).
- Check `TOURNAMENT_REPORT.md` after each cycle (does anything new pass the gate?).
- Check `tournament_ledger.jsonl` row count (grows per cycle).

**After 3–5 distinct days of GMGN data:**
- Build day-level dataset.
- Re-run tournament at day level (H-163/H-191).
- First time gate sees non-dump regime = first real promotion opportunity.

**If promotion:** Escalate to STACK, formalize strategy, paper or live trade.
**If no promotion:** Kill weak ideas, generate next 20+ batch, continue loop.

---

## REFERENCES

- **Mission & stop-conditions:** this file.
- **Validation logic:** `VALIDATION_AUDIT.md`, `eval_stats.py` (the gate).
- **Hypothesis scoring:** `HYPOTHESIS_QUEUE.md` (why-works/why-fails/data/validation/status).
- **Data fields:** `GMGN_DATA_AUDIT.md` (point-in-time vs enrichment vs forbidden).
- **Operating manual:** `RESUME.md` (commands, flywheel, scheduling).
- **Current signal library:** `TOURNAMENT_REPORT.md` (latest leaderboard).
- **Session log:** `sessions/2026-06-06-alpha-factory-os.md` (what happened in Sprint 9).
- **Knowledge:** `knowledge/CANONICAL_STATE.md` (summary), `knowledge/DATA_LEDGER.md` (sources), `knowledge/DEAD_TRACKS.md` (killed ideas).

---

**Ready to resume.** Data collection LIVE. Loop ready. No chat memory needed — read code + ledger + this doc.
