# H-154 — Stablecoin Mint/Burn Flow as Crypto Risk-Appetite Signal

**Status:** proposed · BLOCKED · 2026-06-05
**Zone:** ON-CHAIN / MACRO

## Statement
Large USDT/USDC minting events signal new capital entering crypto (bullish; funding should rise and carry is richer in next 3-7 days). Large burn/redemption events signal capital exit (funding to compress). Gate carry book size on lagged stablecoin net flow.

## Structural logic — who is forced
New stablecoin minting creates dry powder that flows into risk assets via leveraged perp positions. The correlation between mint events and funding spikes is documented anecdotally. The forced flow is the new entrant who deploys stablecoin into perps.

## Data status
data_status: BLOCKED — Stablecoin mint/burn not cached. Requires Etherscan API, Tron API, or Nansen feed. Not accessible in <30min.

## Test (one line)
BLOCKED: fetch USDT/USDC on-chain supply delta from Coingecko or DeFiLlama; align to 8h periods; CCF with mean alt funding; gate carry on positive net flow periods.

## SCORE: 5.0
(edge_plausibility 3.5/5, data_feasibility 1/5 — blocked; novelty 3/5 → 5.0)
