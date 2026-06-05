# H-155 — DeFi TVL Change Rate as Crypto Macro Signal

**Status:** proposed · BLOCKED · 2026-06-05
**Zone:** ON-CHAIN / MACRO

## Statement
Rapid DeFi TVL growth indicates capital deployment into yield strategies, which competes with and reduces perp funding carry. Rapid TVL decline indicates DeFi deleveraging, which may push capital into perp speculation (increasing funding). Gate or size carry book by DeFi TVL rate-of-change.

## Data status
data_status: BLOCKED — DeFi TVL not cached. Requires DeFiLlama API. Accessible in theory but not <30min. Daily resolution at best, mismatched to 8h funding.

## Test (one line)
BLOCKED: fetch DeFiLlama /tvl/all endpoint daily; interpolate to 8h; CCF with mean alt funding; gate carry on TVL-decline regime.

## SCORE: 4.5
(edge_plausibility 2.5/5 — indirect link; data_feasibility 1/5; novelty 3/5 → 4.5)
