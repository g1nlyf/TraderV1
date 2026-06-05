# Session Log — 2026-06-05 — STACK + regime-gate + carry-refinement battery

## Context at start
- Champion: **C-002** carry book (level-fixed RP top-10, basis-aware maker). Reproduced exactly this
  session: TEST **+1.49% APR, Sh 3.54, maxDD −0.19%, CI95 [+0.78%, +2.08%], n=657**.
- Champion status: HEALTHY. Top-10 = UNI, LTC, FIL, LINK, ETH, DOGE, AAVE, ADA, XRP, BTC.
- Priority: test whether a 2nd uncorrelated sleeve (H-042), a basis-vol de-risker, a BTC-vol gate,
  or an alternative selection rule **CI-separates** from the C-002 baseline. Discipline: 3 prior
  false-positive traps caught (win-rate-EV, regime-capture, leverage-maxDD) — preserve.
- Script: `hypothesis_lab/scripts/test_carry_cluster.py` (panel loaded ONCE; reuses
  fh.metrics / fh.block_bootstrap_ci / fh.evaluate / the carry_lift level-fixed RP book; 70/30
  temporal, select on TRAIN, report TEST; realized payoff only).

## Results Summary

| test | APR | Sharpe | CI95 | n | verdict |
|---|---|---|---|---|---|
| **baseline C-002** | +1.49% | +3.54 | [+0.78%,+2.08%] | 657 | champion baseline |
| stack 50/50 (volmatch) | +1.17% | +3.93 | [+0.54%,+2.03%] | 657 | r=−0.08; Sh↑ but APR-CI overlaps base; N |
| stack 70/30 (volmatch) | +1.30% | **+4.05** | [+0.70%,+1.90%] | 657 | r=−0.08; Sh↑ NOT CI-sep; sleeve n=39 sub-gate; N |
| derisk fixed | +1.49% | +3.54 | [+0.78%,+2.08%] | 657 | baseline |
| derisk basis-vol scaled | +1.16% | +3.21 | [+0.53%,+1.64%] | 657 | worse Sh & APR, maxDD ~flat; N (risk rule) |
| btcgate always-on | +1.49% | +3.54 | [+0.78%,+2.08%] | 657 | baseline |
| btc-vol<p50 (off above) | +0.83% | +2.79 | [+0.40%,+1.36%] | 657 | worse; N |
| btc-vol<p50 (0.5x above) | +1.16% | +3.49 | [+0.64%,+1.67%] | 657 | ties down; N |
| btc-vol<p60 (off above) | +1.29% | +3.79 | [+0.68%,+1.83%] | 657 | Sh↑ NOT CI-sep, APR↓, eff-n≈18; N |
| btc-vol<p60 (0.5x above) | +1.39% | +3.84 | [+0.76%,+1.94%] | 657 | Sh↑ NOT CI-sep, APR↓, eff-n≈18; N |
| sel H-021 level (BASE) | +1.49% | +3.54 | [+0.78%,+2.08%] | 657 | base |
| sel H-115 funding AR(1) | +1.58% | +3.85 | [+0.94%,+2.15%] | 657 | Sh↑ NOT CI-sep; N |
| sel H-145 low BTC-beta | +1.50% | +3.97 | [+0.89%,+2.06%] | 657 | best Sh, NOT CI-sep; N |
| sel H-089 level×persist | +1.81% | +2.46 | [+0.87%,+2.65%] | 657 | APR↑ but Sh collapses; N |

- Hypotheses tested: 13 configs across H-080/089/091/092/099/100/110/115/116/140/145/149/150.
- PASS (gate-candidate): **none.**
- INFORMATIVE / thesis-hardening (sub-gate): **H-099 / H-110 / H-149** (stack uncorrelation confirmed).
- FAIL / no CI-separation: H-080/092/100/116/140 (BTC-vol gate), H-091/150 (de-risker),
  H-115/145/089 (selection variants).

## STACK correlation — the load-bearing result
**r(C-002 carry per-8h pnl, H-042 sleeve per-8h beta-adj-excess) = −0.077 on co-active periods
(n=39), −0.000 over the full TEST window.** H-042 sleeve = −8% perp drop + rising funding +
tradeable, H=2 per-period mean beta-adjusted EXCESS forward (market-neutral), reusing h042_deep
logic; one obs per event-period; flat between events (5.9% duty on TEST).

- The two sleeves are **genuinely uncorrelated** (|r|≪0.3). This is the qualitative confirmation
  C-002 lists as a hardening TODO ("measure H-042 corr-to-carry for the stack").
- Raw 50/50 *capital* blend is meaningless: the per-event bounce (~+0.6%/event, std ~1415× the
  carry per-period std) is NOT a per-8h rate. Honest blends are **vol-matched** (sleeve scaled
  k=0.0028 so its full-window per-period std = carry's, then weighted). Vol-matched sleeve-as-book
  APR ≈ +0.86%.
- Vol-matched 70/30 stack Sharpe +4.05 vs carry +3.54 — a real but **NOT CI-separated** lift
  (stack APR CI95 [+0.70,+1.90] overlaps carry [+0.78,+2.08] entirely), and the sleeve carries only
  **39 TEST events (n≪100 gate)**. Per the gate rule (Sharpe improvement must be CI-separated), this
  is **not** a formal gate-candidate — but the uncorrelation is the asset, and it survives once
  H-042's n matures. Status unchanged from C-002's "stack candidate, sub-gate on n."

## Gate / champion candidates
**None promoted.** No config CI-separates from C-002 on APR or Sharpe. The BTC-vol-gate p60
variants tripped the script's mechanical "Sh>base" flag but FAIL the discipline screen:
(a) Sharpe lift 3.54→3.84 is not CI-separated, (b) APR is *lower* (+1.39 vs +1.49), (c) eff-n≈18
autocorrelated ON-runs — a classic regime-capture shape (H-051 trap). Rejected. Selection variants
(H-145 low-beta best at Sh 3.97) likewise tie within CI — no flag.

## Champion stack delta
Before: C-002 = +1.49% APR / Sh 3.54.
After: **unchanged.** No promotion. H-042 confirmed uncorrelated (hardens the stack thesis) but
stays sub-gate on n; no de-risker / gate / selection change clears CI-separation.

## Key insight
Everything that "improved" Sharpe (p60 BTC-vol gate, H-145 low-beta, H-115 AR1) did so by
**trimming variance, not adding return** — and none of the trims is CI-separated from baseline; the
book's maxDD is already −0.19%, so there is almost no risk left to harvest by gating or de-risking.
The one structurally valuable finding is the **near-zero carry⊕H-042 correlation (r≈−0.08)**:
that is a genuine diversification lever, but it cannot be banked until H-042's event count clears
the n>100 gate. Discipline held — no marginal-Sharpe noise was promoted to champion.

## Next session priority
1. Grow H-042 event count (lower threshold sweep / more names / 1m intra-bar) to clear n>100, then
   re-run the vol-matched stack for a CI-separated Sharpe test — the only live path to hardening C-002.
2. Leave C-002 selection/gating frozen; the level-fixed RP top-10 is not beaten within CI.
3. Hunt a 3rd *genuinely uncorrelated* sleeve (not a variance-trim of carry) — that is the only
   thing that moves the Sharpe gate.
