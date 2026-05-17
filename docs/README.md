# TraderV1 — Documentation Index

> **For any LLM reading this folder:** You are the CEO of this project. Read the files listed below in order. Be skeptical: where older docs claim something is "done", cross-check against `STATUS.md` and the V2.0 reality audits. The honest assessment of what works vs. what's aspirational is in `HERMES-REALITY.md` and `GAPS-AND-BLOCKERS.md`.

---

## CEO Onboarding Prompt

```
You are the CEO of TraderV1 — a Solana memecoin AI-driven paper-trading research system.
Your job: read all documents in this docs/ folder and answer these questions:

1. What is this project actually trying to do (in plain business terms)?
2. What is the current verified state of every major system component?
3. What has been built and tested? What only exists on paper?
4. What is "Hermes"? Be specific — there are TWO different things called Hermes.
5. Has the system ever autonomously made a paper trade decision from a real market signal?
6. What is blocking this system from managing real money responsibly?
7. What does "million-dollar ready" mean for this project, and how far are we from it?
8. What should the next sprint focus on?

Reading order:
  1. README.md (this file — index + context)
  2. STATUS.md — current ground truth, what works RIGHT NOW
  3. HERMES-REALITY.md — critical: read this before anything else about Hermes
  4. GAPS-AND-BLOCKERS.md — everything preventing production use
  5. 00-project-definition.md — business purpose, goals, autonomy stages
  6. history/PROJECT-HISTORY.md — sprint history, what was built when
  7. architecture/ — system design docs
  8. V2.0/ — V2.0 audits and hardening progress (most recent ground-truth)
  9. operations/ — how to actually run the system

Key invariants (never negotiable):
  - No live trading until Stage 2 paper P&L is proven positive
  - Risk engine vetoes everything — no agent bypasses it
  - LLM proposes, deterministic systems verify
  - No private keys, no real transactions, no hindsight
```

---

## Quick State (2026-05-17)

| Component | Status | Notes |
|-----------|--------|-------|
| Test suite | ✅ 71/71 pass | Run: `pytest tests/ -q` |
| Legacy pipeline | ✅ Working | 744k+ txns, 38 wallets, 22k+ scores |
| Stage 2 deterministic core | ✅ Complete | signals → risk → paper → exits → P&L |
| Legacy → Stage 2 bridge | ✅ Fixed (2026-05-16) | Real events flowing |
| Hermes CLI agent | ✅ Configured | `scripts/run-hermes.bat` — never run interactively |
| Hermes autonomous review loop | ⚠️ Code complete, wired | 0 real decisions made from real signals yet |
| Circuit breaker + position sizing | ✅ Done | Phase 4 hardening |
| Helius live wallet polling | ✅ Done | Phase 1 hardening |
| Token validation (Helius DAS) | ✅ Done | Phase 2 hardening |
| Pump.fun source | ✅ Done | Phase 5 hardening |
| Production hardening | ✅ Done | JSON logs, /health, /metrics, graceful shutdown |
| Real paper trades from real signals | ❌ Never happened | The core gap |
| Shadow mode (Stage 3) | ❌ Blocked | Needs real quote windows |
| Sprint 3: Adaptive Market Loop | ❌ Not started | |
| Live trading | 🔒 Prohibited by design | Stage 4 gated future |

---

## Document Map

```
docs/
├── README.md                            ← You are here (CEO prompt + index)
├── STATUS.md                            ← ⭐ Ground truth: what works RIGHT NOW
├── HERMES-REALITY.md                    ← ⭐ Honest Hermes assessment (2 systems explained)
├── GAPS-AND-BLOCKERS.md                 ← ⭐ What blocks production / million-dollar use
│
├── 00-project-definition.md             ← Business context, goals, autonomy stages 0-6
├── 01-critical-assessment.md            ← Critical design principles
├── 02-target-market-and-principles.md   ← Market analysis, design principles
│
├── history/
│   └── PROJECT-HISTORY.md              ← Full chronological history (Stage 1 → Hardening)
│
├── architecture/
│   ├── 03-system-architecture.md        ← Full system map
│   ├── 04-hermes-system-design.md       ← Hermes architecture design
│   ├── 05-agent-architecture.md         ← Agent roles and interactions
│   └── 06-data-model.md                ← Database schema (SQLite)
│
├── operations/
│   ├── operator-runbook.md              ← Day-to-day operations guide
│   ├── hermes-runtime.md               ← How to run Hermes CLI agent
│   ├── hermes-agent-persona.md         ← Hermes persona / system prompt
│   ├── free-data-sources.md            ← Data sources and APIs
│   └── current-system-reality-audit.md ← Pre-V2.0 reality audit (historical)
│
├── V2.0/
│   ├── README.md                        ← V2.0 overview
│   ├── AUDIT-2026-05-16.md             ← ⭐ V2.0 gap analysis (before fixes)
│   ├── RUNTIME-CLOSURE-2026-05-16.md   ← ⭐ After-fix runtime verification
│   ├── HARDENING-PROGRESS-2026-05-16.md ← Phase 0-6 hardening detail log
│   ├── final-vision/                    ← Vision: what this becomes at full scale
│   ├── almanac-v2/                      ← V2 contracts, invariants, tool specs
│   └── implementation-plan/             ← V2 sprint plan (3-sprint design)
│
├── release-baselines/
│   └── stage2-accepted-with-gaps-baseline-20260515.md ← Stage 2 acceptance baseline
│
└── implementation-almanac/
    ├── decisions/                       ← ADR-0001 through ADR-0005
    ├── contracts/                       ← Service API contracts
    ├── checklists/                      ← Final acceptance checklist
    └── runbooks/                        ← Continuous run runbook
```

---

## Non-Negotiable Invariants

These cannot be changed without a full architecture review:

1. **No live trading** in Stage 2. Live execution is Stage 4/5 — gated behind proven paper P&L.
2. **No private keys** in LLM context, no signer, no swap adapter, no DEX transaction builder.
3. **No hindsight** — entry, exit, and reasoning are recorded before the trade resolves.
4. **No perfect fills** — paper trades use fees, slippage, latency, and failed fills.
5. **Risk engine is sovereign** — risk veto cannot be bypassed by any agent.
6. **LLM output is a proposal** — deterministic systems decide and record.
7. **No LLM-calculated P&L** — all financial math is deterministic code.
8. **No wallet signal trusted** until it improves net expectancy on new paper trades.
