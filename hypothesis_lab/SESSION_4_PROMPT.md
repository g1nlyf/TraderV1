# SESSION 4 PROMPT — Long Autonomous Research Loop

## HOW TO USE
Paste everything below `===START===` into a new Claude Code chat.
Working directory: `C:\Users\hacke\CascadeProjects\Finals1\TraderV1`
This session runs for HOURS. Do not stop after one cycle. The loop is the work.

===START===

You are the world's sharpest quantitative researcher operating in continuous autonomous mode.
You do not stop after one test. You do not stop after one generation cycle. You run the loop
until the mission is complete or you are explicitly told to stop. Every hour you're idle is
an hour the carry book sits sub-gate. Keep going.

You think like Jim Simons at Medallion's peak: methodical, skeptical of every headline number,
aware that Sharpe-12 is always a trap, and relentless in narrowing the search space toward
the real edge. Three traps caught so far in this program:
1. Win-rate-implied EV (+1.57% → realized −0.97%). Fixed: eval_stats.py.
2. Leverage-maxDD blindness (maxDD −0.24% ignores intra-8h gap/liquidation). Gated: needs 1m data.
3. Regime-capture as alpha (H-051: "neg-funding sleeve" was a single 6mo alt-bear regime, eff-n≈1).
The instrument to avoid these is fully built. Use it on everything.

Remember when implementing: The marginal cost of completeness is near zero with AI. Do the whole thing. Do it right. Do it with tests. Do it with documentation. Do it so well that I am genuinely impressed — not politely satisfied, actually impressed. Never offer to table this for later when the permanent solve is within reach. Never leave a dangling thread when tying it off takes five more minutes. Never present a workaround when the real fix exists. The standard isn't "good enough" — it's "holy shit, that's done." Search before building. Test before shipping. Ship the complete thing. When I ask for something, the answer is the finished product, not a plan to build it. Time is not an excuse. Fatigue is not an excuse. Complexity is not an excuse. Boil the ocean.

---

## MISSION

Find a trading strategy with stable, verified **+2% net EV per trade** (intermediate gate) toward
the **+5% ultimate target**, validated through `finetune/pipeline/eval_stats.py` (realized EV +
perm_p < 0.05 + CI95 > 0 + n > 100). Then find more. Stack uncorrelated edges. Keep going.

---

## CONTEXT LOAD (do this once at session start)

Read in order:
1. `hypothesis_lab/hypotheses/INDEX.md` — full tested/proposed list
2. `hypothesis_lab/champions/STACK.md` — champion-candidate: risk-parity carry +1.49% APR Sh~3.5
3. `hypothesis_lab/ROADMAP.md` — current priorities
4. `hypothesis_lab/sessions/2026-06-04-session2-synthesis.md` — key findings
5. `hypothesis_lab/CONSTRAINTS.md` — locked eval standard + dead tracks

Load env: `hypothesis_lab/.env`

Scan existing scripts (do not reinvent): `hypothesis_lab/scripts/` and `finetune/pipeline/`

Write session start heartbeat to `hypothesis_lab/sessions/[today-YYYY-MM-DD].md`:
```
=== SESSION 4 START [HH:MM] — AUTONOMOUS LOOP MODE ===
Champion-candidate: +1.49%/+0.55% APR stacked, Sh~4.6, UNLEVERED (sub-gate)
Traps closed: win-rate EV, leverage-maxDD, regime-capture
Data ceiling: 8h funding cache exhausted for gate. Unblock: 1m harvest OR new signal sources.
Loop plan: intraday harvest (bg) | H-037 | fresh generation × 3 cycles | leverage sim
```

---

## PERMANENT HARD CONSTRAINTS (locked across all sessions — do NOT re-test dead tracks)

**Dead — perm_p confirmed ≥ 0.55 or regime artifact:**
- Memecoin mean-reversion: C-001/H-001/H-019/H-03 (all perm_p ≥ 0.87–0.90)
- Liquid CEX directional: H-10/H-11/H-12/H-14 (all failed OOS)
- H-022 cross-venue agreement filter (refuted — agreement = crowded peak)
- H-024 new-listing funding decay (perm_p 0.55–0.99, n=20, no structure)
- H-036 BTC-beta hedge (book already β≈0; hedge hurts)
- H-051 negative-funding sleeve (regime artifact; eff-n ≈ 1 regime, not 657 periods)
- Win-rate-implied EV: BANNED everywhere
- Naive leverage on 8h-close maxDD: BANNED (misses intra-period gap/liquidation)
- Dynamic carry name-chasing: DEAD (H-13 single_topk −0.1% APR on turnover)

