=== SESSION 6 HEARTBEAT — WALLET PERSISTENCE FLYWHEEL ===
Start 2026-06-06. Operator: Opus 4.8 autonomous.

GOAL: determine if H-162 (coordinated quality-wallet selling predicts drops) PERSISTS across days/regimes,
and convert it into a CAPTURABLE long-only / avoidance / exit edge (not uncapturable short).

ENTRY TRUTH (from Sprint 5):
- raw_trades = 5.5h snapshot (May-14) + 3,946 May-16 tail. ONE session. -> cross-day persistence NOT yet testable.
- wallet_tapes.json = 86 wallets x 321d (Helius) but survivorship-selected + sparse own-trade labels.
- H-162 real but eff-n=1 session + no short venue. Long alpha dead (H-160/161).

HONEST PLAN (what is real-testable NOW vs what needs the collector):
- PHASE 1 collector: BUILD durable free firehose (the actual unblock). Smoke + dry-run + 1-tick. Days accrue later.
- PHASE 3 persistence: only PROXY available now = intra-session walk-forward blocks (May-14) + May-16 tail as block-2
  + wallet_tapes 321d where labels exist. TRUE cross-day persistence = documented collection target.
- PHASE 4 capturable: avoidance-veto / rotation / exit tests on May-14 cross-section = REAL progress, testable now.
- PHASE 5/6 archetype+network+models with full ablation+baselines.

LOG:
[t0] heartbeat written. Investigating existing ingestion code + free-source config + network access before building.

[t1] PHASE 1 DONE — firehose_collector.py (GeckoTerminal free, keyless, stdlib). Verified LIVE: dry-run 286
     trades/3 pools; live tick 392 trades/34 wallets to _data/firehose.sqlite3; backoff handled 3 rate-limits;
     smoke (parse+dedup) ALL PASS. run_firehose.bat + FIREHOSE_RUNBOOK.md. Network confirmed (GT 200).
[t2] PHASE 3 DONE — test_h162_persistence.py: intra-session walk-forward wq-sell SHORT +7.7% over base,
     perm 0.000, CI[+17.8,+25.7], n=431/469, edge in 3/4 blocks. wq-increment regime-robust; base=regime.
     CROSS-DAY untestable (1 session) -> H-163 needs firehose >=14d. H162_PERSISTENCE_REPORT.md.
[t3] PHASE 4 DONE — test_capturable.py (3 conversions through eval_stats):
     (A) buy-after-distribution +8.8% rel vs fresh-FOMO (perm 0.001) = H-042 on-chain; flips naive veto sign.
     (B) exit-overlay: +3.9/+5.4%/trade saved (perm 0.000); beats shuffled-lag control 100% of draws BOTH H
         => real signal-driven de-risk (~+1.8% beyond mechanical early-exit). Fixed a window-pointer bug (i=j) first.
     (C) rotation A->B targets +0.4-0.6% rel (perm 0.005, n=9369) real but tiny.
     0 capturable LONG rules (all on negative May-14 base). Exit-overlay = Stage-2 RISK module candidate.
     CAPTURABILITY_REPORT.md + PERSISTENCE_SYNTHESIS.md.
[t4] DOCS — INDEX (+H-162p/H-163/H-164/H-166), CANONICAL_STATE, H-162 file, 4 wallet_alpha reports.
     NOTE: LIVE_THREADS/DEAD_TRACKS status superseded by CANONICAL_STATE Sprint-6 block (the override doc).
OUTCOME: collector built+live; H-162 persists INTRA-session (not yet cross-day); no capturable long;
     exit-overlay = real capturable de-risk (not alpha). Flywheel ready; H-163 (multi-day) is the promote/kill test.
