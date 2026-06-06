# ROADMAP — Hypothesis Queue

> State reconciled in `knowledge/CANONICAL_STATE.md`. C-002 sole champion; H-042 sole sub-gate sleeve;
> wallet alpha unproven (long)/uncapturable (short, H-162). **Binding constraint = DATA, not ideas.**

## Track 5: Wallet Intelligence — Sprint 5 DONE (2026-06-06), now DATA-gated
First honest point-in-time wallet-alpha stack built + tested (`wallet_alpha/`, SYNTHESIS.md). H-160/H-161
DEAD; H-162 real-but-uncapturable down-signal. Next steps are the **highest-leverage data unblock** in the
whole program:

| Priority | ID | Next test | Unblock needed |
|----------|-----|-----------|----------------|
| **P0** | — | Multi-day on-chain capture: run the bitquery firehose daily ≥30d | a daily cron dump (cheap) |
| P1 | H-163 | Replicate wq-sell cross-sectional ordering ACROSS sessions (kills regime-capture, eff-n=days) | multi-day capture |
| P1 | H-164 | Down-signal on the CEX/perp-listed shortable subset; fuse with C-002 funding/basis | token↔perp mapping |
| P2 | H-165 | quality-sell-cluster as EXIT overlay for any future long book | a profitable long book (none yet) |
| P2 | — | real memecoin slippage curve by liquidity bucket (replace flat 1.8% cost) | quote/impact data |

## Active Research Tracks

### Track 1: Champion — RESOLVED (was "fix the champion")
H-001 proved the champion was never an edge (realized −0.97%, perm_p 0.887). The
instrument that manufactured it is fixed. There is no edge to "fix".

| Priority | ID | Hypothesis | Status |
|----------|-----|-----------|--------|
| DONE | H-001 | Degradation diagnosis → measurement artifact; champion invalidated | **tested · FAIL** |
| CANCELLED | H-004 | Regime filter for mean-reversion | **cancelled** — no positive base to filter |
| CANCELLED | H-005 | Kelly sizing | **cancelled** — sizing a −0.97% edge sizes the loss |
| P2 | H-006 | LLM residual on rule errors | parked — residual of a negative rule is not promising |

### Track 2: Highest-signal surviving leads (PRIORITY)
Re-pointed by H-001. These are where real structure has actually appeared.

| Priority | ID | Hypothesis | Status | Outcome |
|----------|-----|-----------|--------|-----|
| DONE | H-13 | Funding carry capturability | **resolved** | +9% NOT capturable (times into spot-less names). Capturable = +0.8% tradeable (Sh 1.8) + +0.6% xvenue-maker (Sh 3.9). Best real edges; both <+2% gate. |
| DONE | H-15 | t=7.99 vs perm_p=0.666 contradiction | **resolved → REFUTED** | Overlap-inflated t; eff n≈6 episodes/13d; SOL-down recovery beta, not alpha. |
| DONE | H-03 | Drawdown entry realized re-score | **closed** | Same rule as C-001; realized −0.97%, perm_p 0.887 (H-001). Dead. |

### Track 3: New generation — DONE this session (2026-06-04)
Generated informed by the session's findings (not cold). Tested H-019/H-020 (both FAIL —
memecoins trend not revert; momentum is an unsizeable lottery). Filtered survivors queued:

| Priority | ID | Hypothesis | Status |
|----------|-----|-----------|--------|
| P0 | H-024 | New-listing funding decay carry (harvest launch-hype crowding) | proposed · priority-test |
| P1 | H-021 | Persistence-selected carry (funding sign-stability, not level) | proposed |
| P1 | H-022 | Cross-venue funding *agreement* as carry quality filter | proposed |
| P2 | H-023 | Basis term-structure carry, decomposed | proposed |

**Hard rule:** every new hypothesis is tested through `finetune/pipeline/eval_stats.py`
(realized EV + perm_p<0.05 + CI95>0). Win-rate-implied EV is banned. Capturability of the
selected legs is part of the gate (H-13 lesson).

## Session 2 outcome (2026-06-04)
H-021 VALIDATED (best edge): fixed name-selection carry +1.44% APR Sh3.20; stack w/ xvenue
Sh4.28, maxDD −0.1%, corr +0.01 → first **champion-candidate** (leverage gated on tail risk).
H-022 REFUTED, H-024 FAIL. Generated H-031–H-051 batch (10 survivors).

## Next Session (3) Priority — raise the carry book toward the gate, then lever
1. **H-031** risk-parity sizing + **H-049** carry-to-vol selection + **H-036** beta-hedge —
   lift the champion-candidate's unlevered APR/Sharpe (files written, ready to test).
2. **H-051** negative-funding sleeve — third uncorrelated stack component (Sharpe ↑).
3. **H-037** convex memecoin momentum basket — the one novel non-carry test.
4. **Tail-risk unblock (the REAL gate to +5%):** the leverage path is blocked by DATA, not
   slicing. Naive 21× → +66% is a trap (8h-close maxDD −0.24% ignores intra-8h gap/liquidation +
   basis-blowout). Need: (a) tick/1m perp+spot to simulate intra-period margin under leverage,
   (b) an explicit basis-blowout stress scenario. Then sane 2–3× → ~+3–6% APR is validatable.
5. **Forward-collect tracks:** H-040 smart-money early-buyer, H-024 hedgeable new-listing subset.

Seed directions DEAD (do not regenerate): memecoin mean-reversion (D-005), liquid directional
factors (H-10/11/12/14), win-rate-implied anything, cross-venue *agreement* (H-022 refuted).

## Background Process (verify before each session)
- forward_collector.py — early-buyer data for H-003/H-18 (Windows Task `TraderV1_ForwardCollector`).
- autoloop_meanrev.py — NOW honest (realized EV + perm/CI gate). Safe to schedule daily again.

## Experiment → Promotion Flow
```
proposed → testing → passed (eval_stats: realized EV>2%, perm_p<0.05, CI95>0, n>100)
                  → champion_candidate → champion
        → failed → refinement_proposed → new H-XXX
```
