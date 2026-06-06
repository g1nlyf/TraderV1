# Hypothesis Index

> **Canonical truth lives in `hypothesis_lab/knowledge/`** (CANONICAL_STATE, DATA_LEDGER, DEAD_TRACKS,
> LIVE_THREADS, DUPLICATE_MAP, QUESTIONS, DATA_AUDIT). This index is the per-ID log. H-080..H-159 are
> concept-duplicate-heavy → see DUPLICATE_MAP.md for the collapse.

| ID | Name | Status | EV (net) | Win Rate | n OOS | Date | Notes |
|----|------|--------|----------|----------|-------|------|-------|
| H-001 | Champion degradation diagnosis | **tested · FAIL** | −0.97% realized | 41.7% | 1360 | 2026-06-04 | "Degradation" was a measurement artifact. Champion never had an edge (perm_p 0.887). C-001 retired; eval instrument fixed. |
| H-002 | Funding carry tradeable collapse | proposed | — | — | — | 2026-06-04 | +9% raw → +0.7% tradeable |
| H-003 | Holder-flow signal (on-chain) | proposed | — | — | — | 2026-06-04 | Helius data needed |
| H-004 | Regime filter for mean-reversion | proposed | — | — | — | 2026-06-04 | Disable rule in trending |
| H-005 | Kelly sizing (drawdown-scaled) | proposed | — | — | — | 2026-06-04 | Size up on deeper drawdowns |
| H-006 | LLM residual on rule errors | parked | — | — | — | 2026-06-04 | Residual of a negative rule — not promising |
| H-019 | Memecoin XS reversion (neutral) | **tested · FAIL** | gross −10.8% | — | 15 reb | 2026-06-04 | perm_p 0.90 — memecoins don't revert |
| H-020 | Memecoin XS momentum (neutral) | **tested · FAIL** | +200% lottery | 46.7% | 15 reb | 2026-06-04 | perm_p 0.003 (signal real) but CI spans zero, hit<50% — unsizeable lottery |
| H-021 | Persistence / fixed name-selection carry | **tested · VALIDATED** | +1.44% APR Sh3.20 (stack Sh4.28) | — | 657 | 2026-06-04 | **Best edge to date.** Fixed selection > dynamic chasing. Champion-candidate, leverage gated on tail risk |
| H-022 | Cross-venue funding agreement filter | **tested · REFUTED** | gate worse at every thr | — | 657 | 2026-06-04 | Agreement = crowded extreme, not quality |
| H-024 | New-listing funding decay carry | **tested · FAIL** | early≈mature perm_p 0.55-0.99 | — | 20 listings | 2026-06-04 | No systematic decay; hedgeable hint +20-32% but n=8, collect-forward |
| H-031 | Risk-parity carry sizing (∝1/funding-vol) | **tested · marginal** | +1.49% APR Sh3.54 | — | 657 | 2026-06-04 | Slight lift vs EW Sh3.20; adopt as default sizing |
| H-032 | Funding-acceleration name selection | **tested · marginal** | +1.65% APR Sh1.73 (tradeable) | — | 657 | 2026-06-05 | Higher APR than level but worse Sharpe (chases spiky names); full-panel +4.36% was contaminated by spot-less exotics. Not adopted |
| H-036 | BTC-beta-neutralize the carry book | **tested · REFUTED** | beta≈0; hedge hurts (Sh3.2→2.7) | — | 657 | 2026-06-04 | Book already beta-neutral; hedging adds cost/noise |
| H-037 | Convex memecoin momentum baskets (capped) | **tested · concentration real, n-blocked** | top-3 edge +6.6% vs random | — | 171 full / 52 test | 2026-06-05 | perm_p 0.041 (rank concentrates tail; K=10 dilutes to ~0). But survivorship-inflated, untradeable sub-$ memecoins, test-n<100. Stop doesn't help. Collect-forward |
| H-040 | Smart-money early-buyer overlap | proposed · forward-collect | — | — | — | 2026-06-04 | Helius data growing; n-blocked now |
| H-042 | Liquidation-cascade bounce (market-neutral) | **tested · REAL, sub-gate** | −8%H2 +1.46%/trade (t2.24,n91); −5%H2 +0.22% (t2.49,n325) | 46-55% | 91-325 | 2026-06-05 | **Best new lead.** Survives demean+beta-adj+cluster+cost. Market-neutral → stack candidate. One data-increment under gate |
| H-043 | Funding seasonality (settlement/weekend) | **tested · FAIL** | hour perm_p 0.66, weekday 0.69 | — | 2190 | 2026-06-05 | No settlement/weekday premium — noise |
| H-047 | Cross-venue funding lead-lag | **tested · FAIL** | lead asymmetry −0.03 | — | 44 names | 2026-06-05 | Venues symmetric/contemporaneous; not a price edge anyway |
| H-049 | Carry-to-vol selection (funding/realized-vol) | **tested · marginal** | +1.32% APR Sh3.89 | — | 657 | 2026-06-04 | Sharpe↑ APR↓ vs level; modest |
| H-051 | Negative-funding sleeve | **tested · REFUTED** | +6.92% but regime artifact | — | 657 | 2026-06-04 | 6/10 names had POSITIVE train funding; payoff from test sign-flips — non-stationary, eff-n≈1. Trap caught |
| H-053 | Forced-flow overshoot, both sides | **tested · asymmetric** | down reverts (H-042), up continues | 44-56% | 91-985 | 2026-06-05 | Forced selling (liq) mean-reverts; voluntary FOMO spikes CONTINUE (not fade). Isolates H-042 as the harvestable side; up=momentum lottery (H-020) |
| H-058 | Dropper-basket (portfolio H-042) | **= H-042 period-mean** | see H-042 | — | 91-325 | 2026-06-05 | The market-neutral EW basket of period droppers IS the H-042 period-level series |
| H-060–H-079 | Forced-flow amplifiers (Zone-1 batch) | **tested · ALL FAIL** | none beat H-042 +1.46% | — | 15–325 | 2026-06-05 | H-060 repeat-cascade +2.75% but n=29 (collect-forward); H-065 basis-snap = TRAP #5 (lag-1 autocorr). H-042 edge is idiosyncratic single-name. See sessions/2026-06-05-test-zone1.md |
| H-080–H-159 | Carry/microstruct/calendar/macro (Zone 2-5 batch) | **gen + triaged · 0 gate-clearers** | all within CI of C-002 | — | 657 | 2026-06-05 | ~80 generated. Tested cluster (regime-gate, selection, de-risker) all CI-tie C-002. **STACK r(C-002,H-042)≈0 confirmed** (bank on collect-forward). ~30 BLOCKED (OI/L2/options/OKX/SPX/on-chain); Zone-4 calendar low-n deferred. See sessions/2026-06-05-test-carry.md + genZone1-5.md |
| H-160 | Wallet-consensus quality (point-in-time) | **tested · FAIL (DEAD)** | naive-copy −17.7%; wq-select −22.9% (rho −0.37) | 21% | 455 | 2026-06-06 | Consensus=crowding (buy the top); in-session "skill"=survivorship anti-signal; wallet adds ~0 over token context. Kills copy_engine premise. `wallet_alpha/`, SYNTHESIS.md |
| H-161 | Wallet archetype mix (KMeans sniper/swing/bot/hodler) | **tested · FAIL (DEAD)** | arch rho +0.06–0.10; token+arch≈token | — | 455 | 2026-06-06 | Archetype is a weak proxy token context already holds. Sniper-clusters worst, swing least-bad but n<30. DEAD |
| H-162 | Distribution (sell) cluster down-signal | **tested · REAL, NOT promotable** | wq-sell SHORT +22% EV, perm_p 0.008, CI[+15.9,+27.6], n=212 | 80% down | 390 | 2026-06-06 | Coordinated quality-sells predict drops; selection edge +4.5–5.9% **cost-invariant**. Ordering random<buy<sell<wq-sell. Blocked: no short venue + **eff-n=1 session (regime-capture risk)**. Risk/exit signal. Next: H-163 multi-day, H-164 shortable subset |
| H-162p | H-162 intra-session persistence (walk-forward) | **tested · HOLDS intra-session** | wq-sell SHORT walk-fwd +7.7% over base, perm 0.000, CI[+17.8,+25.7] | — | 431/469 | 2026-06-06 | Edge persists across time-blocks (3/4). wq-increment = regime-robust; base = May-14 regime. Cross-DAY still untestable (1 session). H162_PERSISTENCE_REPORT.md |
| H-163 | Day-level distribution persistence | **proposed · DATA-gated** | — | — | — | 2026-06-06 | THE promote/kill test. Needs firehose ≥14 days. Re-run block walk-forward at day level → does +7.7% wq increment survive different regimes? |
| H-164 | Shortable/avoidance capturable subset | **proposed** | — | — | — | 2026-06-06 | Intersect distribution tokens with CEX/perp-listed names; capture the down-signal where shortable; fuse C-002 context |
| H-166 | Exit-overlay risk module (distribution → exit) | **tested · REAL risk rule, not alpha** | exit saves +3.9/+5.4%/trade, perm 0.000 (book still <0) | — | 1137/1204 | 2026-06-06 | Capturable de-risk (sell rule on a long), not positive-EV. Stage-2 risk filter candidate. CAPTURABILITY_REPORT.md |

