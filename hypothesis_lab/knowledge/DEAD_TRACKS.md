# DEAD TRACKS — refuted, with the reason and the lesson

> A track is DEAD when it failed the gate AND we understand *why*. Do not re-run without new data
> or a new mechanism. Each entry: what / number / why dead / lesson.

## Strategies

### C-001 mean-reversion drawdown rule — DEAD
- realized −0.97%, perm_p 0.887, CI95 spans zero (n=1360).
- Why: promoted on **win-rate-implied EV** (assume every win +20% / loss −12%). Realized losers hit the −12% stop; real EV negative.
- Lesson: EV = realized mean payoff only. → `eval_stats.py`.

### Naive wallet-leaderboard copy — DEAD (as evidence; mechanism still open via honest test) {#naive-leaderboard-copy}
- copy_engine.py reports high win-rates / positive avg_pnl per exit rule.
- Why dead as *evidence*: (a) the 86-wallet universe is selected on realized PnL of the **same tape** → survivorship; (b) exit price requires a tracked wallet to have sold → look-ahead within the tracked set; (c) **no OOS split, no permutation null, no honest cost**; (d) leaderboard `score`/`composite_score` computed over full history. In-sample by construction.
- Lesson: smart-wallet copy must be tested point-in-time with pre-t-only wallet quality + forward label + baselines. Sprint 5 does this.

### H-019 memecoin XS reversion — DEAD (gross −10.8%, perm_p 0.90). Memecoins trend.
### H-020 memecoin XS momentum — DEAD as sizeable (perm_p 0.003 real signal but CI spans zero, hit<50%, +200% lottery). Unsizeable.
### H-022 cross-venue funding agreement filter — DEAD (gate worse at every threshold; agreement = crowded extreme).
### H-024 new-listing funding decay — DEAD (early≈mature, perm_p 0.55–0.99; n=20). Hedge hint n=8 → forward-collect.
### H-036 BTC-beta hedge of carry — DEAD (book already β≈0; hedge cuts Sharpe 3.2→2.7).
### H-043 funding seasonality — DEAD (hour perm_p 0.66, weekday 0.69).
### H-047 cross-venue lead-lag — DEAD (asymmetry −0.03; venues contemporaneous; not a price edge anyway).

## TRAPS (apparent edges that were measurement artifacts) — the museum
1. **H-001 win-rate-implied EV** — Sharpe/EV from assumed payoffs, not realized. → banned.
2. **H-15 effective-n inflation** — t=7.99 but ~6 independent SOL-down episodes in 13d; cluster-robust t→1.1; perm_p 0.68. Recovery beta, not alpha.
3. **H-13 uncapturable legs** — +9.1% topk raw funding NOT tradeable (turnover/borrow); single_topk −0.1%.
4. **H-051 regime capture** — negative-funding sleeve +6.92% Sharpe 9.56, BUT 6/10 names had POSITIVE train funding; payoff from test-window sign flips; eff-n≈1. Sharpe 12 ⇒ artifact.
5. **H-065 lag-1 autocorr** — basis-snap clusterT +25 but it's basis_ret lag-1 autocorrelation −0.44; gross 6bps < 11bps cost. Net negative.
- **Meta-lesson:** any Sharpe > ~6 on a "new" sleeve is an artifact until proven otherwise; always (a) per-name breakdown, (b) cluster-robust / effective-n, (c) realized cost, (d) permutation null.

## Forced-flow amplifiers (Zone-1 batch H-060…H-079) — DEAD
- None beat base H-042 +1.46%. H-060 repeat-cascade +2.75% but n=29 → forward-collect. H-077 breadth INVERTED (systemic breadth contaminates via beta).
- Why dead: H-042's edge is **idiosyncratic single-name overshoot**; amplifying via breadth/contagion adds beta, not alpha. Vein at ceiling on current data.

## Carry refinements (H-080…H-159 cluster) — DEAD as improvements over C-002
- BTC-vol regime gate, AR(1)/low-beta/level×persist selection, basis-vol de-risker, funding dispersion/skew sizing: **all within CI95 of C-002**. Carry book is near-optimal on funding-cache data.
- Why dead: no cheap Sharpe lift left in 730d 8h funding data. (See DUPLICATE_MAP for the ID collisions in this batch.)

## Wallet distribution layers (Sprint 7, 2026-06-06)
- **H-168 co-sell network / cabal cohesion — DEAD.** Co-sell graph cohesion among cluster sellers rho −0.102
  vs forward drop; coordinated co-sellers do NOT out-drop independent sellers. "Cabal distributes together →
  bigger crash" refuted on this data (cohesion used generous full-session membership → robust negative).
- **H-166 as an AUTHORITATIVE risk module — NOT VALIDATED (demoted).** exit_h166 loses to exit-on-any-random-
  sell (−12.84% vs −11.69%); quality-distribution specificity adds nothing over naive sell-reaction; no-trade
  veto worthless (perm 0.910). Keep only SHADOW (log-only). The generic "exit-on-sell" reaction beats hold
  but is naive + single-session. (Sprint-6 over-credited it via a too-weak shuffled-lag control.)
- NOT dead but secondary: H-167 distributor-archetype (rho +0.262) is the best wallet feature yet, but <
  token context (tok_prior_ret +0.332) → no separate edge; retained only for the H-163 cross-day test.

## BLOCKED (not dead — data-gated; cannot test on current cache) {#blocked}
- H-096 OKX carry sleeve (no OKX funding), H-097 quarterly basis (no dated futures), H-098 USDC-margin split, H-102 perp-premium crowding (needs OI), H-103/H-113 OI-timing (no OI history), H-111/H-112 spread/maker-taker (no L2), H-118 implied-vol (no options), H-153 SPX-corr (no macro), H-120–H-139 calendar/macro (low-n + no event data).
- Wallet multi-day persistence, archetype alpha half-life: blocked by the 5.5h raw_trades span (DATA_LEDGER).
