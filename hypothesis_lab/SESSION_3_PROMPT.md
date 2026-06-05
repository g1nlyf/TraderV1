# SESSION 3 PROMPT — Lift the Carry Book + Unlock Leverage

## HOW TO USE
Paste everything below `===START===` into a new Claude Code chat.
Working directory: `C:\Users\hacke\CascadeProjects\Finals1\TraderV1`
Walk away. This session runs 3 parallel tracks.

===START===

You are the world's sharpest quantitative researcher. You think like Jim Simons at his peak — not slicing marginal signals, but finding the clean paths others miss by measuring the wrong things. Every conclusion is earned by the data, not the narrative.

Remember when implementing: The marginal cost of completeness is near zero with AI. Do the whole thing. Do it right. Do it with tests. Do it with documentation. Do it so well that I am genuinely impressed — not politely satisfied, actually impressed. Never offer to table this for later when the permanent solve is within reach. Never leave a dangling thread when tying it off takes five more minutes. Never present a workaround when the real fix exists. The standard isn't "good enough" — it's "holy shit, that's done." Search before building. Test before shipping. Ship the complete thing. When I ask for something, the answer is the finished product, not a plan to build it. Time is not an excuse. Fatigue is not an excuse. Complexity is not an excuse. Boil the ocean.

---

## CONTEXT (5-file load — no cold start)

Read in order:
1. `hypothesis_lab/hypotheses/INDEX.md`
2. `hypothesis_lab/champions/STACK.md`
3. `hypothesis_lab/ROADMAP.md`
4. `hypothesis_lab/sessions/2026-06-04-session2-synthesis.md`
5. `hypothesis_lab/CONSTRAINTS.md`

Load env: `hypothesis_lab/.env`

Write first heartbeat to `hypothesis_lab/sessions/[today-YYYY-MM-DD].md`:
```
=== SESSION 3 START [HH:MM] ===
Champion-candidate: carry stack +1.44%/+0.6% APR, Sharpe 4.28, maxDD -0.1%, UNLEVERED
Mission: lift unlevered → test novel → harvest intraday → validate leverage
```

**Hard-locked from 2 sessions:**
- Memecoins: trend, not revert. No reversion hypotheses. (Dead: H-001/019/03/15, all perm_p ≥0.67)
- Liquid CEX directional: dead. (H-10/11/12/14)
- Win-rate-implied EV: BANNED. Only realized payoff through `eval_stats`.
- Effective-n: count distinct independent events, not overlapping windows.
- Cross-venue agreement filter: REFUTED (H-022). Don't re-test.
- New-listing decay: FAIL (H-024, no systematic pattern at n=20 listings).
- Dynamic carry name-chasing: DEAD (H-13 single_topk −0.1% on turnover). Fixed selection only.

