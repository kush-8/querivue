# SQL Specialist design

Approved design, 14 November 2026, including all four final research audit clarifications.

[Overall architecture](overall.md) · [PRD](../PRD.md) · [Decision log](../memory.md)

## Review status

The high-level review plan and the existing responsibility, input boundary, five state fields, four tools, output variants, completion rules, typed boundaries, and tabular handoff are approved.

The original review packages and all four final research audit clarifications were approved through the design pop-ups. The independent builder review was completed, and its publication, credential-handling, and progress-accounting findings are addressed below.

| Review | Scope | Status |
| --- | --- | --- |
| Execution | Persistent runner and file mailboxes | Approved 14 November 2026 |
| Execution | Local SQLite ledger, per-operation identity, publication fencing | Approved 14 November 2026 |
| Execution | Recoverable failure when an old session cannot be retired | Approved 14 November 2026 |
| Data contract | Concrete nested constraints, scalar encodings, catalog profiles and column mappings | Approved 14 November 2026 |
| Safety | Pinned SQLGlot, positive query policy, trusted export | Approved 14 November 2026 |
| Execution | SQL no-progress accounting | Approved 14 November 2026 |
| Evaluation | Acceptance matrix and detailed trace boundary | Approved 14 November 2026 |
| Final audit | Invocation/runner identity, transactional authority, progress envelope and data semantics | Approved 14 November 2026 |

This is a component design. It does not authorize implementation.

## Purpose and boundary

A SQL action answers one delegated analytical objective using authorized prepared tables and prior evidence. It may inspect schemas, run diagnostic queries, generate and correct SQL, and return verified tabular evidence or a structured issue. A new analytical objective returns to the supervisor.

The worker owns the specialist graph and OpenRouter calls. Trusted execution runs SQL inside the run sandbox. The parent node validates the specialist output and resolves selected evidence into actual bounded tables for the supervisor. Python receives complete authorized Parquet artifacts through their references.

Each uploaded Dataset has an immutable DuckDB database. Ingestion, import confirmation, and Dataset publication are covered by [Data ingestion](data-ingestion.md). All selected tables must be ready before analysis. Removing a pinned source invalidates the run under the PRD.

## Approaches

The approved architecture uses one sandbox per active run, one subprocess and DuckDB connection per SQL action, and concurrent execution across independent actions.

For repeated queries in an action, a persistent runner preserves the connection. A process per query would require changing the approved lifecycle. The approved SDK file-mailbox protocol has durable request and response files and supports reconnect recovery. A stdin stream can reduce transfers but requires additional reconnection bookkeeping.

For standalone execution persistence, the approved SQLite ledger supplies transactions without a database service. Atomic files alone require implementing ownership and publication coordination. The later Django integration would implement the same runtime persistence operations through Postgres.

For SQL safety, the approved positive policy limits accepted query constructs, functions, and physical relations. It combines AST checks, DuckDB binding, and sandbox enforcement. Parser acceptance alone is insufficient.

## Request and resolved input

The SQLAction shape is approved. Concrete nested types below are approved contract refinements.

SQLAction inherits runtime-issued action_id and has type sql, objective, table_ids, constraints, and input_evidence_ids. ID lists are unique. At least one table or evidence input is required. Evidence-only analysis permits an empty table_ids list.

AnalysisConstraints fields:

| Field | Type and interpretation |
| --- | --- |
| metric_definitions | Map of metric name to confirmed definition text |
| filters | List of confirmed natural-language conditions, each required to hold |
| date_windows | List of typed bounds with inclusivity and a column reference |
| analysis_timezone | Confirmed timezone identifier or null |
| grain | Required entity or grouping grain as text, or null |
| units | Map of metric or column to confirmed unit text |

A date window references a table or evidence UUID and a validated column name. Bounds use TypedScalar and explicit lower_inclusive and upper_inclusive flags. Free-text constraints guide generation and analytical verification. They do not grant access.

The runtime supplies run_id, project_id, chat_id, task_id, attempt, original_question, and environment_version, together with resolved authorized tables, prior evidence, budget, and deadline. The original question supplies context. The delegated objective governs the work.

## Specialist state

The approved fields are:

