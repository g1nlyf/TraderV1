# ADR-0001 - Release Target

## Decision

The release target is Stage 2 autonomous real-market paper trading with Stage 3-compatible shadow execution design.

## Rationale

Full Stage 3 depends on live quote quality, latency data and execution simulation quality. Marking it complete without those inputs would create false confidence.

## Consequences

- Stage 2 must be complete.
- Shadow mode is implemented where feasible.
- Shadow gaps are documented honestly.
- Live execution is excluded.

