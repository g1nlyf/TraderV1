# SESSION 2 PROMPT — From Runway to Flight

## HOW TO USE
Paste everything below `===START===` into a new Claude Code chat.
Working directory: `C:\Users\hacke\CascadeProjects\Finals1\TraderV1`
Walk away. Come back to results.

===START===

You are the world's sharpest quantitative researcher. You think like Jim Simons building Medallion — not chasing obvious signals, but finding structural premia others can't touch due to friction, capacity, or attention. Every idea is a million dollar idea or it doesn't exist. Half-measures are not accepted. Incomplete tests are not accepted.

Remember when implementing: The marginal cost of completeness is near zero with AI. Do the whole thing. Do it right. Do it with tests. Do it with documentation. Do it so well that I am genuinely impressed — not politely satisfied, actually impressed. Never offer to table this for later when the permanent solve is within reach. Never leave a dangling thread when tying it off takes five more minutes. Never present a workaround when the real fix exists. The standard isn't "good enough" — it's "holy shit, that's done." Search before building. Test before shipping. Ship the complete thing. When I ask for something, the answer is the finished product, not a plan to build it. Time is not an excuse. Fatigue is not an excuse. Complexity is not an excuse. Boil the ocean.

---

## CONTEXT (load fast — no cold start)

Read these 5 files, in order, before anything else:
1. `hypothesis_lab/hypotheses/INDEX.md`
2. `hypothesis_lab/champions/STACK.md`
3. `hypothesis_lab/ROADMAP.md`
4. `hypothesis_lab/sessions/2026-06-04-synthesis.md`
5. `hypothesis_lab/CONSTRAINTS.md`

Load env vars from `hypothesis_lab/.env`.

Write first heartbeat to `hypothesis_lab/sessions/[today-YYYY-MM-DD].md`:
```
=== SESSION 2 START [HH:MM] ===
State: champion stack EMPTY, instrument honest, 3 leads queued
Mission: H-024 → H-021 → H-022 → broad generation
```

**Three structural truths from Session 1 — hard constraints, do not re-test dead tracks:**
1. **Memecoins trend, they don't revert.** Every reversion bet died (C-001 realized −0.97%, H-015 refuted, H-019 perm_p 0.90). Momentum is real (perm_p 0.003) but unsizeable lottery. Stop.
2. **Liquid CEX directional factors are dead.** H-10/11/12/14 all failed. Don't regenerate them.
3. **Only positive EV found = structural carry (+1.4% APR stacked, sub-gate).** The +9.1% headline is trapped in spot-less perps you can't delta-hedge. The capturable part is small but real.

**The only gate:** `finetune/pipeline/eval_stats.py` — realized EV + perm_p < 0.05 + CI95 > 0 + n > 100. Win-rate-implied EV is banned. Effective-n = distinct independent events, not overlapping windows.

---

## MISSION: THREE PARALLEL TESTS + GENERATION

Dispatch all three testing agents simultaneously. Do not batch sequentially.

---

### AGENT 1 — H-024: New-Listing Funding Decay Carry

```
Agent({
  description: "H-024: New-listing funding decay event study + carry backtest",
  prompt: "
    Working directory: C:\\Users\\hacke\\CascadeProjects\\Finals1\\TraderV1

    Read:
    - hypothesis_lab/hypotheses/H-024-new-listing-funding-decay.md  (full spec)
    - hypothesis_lab/CONSTRAINTS.md  (eval standard)
    - finetune/pipeline/funding_harvest.py  (reuse loaders — search before building)
    - finetune/pipeline/eval_stats.py  (the only gate)
    - finetune/data/funding_cache/  (browse what's cached)

    Hypothesis: newly listed perps carry elevated, decaying positive funding in their first
    weeks (launch-hype crowded longs, no cheap arbitrageur). Structural, recurring, testable
    on cached data.

    Build and run a complete test:

    STEP 1 — Event study
    Per asset, first funding timestamp = listing date (proxy). Compute mean funding APR per
    age bucket: {day 1-3, 4-7, 8-30, 31+}. Paired test across names. Permutation: shuffle
    age-bucket labels within each name 10,000×. Report: funding APR by age bucket + perm_p.
    Effective-n = distinct asset listing events (not 8h periods within one listing).

    STEP 2 — Carry backtest
    Short-perp carry position entered at listing, held for horizon N days, EWMA-sized by
    funding level. Delta-hedged where spot_8h exists (basis-aware leg from funding_harvest);
    basket-hedged otherwise. Realized net PnL after maker cost (1bp/leg). Temporal OOS split
    across listing calendar (train on earlier listings, test on later). Score through eval_stats:
    realized EV + perm_p + CI95. Effective-n = distinct listings in test set.

    STEP 3 — Parameter sweep
    horizon N ∈ {3,7,14,30}d. EWMA span ∈ {1,3,6}. Report best + worst configs.

    STEP 4 — Write results
    Fill hypothesis_lab/hypotheses/H-024-new-listing-funding-decay.md Results + Verdict.
    If PASS: note path to champion stack. If FAIL: write refinement path for cross-venue
    variant (new listings via Binance−Bybit xvenue maker spread — H-13 showed xvenue
    maker +0.6% baseline; new listings may be richer).

    Write heartbeat every 5min to hypothesis_lab/sessions/[today].md.
    Load env: hypothesis_lab/.env
  "
})
```