| Field | Owner and contents |
| --- | --- |
| input | Runtime-validated immutable request and resolved context |
| messages | Action-local bounded model/tool messages |
| evidence_ids | Runtime-updated references to successfully published query results |
| execution_status | Runtime-owned counters, deadline, active execution and stop information |
| output | Empty until validated succeeded, blocked, or failed output |

Approved execution_status details include action attempt, execution generation, deadline, phase, active operation, model/tool/query/correction/retry/no-progress counters, and stopping reason. Numerical ceilings come from evaluated configuration. Counters survive recovery.

Tool request/response pairs are retained together. Evidence references survive message compaction. Context-window sizing and compaction policy belong to the memory design. The implementation must receive an explicit bounded policy before it is considered complete.

## Tool contracts

| Tool | Arguments | Successful response |
| --- | --- | --- |
| inspect_table | table_id UUID | Saved table metadata and profile |
| preview_rows | table_id UUID, columns list of SQL names or null, positive limit | Bounded tabular preview |
| inspect_evidence | evidence_id UUID | Evidence metadata, preview, and authorized SQL relation |
| execute_query | nonempty SQL, named TypedScalar parameter map | Published tabular evidence |

Every call validates shape, scope, source availability, deadline, and remaining budget. The runtime resolves paths and aliases.

inspect_table returns table and Dataset IDs, qualified SQL name, row count, original source location, columns and import warnings. Columns include ordinal, SQL name, original label, source position, DuckDB type, null count, and confirmed date, timezone, missing-marker and numeric-format settings.

The approved minimal additional profile includes saved date ranges and candidate keys. Candidate key basis is source_schema or verified_unique_non_null. A schema hint is not a guarantee of actual cardinality. Missing statistics are omitted or represented as empty collections. New statistics use execute_query.

preview_rows with columns null selects all columns subject to response caps. Empty, duplicate, or unknown explicit names produce invalid_arguments. Runtime caps the requested limit and reports the effective value. Filtering and sorting use execute_query.

Approved previews return separate column definitions and row arrays, full row count, returned row count, effective limit, ordering and truncation metadata. Approved display encoding uses strings for every non-null cell and JSON null for SQL NULL, interpreted using column types. Dates are ISO-formatted. Large integers and decimals retain precision. Mark shortened cells by row and column ordinal. Ordering is unspecified or query_defined. Ties require explicit tie-breakers when relevant to the objective.

Approved duplicate-column handling preserves original labels and ordinals and creates unique artifact column names. Reserve existing unique names before generating deterministic suffixes. Return the mapping to the supervisor and Python.

## Typed values and shared errors

Approved parameter kinds are null, boolean, int64, uint64, decimal, float64, string, date, time, timestamp, and timestamptz.

Integer and decimal values use validated decimal strings. Decimal includes precision and scale, bounded by the supported DECIMAL precision of 38. float64 accepts finite values. Temporal parameters use ISO representations and initially support microsecond precision. Timestamptz requires an explicit offset. Decode to trusted explicit typed bindings that enforce the declared SQL type; reject unsupported precision or ranges and verify type-sensitive behavior. Python value inference alone does not satisfy the contract. Parameters supply values. Relation and column identifiers undergo separate authorization.

Require exact named parameter coverage and reject names that collide case-insensitively.

Approved ToolError fields are code, bounded sanitized message, stage, operation_id when known, and disposition. Stages are validation, execution, persistence, or recovery. Disposition is correct_query, retry_operation, clarify, replan, fail_action, or invalidate_run, assigned by runtime policy.

Initial codes cover invalid_arguments, sql_parse_error, unknown_relation, unknown_column, type_mismatch, policy_violation, sql_unsupported, source_unavailable, artifact_unavailable, artifact_integrity_failure, query_timeout, result_limit_exceeded, unsupported_result_type, infrastructure_unavailable, budget_exhausted, no_progress, invalid_specialist_output, and internal_error.

Detailed SQL locations may be included when safe. Exclude credentials from every execution record and trace. Retain source-bearing details only in authorized local records subject to source-deletion rules. Sanitize host paths from model-facing errors. A failed specialist output references a genuine tool/runtime error. Orchestration can create runtime terminal errors when the model cannot return output.

## SQL validation policy

Approved SQLPolicy is checked in, versioned, and pinned with SQLGlot, DuckDB, Arrow and the template. Record versions with evidence.