**What we have:** champion-candidate = level-fixed top-10 carry (+1.44% APR Sh3.20) + xvenue maker (+0.6% APR Sh3.93), stacked Sh4.28, corr+0.01. Unlevered APR ~+1.0–1.4%. Gate = +2% promoted / +5% target. Path: stack more uncorrelated sleeves + sane 2–3× leverage (tail-gated on intraday data we don't have yet).

---

## THREE PARALLEL TRACKS — dispatch all simultaneously

---

### TRACK 1 (AGENT): Carry Refinements — H-031, H-049, H-036, H-051

Four carry tests, one shared panel load. Same pattern as Session 2's shared harness.

```
Agent({
  description: "Carry refinements: H-031 risk-parity + H-049 carry-to-vol + H-036 beta-hedge + H-051 neg-funding sleeve",
  prompt: "
    Working directory: C:\\Users\\hacke\\CascadeProjects\\Finals1\\TraderV1

    Read:
    - hypothesis_lab/hypotheses/H-031-*.md
    - hypothesis_lab/hypotheses/H-049-*.md
    - hypothesis_lab/hypotheses/H-036-*.md
    - hypothesis_lab/hypotheses/H-051-*.md
    - hypothesis_lab/champions/STACK.md  (the champion-candidate to improve)
    - finetune/pipeline/funding_harvest.py  (reuse loaders — search before building)
    - finetune/pipeline/eval_stats.py  (the only gate)
    Load env: hypothesis_lab/.env

    Baseline: level-fixed top-10 carry +1.44% APR Sharpe 3.20, OOS 6mo.
    Goal: lift unlevered APR toward +2% gate, or lift Sharpe (enables safer leverage later).

    BUILD ONE SHARED SCRIPT: hypothesis_lab/scripts/h031_049_036_051_carry_lift.py

    TEST 1 — H-031: Risk-parity sizing (weight each name by 1/funding-volatility)
    Same top-10 fixed names, but instead of equal-weight, size inversely proportional to the
    trailing 30-day stdev of that name's funding rate. Names with stable funding get more
    weight; spiky names get less. Does this improve Sharpe (consistent carry) vs EW baseline?
    Temporal OOS, eval_stats gate.

    TEST 2 — H-049: Carry-to-vol selection (rank by funding_rate / realized_vol)
    Instead of selecting top-10 by raw funding level, select top-10 by funding/realized_vol
    (carry per unit of price risk). Names with high carry AND low vol are the real premium;
    high carry + high vol might be distressed. Does this selection rule beat pure level-ranked?
    Train: select names on first 70% by Sharpe of (funding_rate/realized_vol). Test: hold those
    names in OOS 30%. Score through eval_stats.

    TEST 3 — H-036: BTC-beta neutralize the carry book
    Compute rolling 60-day beta of the carry book returns to BTC 8h returns. Hedge it by
    shorting BTC proportionally each period. Does removing residual BTC-beta raise Sharpe
    and lower maxDD? Cost: BTC short at 5.5bps/side taker. Compute net APR + Sharpe before/after.

    TEST 4 — H-051: Negative-funding sleeve (third uncorrelated stack component)
    For names where funding is PERSISTENTLY NEGATIVE (select on train, hold on test): go
    LONG the perp (receive negative funding as negative of funding cost) + short the spot leg.
    This harvests the crowded-shorts premium — structurally opposite to the positive-carry sleeve.
    Compute APR, Sharpe, correlation to the positive carry sleeve. If corr < 0.3 and positive APR:
    this is a third uncorrelated stack component.

    For ALL tests: score through eval_stats (realized EV + perm_p + CI95). Stacking rule for
    multi-sleeve combinations: (1+APR_1)×(1+APR_2)×(1+APR_3) − 1.

    Write results to each H-XXX.md file. Update champions/STACK.md if any test passes.
    Write heartbeat to hypothesis_lab/sessions/[today].md every 5 min.
  "
})
```

---

### TRACK 2 (AGENT): H-037 — Convex Memecoin Momentum Basket

The one genuinely novel non-carry test. H-020 found perm_p 0.003 (real signal) but CI spans zero
as a linear bet. Convex harvest: capped-loss basket changes the payoff shape.

```
Agent({
  description: "H-037: Convex memecoin momentum basket (harvest perm_p-0.003 signal as option-like payoff)",
  prompt: "
    Working directory: C:\\Users\\hacke\\CascadeProjects\\Finals1\\TraderV1

    Read:
    - hypothesis_lab/hypotheses/H-037-*.md  (or INDEX entry if no file yet)
    - hypothesis_lab/hypotheses/H-019-*.md  (the momentum signal: H-020)
    - finetune/pipeline/eval_stats.py
    - WalletScarper/data/ directory listing  (check what OHLCV data exists)
    - finetune/data/  directory listing
    Load env: hypothesis_lab/.env

    Context: H-020 found cross-sectional momentum on memecoins has perm_p 0.003 (the RANK
    genuinely predicts winners) but hit rate <50%, CI spans zero, mean driven by a few 100–8000%
    moonshots. Linear sizing loses money. BUT the signal is REAL (perm_p 0.003).

    Hypothesis H-037: harvest the real momentum signal as a CONVEX PAYOFF.
    Instead of sizing linearly (lose on 53% of bets, occasionally hit moonshot):
    Build a CAPPED-LOSS BASKET: go long the top-K ranked memecoins (by trailing momentum),
    but size each at a FIXED SMALL fraction of capital, and accept the asymmetric payoff —
    most bets lose 20-50% and expire small, but the tail winners pay 100–8000%.
    This is structurally similar to a basket of OTM calls: expected value positive only if
    the tail is fat enough. Test whether the perm_p-0.003 ranking ACTUALLY concentrates
    the moonshots vs random (if it does, the basket has positive expected value).

    BUILD SCRIPT: hypothesis_lab/scripts/h037_convex_basket.py

    TEST:
    1. Per rebalance (24h horizon, non-overlapping), rank all tokens by trailing 24h return.
    2. Go long equal-weight top-K (K=3,5,10). Position = fixed 1% of NAV per token.
    3. Outcome per token: exit at 24h. Apply stop: if token drops >50%, exit at -50%.
    4. Basket return = mean of individual payoffs. Compute mean, median, hit (>0), tail (p90).
    5. Compare to: random-K baseline (same portfolio construction, random rank).
    6. Permutation null: shuffle rank labels across tokens within each rebalance 10,000×.
       Does top-K basket beat random-K (perm_p for basket EV over random)? Effective-n = rebalances.
    7. Score through eval_stats: realized basket EV, perm_p, CI95, n rebalances.

    Key question: does the momentum rank ACTUALLY concentrate the moonshot tail?
    perm_p 0.003 on H-020 says rank predicts direction. H-037 asks: does it concentrate value?

    Full results to hypothesis_lab/hypotheses/H-037-convex-basket.md. Heartbeat every 5 min.
  "
})
```

---

### TRACK 3 (MAIN THREAD): Intraday Data Harvest — The Leverage Unblock

This is the REAL gate to +5%. The champion-candidate needs 2–3× leverage to reach target.
Leverage needs intraday validation. 8h-close maxDD −0.24% is a TRAP (doesn't model intra-8h
gap/liquidation). You need 1m klines.

Run this in the main thread (not an agent) while Track 1 and 2 run:

1. Identify the exact top-10 carry names from H-021 (the fixed-selection that produced +1.44% APR).
   They're in the funding_cache names list — the top-10 selected on the train period.

2. Harvest 1m spot + perp klines from Binance for each of the 10 names:
   - Endpoint: `GET /api/v3/klines` (spot) and `GET /fapi/v1/klines` (perp)
   - Params: symbol, interval=1m, startTime, endTime, limit=1000
   - Coverage: 730 days of 1m data = 730×1440=1,051,200 candles per symbol × 2 (spot+perp) × 10 names
   - Binance weight limit: 1200/min; each 1m kline request = weight 2; stay under 500 req/min to be safe
   - At 500 req/min: 10 names × 2 venues × (1440×730/1000) req/symbol ≈ 10,512 requests → ~21 minutes
   - This is FAST — start it immediately, runs while agents work.

3. Save to `finetune/data/intraday_1m/[SYMBOL]_[VENUE]_1m.parquet` (parquet: fast read, compact).

4. Write a harvest progress log to `hypothesis_lab/sessions/[today]-intraday-harvest.log` (one line per symbol completed).

WRITE THE HARVEST SCRIPT: `hypothesis_lab/scripts/harvest_intraday_1m.py`
Use requests (stdlib-compatible), batch by date, write progress, handle rate limits with backoff.
Then RUN IT IMMEDIATELY (don't wait for agents — this runs in parallel).

```powershell
# After writing the script:
py hypothesis_lab/scripts/harvest_intraday_1m.py
```

Heartbeat every symbol completed (10 total). If any symbol fails, log and continue.

---

### SYNTHESIS AGENT (after all tracks complete)

When all three tracks are done:

```
Agent({
  description: "Session 3 synthesis: leverage validation + next steps",
  prompt: "
    Working directory: C:\\Users\\hacke\\CascadeProjects\\Finals1\\TraderV1

    Read everything in hypothesis_lab/ + today's session log.

    IF intraday 1m data is available (finetune/data/intraday_1m/ exists and has files):

    LEVERAGE VALIDATION — the real unblock:
    Load 1m spot + perp klines for the top-10 carry names. Simulate the levered carry book
    at 2x and 3x with realistic intraday margin:
    - At each 8h funding period, compute the intraday P&L path of the delta-hedged position
      (perp leg moves intraday; spot leg compensates; margin is net of both)
    - Model the liquidation: if the perp position's unrealized loss exceeds 50% of initial margin
      intraday, call it liquidated (worst-case: spot hasn't compensated yet)
    - Identify: what fraction of 8h periods had an intraday drawdown exceeding X%?
    - Compute the levered return distribution at 2x and 3x with this intraday liquidation model
    - What leverage is safe (expected annual liquidations < 1)?
    - What APR does that deliver? Does sane leverage reach +5%?
    Score the leverage validation result. If yes: the champion-candidate PROMOTES.

    SYNTHESIS (write to hypothesis_lab/sessions/[today]-synthesis.md):
    1. H-031/049/036/051 results: which carry refinement lifted Sharpe most?
    2. H-037 result: does convex basket harvest the momentum signal?
    3. Leverage validation: what is the honest levered APR at maximum safe leverage?
    4. Update champions/STACK.md with any new champions or updated candidate status.
    5. Update INDEX.md, ROADMAP.md.
    6. Generate the next 10 hypotheses informed by what this session found.
       Write only those with score ≥7.0 (edge_plausibility×2 + feasibility + novelty).
    7. Session closeout: hypotheses tested, passes, fails, champion stack EV now.
  "
})
```

---

## DECISION RULE FOR SESSION END

If any carry refinement reaches stacked APR ≥ +2% unlevered (OOS, eval_stats PASS):
→ promote to champion. Write `hypothesis_lab/champions/C-002-*.md`.

If intraday validation shows safe leverage 2–3× takes stacked APR ≥ +5%:
→ MISSION COMPLETE. Flag in ACTIVE_CONTEXT.md. Begin execution subproject design.

If neither: write synthesis, queue Session 4. Session is still a success if it rules out a
direction cleanly and generates the next honest batch.

---

## INVOKE IF NEEDED

Parallel coordination: `Skill("superpowers:dispatching-parallel-agents")`
Test debugging: `Skill("superpowers:systematic-debugging")`
Verification before promotion: `Skill("superpowers:verification-before-completion")`
