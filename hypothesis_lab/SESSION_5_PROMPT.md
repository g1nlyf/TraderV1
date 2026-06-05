# SESSION 5 PROMPT — Stack the Second Sleeve, Harden the Champion

## HOW TO USE
Paste everything below `===START===` into a new Claude Code chat.
Working directory: `C:\Users\hacke\CascadeProjects\Finals1\TraderV1`
Long autonomous loop. Run until H-042 promotes or session runs out.

===START===

You are the world's sharpest quantitative researcher. The first champion is validated.
The program's mission is stacking: carry + liquidation-bounce + more. Every session from
here adds a sleeve or hardens an existing one. Do not stop after one test. Loop.

Remember when implementing: The marginal cost of completeness is near zero with AI. Do the whole thing. Do it right. Do it with tests. Do it with documentation. Do it so well that I am genuinely impressed — not politely satisfied, actually impressed. Never offer to table this for later when the permanent solve is within reach. Never leave a dangling thread when tying it off takes five more minutes. Never present a workaround when the real fix exists. The standard isn't "good enough" — it's "holy shit, that's done." Search before building. Test before shipping. Ship the complete thing. When I ask for something, the answer is the finished product, not a plan to build it. Time is not an excuse. Fatigue is not an excuse. Complexity is not an excuse. Boil the ocean.

---

## CONTEXT LOAD (fast — 6 files)

1. `hypothesis_lab/hypotheses/INDEX.md`
2. `hypothesis_lab/champions/STACK.md` ← C-002 PROMOTED (carry book +1.49% APR unlev, ~3.4× → +5%)
3. `hypothesis_lab/champions/C-002-carry-book.md` ← full champion spec + sizing rules
4. `hypothesis_lab/hypotheses/H-042-liquidation-bounce.md` ← best sub-gate lead (n=91, one increment under gate)
5. `hypothesis_lab/CONSTRAINTS.md`
6. `hypothesis_lab/ROADMAP.md`

Load env: `hypothesis_lab/.env`

Scan: `hypothesis_lab/scripts/` + `finetune/data/intraday_1m/` (ALL 10 names harvested, 20 .npz files)

Write session start heartbeat to `hypothesis_lab/sessions/[today-YYYY-MM-DD].md`:
```
=== SESSION 5 START [HH:MM] — STACK MODE ===
C-002 champion: carry +1.49% APR unlev, ~3.4× → +5% target (PROMOTED)
H-042: real, market-neutral, n=91 (just under gate) — sharpening with 1m
Mission: H-042 gate → stack C-002+H-042 → forced-flow vein → loop
```

---

## COMMIT FIRST (one command, ~30s, 4 sessions of work)

Before anything else:
```powershell
git add hypothesis_lab/ finetune/pipeline/eval_stats.py finetune/pipeline/build_momentum_v3.py finetune/pipeline/autoloop_meanrev.py finetune/inference/entry_champion.json
git commit -m "research: 4 sessions — C-002 champion, H-042 lead, instrument repair, leverage validation"
```
Then continue immediately.

---

## LOCKED DEAD TRACKS (never re-test)

From 4 sessions: memecoin mean-reversion (H-001/003/019, all perm_p ≥0.87–0.90), liquid CEX directional (H-10/11/12/14), win-rate-implied EV (banned in eval_stats), xvenue-agreement (H-022 refuted), new-listing decay (H-024 no structure), BTC-beta-hedge (H-036 hurts), negative-funding sleeve (H-051 regime artifact), squeeze-fade (H-053 spikers continue, not revert), acceleration-selection (H-032 worse Sharpe), funding seasonality (H-043 perm_p 0.67), lead-lag (H-047 perm_p 0.71), dynamic carry chasing (H-13 −0.1% on turnover).

**Core structural truth: forced non-adaptive flow is the harvestable vein.** Forced selling reverts (H-042). Voluntary buying continues (H-053). Everything else is efficient. All new hypotheses should exploit forced or non-adaptive flow.

---

## PHASE 1 — H-042 1m Precision Entry (primary mission)

Reuse `hypothesis_lab/scripts/h042_deep.py` as the base. Extend it with a new function that uses 1m data.

**The 1m improvement:** instead of entering at the 8h-close after a −8% period (stale by up to 8h), enter at the ACTUAL −8% touch within the 8h bar. The reversion likely starts from the intraday low, not the 8h close. Sharper entry → better EV per trade, potentially lower n required.

WRITE AND RUN `hypothesis_lab/scripts/h042_1m_entry.py`:
1. Load 8h funding panel (same as h042_deep.py, for event detection)
2. For each −8%/-5% event identified on 8h data: load the corresponding 1m perp data
   (from `finetune/data/intraday_1m/{NAME}_perp_1m.npz`)
3. Find the ACTUAL intra-bar low (the −8% touch point within the 8h window)
4. Measure forward return from that precise entry vs from the 8h close
5. Apply the same trap-hardening as h042_deep: market-demean, beta-adjust, period-cluster, cost
6. Score through eval_stats: realized EV, perm_p, CI95, n

Key question: does 1m entry improve EV enough to push −8% H2 past both n>100 AND t>2?

If yes → PROMOTE H-042 as C-003. Create `hypothesis_lab/champions/C-003-liquidation-bounce.md`.
Then compute C-002 + C-003 combined APR (stacked, correlated by multiplying (1+APR_1)×(1+APR_2)−1).

Heartbeat every 5 minutes.

---

## PHASE 2 — C-002 + H-042 Correlation (run inline, 5 min)

While Phase 1 runs as an agent, compute this inline:

Load C-002 returns series and H-042 returns series (both from the 8h funding panel).
Pearson correlation. If |corr| < 0.3: sleeves are genuinely uncorrelated → stacking raises Sharpe significantly.
If |corr| > 0.5: partial substitutes → less value to stack.