## Legacy (from brain vault, pre-2026-06-04)
| ID | Name | EV (net) | Verdict |
|----|------|----------|---------|
| H-03 | Drawdown-threshold entry (memecoin) | -0.800% | FAIL |
| H-10 | Cross-sectional reversion (majors) | NEGATIVE | FAIL |
| H-11 | Oversold-bounce, hedged (majors) | +0.33% net (n=72, CI spans zero) | INCONCLUSIVE |
| H-12 | Cross-sectional momentum (majors) | -0.182%/rebal | FAIL |
| H-13 | Perpetual funding carry | +9.1% topk NOT capturable → tradeable +0.8% (Sh 1.8) + xvenue-maker +0.6% (Sh 3.9) | **RESOLVED** (2026-06-04) — best real edges found, both <+2% gate |
| H-14 | Funding as directional signal | Spans zero | FAIL |
| H-15 | Drawdown entry memecoins SOL-hedged | EV +17.59% but perm_p=0.666 | **REFUTED** (2026-06-04) — overlap-inflated t: eff n≈6 episodes in 13d, cluster-robust t→1.1; SOL-down recovery beta, not alpha |
| H-16 | LP fee vs impermanent loss | All negative | FAIL |
| H-17 | Hold-with-stop (memecoin) | Mean +142% median -0.94% | LOTTERY — not edge |
| H-18 | Early-buyer reconstruction | Data collection running | PENDING |

## Promotion Notes
- **H-001 (2026-06-04): the eval instrument was lying.** The champion's "+1.57%" was a
  win-rate-implied EV (assume every win +20% / loss −12%). Realized EV is −0.97%. Lesson
  now enforced in `finetune/pipeline/eval_stats.py`: EV = realized mean payoff, gated by
  perm_p<0.05 + CI95>0. Win-rate-implied EV is BANNED as a promotion metric.
- H-13 is the most promising lead: raw edge is massive but "tradeable universe" filter kills it
- H-15 anomaly: **RESOLVED → REFUTED** (2026-06-04, scripts/h015_resolve.py). The t=7.99
  was overlap inflation — the 13-day window holds only ~6 independent SOL-down→bounce
  episodes; cluster-robust t collapses to 1.1–3.0. perm_p 0.68 = drawdown filter selects
  nothing over random. 91% of events SOL-down, SOL-up EV negative → recovery beta, not
  alpha. Confirmed effective-n pathology is systemic (same as H-001).
- H-11 run 1 had n=72 — too small, CI spans zero. Run 2 (n=560) went negative. Strategy didn't generalize.
