# ACTIVE_CONTEXT — Session-Local State

**Session protocol**: Reset this file at session start. Write discoveries here during session.
At session end, promote insights to INDEX.md, TREE.md, or champion docs. Do NOT treat as append log.

---

## STATUS: 🏆 C-002 PROMOTED (2026-06-05) — first validated champion. +5% path reached.
Cross-margined fixed-selection carry: unlevered +1.49% APR (CI95 [+0.78,+2.08], n=657), intraday
leverage-validated ~3.4× → +5% target (basis-tail-gated, cap 3–4×). champions/C-002-carry-book.md.
Remaining hardening: 18mo+ funding incl. crash (basis tail), H-042 corr-to-carry (stack), live cross-margin check.

## (historical) STATUS: ✅ H-001 RESOLVED — false alarm, instrument fixed.

### The "degradation" was a measurement artifact (2026-06-04)
The champion did not degrade. It was never an edge. Verified via `scripts/h001_verify.py`:
```
REALIZED rule EV  = -0.97% / trade   (pipeline logged +1.57% via win-rate-implied formula)
edge over base    = -0.80%           (rule selects WORSE-than-random events)
perm_p            =  0.887           (FAIL — beaten by 89% of random subsets)
CI95              = [-2.25%, +0.64%] (spans zero)
temporal split    = NEGATIVE in both OOS halves
```

Root cause = 3 instrument defects, now **fixed and verified**:
1. Unstable-universe walk-forward (n grew via harvest, not time) → fake degradation.
2. No perm/CI gate at promotion (promoted on 34 tokens) → fake validation.
3. Win-rate-implied EV instead of realized EV → fake +1.57%.

### What shipped this session
- `finetune/pipeline/eval_stats.py` — honest scorer (realized EV + perm_p + CI95 + verdict), self-tested.
- `build_momentum_v3.py` — holdout retains realized `net` + `entry_ts` + `token_mint`.
- `autoloop_meanrev.py` — realized EV, perm/CI gate, universe-aware drift, `--validate-only`.
- C-001 retired across STACK.md / C-001 doc / entry_champion.json. Position size ZERO.

## This session — COMPLETE (5 OOS tests, all leads resolved per user directive)
- H-001 → FAIL (champion was a measurement artifact). Instrument fixed.
- H-15 → REFUTED (overlap-inflated t; SOL-down recovery beta).
- H-13 → resolved (+9% not capturable; capturable carry = +0.8% / +0.6% sleeves).
- H-019 → FAIL (memecoins don't revert). H-020 → FAIL (momentum real but lottery).
- Generation done; survivors queued: H-024, H-021, H-022.

## Session 2 done (2026-06-04): champion-CANDIDATE found
- H-021 VALIDATED (best edge): fixed name-selection carry +1.44% APR Sh3.20; stack w/ xvenue
  Sharpe **4.28**, maxDD −0.1%, corr +0.01. First champion-candidate. H-022 REFUTED, H-024 FAIL.
- Insight: carry edge = FIXED selection (not dynamic chasing) + stacking UNCORRELATED sleeves.

## Next Session (3) Priority Queue
1. **H-031** risk-parity sizing + **H-049** carry-to-vol selection + **H-036** beta-hedge —
   raise the champion-candidate's unlevered APR/Sharpe (files written, ready to run).
2. **H-051** negative-funding sleeve — third uncorrelated stack component.
3. **H-037** convex memecoin momentum basket (the one novel non-carry idea).
4. Tail-risk: collect ≥18mo funding (incl. crash) → bound left tail → unblock leverage → +5% path.
5. DEAD — do not regenerate: memecoin reversion, liquid directional, xvenue agreement, win-rate EV.

## Best real edge right now
**Champion-CANDIDATE** carry book: 50/50 stack (level-fixed single + xvenue-maker), +1.02% APR,
**Sharpe 4.28**, maxDD −0.1%, market-neutral, components uncorrelated (champions/STACK.md).
Unlevered below +2% gate; leverageable toward +5% but BLOCKED on tail risk (6mo OOS, no crash).

## Session 3 (2026-06-04): refinements tested, one trap caught, no promotion
- H-031 risk-parity +1.49% Sh3.54 (marginal, adopt). H-049 carry-to-vol +1.32% Sh3.89 (marginal).
- H-036 beta-hedge REFUTED (book beta≈0). H-051 neg-sleeve REFUTED — apparent +6.92%/Sh9.56 +3% stack
  was non-stationary regime capture (6/10 names positive train funding; test sign-flips). Trap caught.
- Champion-candidate unchanged, sub-gate unlevered. **Cached-8h analysis is exhausted for the gate.**

## Next (Session 4) — the only real unblock is DATA
1. **Run scripts/harvest_intraday_1m.py** (to be written) → 1m perp+spot for the top-10 carry names →
   simulate intra-period margin under 2–3× leverage → honest levered APR → promote-or-not. THE gate.
2. H-037 convex memecoin basket (offline, novel, untested).
3. DEAD: neg-funding sleeve, beta-hedge, all Session-1/2 dead tracks.

## Last Updated
2026-06-04 Session 3. Champion-candidate carry book (risk-parity-sized) +1.49% APR Sh~3.5 /
stack Sh4.64, sub-gate unlevered, leverage-gated on intraday data not yet harvested.