---

### AGENT 2 — H-021: Persistence-Selected Carry

```
Agent({
  description: "H-021: Lift the carry sleeve via funding-persistence name selection",
  prompt: "
    Working directory: C:\\Users\\hacke\\CascadeProjects\\Finals1\\TraderV1

    Read:
    - hypothesis_lab/hypotheses/H-021-*.md  (if exists) OR the INDEX.md entry for H-021
    - hypothesis_lab/champions/STACK.md  (current carry baseline: tradeable +0.8% APR)
    - finetune/pipeline/funding_harvest.py  (reuse — especially single_topk engine)
    - finetune/pipeline/eval_stats.py  (the only gate)

    Hypothesis: select carry names by STABILITY of funding sign (consistent positive
    vs spikey/reversing), not by level. Stable-sign names have structural long bias from
    real demand (not noise spikes); carry from them is durable. This should lift the
    validated +0.8% tradeable sleeve toward the +2% gate.

    Build and run:

    STEP 1 — Persistence signal
    For each tradeable asset (29 names from H-13 tradeable filter): compute 30-day rolling
    funding-sign persistence = fraction of 8h periods with positive funding. Sort by
    persistence. Compare carry APR of top-K (most persistent) vs full universe vs bottom-K.
    Permutation null: shuffle persistence-rank assignment 10,000×.

    STEP 2 — Carry backtest on persistence-selected universe
    Replace the 'top-10 by funding level' selection in H-13 with 'top-10 by funding
    persistence'. Re-run the full carry backtest (maker, basis-aware, 8h rebalance).
    Score through eval_stats: realized EV, perm_p, CI95. Compare Sharpe vs baseline +0.8%.

    STEP 3 — Combination test
    Does persistence-selected + xvenue-maker combined beat either alone? Combined realized EV.

    Write full results to hypothesis_lab/hypotheses/H-021-persistence-carry.md (create file
    using H-XXX template from CONSTRAINTS.md). Verdict via eval_stats.
    Write heartbeat to hypothesis_lab/sessions/[today].md.
    Load env: hypothesis_lab/.env
  "
})
```

---

### AGENT 3 — H-022: Cross-Venue Agreement as Carry Quality Filter

```
Agent({
  description: "H-022: Cross-venue funding agreement as carry quality signal",
  prompt: "
    Working directory: C:\\Users\\hacke\\CascadeProjects\\Finals1\\TraderV1

    Read:
    - hypothesis_lab/champions/STACK.md  (xvenue carry baseline: +0.6% APR, fragile)
    - finetune/pipeline/funding_harvest.py  (xvenue engine + data loaders)
    - finetune/pipeline/eval_stats.py  (the only gate)

    Hypothesis: when Binance AND Bybit funding both agree (same sign, similar magnitude),
    the carry is structural demand — not a venue-specific quirk. Filter carry entries to
    periods of agreement. Expected: higher realized EV per entry and/or better Sharpe by
    removing noise entries. Rationale: agreement = broad market crowding (real carry);
    disagreement = venue artefact (no carry, just noise).

    Build and run:

    STEP 1 — Agreement filter definition
    Agreement: |funding_binance - funding_bybit| < threshold × max(|fb|, |fby|), AND
    same sign. Sweep threshold ∈ {0.2, 0.5, 1.0}. Compute what fraction of periods pass.

    STEP 2 — Carry backtest with agreement gate
    Re-run H-13's tradeable single EW carry (baseline +0.8% APR) AND xvenue carry (+0.6%),
    both gated to agreement periods only. Score through eval_stats. Compare:
    - realized EV per trade (agreement-filtered vs unfiltered)
    - Sharpe  (agreement-filtered vs unfiltered)
    - n surviving (is the gate too aggressive?)

    STEP 3 — Combined
    Agreement-filtered tradeable + agreement-filtered xvenue stacked. Combined realized APR.
    Does it clear the +2% gate?

    Write full results to hypothesis_lab/hypotheses/H-022-xvenue-agreement-filter.md.
    Verdict via eval_stats. Write heartbeat to hypothesis_lab/sessions/[today].md.
    Load env: hypothesis_lab/.env
  "
})
```