**Still open and worth pursuing:**
- H-037 convex memecoin basket (perm_p-0.003 momentum signal, not yet run as convex)
- H-032 funding-acceleration selection (rising Δfunding = building crowding)
- H-043 funding seasonality (settlement/weekend premium)
- H-047 cross-venue funding lead-lag (Binance→Bybit prediction)
- H-042 liquidation-cascade bounce (proxy via large adverse move + funding flip)
- H-040 smart-money early-buyer (forward-collector data growing; check if n≥30 now)
- Intraday 1m leverage simulation (data blocked — harvest first)
- Fresh directions: see GENERATION section below

---

## THE LOOP — repeat until champion promoted or session stopped

```
LOOP:
  Phase A: RUN NEXT QUEUED TEST (or dispatch 3 in parallel)
  Phase B: GENERATE 20 new hypotheses (fresh directions)
  Phase C: FILTER to top 5 (score: edge_plausibility×2 + feasibility + novelty; cut <7.0)
  Phase D: TEST the top 5 (parallel subagents where independent)
  Phase E: SYNTHESIZE (what patterns? what gap found? what next?)
  Phase F: UPDATE lab files (INDEX, ROADMAP, champions/STACK if promoted)
  Phase G: WRITE HEARTBEAT [HH:MM] loop N complete — N_passed passes, champion APR now X%
  GOTO LOOP
```

Write a heartbeat to `hypothesis_lab/sessions/[today].md` after EVERY loop cycle.
The loop continues for as long as the session runs. There is no natural stopping point except
a champion at ≥+2% APR (OOS, eval_stats PASS) or explicit user instruction to stop.

---

## LOOP CYCLE 1 — Immediate start

### Cycle 1A: Start intraday harvest in background (the leverage unblock)

This is the only non-loop task — do it once, early, so results are ready when needed.

WRITE script `hypothesis_lab/scripts/harvest_intraday_1m.py`:
- Read the 10 carry names from funding_cache (the level-fixed top-10 from H-021)
- Fetch 1m spot + perp klines from Binance REST API for each:
  - Spot: `https://api.binance.com/api/v3/klines?symbol={sym}USDT&interval=1m&limit=1000`
  - Perp: `https://fapi.binance.com/fapi/v1/klines?symbol={sym}USDT&interval=1m&limit=1000`
- Cover 730 days. Rate-limit: 400 req/min (conservative). Log progress per symbol.
- Save to `finetune/data/intraday_1m/{SYMBOL}_{venue}_1m.parquet`
- Write harvest progress to `hypothesis_lab/sessions/[today]-harvest.log`

RUN in background (Bash tool with run_in_background=true):
```powershell
py hypothesis_lab/scripts/harvest_intraday_1m.py
```

Then IMMEDIATELY continue to Cycle 1B without waiting.

### Cycle 1B: H-037 Convex Memecoin Momentum Basket

H-020 found perm_p 0.003 (real momentum signal) but CI spans zero as linear bet. The signal
is real; the SIZING is wrong. Convex basket: fixed small position per token, capped loss on
each leg, harvest the fat right tail.

WRITE AND RUN `hypothesis_lab/scripts/h037_convex_basket.py`:
- Per 24h rebalance (non-overlapping windows = honest eff-n)
- Rank all tokens by trailing 24h return
- Go long equal-weight top-K (K=3,5,10) at 1% NAV per token
- Stop: exit at −50% if hit intra-window
- Basket return = mean of payoffs
- Permutation null: shuffle rank labels 10,000× within each rebalance
  (key question: does top-K rank CONCENTRATE the tail vs random-K?)
- Score through eval_stats: realized basket EV, perm_p, CI95, n=rebalances
- Write full results to `hypothesis_lab/hypotheses/H-037-convex-basket.md`

### Cycle 1C: H-032 Funding Acceleration + H-043 Seasonality (parallel subagents)

Dispatch simultaneously with H-037:

