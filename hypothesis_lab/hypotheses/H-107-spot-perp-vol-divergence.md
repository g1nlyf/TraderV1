# H-107 — Spot-vs-perp volume divergence as directional pressure signal

**Status:** proposed · 2026-06-05
**Zone:** MICROSTRUCTURE SIGNALS — spot vs perp volume divergence
**ID range:** H-107 (Zone 3 generation)

## Statement
When perp volume >> spot volume (high ratio, e.g. >3× rolling mean), the dominant flow is
LEVERAGED and speculative. When spot volume >> perp volume, real buyers are accumulating.
For carry: avoid (or reduce) carry during perp-volume-dominant periods — this is when
forced-unwind cascades are most likely. Alternatively: the perp/spot volume ratio is a
crowding signal for timing H-042 entries (cascades are more severe when perp vol was elevated
pre-drop, so H-042 EV should be higher in those events).

## Structural logic
**Structural:** Leveraged-only flow has no spot anchor; when it reverses, cascade is violent.
Spot-dominant flow reflects real demand (people buying for utility/hold), reducing cascade risk.
The perp/spot volume ratio is a real-time crowding metric proxy (without L2 data).

## Falsifier
Perp/spot volume ratio has no predictive power for subsequent cascade probability or carry APR;
or ratio is too noisy (perp volume spikes on any volatility, positively correlated with
volatility itself rather than directional crowding).

## Why uncaptured
Requires synchronized 1m volume for both perp and spot — available from the harvested 1m cache
but never constructed. Standard carry implementations use only funding; H-042 uses only price.

## Data status
**HAVE** — 1m perp + spot OHLCV for 10 names (180d); volume field in npz (labeled in `leverage_sim.py`
via `open_time, high, low, close` — need to verify if volume is in the npz or needs fetch).
**FETCHABLE** if volume not in npz: Binance 1m klines have volume directly.

## Test (one line)
New script on `finetune/data/intraday_1m/`: compute 8h-aggregated perp_volume/spot_volume ratio;
regress next-period carry return and H-042 event EV against this ratio; permutation test on
carry-gated vs always-on using `funding_leads2.py` panel.

## SCORE: 7.0
(edge_plausibility=3, data_feasibility=4, novelty=4 → (3×2+4+4)/4 = 3.5 → 7.0)
