# Champion Stack

## Current State: C-002 PROMOTED — first validated champion (2026-06-05)
Cross-margined fixed-selection funding-carry book. Unlevered +1.49% APR (Sh~3.5, CI95 [+0.78,+2.08],
n=657); intraday-validated leverage ~3.4× cross-margin → **+5.0% APR target**. Basis-tail-gated (cap
3–4×). Full doc: champions/C-002-carry-book.md.

**Last updated:** 2026-06-04

The former champion (C-001 mean-reversion) was **invalidated** on 2026-06-04 (H-001):
realized OOS EV −0.97%, perm_p 0.887, CI95 spans zero. It was never a real edge — the
"+1.57%" was a win-rate-implied measurement artifact. See `champions/C-001-meanrev-baseline.md`.

## Active Champions
| ID | Name | Net EV (realized) | sig | Status | Notes |
|----|------|------------------------|--------|--------|-------|
| **C-002** | Cross-margin fixed-selection carry book | +1.49% APR unlev / +5% @3.4× | CI95 [+0.78,+2.08] n=657 | **ACTIVE** | Intraday leverage-validated. Cap 3–4×, basis-tail haircut |
| — | _C-001_ | — | — | retired | C-001 retired 2026-06-04 |

## Retired / Invalidated
| ID | Name | Realized EV | Reason |
|----|------|-------------|--------|
| C-001 | Mean-reversion drawdown rule | −0.97% (perm_p 0.887) | False positive from win-rate-implied EV on 34-token slice |

## CHAMPION-CANDIDATE: market-neutral carry book (Session 2, 2026-06-04)
H-021 found the carry edge is in **FIXED name-selection**, not dynamic chasing (H-13's dynamic
single_topk died at −0.1% on turnover). Selecting good carry names once on train and holding
them lifts the sleeve, and the components are uncorrelated:

| sleeve | net APR (OOS maker) | Sharpe | maxDD | CI95 | source |
|--------|---------------------|--------|-------|------|--------|
| Level-fixed single carry (top-10, basis-aware) | +1.44% | 3.20 | −0.2% | [+0.73%,+2.05%] | H-021 |
| Cross-venue (Binance−Bybit) maker spread | +0.59% | 3.93 | −0.1% | [+0.00%,+1.06%] | H-13 |
| **50/50 STACK** (corr +0.01) | **+1.02%** | **4.28** | **−0.1%** | [+0.53%,+1.41%] | H-021 |

**Status: champion-CANDIDATE, not yet promoted.** Unlevered APR +1.0% (OOS) / +3.16% (full 730d),
Sharpe 4.28, market-neutral, uncorrelated components.

### Tail stress over full 730d (the leverage gate) — and why the headline number is a TRAP
```
APR: full-history +3.16% | OOS +1.02%
maxDD: full-history -0.24% | OOS -0.12%    worst day -0.22%  worst week -0.21%
Naive leverage(budget/maxDD):  -2% budget → 8.4x → +27% APR;  -5% → 21x → +66%;  -10% → 42x → +133%
```
**REJECT the naive leverage math.** maxDD −0.24% is the drawdown of *funding accrual + 8h-close
basis* in a benign window. It does NOT model what actually kills levered delta-neutral carry:
intra-8h gap/liquidation (perp leg liquidated before the spot leg compensates), the rare
basis-blowout tail (FTX/LUNA-scale — likely absent from this 2024-26 cache), funding clamps/ADL,
and maker-fill failure. At 8–42× a single unmodeled gap is fatal (LTCM mode). This is the SAME
program-wide lesson: **the metric measures something that isn't the real risk** (cf. H-001
win-rate, H-13 uncapturable legs, H-15 effective-n).

**Honest read:** unlevered the book is a real, small, market-neutral edge. **SANE leverage 2–3×
→ ~+3–6% APR** is the realistic path to the +5% target — but even that is GATED on an explicit
tail/gap/margin model (intra-period price paths + a basis-blowout scenario), which 8h-close data
CANNOT supply. Promotion needs: (a) tick/1m data to simulate intra-period margin, (b) a stress
scenario for the un-sampled basis tail. Do NOT size on the smoothed-funding maxDD.

## Session 3 carry refinements (2026-06-04) — no promotion; one trap caught
- **H-031 risk-parity** (weight ∝ 1/funding-vol): +1.49% APR Sh3.54 (vs EW +1.44% Sh3.20). Marginal
  real improvement → adopt as default sizing for the level-fixed sleeve.
