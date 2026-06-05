# Session Synthesis — 2026-06-04

Research-director report after a full diagnose → fix → test → generate cycle.

## 1. What this session actually was
It opened as an emergency ("champion degrading −0.47% EV, dispatch a forensic swarm") and
ended as a **methodology correction**. The champion was never an edge; the measurement
pipeline manufactured one. Once the instrument was fixed, two standing leads were resolved
and the search space was narrowed honestly.

Five rigorous OOS evaluations (all via realized payoff + permutation + CI95, no win-rate proxy):

| # | What | Verdict | Decisive number |
|---|------|---------|-----------------|
| H-001 | C-001 mean-reversion "champion" | **FAIL** | realized −0.97%/trade, edge over base −0.80%, perm_p 0.887 |
| H-15 | SOL-hedged drawdown "+17.59% anomaly" | **REFUTED** | cluster-robust t 7.99→1.1; eff n≈6 episodes/13d; perm_p 0.68 |
| H-13 | Funding carry capturability | **resolved** | +9.1% NOT capturable; tradeable +0.8% (Sh1.8) + xvenue-maker +0.6% (Sh3.9) |
| H-019 | Memecoin XS reversion | **FAIL** | gross −10.8%, perm_p 0.90 (rank anti-predictive) |
| H-020 | Memecoin XS momentum | **FAIL (lottery)** | gross +200%, perm_p 0.003 but hit 47%, CI spans zero |

## 2. The synthesis — three structural truths
**(a) The systemic enemy is effective-n, not the market.** H-001, H-15, and H-13 all failed
the same way: a metric reported significance/EV on quantities that were either non-iid
(overlapping events → inflated t), win-rate-implied (not realized), or non-executable
(dynamically-selected untradeable legs). The fix was never "find the regime" — it was *count
honestly*. This is now enforced in `finetune/pipeline/eval_stats.py` (D-006, locked).

**(b) Memecoins trend; they do not revert.** Three independent reversion bets died (C-001
drawdown, H-15 drawdown, H-019 cross-sectional, all perm_p ≥ 0.67–0.90). The only memecoin
signal that beats its null is cross-sectional **momentum** (H-020, perm_p 0.003) — but its
payoff is an option-like lottery (hit <50%, mean = a few moonshots, CI spans zero), so linear
sizing can't harvest it. Memecoins are convex/right-tail instruments, not statistical-arb
instruments. Stop building mean-reversion on them.

**(c) The only positive, capturable EV found is structural carry — and it's small.** Liquid
CEX is efficient (every directional factor dead: H-10/11/12/14). Carry exists broadly
(+3.5–5.5% standalone per name) but the *capturable* slice is ~+0.8% APR (tradeable,
diversified, Sharpe 1.8) + ~+0.6% (cross-venue maker, fragile). The fat +9% lives where you
cannot run delta-neutral (spot-less RWA/illiquid perps) — an inaccessibility premium, not
free money. Stacked carry book ≈ +1.4% APR at Sharpe ~2-4: real, positive, honest, and an
order of magnitude below the +5% target.

**Where the edge most plausibly hides next:** structural premia conditioned on a *fresh*
extreme (so B-03 non-stationarity doesn't apply) with *honest* effective-n. The standout
candidate is **new-listing funding decay (H-024)**: recurring, structural, retail on the
losing side, testable now on cached data, and it stacks with the validated carry sleeves.

## 3. Generation batch (the 20→5 filter)
Generated informed by the above (not cold). Scored edge_plausibility×2 + feasibility + novelty;
cut avg < 7.0. Memecoin-mean-reversion and liquid-directional directions excluded (proven dead).

| ID | Idea | plaus | feas | nov | keep? |
|----|------|-------|------|-----|-------|
| H-019 | Memecoin XS reversion (neutral) | — | — | — | TESTED → FAIL |
| H-020 | Memecoin XS momentum (neutral) | — | — | — | TESTED → FAIL (lottery) |
| **H-024** | **New-listing funding decay carry** | 8 | 7 | 9 | **KEEP (top)** |
| **H-021** | Persistence-selected carry (pick names by funding sign-stability, not level) | 7 | 9 | 6 | **KEEP** |
| **H-022** | Cross-venue funding *agreement* as a carry quality filter | 6 | 8 | 7 | **KEEP** |
| H-023 | Basis (spot−perp) term-structure carry, decomposed from funding | 6 | 7 | 7 | cut (≈ existing basis-aware) |
| H-025 | Aggregate-funding regime on/off filter for the carry sleeve | 5 | 8 | 4 | cut |
| H-026 | Memecoin "graveyard resurrection" long | 4 | 4 | 6 | cut (lottery anti-pattern, H-17) |
| H-030 | Vol-scaled (risk-parity) carry sizing | 6 | 8 | 5 | cut (marginal) |
| H-028 | On-chain holder-flow × carry | 7 | 2 | 8 | cut (data overlap zero, not testable now) |

**Top-5 priority-test queue (next session):** H-024, H-021, H-022, then re-examine whether a
payoff-transformed version of H-020 momentum can escape the lottery (low prior), then H-023.

## 4. Champion stack
Empty (C-001 retired). Best real edges = the two carry sleeves (sub-gate). See `champions/STACK.md`.

## 5. Roadmap forward
1. **H-024** new-listing funding decay — build the listing-age event study (reuse funding_harvest
   loaders + eval_stats). Highest probability of a gate-clearing structural edge.
2. **H-021/H-022** — lift the validated +0.8% tradeable sleeve toward +2% via name selection by
   funding persistence / cross-venue agreement.
3. Keep `autoloop_meanrev` running (now honest) only as a NULL monitor — do not expect it to
   revive; it documents that the memecoin reversion edge stays dead.
4. Estimated sessions to +5%: unknown and possibly unreachable in liquid+memecoin data alone.
   The honest path is stacking several small structural sleeves (carry + new-listing) toward
   +2–3%, and accepting that +5% net/trade may require the on-chain data (H-018) to mature.

## 6. Closeout
- Hypotheses tested OOS this session: **5** (H-001, H-15, H-13, H-019, H-020).
- Passes: 0. Resolved/refuted: 3. Real-but-sub-gate edges surfaced: 2 (carry sleeves).
- New hypotheses documented: H-019, H-020, H-024 (full) + H-021/H-022 (queued).
- Instrument defects fixed: 3 (win-rate-implied EV, discarded payoffs, unstable-universe drift).
- Champion: invalidated (C-001) — stack now honestly empty.
- **Key insight:** the program's losses were measurement artifacts, not bad luck; with an honest
  instrument, the only positive EV in reach is small structural carry, and memecoins are
  convex-momentum (not reverting) vehicles. Next edge most likely at new-listing funding decay.
- **Next session priority:** H-024 → H-021 → H-022.
