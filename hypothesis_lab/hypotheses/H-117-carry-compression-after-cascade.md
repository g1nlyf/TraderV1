# H-117 — Funding carry COMPRESSES after a cascade: exploit the reset window

**Status:** proposed · 2026-06-05
**Zone:** MICROSTRUCTURE SIGNALS — carry-compression post-cascade as skip signal
**ID range:** H-117 (Zone 3 generation)

## Statement
After a liquidation cascade on a name (perp drop >8%), funding rates RESET lower for 2–4 periods
as the leveraged-long pool has been flushed. This is the INVERSE of H-042: while the price
mean-reverts (H-042 edge), the carry collected in those periods is COMPRESSED (the funding earned
is lower than the carry-book average). The optimal play is to: (a) enter H-042 for the price
reversion, while (b) EXCLUDING that name from carry collection for the 2–3 post-cascade periods.

This hypothesis quantifies the carry-compression window and the EV gain from skipping carry
post-cascade vs. collecting it naively.

## Structural logic
**Who is forced / structural:** Post-cascade, the remaining longs are risk-averse; leveraged
demand drops. Funding resets toward zero. The carry book collecting at full size during this window
earns sub-average rates. The smart carry operator suspends the name, collects price reversion
(H-042), and re-enters carry once leverage builds back up.

## Falsifier
Post-cascade periods show funding rates NOT significantly below the name's average; or the
carry collected is positive and comparable — meaning cascades don't reset the carry pool.

## Why uncaptured
H-042 and C-002 have been analyzed separately. The INTERACTION between them (post-cascade carry
being compressed) has not been measured. This is the natural follow-on analysis.

## Data status
**HAVE** — 8h funding + 8h perp prices for 50 names (730d). Cascade events identifiable from
perp price drops. Post-cascade funding distribution measurable directly from the funding panel.

## Test (one line)
Extend `funding_leads2.py`: for each cascade event (perp drop >8%), extract funding rates for
t+1, t+2, t+3 vs. the name's unconditional mean; compute mean difference; permutation test
for significance; compute EV gain from skipping carry in those periods.

## SCORE: 8.0
(edge_plausibility=4, data_feasibility=5, novelty=4 → (4×2+5+4)/4 = 17/4 = 4.25 → 8.5;
slight reduction to 8.0 because n of cascade events is limited and per-period effect may be small)
