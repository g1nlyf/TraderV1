# H-109 — H-042 intra-period 1m entry: enter at the −8% touch, not 8h close

**Status:** proposed · 2026-06-05
**Zone:** MICROSTRUCTURE SIGNALS — 1m cascade entry sharpening
**ID range:** H-109 (Zone 3 generation)

## Statement
H-042 uses the 8h CLOSE to detect and enter cascade events (perp down >8%, funding rising).
By the close, the name has partially recovered — the best entry is at the INTRA-PERIOD trough
(the exact −8% touch on 1m bars). Entering at the 1m trough should significantly improve
per-trade EV: you capture the overshooting region rather than the post-recovery close.

This is a sharpening of H-042 (not a new hypothesis), but the signal-generating mechanism
is identical — only the entry timing changes. The structural edge is the same forced liquidation.

## Structural logic
**Who is forced:** Same as H-042 — margin-called longs are price-insensitive forced sellers.
The trough is the exact moment of maximum forced selling before liquidity returns. Entering
at the trough vs. the period close captures the full reversion amplitude, not just the residual.

## Falsifier
Intra-period entry at the −8% touch does NOT improve EV over 8h-close entry (cascade is still
active at the 1m trough and the name continues to fall); or the 1m touch is not reliably
identifiable in practice (flash move, recovery within the same 1m bar).

## Why uncaptured
Requires 1m data to locate the intra-period trough. Until Session 4, only 8h closes existed.
Now testable on 10 names with the harvested 1m perp data.

## Data status
**HAVE** — 1m perp OHLCV for 10 names (180d) in `finetune/data/intraday_1m/`. The cascade
detection can use the 8h-period mask from H-042 logic, then locate the 1m LOW within that
period for the entry price.

## Test (one line)
New script on `finetune/data/intraday_1m/`: for each 8h period where 8h return < −8%, find
the 1m LOW; compute forward return from that 1m LOW to the period close and to 2h later;
compare to H-042 8h-close EV; permutation test on the same events.

## SCORE: 8.5
(edge_plausibility=5 — this is a direct mechanistic improvement on an already-validated signal;
data_feasibility=5; novelty=2 → (5×2+5+2)/4 = 17/4 = 4.25 → 8.5)
