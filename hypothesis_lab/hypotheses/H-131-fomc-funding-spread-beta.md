# H-131 — FOMC cluster: high-BTC-beta names fund more on event days

**Status:** proposed · 2026-06-05
**Zone:** CALENDAR / EVENT-DRIVEN
**Score:** 6.5
**Asset universe:** 29 tradeable Binance perps (funding 8h, 730d)
**Created:** 2026-06-05

## Statement
On FOMC days, high-BTC-beta alts (ETH, SOL-linked, large-cap alts) experience larger funding
spikes than low-BTC-beta alts (stablecoins, utility tokens with idiosyncratic demand).
The CROSS-SECTIONAL SPREAD of funding on FOMC days is predictably wider than on non-event
days. Trade: on FOMC-eve, enter carry concentrated in HIGH-BETA names (where funding spikes
most), and exit in LOW-BETA names (where it doesn't spike and you're overpaying).

## Structural reason (who is forced)
High-BTC-beta names are the vehicles for macro speculation. FOMC-day directional bets
concentrate in ETH/SOL/LINK (macro-correlated alts), not in idiosyncratic small-caps.
Speculators MUST use these names for macro positioning (liquidity, tradability). Low-beta
names don't attract the same flow. This creates predictable cross-sectional funding divergence.

## Falsifier
(1) Cross-sectional funding spread (high-beta minus low-beta) is NOT wider on FOMC days
    than on random days (permuted on events).
(2) "Beta" measured from training data doesn't predict which names spike on FOMC days OOS
    (it's regime-dependent, not stable).
(3) Concentrating carry in high-beta names HURTS Sharpe due to correlated tail risk.

## Why uncaptured
Requires computing name-level BTC-beta, building the cross-sectional spread, and matching to
FOMC calendar. Low eff-n (16 events) makes this statistically unreliable. Large funds already
know which names are their macro vehicles.

## Data status & effective-n
- data_status: HAVE — funding 8h + BTC price (for beta estimation). FOMC dates hardcodable.
- eff-n: 16 FOMC events, cross-sectional comparison within each event. Within-event power
  is higher than cross-event (paired test: high-beta vs low-beta funding spread per FOMC event).
- Feasibility: low-n but within-event design helps.

## One-line test
Extend `funding_leads2.py`: for each FOMC date, compute cross-sectional funding rank by
BTC-beta (rolling 90d beta from 8h price); test high-beta minus low-beta mean funding on
FOMC days vs random days; permute on 16 events.
