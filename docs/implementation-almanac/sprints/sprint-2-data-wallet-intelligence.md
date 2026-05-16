# Sprint 2 - Data, Token Discovery And Wallet Intelligence

## Goal

Turn raw sources into normalized token and wallet evidence.

## Scope

Build:

- source adapters;
- source health and rate-limit handling;
- browser research adapter with confidence/degradation policy;
- `TokenCandidate`;
- `TokenProfile`;
- token triage buckets;
- wallet trade reconstruction;
- `WalletProfile`;
- `WalletCluster`;
- historical wallet metrics;
- evidence quality.

## Non-goals

- No paper trades.
- No strategy promotion.
- No use of browser-only prices for high-confidence P&L.
- No assumption that historical wallet profitability proves strategy success.

## Tasks

1. Implement data source registry.
2. Implement at least one real token/market source adapter.
3. Implement source confidence and degradation state.
4. Store `MarketSnapshot` with timestamps and source refs.
5. Implement token discovery pipeline.
6. Implement token triage with configurable bucket priors.
7. Implement wallet trade reconstruction.
8. Compute historical reconstructed wallet metrics.
9. Add wallet class labels with confidence.
10. Add wallet cluster flags.
11. Add browser extraction records for non-API sources.
12. Add tests for stale data and browser adapter failure.

## Acceptance gate

- System discovers real token candidates.
- Token profiles are normalized and timestamped.
- Wallet profiles are created from observed data.
- Historical wallet metrics are marked as candidate evidence only.
- Browser-derived data is non-canonical.
- Data quality and source confidence are visible downstream.

## Failure conditions

- Strategy performance is inferred from historical wallet P&L.
- Browser-only prices enter canonical high-confidence P&L.
- Triage hardcodes unvalidated holder/liquidity rules as truth.
- Source failure silently creates normal-looking data.

