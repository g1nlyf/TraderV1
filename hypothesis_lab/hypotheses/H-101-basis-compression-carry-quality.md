# H-101 — Basis-compression post-cascade as carry-quality filter

**Status:** proposed · 2026-06-05
**Zone:** MICROSTRUCTURE SIGNALS — basis compression after cascade
**ID range:** H-101 (Zone 3 generation)

## Statement
After a liquidation cascade (perp drops >5% in 8h), the perp/spot basis temporarily widens
as panicked sellers dump perp while spot lags. Over the next 2–4 periods the basis COMPRESSES
back toward zero. Names where the basis compresses FAST (within 1 period) have higher-quality
carry going forward — their funding rates reflect real demand for leverage, not technicals.
Gate the carry book: overweight names that showed fast post-cascade basis compression.

## Structural logic
**Who is forced:** Post-cascade, basis-arb desks buy perp / sell spot to harvest the widened
discount. This is FAST forced flow (basis arb bots close the spread within minutes). Names where
the spread closes fast have deep, active arbitrage coverage — meaning the carry pool is competitive
and stable. Names where it closes slowly are illiquid or dominated by directional flow that
overwhelms arb capacity, which is a carry-quality warning signal.

## Falsifier
Fast-basis-compression names do NOT show higher subsequent carry APR; or compression speed is
uncorrelated with basis-blowout frequency.

## Why uncaptured
Requires 1m perp+spot price to measure per-period basis compression speed. Standard 8h-close
carry analyses cannot observe this.

## Data status
**HAVE** — 1m perp+spot for 10 names (180d); 8h perp+spot for 50 names (730d at coarser resolution).
1m data makes this testable on 10 names now.

## Test (one line)
New script on `finetune/data/intraday_1m/`: for each cascade event (perp drop >5% at 8h), measure
time-to-half-compression of basis; sort names by median compression speed; compare subsequent 8h
carry APR (from `funding_leads2.py` panel) for fast vs slow compressors.

## SCORE: 7.5
(edge_plausibility=4, data_feasibility=4, novelty=4 → (4×2+4+4)/4 = 4.0 normalized = 8.0;
small n=10 names caps at 7.5)