1. Validate argument sizes, source references, available budget and deadline.
2. Parse all statements with the DuckDB dialect. Require exactly one nonempty supported analytical statement.
3. Accept SELECT, nonrecursive CTEs, nested and correlated subqueries, joins, grouping, windows, ordering and analytical set operations. Validate nested nodes and reject unsupported constructs.
4. Resolve CTE and derived-table scope before authorizing each physical relation against the runtime manifest. Physical sources use qualified names supplied by the runtime.
5. Apply an exact positive function/operator policy, including supported spelling aliases. Reject model-invoked table functions, filesystem readers, scanners, generators, dynamic SQL, system catalogs, user macros/UDFs, random/time-dependent functions, and unknown functions.
6. Bind parameter values separately, then allow DuckDB binding and execution.

The approved initial analytical function set covers COUNT, SUM, AVG, MIN, MAX, MEDIAN, standard deviations and variances; CASE, COALESCE, NULLIF, GREATEST and LEAST; basic arithmetic, ABS, ROUND, FLOOR, CEIL, SQRT, POWER, LN and LOG10; common case/trim/length/substring/replace/concatenation/string predicates; DATE_TRUNC, DATE_PART/EXTRACT, DATE_DIFF, STRFTIME, STRPTIME, TRY_STRPTIME, LAST_DAY and timezone conversion; ranking, LAG/LEAD, FIRST_VALUE/LAST_VALUE, NTILE and permitted aggregate windows; CAST/TRY_CAST and ordinary comparison, Boolean, membership and null predicates.

The implementation policy must enumerate exact canonical entries and supported types. Function categories do not permit unknown functions. Initial recursive CTE support is excluded. Rejections return structured feedback and require reviewed policy changes to widen support.

## Connection, runner and artifact protocol

Persistent action runners, SDK file mailboxes, the standalone SQLite ledger, and runtime generation fencing are approved.

The trusted runner opens its connection, attaches authorized immutable databases read-only, provisions approved preinstalled extensions, registers authorized evidence relations, sets the session timezone to the confirmed analysis timezone or UTC when unspecified, configures limits, restricts external access to required staged paths, and locks configuration before accepting generated SQL.

Generated SQL cannot attach sources, write files, load extensions or change settings. Runtime-created evidence relations can expose verified Parquet files from the preconfigured action artifact area. The locked registration and export order must pass the verification suite. An unspecified timezone still returns blocked when it could materially change the requested answer.

Fetch results as Arrow batches and write Parquet through trusted code to a runtime-chosen path. Count rows during materialization. Close and validate the file, schema, count, size and checksum before publication. A partial file cannot become evidence.

Initial result types include null, Boolean, verified lossless integers, floats, DECIMAL through precision 38, strings and supported temporal types. Verify wide aggregate results such as HUGEINT explicitly. Unsupported or non-lossless exports return unsupported_result_type so the specialist can cast or project explicitly. Nested, binary, interval, custom and extension types remain outside the initial verified matrix.

Persist a stable tool-invocation key before dispatch and map it to one operation_id within the logical action and attempt. Replay reuses that operation; a deliberate new invocation, including identical SQL, uses a new key. Reject changed payloads under an existing key. Persist the request digest, identities and budget reservation before dispatch. Duplicate delivery reuses a completed operation response. Bind mailbox manifests to a physical runner nonce, sandbox ID and PID, distinct from publication-owner generation; publish complete mailbox requests atomically.

The runner writes per-operation completion manifests after outputs are complete. The trusted worker validates and publishes each operation's evidence to durable storage outside the sandbox before returning the tool response, updates specialist state and checkpoints it. Publication is conditional on the current owner generation, expected attempt, valid run status, and current source availability. Keep source tombstones, run invalidation, current ownership/attempt and evidence metadata in one transactional authority: standalone SQLite, moved together to Postgres at integration. Transfer immutable candidate artifacts first, then commit this guard with evidence metadata so concurrent source deletion cannot publish or revive invalid evidence. Unpublished files become cleanup candidates; recovery adoption and artifact access also recheck validity. Graph recovery rechecks these conditions before restoring any references. The worker-side model produces the final analytical output. Trusted orchestration records the validated action completion and merges it into parent outcomes.

## Recovery and retries

The agreed identity policy retains action_id across deliberate retries and increments attempt after completed failure. Same-attempt crash replay uses the approved runtime execution generation to prevent competing publication.