---

### Heartbeat while waiting

Every 5 minutes while agents run, append to `hypothesis_lab/sessions/[today].md`:
`[HH:MM] Agents running: H-024 [status], H-021 [status], H-022 [status]`

---

## AFTER ALL THREE COMPLETE — Synthesis + Generation

When all three agents finish, dispatch:

```
Agent({
  description: "Session 2 synthesis + next-batch generation",
  prompt: "
    Working directory: C:\\Users\\hacke\\CascadeProjects\\Finals1\\TraderV1

    Read everything in hypothesis_lab/ (all H-XXX files, STACK.md, INDEX.md, ROADMAP.md,
    today's session log). You are the research director after the session's test cycle.

    SYNTHESIS (write to hypothesis_lab/sessions/[today]-synthesis.md):
    1. What did H-024, H-021, H-022 find? Are any carry sleeves now at or near the +2% gate?
    2. What patterns emerged? What does the distribution tell you about WHERE the edge hides?
    3. Update champions/STACK.md if anything passed (combined EV formula: (1+EV1)×(1+EV2)−1).
    4. Update hypotheses/INDEX.md with all new verdicts.
    5. Update ROADMAP.md.

    GENERATION (write 15 new H-XXX files to hypothesis_lab/hypotheses/):
    Now generate 15 'million dollar idea' hypotheses INFORMED BY WHAT THIS SESSION FOUND.
    Hard constraints:
    - No memecoin mean-reversion (dead: H-001, H-019, perm_p ≥0.87-0.90)
    - No liquid CEX directional factors (dead: H-10/11/12/14)
    - No win-rate-implied EV anything
    - Effective-n must be honest (distinct independent events, not overlapping windows)
    - Each must be testable with data in CONSTRAINTS.md
    - Each must have a clear structural reason why a top fund can't capture it (friction/capacity/newness)

    Directions that are open and unexplored:
    - On-chain signals: early-buyer overlap × token age × wallet win-rate (H-003/H-018 data growing)
    - Carry extensions: new listings, liquidation events, funding during extreme volatility
    - Options/vol surface signals if any CEX options data cached
    - Cross-asset: BTC/ETH options skew as memecoin entry gate
    - Token-specific: unlock schedules, airdrop dates, governance vote windows
    - Order flow: does the direction of large trades predict short-horizon returns on perps?
    - Time-of-day / day-of-week seasonality in funding (real? structural? testable?)
    - Liquidation cascade: does a large forced liquidation event create a measurable bounce?
    - Smart money wallets × new token launches: are there tracked wallets that consistently
      buy early and win? (H-003 / forward_collector data)

    Score each generated idea (edge_plausibility×2 + feasibility + novelty) before writing it.
    Only write full H-XXX files for ideas scoring ≥7 average. Assign IDs H-031 onward.

    Write a 1-line filter note in INDEX.md for anything scored and cut.
  "
})
```

---

## SUCCESS CRITERIA

Session ends when:
- `champions/STACK.md` shows any champion at ≥ +2% realized OOS EV → **gate cleared, step toward execution**
- OR all three leads tested + 15 hypotheses documented → closeout, queue session 3

Write session closeout to `hypothesis_lab/sessions/[today].md`:
- H tested, H passed, H failed
- Champion stack EV now
- #1 priority for session 3

---

## INVOKE IF NEEDED

Solana-specific thinking: `Skill("anthropic-skills:solana-memecoin-expert")`
Parallel swarm coordination: `Skill("superpowers:dispatching-parallel-agents")`
Test debugging: `Skill("superpowers:systematic-debugging")`
External strategy research: `Skill("research-deep")`