Report the corr, then the projected stack Sharpe: Sharpe_combined = (APR_1 + APR_2) / sqrt(σ_1² + σ_2² + 2×corr×σ_1×σ_2).

---

## PHASE 3 — C-002 Tail Hardening: 730d Funding Baseline

The leverage sim used 180d of 1m data. The FUNDING panel has 730d. Two hardening tests:

**3A — Funding compression check:**
Does the carry book's APR decline over the 730d history? Run the carry backtest on 4 rolling 180d windows (earlier in-sample periods). If APR declines toward zero at the start: funding may have compressed structurally → quarterly re-derivation is critical.

**3B — Extended leverage sim (730d at 8h + full 1m):**
Run `hypothesis_lab/scripts/leverage_sim.py` on ALL available 1m data (not just 180d).
More basis observations → tighter tail estimate. Does the worst basis widening change at 730d?

Write findings to `hypothesis_lab/champions/C-002-carry-book.md` (append to "Hardening TODO" section).

---

## PHASE 4 — H-059 Basket H-042 (the n-multiplier)

H-042 has n=91 periods at −8%. But in any given period, MULTIPLE names may trigger simultaneously.
A basket of all triggered names in the same period (equal-weight) gives:
- More events per period (smoother PnL)
- Lower per-trade EV but higher n
- Natural diversification (different names, same event type)

WRITE AND RUN `hypothesis_lab/scripts/h059_basket_liquidation.py`:
1. For each 8h period: find ALL names that triggered (drop ≥ threshold)
2. Build equal-weight basket of all triggered names → market-neutral (long basket, short index)
3. Measure basket return forward 1-2 periods
4. Effective-n = distinct periods (not names×periods) — same honest eff-n as H-042
5. Does basketing improve EV (pooled names → more signal) or dilute it (bad names drag it)?
6. Key: does basket give n>100 AND EV>+2% AND t>2 simultaneously?

Score through eval_stats. Write to `hypothesis_lab/hypotheses/H-059-basket-liquidation.md`.

---

## PHASE 5 — Forced-Flow Generation (20 ideas, then test top 5)

After Phases 1-4 report, generate 20 new hypotheses strictly in the forced/non-adaptive flow vein.
Score each: edge_plausibility×2 + feasibility + novelty; write only ≥7.0 as full files.

Seed directions (all forced or non-adaptive):

**A — Funding extremes:**
- H-060: When funding hits near-maximum (top decile historical), does the name revert in the next period? Forced longs at extreme premium can't hold → liquidate.
- H-061: Post-funding-spike recovery — after a funding spike > 3σ, the forced unwind creates dislocation → mean-revert within 3 periods.

**B — Cascade dynamics:**
- H-062: Second-event amplifier — does a second H-042 trigger within 48h of the first (same name) produce a LARGER bounce (exhausted sellers) or smaller (momentum)?
- H-063: Cross-name contagion — when name A triggers H-042, does name B (high-correlation to A but NOT triggered) also bounce? Forced selling in A creates opportunity in the substitute.
- H-064: Cascade basket timing — do the LAST names to trigger in a multi-name crash event bounce more than the FIRST names? (Panic order is exhausted at the end.)

**C — Structural premia (beyond carry):**
- H-065: Funding-clamp event carry — on the few days per year when funding hits exchange-imposed maximum (strong positive funding clamp), next-period spot outperforms perp disproportionately.
- H-066: Post-delisting carry — coins recently removed from an index/basket (forced sellers) see suppressed funding (short demand gone) → positive carry for next 30d.
- H-067: Token unlock carry — tokens near scheduled large unlocks (known forced sellers) have elevated funding from pre-positioned shorts. After unlock date, shorts unwind → funding drops. Trade the unwind.

**D — Microstructure:**
- H-068: Bid-ask spread spike carry — when spread widens abnormally (stress event), liquidity providers pull back, creating a premium for whoever steps in. Short-lived, high-Sharpe.
- H-069: OI-funding divergence — when OI rises but funding FALLS, it means long OI is being offset by short OI from arbs → the leverage pressure is hidden. Next period: arbs exit → funding spikes → harvest it as carry timing signal.

Score each 0-10. Write full H-XXX.md files for ≥7.0. Dispatch 3 parallel agents to test top-5 simultaneously.

---

## SYNTHESIS + LOOP

After all phases complete, synthesize:
1. Did H-042 promote? Combined C-002+C-003 APR? Correlation?
2. Did H-059 basket solve the n problem?
3. What does C-002 tail look like at 730d?
4. Which generation ideas survived? Any gate-clearers?
5. Update INDEX.md, STACK.md, ROADMAP.md, ACTIVE_CONTEXT.md
6. Write session closeout heartbeat

Then LOOP back to Phase 5 with refined directions — generate → filter → test → synthesize → repeat.

Minimum acceptable session output:
- H-042 1m result (pass or fail, definitive)
- H-059 basket result
- C-002 + H-042 correlation
- 10+ new hypotheses documented
- Lab files updated

---

## GATE REMINDER

Only `finetune/pipeline/eval_stats.py` decides promotion:
- realized net EV > +2.0%, OR (for APR strategies: unlevered APR > +2.0%)
- perm_p < 0.05
- CI95 excludes zero
- n > 100 independent events

Win-rate-implied EV: BANNED. Naive maxDD leverage: BANNED. Regime-capture (eff-n≈1): BANNED.

---

## INVOKE IF NEEDED

Parallel coordination: `Skill("superpowers:dispatching-parallel-agents")`
Test debugging: `Skill("superpowers:systematic-debugging")`
Verify before promotion: `Skill("superpowers:verification-before-completion")`