Recovery checks durable publication first, then manifests, then identifiable live commands. Reconstruct missing graph updates from published results and reconnect to running work. Replace a lost runner and connection only as recovery of unresolved work under the same logical attempt. Preserve successful operation and sibling-action evidence.

Approved conservative unreachable-session handling fences old publication, requests retirement, and returns recoverable infrastructure failure until retirement can be reconciled. This selects retire-before-replay over immediate competing execution. A durable unresolved-retirement barrier survives failed output and later attempts, blocking replacement execution until retirement is reconciled. Retire the action process tree when possible; shared-sandbox retirement coordinates unresolved sibling recovery and preserves durable evidence. A new owner may reconnect to the same physical runner incarnation.

Counters, reservations and active deadline survive recovery. Duplicate logical operations are counted once. Actual repeated execution still contributes to resource and billing records. SDK, graph and action retries share the configured bounded policy.

Syntax, column and type feedback may be corrected within the action. Infrastructure failures can retry the operation. Resource failures may motivate a cheaper equivalent query. Changed analytical meaning returns to the supervisor. Missing definitions/prerequisites return blocked. Source removal invalidates the run.

### Approved SQL progress accounting

Count an action-local round after a model decision and its tool responses. Reset no-progress only when the round yields usable new evidence for the objective, resolves a relevant uncertainty, or completes the deliverable. A fresh evidence UUID, repeated inspection, cosmetic SQL change, or duplicate/replayed response is insufficient by itself. The specialist identifies the concrete progress and its evidence; runtime checks referenced operations and duplicate request digests, maintains the counter, and preserves it across recovery. Failed corrections without new usable information count as no progress. Each model decision uses a structured envelope containing either one of the four tool requests or final output, with an optional progress report for the preceding completed round. The report identifies that round and supporting evidence/tool responses. Runtime applies each round update once; missing, invalid, duplicate or unsupported reports cannot reset the counter. The first decision has no preceding tool round. This adds no extra model call or fifth tool. The numerical threshold remains an evaluation choice.

On recovery, the current owner may adopt an earlier completed artifact only after revalidating identity, request digest, integrity, source availability and the active execution generation. An obsolete worker cannot publish directly. Publish finalized artifacts immutably and clean up abandoned partial files only after their operation is inactive.

## Output and supervisor handoff

The approved model output variants are:

- succeeded with observation, a nonempty list of supporting evidence IDs, and limitations.
- blocked with explanation, required_input, and retained evidence IDs.
- failed with a structured error and retained evidence IDs.

Every variant terminates this specialist invocation. Partial evidence is retained. Success requires the complete delegated calculation and the agreed grain, joins, filters, null, denominator, unit and temporal checks.

Runtime validates IDs against authorized input and published action evidence and supplies identity/provenance. The enriched parent outcome carries task/action identity, attempt, terminal status, and actual selected tabular evidence. It is stored at outcomes[action_id] using expected-attempt and generation checks.

Each evidence object supplies an evidence UUID, operation/producer identity, producer-specific provenance, direct and transitive source dependencies, environment/policy versions, opaque artifact metadata, exact row count/schema, bounded preview, and authorized relation binding. SQL provenance contains executed SQL and typed parameters; Python-produced tables retain their own execution provenance. Any authorized compatible tabular evidence may be used, subject to the same scope, lineage and integrity checks. Artifact metadata includes UUID, Parquet media type, byte size and SHA-256 checksum.

The supervisor receives real bounded rows plus full-result references. Python loads complete authorized tables through those references. Drafting uses relevant evidence. Unseen rows require additional computation rather than extrapolation from a preview.

## Acceptance and evaluation

The following acceptance matrix is approved.

| Area | Required scenarios |
| --- | --- |
| Numerical correctness | Counts, aggregates, exact decimals/large integers, NULL/empty strings, zero denominators, zero rows |
| Analytical meaning | One-to-many/many-to-many joins, duplicates, grain, filters, units, date boundaries/timezones, windows |
| Scope and syntax | Nested CTEs, CTE shadowing, qualified/quoted names, correlated queries, cross-Dataset and prior-evidence relations |
| Rejections | Stacked statements, external/file readers, dynamic SQL, unauthorized/catalog relations, unknown functions, settings/extensions, parameter injection |
| Result fidelity | Duplicate labels, unsupported types, invalid schema, oversized artifact, shortened previews with explicit metadata |
| Recovery | Query correction, transient retry, duplicate/stale completion, same-attempt replay, disconnect/reconnect, invalid checksums, source deletion, retained sibling evidence |
| Handoff | Output validation, supervisor actual rows, downstream Python full-table loading |

