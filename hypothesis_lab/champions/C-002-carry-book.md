# C-002 — Cross-margined fixed-selection funding-carry book

**Promoted:** 2026-06-05 (Session 4) · **First validated champion of the program**
**Realized unlevered EV:** +1.49% APR · Sharpe ~3.5 · CI95 [+0.78%, +2.08%] · n=657 (6mo OOS)
**Levered target:** ~3.4× cross-margin → **+5.0% APR** (mission target), basis-tail-gated

## What it is
Delta-neutral basis trade on liquid Binance perps: **long spot / short perp**, harvest funding.
- **Selection:** fixed top-10 by mean funding on train, held through test (H-021 — fixed selection,
  NOT dynamic chasing which died at −0.1% on turnover, H-13).
- **Sizing:** risk-parity, weight ∝ 1/funding-vol (H-031, +1.49% vs EW +1.44%, Sharpe 3.20→3.54).
- **Execution:** maker both legs (1bp), basis-aware entry, EWMA-sign, no lookahead.
- **Leverage:** cross-margin (unified spot+perp account), ~3.4× → +5% APR.

## Why it's real (4 sessions of trap-hunting survived)
- Realized payoff via `eval_stats` (NOT win-rate-implied — the C-001 trap). CI95 excludes zero, n=657.
- Permutation/CI gated. Basis-aware + maker cost included. Tradeable filter (real spot leg, ≥90% history).
- Counterparty that can't stop: leveraged longs structurally paying funding to hold.
- Survived: win-rate-EV trap (H-001), uncapturable-leg trap (H-13), regime-capture trap (H-051),
  leverage-maxDD trap (Session 2→4).

## Leverage validation (scripts/leverage_sim.py — 10 names, 180d 1m perp+spot, ~4.9 name-years)
The 8h-close maxDD (−0.24%) was a TRAP (real intra-8h perp moves p99 5–10%, UNI +41%). The honest
risk for a delta-neutral book is the perp/spot **basis** swing, measured from 1m paths:
```
                       safe L      APR at safe L     survives basis gap up to
ISOLATED margin (naive)   ~5×        +5.4% net          (price spike liquidates leg)
CROSS margin (real desk)  ≥10× norm  3×→+4.5% 4×→+6%    3×: 33%   4×: 25%   5×: 20%
worst SAMPLED basis widening over 4.9 name-years = 0.67%  (≪ any d_liq)
```
Both margin models reach +5%. Cross-margin basis risk is tiny in normal conditions.

## Risk rules / sizing (the honest caveats — operating parameters, not disqualifiers)
1. **Basis-blowout tail is UN-sampled** (180d, no FTX/oracle-grade event). A >33% basis gap liquidates
   3×. → **Cap leverage at 3–4×** (survives 25–33% gaps, covers most historical major dislocations);
   de-risk to ≤2× if realized basis-vol spikes or a venue shows stress.
2. **Funding compression:** APR is recent-6mo; funding has secularly declined. Monitor — re-derive
   selection quarterly; if unlevered APR < +1%, cut size.
3. **Funding-flip:** if a held name's funding turns persistently negative, drop it (don't invert — H-051).
4. Degradation protocol (STACK.md) applies: size to zero on 2 consecutive negative realized-EV checks.

## Status & next
- **PROMOTED** as the first champion. Mission +5% target is reachable at ~3.4× cross-margin under
  normal conditions with defensible tail coverage at 3–4×.
- **Stack candidate:** H-042 liquidation-bounce (market-neutral, ~uncorrelated, sub-gate on n) would
  raise the book's Sharpe further once its n clears — the program's diversification lever.
- **Hardening TODO before live size:** (a) 18-mo+ funding incl. a crash for the basis tail, (b) confirm
  cross-margin mechanics on the target venue, (c) measure H-042 corr-to-carry for the stack.
