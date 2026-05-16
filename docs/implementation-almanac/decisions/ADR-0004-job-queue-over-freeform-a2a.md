# ADR-0004 - Job Queue Over Freeform A2A

## Decision

Internal agent coordination uses database-backed jobs, monitoring sessions and leases instead of free-form agent-to-agent chat.

## Rationale

Trading research requires auditable state ownership, retries, timeouts and conflict resolution. Free-form A2A is too hard to verify.

## Consequences

- Every task has schema.
- Every worker has lease.
- Conflicts are explicit.
- A2A protocol is future-only for independent services.

