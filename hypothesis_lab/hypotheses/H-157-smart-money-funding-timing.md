# H-157 — Smart-Money Wallet Entry Timing vs Funding Rate Spike (On-Chain + Perp Fusion)

**Status:** proposed · forward-collect-pending · 2026-06-05
**Zone:** ON-CHAIN / MACRO

## Statement
When smart-money wallets (from WalletScarper / Helius forward collector) accumulate a token in the first hour of a price move, AND the token's associated perp funding rate spikes simultaneously, this is stronger evidence of the move being legitimate (coordinated spot + perp positioning) versus a purely perp-driven pump (funding spike without wallet inflow). Hypothesis: tokens showing smart-money wallet inflow AND contemporaneous funding spike have better 24h forward returns than funding-spike-only tokens.

## Structural logic — who is forced
Smart-money wallet accumulation + funding spike = coordinated demand across spot and derivatives. The perp-funding-only spike without smart-money backing is more likely to be retail FOMO using leverage — less sustainable and more likely to cascade. The fusion signal isolates genuine new demand from recycled leverage.

## Falsifier
Conditioned on funding spike, the presence vs absence of smart-money wallet inflow has no significant difference in forward returns (t-test, block-bootstrap).

## Why uncaptured
H-040 (smart-money overlap) is proposed but n-blocked. This is a fusion of on-chain and perp signals that has never been tested in any session. Requires both datasets to have sufficient overlap in time and token universe.

## Data status
data_status: forward-collect-pending — Helius wallet data n<30 distinct token episodes. WalletScarper DB: ~9 tokens with outcomes, ~7 wallets. Insufficient for stat tests now. Continue collecting.

## Test (one line)
PENDING: once n>50 token-episodes, merge Helius first-hour wallet inflow flag with Binance perp funding spike (>+0.02%) on same 8h period; compare 24h forward return distribution (with/without wallet inflow) via t-test + permutation.

## SCORE: 6.0
(edge_plausibility 4/5; data_feasibility 1.5/5 — forward-collect-pending, n<30; novelty 4.5/5 → (4×2+1.5+4.5)/4 = 14/4 = 3.5 → ×2 = 7.0 → discounted to 6.0 for current n)
