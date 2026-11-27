# Standalone implementation checkpoint · 27 November 2026

**Next prerequisite: harden T03 ledger schema admission before further runtime integration.** T02 already has substantial implementation and passing fixed-vector checks; do not restart it from the stale 24 November status. This checkpoint is a scoped source/evidence audit, not complete acceptance of T01–T18 or authorization to implement fixes.

## Evidence and scope

Inspected the current working tree at HEAD `bec805ee710641ddd48dd4c64b81c6363b3e5921`, preserving unrelated pending planning/frontend dependency changes. CRG MCP reported a populated graph matching HEAD (119 indexed files); its codec test relationships and CLI file summary narrowed source inspection. Actual source/tests, not graph names, determine the findings below. No graph rebuild was performed.

Ran in the existing agent environment with hosted tracing disabled:

```text
.venv/Scripts/python.exe -m pytest tests -m "not live and not redis" -q -rs -p no:cacheprovider
809 passed, 10 skipped, 1 warning in 10.22s
```

The reported warning is Pydantic's `ToolDeclaration.schema` shadowing a parent attribute. Pytest also emitted a startup deprecation warning for unset pytest-asyncio fixture-loop scope. Neither failed this run. No Redis/provider service, live model call, package installation or untrusted generated analysis was requested; the retained offline tests exercise their local fixtures. No production source/test was changed by this checkpoint.

This is current offline-suite evidence, not full contract coverage. Several passing integration-named tests only construct DTOs or assert shape; their names cannot establish crash/replay/import behavior. Ten explicit skips identify unfinished capability tests. No new package/wheel, real Redis checkpoint, admitted sandbox, provider or end-to-end milestone acceptance was performed.

## Status against the implementation sequence

| Task area | Observed status and limits |
| --- | --- |
| T01 contracts/config/package | Prior completion record exists; current retained suite passes. This checkpoint does not rerun historical wheel/package acceptance. |
| T02 canonical codec | Existing `codec.py`, exact `rfc8785` dependency, committed golden byte/hash fixtures and substantive tests cover tagged scalar forms, hash boundaries, strict decoding and fresh-subprocess re-encoding. Those tests pass in this run. Treat as existing implemented/offline-verified work, not missing scaffolding; no blanket proof for every later persistence boundary. |
| T03 ledger | Existing schema, transaction wrapper, ledger operations and real SQLite tests. WAL/FULL/foreign-key/short-transaction machinery exists. **Incomplete: incompatible schema admission demonstrably mutates/accepts a future-version database.** This is the earliest confirmed unmet prerequisite in the task sequence. |
| T04–T06 artifacts/authority/budgets/models | Substantial modules and tests exist and were included in the passing offline suite. Full task-by-task semantic/independent acceptance was not audited here; do not mark complete or overwrite them as absent. |
| T07 graph/checkpoints | Wrappers and a separate RedisProjection helper exist. The inspected helper serializes broad runtime state and writes seven-day TTLs. Native StateGraph/RedisSaver integration is not established by this inspection. This remains nonconformant/unproven against the approved graph/checkpoint design. |
| T08 answer/review | Drafting/review code and offline tests exist; full independent review/publication acceptance is not established by a suite total. |
| T09 environment/sandbox | Inspected controller still copies host environment and launches a local subprocess; its default manifest supplies `observed_controls` claims. This is not proof of the required isolated environment. Live generated execution remains unadmitted. |
| T10–T12 preparation/SQL/CLI slice | Preparation/SQL modules and tests exist, but CLI `import` and `prepare` explicitly return unavailable/not implemented. Do not claim a working import-to-grounded-answer milestone from the presence of `ask` code. |
| T13–T16 follow-up/Python/adversarial/recovery | Source exists across orchestration/specialist/runtime modules; complete flows remain unverified. Explicit skip reasons include context overflow, Direct latch, terminal reservations, crash replay, duplicate delivery and cross-attempt partial recovery. |
| T17 all formats | Integration-named cases include DTO construction, not actual full-format fidelity proof. Key-candidate and archive-preflight tests explicitly skip as unimplemented. |
| T18 evaluation | Contracts/tests exist; independent oracles and fixture-family hashing explicitly skip. No reproducible measured comparison/report is established. |

