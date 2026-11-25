# Phase 5: worker checkpoint integration — working plan

Started 26 November 2026 at the user's request to continue after approval of the background-worker design. Planning and reversible documentation edits are authorized; coding, package changes, migrations, services and live/paid execution are not authorized by this phase.

## Objective and boundaries

Connect the approved Celery worker lifecycle to the standalone agent's Redis-backed checkpoint/recovery capability. Preserve the same run identity, Postgres authority, source scope, consumed budgets, review counts, publication identities and unresolved execution-retirement barriers. Checkpoints remain reconstructible projections; application integration does not introduce them for the first time.

Phase 6 owns combined backend failure/race verification. This phase settles the worker/runtime/checkpointer interfaces, ownership and restore order, compatibility/migration rules, Redis outage behavior, wait/resume and acceptance handoff. It does not reopen approved agent/storage/API/worker behavior or claim current standalone implementation passes its milestones.

## Work and review sequence

- [ ] Retrieve the approved checkpoint/worker/authority contracts and inspect relevant current runtime/checkpointer interfaces.
- [ ] Verify exact framework behavior in official documentation where it affects replay, transactions, serialization and concurrency.
- [ ] Prepare a coherent integration packet with normal/restart/reply paths, failure/recovery matrix, compatibility/deletion behavior and acceptance ownership.
- [ ] Resolve consequential choices in ordinary chat and retain approved versus proposed status explicitly.
- [ ] Transfer lasting contracts/rationale/open gates to a focused guide and decision log.
- [ ] At closure delete this temporary plan and repair links, refresh/show the local blueprint and perform due index maintenance.

## Completion boundary

Settle identity, ownership, inputs/outputs, durable transitions and replay semantics, retries/stopping, deletion, compatibility and measured verification owners. Exact build/configuration values remain explicit enablement gates. Preserve unrelated ongoing standalone work.

## Current status

Discovery is starting. No new checkpoint integration choice or runtime readiness is approved by starting this phase.
