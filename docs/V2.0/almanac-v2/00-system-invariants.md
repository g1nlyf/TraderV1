# V2 System Invariants

## Agentic Architecture

- The final system is agentic trading, not script trading.
- Scripts provide evidence and tools.
- Hermes and specialist agents decide what to investigate, which wallet/token to trust and whether to create paper/shadow signals.
- No deterministic metric may be treated as the full trading decision by itself.

## Authority

- Hermes can create or request decisions only through typed tools.
- Token Selection Agent can choose token attention state, not direct entry.
- Wallet Intelligence Agent can include/exclude/rate wallets, not mutate P&L.
- Risk engine can veto every entry and exit.
- Evaluation engine is the only source of canonical P&L, expectancy, drawdown and win rate.

## Evidence

- Every agent decision references source evidence.
- Every source artifact includes timestamp, provenance, source quality and confidence.
- Missing source quality must degrade decisions rather than be filled by hallucination.
- Browser-derived evidence is non-canonical unless cross-checked by stronger sources.
- Wallet historical metrics are candidate evidence until forward paper/shadow contribution is measured.

## Wallet Database

- Elite wallet inclusion requires deterministic metrics plus Wallet Intelligence Agent review.
- Each wallet stores "why yes", "why no", demotion triggers and evidence refs.
- Wallets compete continuously by forward contribution.
- A wallet can be demoted even if its historical P&L is strong.
- Wallet clusters must prevent fake independent confirmations.

## Trading And Safety

- V2.0 remains paper/shadow only.
- No private keys, signers, swap adapters or DEX transaction builders.
- No live execution path.
- No `PaperOrder` without prior `Signal`, `TradeThesis` and passed deterministic entry `RiskCheck`.
- No exit fill without prior `ExitDecision` and passed deterministic exit `RiskCheck`.
- No rewriting signal/thesis/risk/fill/outcome after result.

## Active Market Loop

- Market cadence is adaptive, not fixed.
- Normal watched tokens use lower-frequency polling.
- Active tokens use higher-frequency polling only when source limits and source health support it.
- Open paper/shadow positions have the highest observation priority.
- One-second snapshots are a maximum/high-priority mode for active tokens and open positions, not the default for every token.
- If free sources cannot sustain requested cadence, the system must lower cadence honestly and record `cadence_degraded` or equivalent quality flags.
- Open paper positions and exit checks outrank new token research.
- Stale or low-confidence market data must block or downgrade action.

## Wallet Data Sufficiency

- Wallet personality/profile claims require enough transaction history and source coverage.
- If wallet history depth is insufficient, the system must say "interesting wallet, insufficient data" instead of inventing behavior.
- Agent wallet reviews must separate observed behavior, inferred behavior and unknowns.
- A wallet can be tracked on probation with insufficient data only when the decision explicitly records the missing evidence and review expiration.

## Learning

- Positive P&L after costs is primary.
- Win rate is secondary but required for wallet quality context.
- Strategy and wallet promotion require forward evidence.
- Memory entries must be curated, evidence-tagged and allowed to expire.
- Agent conclusions must remain falsifiable by deterministic outcomes.
