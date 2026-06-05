# H-156 — Solana Network Activity (TPS/Fee Pressure) as Memecoin Carry Signal

**Status:** proposed · BLOCKED · 2026-06-05
**Zone:** ON-CHAIN / MACRO

## Statement
High Solana TPS and fee pressure (priority fees spiking) indicate peak memecoin speculation activity. This regime corresponds to the highest memecoin momentum (H-037 lottery territory) and potentially elevated SOL perp funding. Gate H-037 memecoin basket OR SOL carry entry on Solana fee/TPS spikes.

## Data status
data_status: BLOCKED — Solana on-chain TPS/fee data not cached. Requires Helius or Solana RPC polling. Helius API is available in environment but real-time only; historical aggregated TPS is sparse/not cached.

## Test (one line)
BLOCKED: poll Solana recent performance samples from Helius; build rolling TPS series; correlate with WalletScarper stage2_foundation.sqlite3 memecoin hourly volume as a proxy; test on memecoin momentum timing.

## SCORE: 4.0
(edge_plausibility 2.5/5; data_feasibility 1/5 — blocked; novelty 3.5/5 → 4.0)
