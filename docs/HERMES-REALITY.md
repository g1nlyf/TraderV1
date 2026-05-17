# Hermes — What It Is and What It Isn't

**Read this before any other Hermes documentation.**

---

## The Core Confusion

There are **two completely different things** in this project both called "Hermes." They share a name, share an OpenRouter API key, and share a model — but they are architecturally separate. Confusing them leads to wrong conclusions about system readiness.

---

## Thing 1: Hermes CLI Agent (External Tool)

**What it is:** A third-party AI agent CLI tool — `hermes-agent` — installed in `external/hermes-agent/`. This is NOT code written for this project. It's an external tool that has been installed, configured, and given a custom plugin.

**How to run:**
```bash
scripts/run-hermes.bat
# Opens an interactive terminal session where you chat with Hermes
```

**What it does:** You chat with it in natural language. It can call 24 project-specific tools (`traderv1_operator` plugin) to inspect system state, run reports, and make paper trading decisions.

**Model:** `openai/gpt-oss-20b:free` via OpenRouter  
**Config:** `~/.hermes/config.yaml`  
**Plugin:** `.hermes/plugins/traderv1_operator/plugin.yaml` — 24 V2 tools registered

**What it CAN do:**
- Read system health, token candidates, wallet scores
- Review wallet histories, token profiles
- Record `agent_wallet_review` decisions
- Trigger the full paper trading path: signal → risk → paper → exit
- Access all 24 V2 tools through natural language

**Verified working:**
- `hermes.exe` exists in `.venv/Scripts`
- Plugin registered with 24 tools
- Direct OpenRouter smoke test passed
- Hermes one-shot passed when env was loaded (from `current-system-reality-audit.md`)

**Has it been used in production?**  
No. The operator has never run `scripts/run-hermes.bat` interactively. The tool is configured and working, but has not been part of any real trading decision.

**Is it "real Hermes" or a custom hack?**  
It's a real external tool, properly installed. The `traderv1_operator` plugin (24 tools) is custom code for this project, but the Hermes agent itself is not a custom hack.

---

## Thing 2: HermesSignalReviewService (Custom Autonomous Loop)

**What it is:** Custom Python code in `walletscarper/stage2/hermes_review/service.py`. This is NOT the Hermes CLI agent. This is an autonomous background service written specifically for this project.

**What it does:**
1. Polls `tracked_wallet_signal_events` for unreviewed real signals every scheduler tick
2. Builds a context prompt with wallet history, token data, signal details
3. Calls OpenRouter API directly (no Hermes CLI involved)
4. Gets back JSON: `{decision_type, confidence, signal_strength, reasoning, ...}`
5. Records `AgentTradingDecision` in the deterministic ledger
6. If `decision_type == "signal"` AND confidence/strength meet thresholds → runs full paper path

**Model:** `openai/gpt-oss-20b:free` via OpenRouter  
**API call:** Direct `httpx` POST to `https://openrouter.ai/api/v1/chat/completions`  
**Config:** `HERMES_ENABLED`, `HERMES_API_KEY`, `HERMES_MODEL` in `.env`

**Decision schema returned by LLM:**
```json
{
  "decision_type": "signal" | "no_trade" | "wait" | "downgrade_wallet",
  "pre_action_reasoning": "2-5 sentence explanation",
  "confidence": "high" | "medium" | "low",
  "signal_strength": "strong" | "moderate" | "weak" | "absent",
  "wallet_assessment": "1-2 sentences",
  "token_assessment": "1-2 sentences",
  "uncertainties": ["list of unknowns"]
}
```

**Gates before paper path runs:**
1. `HERMES_ENABLED=true` in env
2. `HERMES_API_KEY` set
3. Not rate-limited (< 50 decisions/hr by default)
4. `decision_type == "signal"`
5. `confidence == "high"` (configurable)
6. `signal_strength >= "moderate"` (configurable)

**Has it ever made a real decision?**  
**No.** As of 2026-05-17: 7 real wallet signal events exist in `tracked_wallet_signal_events` with `input_mode=real_source`. Zero `agent_trading_decisions` are linked to any of them.

**Why not?**  
Most likely reasons:
- Scheduler hasn't been running long enough in configured state
- `HERMES_ENABLED` may not have been `true` before OpenRouter key was added (2026-05-16)
- The 7 signals exist but the review service hasn't processed them yet
- This is NOT a code bug — the code is correct and wired. It just hasn't run.

---

## The Model: `openai/gpt-oss-20b:free`

Both Hermes systems use this model. Key facts:

- **Free tier** model via OpenRouter
- ~20 billion parameters
- **NOT GPT-4, NOT Claude Sonnet, NOT a frontier model**
- Capable of basic reasoning, structured JSON output, following instructions
- May produce lower-quality trading analysis than a frontier model
- For production use with real money, upgrading to `anthropic/claude-3.5-sonnet` or `openai/gpt-4o` would be recommended

To change model, update `.hermes/config.yaml` (for CLI agent) or `HERMES_MODEL` env var (for autonomous loop).

---

## Summary: Is "Hermes" Working?

| Question | Answer |
|----------|--------|
| Is the Hermes CLI agent installed? | ✅ Yes |
| Can it access the 24 V2 tools? | ✅ Yes |
| Has it ever been run by the operator? | ❌ No |
| Is the autonomous review loop coded? | ✅ Yes |
| Is it wired to the scheduler? | ✅ Yes |
| Has it made a real trading decision? | ❌ No |
| Has it made a fixture-mode decision? | ✅ Yes (smoke tests pass) |
| Is the OpenRouter key configured? | ✅ Yes (added 2026-05-16) |
| Is the model frontier/powerful? | ⚠️ No — free 20B model |

**Bottom line:** Hermes is real infrastructure, not a hallucination. The autonomous loop is wired and ready. It simply hasn't been run against real signals long enough to produce decisions. This should be the first thing to verify: run `scripts/run-hermes.bat`, then let the scheduler run for 30 minutes and check if `agent_trading_decisions` populates.

---

## How to Verify Hermes is Working

### Test 1: Run Hermes CLI Interactively
```bash
scripts/run-hermes.bat
# In the session, type:
> health check
> show me the top token candidates
> what tracked wallet signals are waiting for review?
```

### Test 2: Check Autonomous Loop
```bash
# 1. Confirm env vars
grep HERMES WalletScarper/.env

# 2. Confirm 7 unreviewed real signals exist
python -m walletscarper stage2-v2-tool agent.list_pending_reviews

# 3. Run a single review tick manually
python -c "
import asyncio
from walletscarper.stage2.db import Stage2Database
from walletscarper.stage2.hermes_review.service import HermesSignalReviewService
async def main():
    db = Stage2Database()
    await db.initialize()
    svc = HermesSignalReviewService(db)
    result = await svc.review_pending_signals(max_signals=1)
    print(result)
asyncio.run(main())
"

# 4. Check if a decision was recorded
python -m walletscarper stage2-v2-tool agent.record_trading_decision --list
```

### Test 3: Check Scheduler is Running Hermes
```bash
python -m walletscarper run  # starts full scheduler
# Watch logs for: "hermes_review: reviewed=X recorded=Y"
```