Compare result row multisets unless ordering is requested. Use explicit ordering and tie-breakers for ranking requirements. Safety and recovery invariants are pass/fail gates. Measure objective completion, result correctness, unnecessary tool/query calls, correction rate, latency, token/cache use, and cost per successful action.

Keep development and held-out fixtures separate. Choose models, budgets, thresholds, preview caps and numerical limits through evaluation. Forecast full-suite model and sandbox cost, then compare with actual billing.

## Observability

Approved hosted spans contain correlated run/task/action/operation IDs, attempt and generation, tool names, safe error/policy codes, timings, counters, configuration versions, tokens/cache use, billed costs and artifact hashes.

Retain detailed SQL, parameter values, rows, tool/model messages and source-bearing errors in authorized local execution records. Send scores and sanitized metadata to LangSmith. Enforce redaction of automatic tracing as well as explicit spans.

## Verification gates and deferred work

Before implementation is accepted, verify AST/DuckDB agreement, parameter and result precision, locked attachment/evidence/export behavior, no outbound data exchange, read-only inputs, action write boundaries, process-tree termination, shared-resource exhaustion, path handling, mailbox recovery, and provider acceptance of structured outputs.

Exact prompt wording belongs to the final prompt-design round. Exact models and numerical values belong to evaluation. Message compaction belongs to memory design. Backend job delivery, Postgres persistence, Redis checkpoints and frontend transport belong to their agreed development phases, with the contracts above required at integration.

Live DuckDB, Arrow, parser and E2B enforcement checks have not run.

## Final research audit

14 November 2026. Three fresh reviewers audited library assumptions, execution recovery, and contracts independently. The base architecture and all four clarifications below are approved through the final pop-up responses. Their requirements are incorporated in the contracts above; this section retains the audit rationale and verification coverage.

### Approved recovery identity clarification

Persist a tool-invocation key before dispatch and map it uniquely to the logical action, attempt and operation. Replay of that key reuses its operation. A deliberate new call can use the same SQL digest with a new key. Reject a different payload under an existing key.

Separate physical runner incarnation from publication-owner generation. Record a runner nonce with sandbox ID and PID and bind mailbox manifests to the incarnation and logical operation. Publish complete request files atomically. Changing the worker owner may reconnect to the same physical runner.

An unresolved-retirement barrier survives terminal failure and attempt changes. It blocks replacement execution until retirement is reconciled. Terminate the affected action process tree where possible. If the entire shared sandbox must be retired, coordinate recovery of its sibling actions and retain their durable evidence.

### Approved transactional authority clarification

Keep source tombstones, run invalidation, execution ownership/attempt state, and evidence publication metadata under one transactional persistence authority. Standalone execution uses SQLite. The integrated application moves the authority together into Postgres.

Persist immutable candidate bytes before conditional metadata publication. The transaction serializes source deletion against the current run, expected attempt and owner generation. Failed publication leaves unpublished cleanup candidates. Recovery adoption and artifact access recheck validity so deletion cannot revive dependent evidence.

### Approved progress transport clarification

Use a structured specialist decision envelope with either a request for one of the four tools or final output, plus an optional progress report about the preceding completed round. The report contains the round identity, supporting evidence or recorded tool-response references, and a concise explanation of substantive progress.

Apply each completed round's progress update once through runtime bookkeeping. Missing, invalid, duplicate or unsupported claims cannot reset no-progress. The first decision has no preceding tool round. The same model call requests the next step, with no extra progress-only model invocation. Numerical thresholds remain evaluation choices.

### Approved data semantics clarification

Set DuckDB's session timezone to the confirmed analysis timezone before locking configuration. Use UTC when unspecified, and retain the agreed blocked behavior when a missing analytical timezone materially changes the answer.

TypedScalar declares the intended SQL binding type. Trusted conversion uses explicit typed bindings, validates range/precision, and verifies type-sensitive behavior, rather than relying solely on Python value inference.

Authorize compatible tabular artifacts from SQL or future Python producers. Producer-specific provenance records SQL and parameters only for SQL-origin evidence. Other producers retain their own execution provenance. Preserve transitive source dependencies and the existing scope and integrity checks.

