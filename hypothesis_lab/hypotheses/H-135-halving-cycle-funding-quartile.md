# H-135 — Halving-cycle position: funding level vs days-since-halving quartile

**Status:** proposed · 2026-06-05
**Zone:** CALENDAR / EVENT-DRIVEN
**Score:** 6.5
**Asset universe:** 29 tradeable Binance perps (funding 8h, 730d)
**Created:** 2026-06-05

## Statement
BTC halving (2024-04-20) divides the crypto cycle. In the 730d data window, we observe the
post-halving period (Apr 2024 – Apr 2026 approximately). Historically, funding rates are:
- Elevated in months 1-6 post-halving (euphoric bull market, leveraged longs dominant)
- Compressed in months 6-18 (consolidation phase, de-leveraging)
- Re-elevated in months 18-24 approaching the next pre-halving period

Compute days-since-halving for each 8h period; split into quartiles (Q1: 0-6mo, Q2: 6-12mo,
Q3: 12-18mo, Q4: 18-24mo); test whether mean funding differs across quartiles.

This is a REGIME IDENTIFICATION tool (what cycle position yields highest carry), not a
per-event trade. If confirmed: concentrate carry portfolio in high-funding-quartile cycle
positions; reduce allocation in low-funding-quartile.

## Structural reason (who is forced)
Halving creates supply shock → price appreciation → leveraged long demand increases
(structural long bias in early post-halving). As the cycle matures, leveraged longs are
de-risked by corrections. This creates a predictable funding-level arc over the 4-year cycle.
Who's forced: cycle-aware institutional allocators who increase crypto exposure post-halving.

## Falsifier
(1) Funding does NOT differ across days-since-halving quartiles (controlling for BTC return —
    the quartile effect is just contemporaneous trend, not calendar position).
(2) Only 1 halving in the data window — this is a single cycle observation; no statistical test
    is meaningful (same as H-126 n=1 problem, but at cycle-quartile level).
(3) The trend within the halving cycle is monotone in BTC price, not independently predictive.

## Why uncaptured
Single halving in data window = eff-n 1 cycle (4 quartiles within 1 cycle = not independent).
Large funds actively model this; the premium is front-run by sophisticated players. Retail
doesn't distinguish cycle position.

## Data status & effective-n
- data_status: HAVE — funding 8h, UNIX timestamps. Halving date 2024-04-20 hardcodable;
  days-since-halving derivable from timestamps.
- eff-n: 730d of data ÷ 4 quartiles = ~182 periods per quartile → within-quartile n is HIGH.
  But independence across quartiles: only 1 cycle → 4 non-independent observations.
  Statistical test across quartiles is valid for DESCRIPTION; causal inference requires
  multiple cycles.
- Feasibility: moderate for descriptive analysis; low for causal inference.
- data_status tag: HAVE, but 1-cycle caveat.

## One-line test
Extend `funding_leads2.py`: derive days_since_halving from UNIX timestamps (halving=2024-04-20);
split into 4 quartiles; compute mean funding per quartile; ANOVA on 730d × 50 names panel;
report as DESCRIPTIVE (not permutation null — no independent cycle replication).