- **H-049 carry-to-vol selection**: +1.32% APR Sh3.89 (Sharpe↑, APR↓). Marginal.
- **H-036 BTC-beta hedge**: REFUTED. Book beta ≈ 0 already; hedging adds cost/noise (Sh 3.20→2.72). Don't.
- **H-051 negative-funding sleeve**: **REFUTED — trap caught.** Apparent +6.92% APR Sh9.56, and a
  3-sleeve stack +3.00% APR Sh11.97 that *looks* like it clears +2% — but the per-name breakdown shows
  6/10 selected names had POSITIVE train funding; the payoff comes from test-window sign FLIPS (FET
  train +3.4%→test −23.1%). It is non-stationary regime capture (eff-n ≈ 1 alt-funding regime), not a
  predictive edge. Sharpe 12 ⇒ artifact. **Do NOT promote the 3-sleeve stack.**
- **Net:** champion-candidate unchanged = level-fixed (risk-parity-sized) +1.49% APR Sh3.20-3.54,
  stacked w/ xvenue → +1.04% APR Sh4.64. Still sub-gate unlevered; still leverage-gated on intraday data.

## LEVERAGE GATE — intraday-validated (Session 4, 2026-06-05, scripts/leverage_sim.py)
The 8h-close maxDD (−0.24%) was a trap, CONFIRMED: real intra-8h perp moves are huge (p99 5–10%,
UNI +41% in one 8h). But the trap was the wrong MARGIN MODEL. Harvested 1m perp+spot (180d) and
simulated both:
- **ISOLATED margin** (naive): one +N% spike liquidates the short-perp leg → safe only ~2x; net APR
  goes negative by 3x. Untradeable levered.
- **CROSS margin** (real pro carry desk, unified account): the delta-neutral book's MTM swing is the
  perp/spot BASIS, which stays tight intra-period. **Zero basis-liquidations even at 10x in 180d.**
  At 3x the book survives a basis widening up to d_liq≈33% (covers most historical major dislocations).

| leverage (cross-margin) | carry APR | survives basis move up to |
|----|----|----|
| 3x | +4.5% | 33% |
| 4x | +6.0% | 25% |
| ~3.4x | **+5.0% (target)** | ~30% |

**Status: leverage path VALIDATED in normal conditions — the +5% target is reachable at ~3.4x cross-margin.**
This overturns the Session-2 "leverage is just a trap" framing WITH intraday evidence. BUT not yet a
promoted champion: (a) only 4 names / 180d so far (full 10-name rerun pending harvest), (b) the
basis-blowout TAIL is un-sampled — a >33% basis gap (FTX/oracle-failure grade) liquidates even 3x.
Promotion needs the full names + an explicit basis-blowout stress haircut. Real desks run 3–5x and
de-risk in stress; that is the operating model this validates.

## Sleeve #2 CANDIDATE: liquidation-bounce (H-042, Session 4, 2026-06-05)
First NON-carry edge to survive full trap-hardening (market-demean + per-name beta-adjust + period-
clustered eff-n + cost). Long an alt perp after it prints −8% in an 8h period (forced-liquidation
proxy, funding rising), short the index → harvest the per-name overshoot. Market-NEUTRAL.
- −8% drop, 2-period hold: **+1.46%/trade** (median +0.43%, hit 55%, cluster-t 2.24, n=91 periods).
- −5% drop, 2-period hold: +0.22%/trade (cluster-t 2.49, n=325 — significant but small/lottery).
- Survives beta-adjust (betaAdj ≈ excess) ⇒ genuine overshoot, not high-beta recovery.
**Sub-gate:** no single config clears magnitude(+2%)×n(>100)×significance(t>2) at once — sits one
data-increment under. Market-neutral & event-driven ⇒ likely ~uncorrelated to carry ⇒ a real 2nd
stack sleeve once n clears. Next: 1m-entry sharpening (harvest running) + corr-to-carry + collect-forward.

