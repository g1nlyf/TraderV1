# H-142 — BTC Realized-Vol as H-042 Liquidation-Bounce Sizing Input

**Status:** proposed · 2026-06-05
**Zone:** CROSS-ASSET / MACRO

## Statement
H-042 (liquidation-bounce) produces a signal when an alt perp drops ≥8% in a single 8h period. The magnitude of the bounce should be larger when BTC realized-vol is HIGH, because high-BTC-vol regimes correspond to panic liquidations (cascade, not orderly selling), creating deeper overshoots. Hypothesis: scale H-042 position size inversely proportional to BTC realized-vol (larger in high-BTC-vol → deeper liq = larger bounce; smaller in low-BTC-vol mild drops). This is the inverse logic to H-140: the same BTC high-vol that kills carry creates RICHER H-042 opportunities.

## Structural logic — who is forced
In high-BTC-vol episodes, cascade liquidations are triggered by margin calls. The forced selling is mechanically larger than voluntary selling. The mean-reversion after a 8%+ drop is a forced-exit-overshoot correction — the same mechanism that makes carry dangerous (basis blowout) makes H-042 edges richer. BTC vol is the common driver of both the danger (carry) and the opportunity (bounce).

## Falsifier
H-042 bounce magnitude not correlated with concurrent BTC realized-vol; or BTC-vol-scaled H-042 has no better Sharpe than equal-sized H-042.

## Why uncaptured
H-042 was validated with uniform sizing. The BTC-vol interaction as a sizing modifier has not been tested. This directly completes the H-042 → C-002 complementarity picture (carry OFF in high-BTC-vol, H-042 sized UP in same regime).

## Data status
data_status: HAVE — BTC_8h_klines.npz (730d); perp 8h for all names (730d); H-042 signals derivable from the same dataset.

## Test (one line)
Extend h042_deep.py: compute BTC rolling-21 realized-vol at each signal date; split H-042 event PnL by BTC-vol quintile; test mean payoff by quintile + BTC-vol-weighted sizing vs equal via block-bootstrap.

## SCORE: 8.0
(edge_plausibility 4/5, data_feasibility 5/5, novelty 4/5 → (4×2+5+4)/4 = 17/4 = 4.25 → ×2 = 8.5... normalized at 8.0 conservatively for the sub-gate baseline of H-042)
