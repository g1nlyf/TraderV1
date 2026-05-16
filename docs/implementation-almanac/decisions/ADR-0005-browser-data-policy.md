# ADR-0005 - Browser Data Policy

## Decision

Browser-derived data is context or low-confidence evidence, not canonical high-confidence P&L.

## Rationale

Browser extraction can break silently due to layout changes and cannot be trusted like structured market/indexer data.

## Consequences

- Browser facts require URL and extraction timestamp.
- Browser-only prices cannot promote strategies.
- If no better source exists, output is research-only or shadow-gap evidence.

