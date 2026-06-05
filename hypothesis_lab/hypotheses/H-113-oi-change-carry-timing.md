# H-113 — Open-interest change as carry crowding early indicator

**Status:** proposed · BLOCKED · 2026-06-05
**Zone:** MICROSTRUCTURE SIGNALS — OI history as crowding signal
**ID range:** H-113 (Zone 3 generation)

## Statement
Rising OI with rising funding = crowding building. When OI drops sharply (de-levering event),
carry quality IMPROVES in the subsequent periods as the weak hands have been flushed.
Use OI change rate as a carry-entry timing signal: enter/add on OI drops + stable funding;
reduce on OI expansion + funding spike.

## Structural logic
**Who is forced:** OI rising = new leveraged longs being added. When OI falls suddenly, those
longs were forcibly closed (liquidation cascade). The subsequent carry is collected against a
less-crowded field.

## Falsifier
OI change has no predictive power for subsequent 1–3 period carry APR or cascade probability.

## Data status
**BLOCKED** — OI history only available for 30d via Binance REST (`/fapi/v1/openInterestHist`).
730d OI cache does not exist. Cannot build a meaningful historical backtest with only 30d.

## Test (one line)
BLOCKED — collect OI history forward; once 180d+ available, merge with funding panel in
`funding_leads2.py` and test OI-delta-gated carry APR.

## SCORE: 5.0
(edge_plausibility=4, data_feasibility=1, novelty=3 → (4×2+1+3)/4 = 12/4 = 3.0 → 6.0; BLOCKED → 5.0)