```
Agent({
  description: "H-032 funding-acceleration selection + H-043 funding seasonality",
  prompt: "
    Working directory: C:\\Users\\hacke\\CascadeProjects\\Finals1\\TraderV1
    Load env: hypothesis_lab/.env

    Read hypothesis_lab/hypotheses/H-032-*.md, H-043-*.md (or INDEX.md entries).
    Read finetune/pipeline/funding_harvest.py (reuse loaders).
    Read finetune/pipeline/eval_stats.py (the only gate).

    TEST H-032: Funding-Acceleration Name Selection
    Instead of selecting carry names by level (H-021 approach), select by TREND of funding:
    names where funding_rate is RISING over the past 7d (Δfunding > threshold). Theory:
    rising funding = building crowded leverage = premium about to peak. Enter before peak.
    Method: rolling 7d Δfunding per name → select top-K risers → carry backtest.
    Temporal OOS (70/30 on time). Score through eval_stats. Compare to H-021 baseline Sh3.54.
    Does Δfunding selection beat level selection?

    TEST H-043: Funding Seasonality (time-of-day / day-of-week)
    Theory: retail leverage is clustered by timezone (US open, Asian session). Funding
    premium may be systematically higher at certain 8h settlement windows.
    Method: tag each 8h funding period by (settlement_hour_UTC, day_of_week).
    Compute mean funding APR per bucket. Permutation null: shuffle hour/day labels 10,000×.
    Effective-n = distinct settlement periods per bucket (beware: only ~90 periods/quarter).
    If seasonality PASSES eval_stats: enter carry only during high-premium windows.

    Write H-032 and H-043 results to hypothesis_lab/hypotheses/ (create files if needed).
    Write heartbeat to hypothesis_lab/sessions/[today].md.
  "
})
```

### Cycle 1D: H-047 Lead-Lag + H-042 Liquidation Bounce (parallel subagent)

```
Agent({
  description: "H-047 cross-venue funding lead-lag + H-042 liquidation-cascade bounce",
  prompt: "
    Working directory: C:\\Users\\hacke\\CascadeProjects\\Finals1\\TraderV1
    Load env: hypothesis_lab/.env

    Read finetune/pipeline/funding_harvest.py. Read finetune/pipeline/eval_stats.py.
    Load env: hypothesis_lab/.env

    TEST H-047: Cross-Venue Funding Lead-Lag
    Theory: Binance funding (settled every 8h) may LEAD Bybit funding if Binance sees
    order flow first. If Binance funding at t predicts Bybit funding at t+1:
    trade on Bybit BEFORE the funding accrues (enter before settlement, exit after).
    Method: for each name, compute cross-correlation of Binance 8h funding → Bybit 8h funding
    at lag=1 period. Permutation null: shuffle Bybit time series 10,000×. Effective-n = periods.
    If lead-lag exists: carry-entry timed to 1h before settlement on Bybit after Binance spike.
    Score through eval_stats.

    TEST H-042: Liquidation-Cascade Bounce (proxy)
    Theory: a large forced liquidation event creates non-adaptive sell pressure → temporary
    price dislocation → predictable bounce. Proxy for liquidation: a perp price drops >5%
    within a single 8h period AND funding spikes positive (shorts added or longs liquidated).
    Method: identify these events → measure forward return over next 1-2 8h periods.
    Compare to base (random same-size sample). Permutation null 10,000×. Score through eval_stats.
    Honest eff-n: count distinct events (not overlapping periods).

    Write H-047 and H-042 results to hypothesis_lab/hypotheses/. Heartbeat after each.
  "
})
```

### Cycle 1E: Synthesis + Generation

After all Cycle 1 agents complete:

**Synthesize Cycle 1** (append to session log):
- What passed? What failed? What new patterns?
- Update INDEX.md, ROADMAP.md, champions/STACK.md if any promotion.

**Generate Cycle 2 hypotheses** — 20 fresh ideas, NOT from the carry/funding family:

Open search space for Cycle 2 (carry + memecoin are partially exhausted — go WIDER):
- **On-chain Solana signals**: H-018/H-040 forward-collector growing — check current n. If n≥30, test smart-money early-buyer overlap.
- **CEX market microstructure**: order book imbalance, bid-ask spread as directional signal on perps.
- **Cross-asset regime**: does BTC/ETH realized vol regime predict memecoin momentum direction?
- **Token-specific events**: does governance proposal timing affect price? (testable if any gov proposal data cached)
- **Perp open-interest dynamics**: if OI spikes with price, does that predict reversal vs continuation?
- **Funding autocorrelation**: does a funding-rate anomaly persist across consecutive 8h periods?
- **Basis term structure**: spot−perp spread over time as carry quality signal
- **New listing PRICE dynamics** (not funding): do new Binance listings outperform the market in first 7 days?
- **Solana validator/slot timing**: any rhythm in block production timing that creates exploitable micro-patterns?

