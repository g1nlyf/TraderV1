# CANONICAL STATE — single source of truth

> If any other doc disagrees with this file, **this file wins**. Updated end of every sprint.
> Last update: 2026-06-06 (Sprint 5 — Wallet Intelligence Alpha Engine).

## Champions
| ID | What | Status | Honest number | Promotion basis |
|----|------|--------|---------------|-----------------|
| **C-002** | Cross-margin fixed-selection funding-carry book | **ACTIVE — sole champion** | +1.49% APR unlevered, Sharpe ~3.5, CI95 [+0.78%,+2.08%] APR, n=657 (8h periods, OOS) | leverage-validated to ~3.4× cross-margin → +5% APR target; basis-tail-gated |
| C-001 | Mean-reversion drawdown rule | **DEAD (retired 2026-06-04)** | realized −0.97%, perm_p 0.887, CI95 spans zero | was a win-rate-implied artifact; never had an edge |

## Sleeve candidates (NOT champions)
| ID | What | Status | Honest number | Blocker |
|----|------|--------|---------------|---------|
| H-042 | Liquidation-cascade bounce (market-neutral) | **REAL but SUB-GATE** | −8%/H2 +1.46%/trade, cluster-t 2.24, n=91 periods | magnitude×n×significance frontier: no config clears EV>2% ∧ n>100 ∧ perm/CI at once. Needs forward-collect to grow n |

## Wallet / on-chain alpha — TESTED honestly (Sprint 5), still NOT sized
**LONG: UNPROVEN/DEAD on this data. SHORT: REAL but uncapturable.** The first leakage-controlled
point-in-time test stack (`wallet_alpha/`, SYNTHESIS.md) is built and run. Results (temporal OOS, capped
realized EV, eval_stats gate):
- **Naive smart-wallet copy = −17.7% EV** (cluster-buys mark the local top). Invalidates
  `finetune/pipeline/copy_engine.py` (in-sample + survivorship by construction).
- **H-160 wallet-quality selection: DEAD** — pre-t quality *anti*-predicts (rho −0.37 = in-session
  survivorship); adds ~0 over token-microstructure context. **H-161 archetype: DEAD.**
- **H-162 distribution-sell down-signal: REAL, NOT promotable** — coordinated quality-wallet sells predict
  larger forward drops (wq-sell SHORT +22% EV, perm_p 0.008, CI [+15.9%,+27.6%], n=212; selection edge
  +4.5–5.9% cost-invariant). Blocked: no short venue for microcaps + eff-n=1 session (regime-capture risk).
  Logged as a risk/exit signal, not a champion.

`wallet_leaderboard.json`, `wallet_scores`, `wallet_token_pnl`, GMGN `composite_score` remain **look-ahead
selection labels, not alpha** — never features. **Wallet alpha must not be sized.** Next = multi-day capture
(H-163/H-164) to test persistence + find a capturable subset. See `DEAD_TRACKS.md#naive-leaderboard-copy`.

## The promotion gate (CONSTRAINTS.md, enforced by `finetune/pipeline/eval_stats.py`)
A rule is promotable ONLY if, on a temporal OOS holdout with **realized** payoffs:
1. realized net EV > **+2.0%** per trade, AND
2. permutation-null **perm_p < 0.05**, AND
3. block-bootstrap **CI95 excludes zero**, AND
4. **n_OOS > 100** independent events.

Win-rate-implied EV is **banned** (it manufactured C-001). Sharpe-only heuristics are **not** the gate
(they overstate — see `QUESTIONS.md#q8-carry-cluster-gate`).

## Locked structural truths (do not re-litigate without new data)
1. **Memecoins trend, they don't revert** (H-019 fail, H-020 lottery, H-017 lottery).
2. **CEX direct-funding carry is structural but small** (H-13: +9.1% raw NOT capturable → +0.8–1.5% tradeable).
3. **Fixed name-selection > dynamic chasing** for carry (H-021 vs H-13 dynamic single_topk −0.1%).
4. **Forced flow is asymmetric**: liquidation selling mean-reverts (H-042 real); FOMO spikes continue (H-053) = momentum lottery.
5. **Effective-n pathology is systemic**: overlap/regime inflation fooled H-001, H-15, H-051, H-065. Always cluster-robust.
6. **The binding constraint is DATA, not ideas.** Same-data generation = diminishing returns (Sprint 4: 100 generated, 0 promoted).

## Data truth (the fact that reorients Sprint 5)
The "847K trade tape" = `raw_trades` in `walletscarper.sqlite3`: **843,323 trades inside a 5.5-hour window
on 2026-05-14 (10:00–15:31 UTC)** + 3,946 stragglers on 05-16. It is a calendar-SHALLOW, cross-section-DEEP
firehose (120,418 wallets × 12,318 tokens), **not a time series**. Consequences:
- Intraday cross-sectional wallet tests: feasible, large n.
- **Multi-day forward labels: impossible** (calendar price sources overlap only 16/12,318 tokens).
- **Persistence / alpha half-life: untestable** (needs weeks; we have 5.5h). This is the #1 promotion-blocker for wallet alpha.

Full inventory: `DATA_LEDGER.md`. Full audit: `DATA_AUDIT.md`.
