# hypothesis_lab — Claude Opus 4.8 Research Workspace

**Purpose**: Clean, minimal, LLM-optimized workspace for trading strategy hypothesis research.
This is NOT operational code. TraderV1/ handles execution. This directory handles research.

## Session Protocol (read this first, every session)

### Step 1: Load mandatory context (in order)
```
1. This README (you are here)
2. ACTIVE_CONTEXT.md  ← current state + ALERTS
3. CONSTRAINTS.md     ← locked eval standard + anti-patterns
4. champions/STACK.md ← current champion status
5. ROADMAP.md         ← what to work on next
```

### Step 2: Load env vars
```powershell
Get-Content WalletScarper/.env | Where-Object { $_ -match "^[A-Z_]+=.+" } | ForEach-Object {
    $parts = $_ -split "=", 2
    [System.Environment]::SetEnvironmentVariable($parts[0], $parts[1], "Process")
}
```

### Step 3: Check walk-forward status
```powershell
Get-Content finetune/data/meanrev_log.jsonl | Select-Object -Last 3
```

### Step 4: Work on ACTIVE_CONTEXT.md priorities

### Step 5 (end of session): Update
- Write insights to relevant H-XXX.md files
- Update champions/STACK.md if any promotions
- Update ROADMAP.md with new hypotheses generated
- Update hypotheses/INDEX.md with status changes
- Reset ACTIVE_CONTEXT.md for next session

---

## Directory Map
```
hypothesis_lab/
├── README.md           ← YOU ARE HERE — session protocol
├── ACTIVE_CONTEXT.md   ← 🚨 READ THIS SECOND — current state + alerts (session-local)
├── CONSTRAINTS.md      ← READ THIRD — locked eval standard, anti-patterns, data assets
├── ROADMAP.md          ← hypothesis queue, priorities
│
├── hypotheses/
│   ├── INDEX.md        ← master table of all hypotheses
│   ├── H-001-*.md      ← URGENT: champion degradation
│   ├── H-002-*.md      ← funding carry collapse investigation
│   ├── H-003-*.md      ← holder-flow signal (Helius)
│   ├── H-004-*.md      ← regime filter
│   ├── H-005-*.md      ← Kelly sizing
│   └── H-XXX-*.md      ← new hypotheses go here
│
├── champions/
│   ├── STACK.md        ← current champion stack + combined EV
│   └── C-001-*.md      ← 🚨 DEGRADING: mean-reversion baseline
│
├── decisions/
│   ├── TREE.md         ← decision tree (what's locked, what's open)
│   └── D-XXX-*.md      ← individual decisions
│
├── sessions/
│   └── YYYY-MM-DD.md   ← per-session logs (heartbeats, results, insights)
│
└── scripts/
    └── run_hypothesis.py  ← test runner (H-001, H-004, H-005 implemented)
```

## 🚨 CRITICAL STATUS

**Champion is DEGRADING.** Walk-forward alert on 2026-06-01:
```
2026-05-31: rule_ev=+0.0157 ✅
2026-06-01: rule_ev=-0.0047 🚨 EDGE DEGRADING (drift=-0.0204)
```

**First priority**: H-001 (diagnosis) → H-004 (regime filter fix).
**DO NOT size up trading until edge is recovered or replaced.**

## Research Philosophy

Every hypothesis must be a **"million dollar idea"** — not incremental, not obvious.
Ask: "Would a top quant fund be surprised this works?"

Every test must use the **temporal holdout + triple-barrier** standard (see CONSTRAINTS.md).
No shortcuts. Leaky results are worse than no results.

**Research loop:**
```
Generate (10-20 ideas, all "million dollar idea" quality)
  → Filter (score: plausibility + data feasibility + novelty; cut <7)
  → Test (temporal holdout, permutation null, triple-barrier)
  → Record (fill H-XXX.md Results + Verdict)
  → Refine (failing hypothesis → find the gap → stronger version → new H-XXX)
  → Stack (passing hypotheses → add to champions/STACK.md)
  → Repeat
```

## Running Tests
```powershell
# From TraderV1 root
python hypothesis_lab/scripts/run_hypothesis.py --hypothesis H-001
python hypothesis_lab/scripts/run_hypothesis.py --hypothesis H-004
python hypothesis_lab/scripts/run_hypothesis.py --hypothesis H-005
```

## Subagent Dispatch
When generating hypotheses in bulk, dispatch parallel subagents:
- See MASTER_PROMPT.md for the complete autonomous research session prompt