**STACK TEST (2026-06-05, test_carry_cluster.py):** r(C-002 carry per-8h, H-042 bounce per-event) = −0.08 co-active
/ −0.00 full window → **genuinely UNCORRELATED** (diversifier confirmed). Vol-matched 70/30 stack Sharpe 4.05 > carry
3.54, but NOT CI-separated, and H-042 sleeve n=39 (sub-gate). ⇒ bankable ONLY after H-042 clears n>100 via forward-
collection. NOTE: naive equal-CAPITAL blend meaningless (bounce-vol ~1415× carry-vol → +5000% APR artifact); must vol-match.
Carry refinements same run (BTC-vol regime gate, AR(1)/low-beta/level×persist selection, basis-vol de-risker): ALL within
CI95 of C-002 → carry book is **near-optimal on current data**; no cheap Sharpe lift. 100-hyp sweep promoted 0 new champions.

## Retired earlier sub-gate framing (superseded by H-021)
Session-1 baseline was EW-all tradeable +0.8% (Sharpe 1.79). H-021's fixed-selection +1.44%
(Sharpe 3.20) supersedes it as the single-sleeve best.

## Wallet / on-chain alpha (Sprint 5, 2026-06-06) — UNPROVEN (long) / REAL-but-uncapturable (short)
First honest point-in-time test (`hypothesis_lab/wallet_alpha/`, SYNTHESIS.md). Substrate = raw_trades
5.5h cross-section. Results (temporal OOS, capped realized EV, eval_stats gate):
- **H-160 consensus quality: DEAD.** Naive smart-wallet copy = −17.7% EV (cluster-buys mark the top).
  Point-in-time wallet quality *anti*-predicts (rho −0.37 = in-session survivorship). Adds ~0 over token context.
  → invalidates `finetune/pipeline/copy_engine.py` (it was in-sample + survivorship).
- **H-161 archetype mix: DEAD.** Archetype is a weak proxy token context already holds.
- **H-162 distribution-sell down-signal: REAL, NOT promotable.** Coordinated quality-wallet sells predict
  larger forward drops; SHORT side gate-clears (wq-sell +22% EV, perm_p 0.008, CI [+15.9%,+27.6%], n=212;
  selection edge +4.5–5.9% cost-invariant). Blocked by (a) no short/avoid venue for microcaps, (b) eff-n=1
  session ⇒ regime-capture risk (the −17% base is a May-14 down-session). Logged as risk/exit signal.
- **No new champion. No new stack sleeve.** Wallet alpha is not sized. Binding constraint reconfirmed = DATA
  (need multi-day capture for persistence + a shortable subset for capture). Next: H-163/H-164.

### Sprint 6 (2026-06-06) — persistence flywheel + capturability
- **Free firehose collector built + LIVE** (`wallet_alpha/firehose_collector.py`, GeckoTerminal, keyless).
  Accruing days → makes H-163 cross-day persistence testable.
- **H-162 persists INTRA-session** (walk-forward +7.7% over base, perm 0.000). Cross-day = open (H-163).
- **Exit-overlay (H-166) = RISK MODULE CANDIDATE, not a champion.** Distribution-timed exit on a held long
  saves +3.9/+5.4%/trade (perm 0.000) and beats a shuffled-lag control 100% of draws (real signal, ~+1.8%
  beyond mechanical early-exit). But the book stays −11% → de-risk only, never sized as alpha. Stage-2 paper
  reject/exit filter once a profitable long book exists (none yet). See wallet_alpha/CAPTURABILITY_REPORT.md.
- Still: C-002 sole champion; H-042 sole sub-gate sleeve; wallet long alpha DEAD.

## Pending Promotions
_None._ C-002 sole champion; H-042 sole sub-gate sleeve; wallet alpha unproven (long)/uncapturable (short).
See ROADMAP for the multi-day-capture unblock (now the highest-leverage data need).

## Stacking Rule
Champions are independent filters applied serially. Combined EV = (1+EV_1)×(1+EV_2)−1.

## Promotion Gate (enforced by finetune/pipeline/eval_stats.py)
A rule is promotable ONLY if, on a temporal OOS holdout with realized payoffs:
- realized net EV > +2.0% per trade, AND
- permutation-null perm_p < 0.05, AND
- block-bootstrap CI95 excludes zero, AND
- n_OOS > 100.

Win-rate-implied EV is **banned** as a promotion metric (it manufactured C-001).

## Degradation Protocol
1. Size to ZERO on 2 consecutive negative realized-EV checks (same universe_fp).
2. Diagnose with `hypothesis_lab/scripts/h001_verify.py` pattern (realized + perm + CI + temporal split).
3. Do not restore trading until a fix passes the gate above OOS.
