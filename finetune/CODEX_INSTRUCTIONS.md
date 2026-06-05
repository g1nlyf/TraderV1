# Codex 5.5 — Teacher Data Collection Instructions

## Your Task

Run the teacher service to collect training data for fine-tuning a signal reviewer model.
You will process real trading signals from the stage2 database using OpenRouter + owl-alpha,
save full tool-call conversations as training sessions, and repeat until the target count is reached.

**Goal: collect 200–300 labeled training sessions.**

---

## Environment Setup

### 1. Set environment variable (REQUIRED — never write key to any file)

```powershell
$env:OPENROUTER_API_KEY = "your-api-key-here"
```

### 2. Install dependencies (if not already installed)

```powershell
cd C:\Users\hacke\CascadeProjects\Finals1\TraderV1
pip install openai aiosqlite pydantic rich
```

### 3. Verify WalletScarper venv exists

```powershell
Test-Path "C:\Users\hacke\CascadeProjects\Finals1\TraderV1\WalletScarper\.venv\Scripts\python.exe"
# Must return True — this venv executes the tool calls
```

If False, set it up:
```powershell
cd C:\Users\hacke\CascadeProjects\Finals1\TraderV1\WalletScarper
python -m venv .venv
.venv\Scripts\pip install -e .
```

---

## Running the Teacher Service

### Basic run (process all pending signals, write to DB + sessions):

```powershell
cd C:\Users\hacke\CascadeProjects\Finals1\TraderV1\finetune
python scripts/teacher_service.py --provider openrouter --model openrouter/owl-alpha
```

### Dry run first (no DB writes, verify everything works):

```powershell
python scripts/teacher_service.py --provider openrouter --model openrouter/owl-alpha --dry-run --max-signals 3
```

### Limit batch size (recommended: process in batches of 20):

```powershell
python scripts/teacher_service.py --provider openrouter --model openrouter/owl-alpha --max-signals 20
```

### Run repeatedly until target reached:

```powershell
# Keep running until you have 200+ sessions in finetune/data/sessions/
while ($true) {
    $count = (Get-ChildItem "data/sessions/*.json" -ErrorAction SilentlyContinue | Measure-Object).Count
    Write-Host "Sessions collected: $count"
    if ($count -ge 200) { Write-Host "Target reached!"; break }
    python scripts/teacher_service.py --provider openrouter --model openrouter/owl-alpha --max-signals 20
    Start-Sleep -Seconds 5
}
```

---

## What the Script Does

For each pending signal in `stage2_foundation.sqlite3`:

1. Sends signal to `openrouter/owl-alpha` with system prompt from `prompts/teacher_system.md`
2. Model calls tools in sequence:
   - `wallet_profile_history` → queries real DB via stage2-v2-tool CLI
   - `token_get_profile` → queries real DB + external sources
   - `agent_record_trading_decision` → writes decision to DB
3. Full conversation (messages + tool results) saved to `data/sessions/<signal_id>.json`
4. Session includes: signal_id, model, elapsed_time, decision_recorded, full message history

---

## Session File Format

Each session saved to `finetune/data/sessions/<uuid>.json`:

```json
{
  "session_id": "uuid",
  "signal_id": "uuid",
  "model": "openrouter/owl-alpha",
  "provider": "openrouter",
  "timestamp": "2026-05-26T...",
  "elapsed_seconds": 12.4,
  "decision_recorded": true,
  "outcome_label": null,
  "messages": [
    {"role": "system", "content": "..."},
    {"role": "user", "content": "AUTONOMOUS SIGNAL REVIEW..."},
    {"role": "assistant", "tool_calls": [...]},
    {"role": "tool", "tool_call_id": "...", "content": "{...}"},
    {"role": "assistant", "tool_calls": [...]},
    {"role": "tool", "tool_call_id": "...", "content": "{...}"},
    {"role": "assistant", "tool_calls": [{"function": {"name": "agent_record_trading_decision", ...}}]},
    {"role": "tool", "tool_call_id": "...", "content": "{\"ok\": true, ...}"}
  ]
}
```

---

## Monitoring Progress

### Check session count:
```powershell
(Get-ChildItem "data/sessions/*.json" | Measure-Object).Count
```

### Check decision rate (sessions with decision_recorded=true):
```powershell
Get-ChildItem "data/sessions/*.json" | ForEach-Object {
    $s = Get-Content $_ | ConvertFrom-Json
    $s.decision_recorded
} | Group-Object | Format-Table
```

### Check pending signals remaining:
```powershell
cd C:\Users\hacke\CascadeProjects\Finals1\TraderV1\WalletScarper
.venv\Scripts\python -c "
import sqlite3
db = sqlite3.connect('data/stage2_foundation.sqlite3')
n = db.execute('''
    SELECT COUNT(*) FROM tracked_wallet_signal_events s
    WHERE s.input_mode = ''real_source''
    AND NOT EXISTS (
        SELECT 1 FROM agent_trading_decisions d
        WHERE d.linked_tracked_wallet_signal_event_id = s.tracked_wallet_signal_event_id
    )
''').fetchone()[0]
print(f'Pending signals: {n}')
"
```

---

## Handling Errors

### "WalletScarper venv not found"
→ Set up the venv (see Environment Setup step 3).

### "Tool wallet.profile_history failed (rc=1)"
→ The stage2 DB may be empty or schema mismatch. Check:
```powershell
cd WalletScarper
.venv\Scripts\python -c "
import sqlite3
db = sqlite3.connect('data/stage2_foundation.sqlite3')
tables = db.execute(\"SELECT name FROM sqlite_master WHERE type='table'\").fetchall()
print(tables)
"
```

### OpenRouter rate limit errors (429)
→ Add sleep between batches: `Start-Sleep -Seconds 30` between 20-signal batches.
→ owl-alpha is free tier — if rate-limited, try `openrouter/qwen/qwen3-30b-a3b:free` as fallback.

### "No pending signals"
→ WalletScarper needs to run to generate new signals. Check if the daemon is running:
```powershell
cd WalletScarper
.venv\Scripts\python -m walletscarper stage2-run-daemon --help
```
Or trigger discovery manually to populate signals first.

---

## What to Do When Signals Run Out

If fewer than 200 pending signals exist, also generate synthetic training examples:

```powershell
cd C:\Users\hacke\CascadeProjects\Finals1\TraderV1\finetune
python scripts/03_generate_bootstrap.py --count 150
```

This creates `data/training/bootstrap.jsonl` with format-correct synthetic examples
(no real context, but teaches correct tool call sequences).

---

## After Collection: Next Steps

Once 200+ sessions collected, report back to the user. The next phases are:

1. **Label outcomes** (05_label_outcomes.py) — match sessions to paper trade P&L
2. **Export dataset** (06_export_dataset.py) — convert sessions → JSONL for fine-tuning
3. **Fine-tune on Together.ai** (07_train.py) — submit Qwen 2.5 7B training job
4. **Deploy fine-tuned model** — replace owl-alpha teacher with trained flash model
5. **Phase 2** — real-budget paper trading loop with continuous retraining

---

## Important Notes

- **Never write OPENROUTER_API_KEY to any file** — env var only
- The script skips signals that already have a decision in `agent_trading_decisions`
- Sessions with `decision_recorded: false` are kept but not used for training
- Target decision rate: >80% (model should record a decision for most signals)
- If decision rate is low (<60%), check `prompts/teacher_system.md` — the model may be confused
