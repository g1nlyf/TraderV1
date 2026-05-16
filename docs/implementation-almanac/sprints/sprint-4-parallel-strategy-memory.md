# Sprint 4 - Parallel Monitoring, Strategy Search And Memory

## Goal

Scale from one linear workflow to bounded autonomous research across many tokens, wallet clusters and strategy hypotheses.

## Scope

Build:

- per-token monitoring sessions;
- per-paper-position monitoring sessions;
- per-wallet-cluster sessions;
- bounded worker pools;
- conflict review;
- strategy mutation proposals;
- strategy comparison / leaderboard v1;
- promotion/demotion/kill criteria;
- post-trade review;
- memory curator.

## Non-goals

- No unbounded swarm.
- No free-form A2A as state transport.
- No framework adoption unless measured bottleneck exists.
- No strategy promotion without config snapshot.

## Tasks

1. Implement monitoring session state machine.
2. Implement worker pool leases and heartbeats.
3. Enforce max parallel investigations.
4. Prioritize paper position monitoring over new discovery.
5. Implement `StrategyMutationProposal`.
6. Implement `StrategyConfigSnapshot` links.
7. Implement `PromotionCriteriaSnapshot`.
8. Implement strategy comparison / leaderboard v1.
9. Implement promotion/demotion/kill decisions with snapshots.
10. Implement post-trade review.
11. Implement memory proposal and curation.
12. Implement conflict review flow.

## Tests

- Lease timeout returns job to queue.
- Two workers cannot own same session.
- Conflicting actions create conflict review.
- Strategy mutation creates new version.
- Promotion requires criteria snapshot.
- Memory cannot rewrite ledger.

## Acceptance gate

- Multiple token sessions run without corrupting state.
- Open paper positions receive priority.
- Strategy versions are comparable.
- Reviews update curated memory without rewriting history.
- Queue metrics show controlled parallelism.

## Failure conditions

- Agents share raw scratch memory globally.
- Worker overwrites another worker's state.
- Strategy promotion is based on narrative review.
- Agent disables risk/cost assumptions.

