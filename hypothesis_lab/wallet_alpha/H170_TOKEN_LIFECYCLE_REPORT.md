# H-170 Token Lifecycle Model + Beat-Token-Only Gate (Sprint 8, 2026-06-06)

Exploited Sprint-7's strongest clue (token context dominates wallet behavior) two ways: (A) a deterministic
token **lifecycle state machine** validated for OOS EV separation, and (B) a reusable **beat-token-only gate**
that asks whether wallet/cluster features add anything over token context in a full multivariate ML setting.
Code: `token_lifecycle.py`. Source = ORGANIC May-14 raw_trades (ONE session). Temporal OOS, eval_stats gate,
strong controls. Honest scope: cross-sectional state prediction is valid; absolute EV levels are regime-bound.

## Sampling (honesty first)
- Token-centric sample: ≤3 decision points/token, spaced ≥H (1800s) so within-token forward windows never
  overlap. n=1027 across 609 tokens. Cross-token temporal split (first 60% by decision-time = train).
- Forward label = capped net VWAP return (entry 0–300s, exit at 1500–1800s), cost 1.8%. No forward
  liquidity = stuck = −100% (the honest rug tail).

## PART A — Token lifecycle (H=30m, n=1027, test n=411, base EV −13.13%)

### A1 — per-state forward EV (test fold) + canonical gate
| state | test n | test EV | gate edge over base | perm_p |
|-------|--------|---------|---------------------|--------|
| **neutral** | 120 | **−7.35%** | **+8.02%** | **0.000** ✅ (CI [−8.0%,−1.4%]) |
| rug_dead | 91 | −8.97% | −3.23% | 0.897 |
| crowded_top | 6 | −11.73% | −12.16% | 0.868 |
| acceleration | 6 | −12.63% | +4.83% | 0.315 |
| distribution | 21 | −18.13% | +4.80% | 0.180 |
| ignition | 46 | −19.59% | −4.32% | 0.911 |
| decay | 121 | −18.76% | −6.79% | 0.996 |

States **materially separate** forward EV (neutral −7% to decay/ignition −19%). `neutral` (past ignition,
not topped, not selling-off, not rugging) is significantly least-bad (perm 0.000). But **every state is
negative** → this is an AVOIDANCE axis ("which is least bad in a dump"), not a long edge.

### A2–A3 — does the lifecycle state add over raw token features?
- Token-only GBM (top-30% by predicted net): edge **+1.87%** (perm 0.301, n.s.)
- Token-only **+ state one-hot**: edge +1.97% → **incremental from state = +0.10% (≈ nothing)**
- **Key finding:** a GBM on the continuous token features already captures the lifecycle information. The
  explicit state machine is **interpretable packaging, not new signal**. Its value is human-readable risk
  states + the avoidance filter below — not incremental alpha.

### A4 — avoidance no-trade filter (capturable)
Skip rug_dead + distribution + decay: base −13.13% (n=411) → kept **−10.84%** (n=178), **delta +2.29%**.
A real, capturable de-risk no-trade filter (book still negative → de-risk, not alpha). Shadow candidate.

### A5 — random control: edge −1.68% (perm 0.676) — selection is not luck.

## PART B — Beat-Token-Only Gate (cluster events, n=1137, test n=455, base −17.70%)
The falsification gate the program needs. Full multivariate GBM, token-only vs token+wallet, temporal OOS.

| model | top-30% edge over base | perm_p | CI95 | OOS Spearman |
|-------|------------------------|--------|------|--------------|
| token_only | +9.81% | 0.001 | [−10.06%, −0.94%] | +0.400 |
| **token+wallet** | **+11.36%** | **0.000** | **[−7.27%, +0.24%]** | **+0.474** |

**Wallet/cluster features ADD incremental OOS value over token context: +1.55% edge AND +0.074 Spearman.**
This **revises Sprint-7's univariate conclusion** ("wallet adds ~nothing"): in a *multivariate* model the
wallet-quality + cluster-cohesion features carry information the token features don't. token+wallet is also
the **closest any selection has come to break-even** (CI upper +0.24%). Still negative EV on the down-regime
→ not promotable, but wallet intelligence is **NOT dead** — demote-to-secondary was too harsh.

## Verdict
1. **Token lifecycle states (H-170): REAL OOS EV separator, but on the avoidance axis** and **not
   incremental over continuous token features**. Value = interpretable risk states + a +2.3% no-trade filter.
   Not alpha. Shadow/de-risk candidate.
2. **Wallet incremental value (H-171): SUGGESTIVE REVISION of the wallet-dead verdict.** Multivariate
   token+wallet beats token-only OOS (+1.55% edge, +0.074 Spearman, perm 0.000). Needs walk-forward
   confirmation (single split). The combined model is the best ranker built so far (CI upper +0.24%).
3. **Nothing clears the +2% gate** — every selection is negative EV. The recurring wall is unchanged: ONE
   down-regime. Absolute profitability is untestable until a second regime exists.

## Strategy assembly (Trunk 6 — no orphan research)
| signal | role | status |
|--------|------|--------|
| Token lifecycle avoidance filter (skip rug/distribution/decay) | **no-trade filter** | shadow candidate (+2.3%, capturable) |
| `neutral`-state preference (perm 0.000) | no-trade / sizing input | shadow candidate |
| token+wallet GBM ranker (CI upper +0.24%) | **entry-ranking model** | promote-WATCH, needs cross-day + walk-forward |
| lifecycle state machine | interpretability layer | keep (human-readable risk states) |
| explicit state one-hot as ML feature | — | DROP (adds nothing over continuous feats) |

## Mandatory review
- **Strongest reason it works:** lifecycle states have structural meaning — rug/distribution = forced future
  selling; neutral = pre-discovery accumulation. Wallet-quality + cohesion proxy informed flow.
- **Strongest reason it fails:** all evidence is one down-session; "least-bad in a dump" need not become
  "positive in a normal regime"; microcaps aren't shortable so the avoidance/short side isn't capturable.
- **Hidden assumption smuggled in:** that a cross-sectional EV *separator* on a down-day converts to a
  *profitable* selector on an up/flat day. UNTESTED.
- **Evidence that would change my mind:** a second regime (up/flat day, via Corecast ≥14 days) where
  neutral-state or token+wallet selection clears EV > +2% with perm < 0.05.
- **What the project still hasn't learned:** whether ANY of these cross-sectional separators survive a
  non-dump regime. Every wallet/token sprint hits this identical wall. **Regime diversity (cross-day data)
  is THE binding constraint** — not features, not models, not architecture.

## Anti-repeat notes
- Do NOT add an explicit lifecycle-state one-hot as an ML feature — a GBM on the continuous token features
  already captures it (+0.10% only). Keep the state machine for interpretability/avoidance only.
- Do NOT re-kill wallet intelligence on univariate rho alone — multivariate ML shows it adds +1.55%/+0.074.
- Do NOT claim any +EV long on May-14 data — every selection is negative; it is a down-regime.
- The next decisive experiment is regime diversity (H-163 cross-day), not another feature.