The rows beyond T03 are targeted blockers/evidence limits, not a comprehensive audit of each later module. Existing code and test count are useful progress; neither substitutes for the original acceptance oracles.

## Reproduced T03 defect

`Ledger.open()` in `agent/src/querivue_agent/storage/ledger.py` configures the connection and executes the initializer without reading/refusing an unsupported existing schema version. `storage/schema.sql` creates missing tables and inserts version 1 with `INSERT OR IGNORE`.

A disposable SQLite database was created with only the existing version-table shape and row `(999, 'audit')`. Calling `Ledger.open()` succeeded. Afterward:

```text
Future schema ACCEPTED; versions: [1, 999] table count: 33
File changed during open: True
```

Only the audit's temporary directory was used; no operator state or retained application database was opened. This directly contradicts T03's requirement that schema incompatibility fail explicitly.

The existing `test_schema_incompatibility_fails_explicitly` at `agent/tests/integration/test_ledger_races.py` tests a missing-project foreign-key failure. Its comment explicitly switches away from schema incompatibility, so it cannot detect this defect. Keep meaningful foreign-key coverage, but name and test the two guarantees separately.

## Concrete next implementation packet

Scope the next change to T03 schema admission and focused regression coverage, preserving the existing ledger API and all working later modules:

1. Distinguish genuinely new/allowed empty database initialization from an existing supported schema. Inspect version/metadata before schema initialization or mutating connection configuration; reject unsupported/inconsistent versions explicitly rather than inserting version 1 beside them. Do not silently repair or recreate an unknown database.
2. Close rejected connections, preserve the original database/schema/data on failure and retain current short-transaction/durability behavior for supported databases. No migration to a new schema or Postgres adapter is part of this repair.
3. Verify fresh initialization, supported reopen, unsupported future version, conflicting version metadata and failure-path preservation using actual SQLite state. Replace the misleading schema test with a real compatibility assertion while retaining separately named FK coverage. Implement from the existing specification, then verify; no broad test rewrite.
4. Run the affected ledger/authority checks, inspect the diff, then repeat the offline suite only if the changed shared boundary warrants it. Update actual T03 evidence. Fixing this one defect does not complete all T03 or later-task acceptance automatically.

After that packet, audit remaining T03 invariants and proceed in prerequisite order. The graph/checkpoint and sandbox blockers above must be resolved before claiming a runnable/admitted standalone milestone. The agreed application build order still follows standalone acceptance; do not jump to frontend or CI implementation because their designs are closed.

## Subsequent codebase and graph refresh

At the user's explicit request to check the codebase and update graphs, verified that the pending tracked changes were documentation/frontend manifests, with no agent/backend/frontend source diff. Reused the immediately preceding unchanged-source offline-suite evidence rather than rerunning it. Parsed 58 agent source, 44 agent test and six backend Python files successfully (108 total). The existing backend environment's `python manage.py check` reported no issues, zero silenced. This is syntax/foundation evidence, not application integration or Django deployment certification.

CRG MCP incremental maintenance completed without errors and advanced freshness at HEAD `bec805ee710641ddd48dd4c64b81c6363b3e5921`; no source file required reparsing. Post-update statistics: 119 files, 1,916 nodes and 16,226 edges. Of CALLS relationships, 2,644 are directly resolved and 6,108 are unresolved name matches; graph connectivity is an exploration aid rather than proof that every inferred call occurs. No embedding model, network service or new dependency was installed.

The existing Floorplan architectural blueprint was refreshed, preserving planned application/frontend/CI components rather than silently replacing that view with a source scan. Corrected stale CLI hello-scaffold and T02-not-implemented labels, tour notes and next-task flow; added the real ledger/initializer boundary and R11 schema-admission blocker. It has 92 illustrative files, 33 endpoints, six planned screens, thirteen flows, zero unassigned files and zero generic design alerts. Eleven empirical gates remain unpassed; original audit findings retain their evidence dates. CRG is the actual-source graph, while Floorplan remains a mixed planned/observed architecture view.

The existing map preview opening was queued at http://127.0.0.1:4378/. No new HTTP reachability probe was attempted after the earlier approval-service usage-limit failure; this task does not claim that the queued open verified the page. No product source/test fix or live capability execution occurred.
