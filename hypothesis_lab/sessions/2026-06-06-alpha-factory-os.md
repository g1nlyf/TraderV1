=== SESSION 9 HEARTBEAT — FREE-DATA ALPHA FACTORY OS (corrective loop) ===
Start 2026-06-06. Operator: Opus 4.8 autonomous. Paper/research only. Free data only.

CORRECTION ACCEPTED: Sprint 8 stopped too early, treated 14-day as full blocker, no persistent loop, and had
a VALIDATION BUG (token_lifecycle passed full-sample all_nets into the gate while firing test-only -> perm
null + base computed over train+test, contaminated). Build a research OS, not a report. Run many cycles.

WORKSTREAMS:
- A AUDIT+FIX: test-only gate semantics (load-bearing). Re-run lifecycle numbers corrected.
- B TOURNAMENT HARNESS: reusable, candidate registry, walk-forward folds, controls, perm+bootstrap, persistent
  ledger + auto markdown. Not a one-off.
- C COLLECTOR FLYWHEEL: Corecast adapter -> same firehose schema, scheduler, resume-safe, health, blocker doc.
- D HYPOTHESIS QUEUE: >=20 compound hypotheses, clustered/prioritized, machine-consumable.
- E RUN TOURNAMENT: all immediately-testable candidates vs base/token-only/random/prev-best. Multiple cycles.
- F STRATEGY ASSEMBLY + ledgers + canonical + RESUME commands.

VALIDATION STANDARD: eval_stats gate, TEST-ONLY universe, walk-forward, perm<0.05, bootstrap CI>0, n>100,
no lookahead, controls stronger than signal.

LOG:
[t0] heartbeat. Building corrected tournament harness (test-only gate + walk-forward) first.

[t1] A AUDIT+FIX — found Sprint-8 bug (gate fed full-sample all_nets while firing test-only -> contaminated
     base/perm). Fixed in tournament.py (POOLED TEST-ONLY walk-forward gate). VALIDATION_AUDIT.md.
[t2] B HARNESS — tournament.py: reusable Dataset + candidate registry + walk-forward folds + test-only gate +
     persistent ledger (jsonl) + auto TOURNAMENT_REPORT.md. test_tournament.py 7/7 PASS (incl gate-isolation
     proving fix: base=+0.167 test-only not -0.10 full-sample; non-leak; non-overlap; classifier; folds).
[t3] E RUN cycle 1 — findings SURVIVE the fix: token_gbm perm 0.044 (was 0.301 contaminated), neutral 0.002,
     token+wallet +1.78% over token-only perm 0.000 (CI upper +1.69%). CORRECTED: naive avoidance filter n.s.
     (0.117). promoted=0 (all EV<0, down-regime).
[t4] D QUEUE — HYPOTHESIS_QUEUE.md: 20+ compound hypotheses (archetype-consensus, wallet-token fit, lifecycle
     continuation/reversal, liquidity migration, co-buy cluster, rug pre-detect, sizing, regime tagger, edge
     stack), clustered/prioritized, 12 test-now.
[t5] E RUN cycle 2 (loop cycling, ledger accumulates) — added H-184 rug-skip + H-171b ablation:
     H-184 rug pre-detection no-trade filter +4.73% perm 0.000 (ROBUST, superior to naive avoidance);
     H-171b: wallet increment carried by BOTH wq (token+wq CI upper +2.14%) AND cohesion.
[t6] C FLYWHEEL — corecast_adapter.py: free high-volume Corecast stream -> firehose schema; mapping+dedup
     selftest PASS; gRPC stream env-gated (BITQUERY_TOKEN), resume-safe; proto already installed in WS venv.
     Blocker = 1 token. RESUME.md loop operating manual (state files, cycle commands, flywheel, stop conditions).
[t7] F DOCS — VALIDATION_AUDIT + CANONICAL/INDEX/STACK/DEAD_TRACKS Sprint-9 + this log.
OUTCOME (part 1): Operating mode corrected — built a RESEARCH OS (reusable tournament + queue + ledger +
     flywheel + resume manual), fixed a validation bug, ran 2 cycles, sharpened the signal library. Findings
     robust under corrected gate. promoted=0 (single down-regime is the wall). C-002 sole champion.

=== CONTINUATION (GMGN primary correction) ===
[t8] GMGN AUDIT — gmgn-cli has `track smartmoney|follow-wallet|kol` returning RAW POINT-IN-TIME trade records
     (tx_hash, maker, base_address, side, amounts, price, TIMESTAMP). Classified fields: point-in-time
     (events) vs discovery-only (smart-money membership) vs enrichment-snapshot (tags, token meta) vs FORBIDDEN
     (portfolio stats aggregates = leaderboard class). GMGN_DATA_AUDIT.md.
[t9] gmgn_adapter.py — PRIMARY collector -> firehose schema (source=gmgn:smartmoney), dedupe, raw stored,
     provenance. selftest PASS. LIVE: 1 poll = 100 fetched/95 new/26 wallets/27 tokens/508s span ≈ 17K
     smart-money trades/day (vs GeckoTerminal 0.5 clusters/day). Rows dated ~today = cross-day seed vs May-14.
     Corecast demoted to FALLBACK.
[t10] loop_runner.py — continuous loop (repeat tournament cycles, optional GMGN poll/cycle, resume from ledger,
     schedulable, no chat memory). Ran cycle 3.
[t11] Tournament cycle 3 — added H-183 (continuation/reversal) + H-185 (transition) via prev_state augment:
     H183_buy_acceleration EV -22% edge -9% (continuation FAILS); H183_buy_distribution +3.4% n.s.;
     H183_neutral_post_distrib +5.57% EV (only positive seen) but n=2 (noise, needs volume); H185 transitions
     too sparse (n=6). Survivors persist (token_gbm 0.044, neutral 0.002, H184 0.000, token+wallet 0.000).
     Ledger=43 rows across 3 cycles. promoted=0.
OUTCOME (part 2): GMGN = the real data unblock (primary, point-in-time, live, ~17K/day). Collection RUNNING
     (95 rows seeded, cross-day started). Loop runs continuous cycles + ledgers. Lifecycle directional signals
     real but sparse on 1 session -> GMGN cross-day volume is the path. STOP-CONDITION MET: data collection
     actually running (gmgn_adapter --loop). promoted=0; C-002 sole champion.