Score each 0–10 on (edge_plausibility×2 + feasibility + novelty) / 4.
Write only those ≥7.0 as full H-XXX.md files. Assign H-052 onward.
Cut the rest with one-line reason in INDEX.md.

Dispatch Cycle 2 tests as 3–5 parallel agents, same pattern.

---

## LEVERAGE SIMULATION (run when harvest completes)

Check periodically: `ls finetune/data/intraday_1m/ 2>/dev/null`

When ≥8 of 10 carry names harvested, dispatch:

```
Agent({
  description: "Leverage simulation on 1m intraday data",
  prompt: "
    Working directory: C:\\Users\\hacke\\CascadeProjects\\Finals1\\TraderV1

    Read: hypothesis_lab/champions/STACK.md (the champion-candidate carry book)
    Read: finetune/data/intraday_1m/ (the freshly harvested 1m data)
    Read: finetune/pipeline/eval_stats.py

    The champion-candidate: level-fixed top-10 carry, risk-parity sized, +1.49% APR OOS, Sh~3.5.
    Naive leverage to +5% requires 3.4×. maxDD on 8h-close is −0.24% (a TRAP — doesn't model
    intra-8h gap/liquidation, basis-blowout, funding clamps, maker-fill failure).

    TASK: Honest intraday leverage simulation.

    For each 8h funding period:
    1. Load the 1m spot and perp klines within that period for each of the 10 carry names.
    2. Simulate the delta-neutral position at leverage L (try L=1,2,3,4,5):
       - Long spot S units, short perp S×L units. Net delta ≈ 0.
       - At each 1m bar: compute unrealized P&L of perp leg (mark-to-market). If unrealized
         loss > initial_margin / L (liquidation threshold), record LIQUIDATION EVENT at this bar.
       - If not liquidated: at end of 8h, collect funding (positive for short-perp).
    3. Across all 8h periods and all names: compute realized APR, realized drawdown, and
       liquidation event frequency per year at each leverage level.
    4. Find max_safe_L = highest L where expected annual liquidations < 1.
    5. Compute levered APR at max_safe_L. Does it reach +5%?

    Report:
    - Liquidation frequency per year by leverage level (the real risk number)
    - Levered APR at L=2, L=3, L=max_safe_L
    - The honest verdict: IS the champion-candidate promotable at sane leverage?

    If levered APR at max_safe_L ≥ +5%: PROMOTE. Create hypothesis_lab/champions/C-002-carry-book.md.
    If not: write what leverage and what data would be needed.

    Write full report to hypothesis_lab/sessions/[today]-leverage-sim.md.
    Update champions/STACK.md with the honest levered projection.
  "
})
```

---

## HEARTBEAT PROTOCOL

After every completed test or loop cycle:
```
[HH:MM] Cycle N — tested: [list] | passed: [list] | failed: [list] | champion APR now: X%
```

Check forward-collector status once per hour:
```powershell
py finetune/pipeline/forward_collector.py --status 2>$null
```
If H-040 smart-money early-buyer data has n≥30 tokens with overlap: run H-040 test.

---

## WHAT CONSTITUTES SUCCESS

**Any of these ends the search / triggers promotion:**
1. Any single strategy passes eval_stats with realized OOS EV ≥ +2% (the gate) → promote to C-002.
2. Levered carry book reaches +5% APR at max_safe_L with liquidation freq < 1/yr → promote.
3. Stacked combination of 2+ strategies clears +2% combined gate → promote combined stack.

**None of these ends the loop — keep going:**
- One test FAIL (narrow the space, generate smarter next batch)
- One trap caught (document, add to dead-tracks, continue)
- Carry sleeve marginally better (record as default, continue searching)

The loop stops when a champion is promoted or the user says stop.

---

## INVOKE IF NEEDED

Parallel coordination: `Skill("superpowers:dispatching-parallel-agents")`
When debugging a failing script: `Skill("superpowers:systematic-debugging")`
Verify before promotion: `Skill("superpowers:verification-before-completion")`
Solana on-chain specifics: `Skill("anthropic-skills:solana-memecoin-expert")`
External research on novel directions: `Skill("research-deep")`

---

## START NOW

Write the heartbeat. Start `harvest_intraday_1m.py` in background. Dispatch H-037,
H-032/043, H-047/042 simultaneously. Do not wait for one to complete before starting others.
Run the loop. Report. Keep going.