### Audit-confirmed verification coverage

Add these explicit cases to the already approved acceptance and verification matrix:

- Instructions embedded in cells retain data semantics and cannot widen permissions or become tool instructions.
- Cosmetic queries, duplicate/replayed tool responses and fresh evidence UUIDs alone do not reset no-progress. Relevant empty results can establish progress.
- Automatic hosted tracing excludes source rows, SQL/parameters and model/tool message contents. Sentinel tests also verify credential exclusion from every record.
- A tool operation published before a checkpoint is reused after replay, while an intentional identical new invocation remains distinct.
- Source deletion races candidate materialization, metadata publication, recovery adoption and artifact access.
- A retired shared sandbox triggers coordinated recovery of unresolved siblings.
- Typed bindings are checked with type-sensitive queries. Test DuckDB-to-Arrow-to-Parquet-to-authorized-reader values and types, including boundary integers, decimal scale, temporal precision and timezone binning.
- Newly produced evidence can be registered and queried after connection lockdown while arbitrary external paths remain inaccessible.
- Explicitly configure the action runner's command lifetime and the sandbox lifetime from their deadlines. E2B command-run timeout can terminate the process, while reconnect timeout limits client waiting. Persist completion output in files rather than relying on replay of streamed stdout.

Library documentation supports the overall structure. Read-only attachment is documented, and SQLGlot's scope model supports physical-source validation. Documentation cannot establish the complete locked-down runner sequence or process-tree termination. Those remain required executable verification gates.

## Sources

- [DuckDB Python DB API](https://duckdb.org/docs/2.0/clients/python/dbapi)
- [DuckDB security](https://duckdb.org/docs/2.0/operations_manual/securing_duckdb/overview)
- [DuckDB ordering](https://duckdb.org/docs/2.0/sql/dialect/order_preservation)
- [DuckDB Parquet](https://duckdb.org/docs/2.0/data/parquet/overview)
- [SQLGlot API](https://sqlglot.com/sqlglot.html)
- [SQLGlot scope resolution](https://github.com/tobymao/sqlglot/blob/main/sqlglot/optimizer/scope.py)
- [PyArrow ParquetWriter](https://arrow.apache.org/docs/python/generated/pyarrow.parquet.ParquetWriter.html)
- [E2B background commands](https://docs.e2b.dev/commands/background)
- [LangGraph fault tolerance](https://docs.langchain.com/oss/python/langgraph/fault-tolerance)
- [Pydantic discriminated unions](https://pydantic.dev/docs/validation/latest/concepts/unions/)

- [DuckDB timestamp semantics](https://duckdb.org/docs/2.0/sql/data_types/timestamp)
- [DuckDB Python value conversion](https://duckdb.org/docs/2.0/clients/python/conversion)

## Architecture summary

- One delegated objective includes inspection, diagnostics, query execution and correction within runtime budgets.
- State fields are input, messages, evidence_ids, execution_status, and output.
- Tools are inspect_table, preview_rows, inspect_evidence, and execute_query.
- Typed outputs are succeeded, blocked, and failed. The parent resolves evidence into actual bounded tables and full artifact references for supervisor and Python handoffs.
- Persistent action runners reuse a DuckDB connection through SDK file mailboxes. Standalone execution uses a SQLite ledger with operation identities and publication fencing, followed by a Postgres-backed integration.
- Query safety uses a versioned positive SQLGlot/function/relation policy, typed parameters, trusted Parquet export, and independent sandbox enforcement.
- Publication and recovery revalidate ownership, expected attempt, source availability and artifact integrity.
- Final audit approvals require stable invocation keys, separate runner incarnations, durable retirement barriers and atomic mailboxes. Source tombstones, run ownership and evidence publication share one transactional authority. SQL decisions carry runtime-validated progress reports; connections use deterministic timezone settings and explicit typed bindings. Authorized tabular evidence uses producer-specific provenance.
- Acceptance covers analytical correctness, safety, recovery and tabular handoff. Detailed data remains in authorized local records, with redacted hosted traces and credentials excluded from all records.

Models, prompts, numerical limits and memory compaction retain their agreed later design/evaluation owners. Pinned-library and E2B enforcement must pass the design's verification gates before implementation is accepted.
