# Python Specialist design

15 November 2026. **Rounds 1–7 approved; Python Specialist design review closed with explicit gates.** The design has explicit context/configuration dependencies and unrun runtime gates; it is not implementation-ready. No code, paid runs or live verification have been performed.

[Overall architecture](overall.md) · [Review plan](python-specialist-plan.md) · [SQL Specialist](sql-specialist.md) · [Supervisor](supervisor.md)

## Existing decisions

The supervisor owns routing and delegation. SQL handles simple counts and comparisons; Python is used when computation or visualization needs it. Specialists return findings to the supervisor. Fresh answers go through the Answer Specialist and Reviewer, with at most two review passes. A failed requested chart must preserve supported findings for a visibly partial answer where possible.

Authorized tabular evidence already has a shared handoff: complete typed Parquet, exact schema and row count, bounded previews, original/artifact column mappings, integrity metadata, producer provenance, and direct/transitive source dependencies. The approved SQL design supports compatible evidence from SQL and future Python producers. Round 1 separately approved evidence artifacts as Python's exclusive initial data inputs.

Run scope, source invalidation, read-only inputs, no outbound internet, worker-side OpenRouter calls, per-action execution contexts and persistent reusable outputs remain existing requirements. Their enforcement in the eventual Python runtime is not verified.

## Round 1: responsibility and input access

### Approved responsibility

Python completes one focused calculation or visualization delegated by the supervisor, using explicitly authorized inputs. It returns computed evidence, requested artifacts, analytical limitations, and unmet prerequisites to the supervisor.

SQL remains the normal route for source selection, filtering, ordinary joins, grouping, counts and comparisons. Python handles chart creation and calculations whose procedure needs the approved Python environment. Calculations necessary to the delegated algorithm or plot may happen in Python; this routing rule does not prohibit checking its input shape or computing plotted values. It does not add a general forecasting or machine-learning feature.

Python uses the supplied metric definitions, population, filters, grain, units, date windows and timezone. If a missing assumption could materially change the answer, it returns the issue to the supervisor for clarification. If a required column, row population or relational preparation is missing, it returns that prerequisite so the supervisor can arrange another SQL action. It cannot silently broaden the objective, fetch more sources, or delegate to another specialist itself.

Results must remain inspectable independently of a chart. Newly calculated quantities require saved numerical evidence; a picture or stdout alone is insufficient. A chart that displays existing evidence unchanged may reference that evidence. If rendering fails after a calculation succeeds, preserve the published calculation and identify the missing chart for the supervisor's answer/review flow. Exact artifact and terminal-output representations belong to round 4.

### Input alternatives

These tradeoffs are architecture analysis, not requirements imposed by a library.

| Alternative | Access | Benefit and cost |
| --- | --- | --- |
| A. Authorized evidence artifacts only — approved initially | Explicitly delegated compatible evidence from SQL or earlier Python work. No original upload or prepared Dataset database access. | Reuses the approved handoff and its provenance. Missing rows require an upstream SQL extraction, adding execution/model latency, storage and a dependency. Export/type/resource limits also constrain inputs. |
| B. Evidence plus trusted prepared-table loading | Explicit table IDs resolved by trusted runtime into scoped inputs, alongside evidence references. Generated Python does not receive the whole multi-table Dataset file. | Avoids a SQL specialist call solely for row selection. Adds an input-resolution/extraction contract, validation, provenance and recovery work; serialization and limits still apply. |
| C. Direct read-only prepared database access | Generated Python receives authorized DuckDB database files or connections. | Can avoid intermediate extraction, but a file can contain several tables. File-level access is broader than a delegated table set and creates another relational execution boundary to govern. |

**Approved choice A:** start with evidence artifacts only. An artifact may contain all required unaggregated rows and columns, not merely a summary. Use existing valid evidence when available. Otherwise the supervisor obtains a complete required extraction through SQL before dispatching Python. Do not silently sample, truncate, aggregate away required rows, cast lossy values or bypass a reported export/resource limit. Report a prerequisite or limit that prevents the delegated calculation.

Arrow documents reading all Parquet row groups and optional column selection/batched reads. This supports full row-level artifacts; it does not prove lossless conversion for every data type or algorithm. [Arrow single-file Parquet](https://arrow.apache.org/docs/python/parquet/parquet.html), [read_table API](https://arrow.apache.org/docs/python/generated/pyarrow.parquet.read_table.html).

DuckDB documents read-only connections. Its security guidance separately requires sandboxing untrusted execution; read-only mode is not an execution sandbox. The wider table exposure in alternative C follows from Querivue storing multiple tables in one Dataset file. [DuckDB Python DB API](https://duckdb.org/docs/2.0/clients/python/dbapi), [DuckDB security](https://duckdb.org/docs/2.0/operations_manual/securing_duckdb/overview).

Measure the extra preparation calls, latency, cost and export-limit failures. Reconsider alternative B if that measured overhead materially harms the agreed workflow. Alternatives B and C are not approved fallbacks.

### Concrete routing examples under the approved boundary

| Request or condition | Behavior |
| --- | --- |
| Plot monthly revenue; valid monthly totals already exist | Python plots the complete result artifact; no repeat SQL calculation is needed. |
| Plot a distribution requiring individual transaction values | SQL supplies all required eligible values without aggregation or sampling; Python performs the visualization. |
| Perform an agreed statistical calculation requiring one row per subject | SQL supplies complete subject-level inputs; Python executes the delegated method and saves the computed evidence. Missing method/population assumptions return to the supervisor. |
| Join customers and orders, then visualize the result | SQL prepares the join and verifies its grain/cardinality; Python receives the relevant complete artifact. Algorithms needing separate input tables may receive multiple authorized artifacts. |
| Input is only an aggregate and the algorithm needs individual rows | Return the missing-input requirement; do not infer the distribution from a preview or aggregate. |
| Calculation succeeds but chart creation fails | Preserve published numerical evidence and return the missing deliverable; the existing supervisor/answer/reviewer flow handles the partial answer. |

### Round 1 approval scope

The user approved the focused calculation/visualization responsibility, the routing and return-to-supervisor rules, artifact-only initial input access, and independently inspectable numerical evidence behind charts. That approval does not select a library, chart format, tool count, state schema, interpreter protocol, sandbox enforcement mechanism or numerical ceiling.

## Round 2: approved request, context and state

### Python action request

Reuse the shared Action identity and the SQL request conventions, with no `table_ids` or file-path selectors. Approved fields:

| Field | Type and meaning |
| --- | --- |
| `action_id` | Runtime-issued UUID from the shared Action model. |
| `type` | Literal `python`. |
| `objective` | Nonempty focused analytical objective, including mandatory deliverables and relevant input-column meaning. The original user question remains separate context. |
| `input_evidence_ids` | Nonempty unique list of compatible tabular evidence UUIDs explicitly delegated to this action. |
| `constraints` | The existing shared `AnalysisConstraints`: metric definitions, filters, typed date windows, analysis timezone, grain and units. |
| `required_outputs` | Nonempty unique list containing `evidence`, `chart`, or both. These declare minimum deliverable kinds, not their complete schemas. |

`required_outputs=["evidence"]` requires a newly computed, published numerical result supporting the objective. `required_outputs=["chart"]` requires a published chart and valid numerical backing; unchanged backing evidence may be an input rather than a new calculation. If creating the chart needs new calculated values, those values still need independently inspectable saved evidence under round 1. Request both kinds when the objective requires a computed result and a chart. Detailed chart counts, representations and terminal fulfillment checks belong to round 4; merely having one artifact of each requested kind does not establish analytical completion.

This list is local to a Python action. It does not add the separate supervisor-level `requested_outcomes` field previously rejected. An objective-only request is shorter but leaves a missing required chart entirely dependent on prose interpretation. A detailed deliverables object would prematurely choose chart/output schemas. The user approved the two-kind list as the minimum between them.

Illustrative request; UUIDs are examples, not existing project records:

```json
{
  "action_id": "ad9010dd-046f-47e3-8dd5-adce1748588b",
  "type": "python",
  "objective": "Plot the supplied monthly revenue totals in month order using month and revenue. The input producer's SQL supplies the cancelled-order exclusion; inspect that basis rather than trying to filter absent order-status rows.",
  "input_evidence_ids": ["a8268056-b1f4-416a-9f22-a9d02aa6bac8"],
  "constraints": {
    "metric_definitions": {"revenue": "Confirmed paid-order revenue definition"},
    "filters": ["Exclude cancelled orders"],
    "date_windows": [],
    "analysis_timezone": "Asia/Kolkata",
    "grain": "calendar month",
    "units": {"revenue": "INR"}
  },
  "required_outputs": ["chart"]
}
```

### Runtime-resolved context and access

The runtime supplies `run_id`, `project_id`, `chat_id`, `task_id`, the original question, and environment/policy versions. Current expected attempt, execution generation, deadline, remaining budget and active-operation status are runtime-owned operational context, reflected in `execution_status`. The model cannot choose or change them. The immutable action objective controls the delegated work; the original question supplies relevant context rather than permission to expand the task.

For every input evidence ID, resolve its published compatible tabular evidence and complete artifact reference, exact schema/count, original/artifact column mappings, bounded preview, checksum/size/media type, producer provenance and direct/transitive source dependencies. Reuse the shared evidence contract. Resolve only the delegated inputs, not all evidence or all Datasets eligible for the run. An existing UUID alone is not authorization.

Check run/project authorization, pinned Dataset scope, valid publication, source availability, compatible types and artifact integrity before materializing an input. Repeat current-validity checks when loading or resuming; a cached manifest or checkpoint does not revive a removed source. Report failed validation before generated code can consume that input. Source IDs or names appearing in provenance/constraints are context and invalidation dependencies, not additional data capabilities.

Model context uses opaque evidence/artifact identities and relevant metadata. Host/provider storage paths, transfer URLs and credentials remain runtime-owned. Round 3 will decide how execution receives action-local inputs; any local path is an ephemeral execution binding, not a durable artifact identity or extra authority. No raw upload or prepared Dataset database is supplied.

### Source constraints versus remaining artifact work

Keep `AnalysisConstraints` unchanged. Preserve confirmed source semantics even when an upstream projection or aggregation removed the original columns. A Q2 monthly-total artifact can legitimately lack transaction-date and order-status columns.

The supervisor records relevant upstream preparation and the remaining work in the focused objective, referring to the delegated evidence. The runtime provides the actual saved producer SQL/parameters or other producer provenance and column mappings. Do not add a separate preparation-summary model or an `already_verified` flag in this round: an explanation is not proof. Python checks whether the supplied basis supports its objective. Runtime validation checks identities, scope and mappings; it does not establish that a filter, denominator or analytical interpretation is correct merely because a query ran or the lineage is valid.

Original source-column references may remain as contextual constraints when they resolve to saved source metadata in the delegated evidence's verified lineage. They never authorize source reads. References used to operate on an artifact must resolve unambiguously to that artifact's actual schema. Do not reject a legitimate upstream-only source reference just because the source column was aggregated away, and do not silently apply it again to a different column such as a month label. Missing support, conflicting constraints, insufficient grain or a genuinely missing operation input returns to the supervisor for preparation or clarification.

### Specialist state and ownership

Extend the SQL state pattern with a separate published-chart collection:

| State field | Owner and contents |
| --- | --- |
| `input` | Runtime-validated immutable request, logical run context and resolved input-evidence metadata. Full artifact bytes live outside graph state. |
| `messages` | Bounded action-local model/tool history; request/response pairs stay together. Historical messages are not authority for artifact validity or runtime counters. |
| `evidence_ids` | Runtime-updated unique references to successfully published numerical/tabular outputs produced by this action. Input evidence stays in `input`. |
| `chart_artifact_ids` | Runtime-updated unique references to successfully published charts produced by this action. Chart format and metadata schema remain round 4 decisions. |
| `execution_status` | Runtime-owned phase, expected attempt, current generation, active deadline/budget, active operation, applicable model/tool/execution/correction/retry/no-progress counters and stop information. Exact operation/replay mechanics and ceilings retain their later owners. |
| `output` | Empty until the runtime validates a terminal specialist return. Exact variants, errors and partial-result representation belong to rounds 4/5. |

A generic `published_outputs` union would save one collection but introduce a new tagged-reference contract before chart outputs are designed. Keeping `evidence_ids` and adding `chart_artifact_ids` preserves the approved tabular convention with one explicit extension.

The runtime updates output-reference lists only after trusted publication. A model-mentioned UUID is not a published output. Corrections, message compaction and checkpoint recovery preserve valid published references, including calculations saved before a later chart failure. Neither list by itself establishes completion. Check source validity, integrity and expected-attempt/publication ownership before restoring or returning references, under the later lifecycle contract.

Checkpoint state contains no live dataframe, figure, interpreter, module, database connection or process object. Unsaved variables and files are not recoverable results. Executed code and source-bearing tool details may remain in authorized local records/messages under existing privacy rules; they are not exported to hosted traces. The broader context-window/compaction policy remains with memory design, with an explicit bounded policy required before implementation is accepted.

### Round 2 acceptance scenarios

- Reject wrong discriminator, malformed IDs, empty objective/input lists, duplicate IDs, invalid output kinds, malformed shared constraints and unexpected fields such as a table/path selector. Exact numerical payload caps remain evaluated configuration.
- Reject unauthorized, unpublished, corrupt, incompatible, source-invalidated or unavailable inputs before loading; metadata and UUIDs cannot widen action access.
- A valid upstream-filtered aggregate remains usable when its original source columns are absent. Missing analytical support is reported rather than treated as proven by lineage. A missing column required for new Python work returns to the supervisor.
- A chart-only request can reuse valid input evidence. New numerical values require saved evidence. A request for both numerical evidence and a chart retains both obligations if rendering fails; exact terminal reporting follows round 4.
- Runtime identity, attempt/generation, deadline, counters and published-reference collections cannot be overwritten by model output. Output/reference restoration respects current publication and source validity.
- Valid published calculation/chart references survive correction and compaction without restoring live interpreter objects or relying on stale sandbox paths.

### Round 2 approval scope

The user approved the six request fields and their validation, runtime-resolved authorized context, source-constraint interpretation rules, and six state fields with their ownership. Tool APIs, package/rendering choices, code isolation, detailed artifact/output schemas, operation recovery and numerical limits remain for their scheduled rounds.

## Round 3A: approved tools and code-call lifetime

The user approved 3A's model-facing tools and execution unit. Round 3B settles the concrete OS isolation/launch profile and provider feasibility gates. Approval of 3A does not authorize executing Python with an unenforced boundary.

### Two model-facing tools

| Tool | Approved common arguments | Runtime response |
| --- | --- | --- |
| `inspect_evidence` | `evidence_id` UUID | Shared evidence metadata, exact schema/count, column mappings, producer provenance, bounded preview and complete artifact reference. |
| `execute_python` | Nonempty `code`, nonempty unique `input_evidence_ids`, and `outputs`, a list of declarations containing a logical `name` and `kind` (`evidence` or `chart`). | Runtime operation identity, execution outcome, bounded diagnostic output with truncation metadata, and successfully published evidence/chart references with their metadata. Failure returns a sanitized structured tool/runtime error; exact additional codes follow the lifecycle round. |

Both tools accept only the action's delegated input evidence or compatible evidence successfully published by that same action. `execute_python` narrows that set through its explicit per-call inputs; a chart artifact is not a tabular input. Other run evidence and sibling outputs require supervisor delegation, not filesystem discovery. Recheck scope, current source validity and deadline/budget on every call.

The runtime stages only the code call's selected complete inputs read-only. A read-only operation descriptor maps evidence IDs and declared output names to runtime-chosen action-local filenames, media types and relevant metadata. Generated code uses these files through the preinstalled libraries. There is no additional model-facing load, file-browser, shell, package-install or publish tool. Host storage paths, transfer URLs and credentials are absent from the descriptor. Descriptor paths are temporary bindings; they do not become checkpoint authority.

Output names are unique simple ASCII identifiers matching `[A-Za-z][A-Za-z0-9_]*`, not paths. The runtime chooses the output directory, extension and filenames under the eventual format policy. Reject path separators, traversal names, duplicate names, unknown kinds and unknown input IDs before launch. Type-specific chart/evidence metadata and backing references remain round 4 contracts; the two fields here are the common declaration shape, not the complete format schema.

### Fresh interpreter per code call

| Approach | Benefit | Cost |
| --- | --- | --- |
| Persistent stateful action interpreter | Reuses loaded objects and imports between calls. | Errors can leave partially mutated state; replay/recovery must reconstruct or discard variables and earlier effects. |
| Fresh script interpreter for each call — approved | Each call is complete given its declared artifacts and recorded code. Corrections start clean, and subsequent calls use durable results. | Repeats imports/input loading and writes intermediate artifacts instead of retaining dataframes. |

**Approved choice:** run each code call as a complete script in a fresh interpreter and fresh scratch/output area. One action owns its execution context and process tree; its calls are serial, while independent actions may still run concurrently through the supervisor. A trusted action controller outside generated-code privileges launches disposable interpreter children. Reusing a Python globals dictionary or clearing variables in a persistent process is not the promised fresh-interpreter behavior.

This approved refinement replaces the earlier shorthand of one subprocess/interpreter per Python action with one action-owned execution context/process tree and a disposable interpreter for each call. SQL's persistent per-action connection and runner are unchanged. The shared execution wording is updated to match.

Each script must load everything it needs from the declared input artifacts and its recorded code. It cannot rely on variables, imports, scratch files or local paths from an earlier call. Previously published numerical outputs can be selected as new inputs. Code corrections submit a complete corrected script within the same focused objective and budgets. Changed analytical meaning, missing preparation or consequential ambiguity returns to the supervisor. Operation identity, duplicate dispatch and recovery bookkeeping remain round 5 decisions.

### Separate numerical publication from chart rendering

All nonempty output declarations in one call must have the same kind. Numerical evidence and charts therefore use separate code calls. `outputs=[]` permits a bounded diagnostic call, but its stdout is not computed evidence and cannot fulfill a required numerical deliverable.

When a chart requires new calculated values, first run a numerical call and wait for its validated durable evidence references. Then run a chart call using those references. A chart displaying existing evidence unchanged can go directly to the chart call. This preserves independently supported calculations if later rendering fails.

Publish outputs only after successful script execution, confirmed termination of its descendant processes, and trusted validation of every declared output. If the script exits while descendants remain, terminate them and fail that call rather than publishing while writers may still be active. A nonzero exit, timeout, execution/resource limit, missing or invalid declared file, or unconfirmed process termination publishes no candidate output from that call. Earlier successfully published calls remain available. A publication infrastructure failure may require recovery; do not return candidate IDs as published successes. Detailed transactional recovery remains round 5.

Generated files, stdout, completion claims and manifests are untrusted. The worker/trusted controller uses its saved request and actual execution status, not a generated manifest as publication authority. Collect only declared regular files from the runtime-owned output area after writers are gone. Reject symlinks, hardlinks, redirected paths, undeclared output references, oversized or malformed files; compute/verify actual size, schema and checksum before durable publication. Isolate untrusted file decoding/validation too; generated code cannot access publication credentials or modify the controller's records. Exact validation/format contracts follow round 4 and the isolation mechanism follows 3B.

Record the code identity, explicit operation inputs and output declarations for provenance. The precise dependency/lineage rule for arbitrary Python, including conservative attribution when inputs are declared but not demonstrably read, belongs to round 4. Do not assume generated code can truthfully attest to a narrower source dependency set.

### Package and execution requirements

Use a pinned, read-only template environment with the approved preinstalled libraries; no model-selected package installation or external data download. Exact analytical/rendering libraries and versions remain to be selected and verified. Missing required support returns an explicit environment/prerequisite failure rather than silently installing or changing the analysis.

The trusted launcher passes code as a script and arguments as an argument vector, not a shell-composed command. It supplies a minimal environment and descriptors without credentials, bounds diagnostics before they can exhaust memory/disk, and keeps source-bearing code/output in authorized local records rather than hosted traces. Python's subprocess API permits explicit arguments/environment; its ordinary timeout describes killing the direct child, which does not establish our required descendant cleanup. [Python 3.12 subprocess](https://docs.python.org/3.12/library/subprocess.html).

Fresh interpreters, current directories, import settings and Python audit hooks are not the security boundary. Python explicitly warns that Python-level audit hooks are unsuitable for sandboxing. Round 3B must enforce the private input/filesystem view, sibling/process/controller separation, denied network, finite aggregate resource limits and full-tree termination. Refuse execution when the required profile cannot be established. [Python 3.12 audit hooks](https://docs.python.org/3.12/library/sys.html#sys.addaudithook).

### Round 3A acceptance and approval scope

An independent scoped consistency review found no approval-blocking contradictions with rounds 1–2 or the shared contracts. This was a design review, not a live enforcement test.

- The two tools reject out-of-scope/unpublished inputs, arbitrary path selectors, invalid output names and mixed evidence/chart declarations before launch.
- A second code call cannot read the first call's unsaved variables or scratch files. It can load a valid published result only through an explicitly selected reference.
- A successful numerical call followed by a failed chart call retains the numerical evidence. A failed numerical call publishes none of its candidates. Diagnostics cannot substitute for required evidence.
- Incomplete, missing, redirected or oversized outputs and a script leaving descendants alive cannot produce published success. Forged completion/provenance claims do not override trusted validation.
- Identity, source availability, active budgets and artifact validity remain runtime-owned. No code launches before the isolation profile and its required feasibility checks are satisfied.

The user approved the two tools and common arguments, per-call input staging, disposable-interpreter refinement, separate numerical/chart operations, failed-call publication rule, trusted collection boundary and package policy. The concrete isolation profile, type-specific output formats/schemas, detailed lifecycle/retry protocol and evaluated numerical ceilings remain for their scheduled reviews.

## Round 3B: approved target OS isolation profile

### Approach and approval boundary

Keep the approved one-E2B-sandbox-per-active-run architecture. Inside it, use a fresh bubblewrap boundary for each Python code call, controller-owned cgroup-v2 limits, and a small trusted exit supervisor. The worker remains the publication authority outside the sandbox; the guest controller never grants generated code publication credentials.

The user approved this target pending verification, not a claim that E2B supports or enforces every required primitive. A reviewed, pinned template must pass the gates below before execution is enabled. If it cannot, return an infrastructure failure and review a different architecture; never degrade to directory separation, ordinary subprocess timeouts or partial namespace setup.

| Alternative | Tradeoff |
| --- | --- |
| Shared run sandbox plus per-call OS boundary — approved target | Preserves existing staging and concurrency decisions. Requires a maintained launch policy, a small exit supervisor and proof that guest namespace/mount/cgroup facilities work. |
| Separate provider sandbox for each code call | Gives each call a separate guest and simplifies sibling visibility. Changes the approved run-sandbox lifecycle, adds staging/startup and concurrency costs, and still needs trustworthy completion, output validation and controller access rules. It is not an automatic fallback. |

Bubblewrap supplies isolation mechanisms whose effectiveness depends on launch policy; it is not a complete preconfigured policy. Pin a reviewed non-setuid build, source/package digest and template identity. The researched release candidate is 0.13.1; exact installed build identity and compatibility must be recorded before enablement. [Upstream security model](https://github.com/containers/bubblewrap), [release candidate](https://github.com/containers/bubblewrap/releases/tag/v0.13.1).

### Files, privileges and communication

The privileged guest controller prepares mounts/cgroups under a different guest UID from the unprivileged executor. It fixes every launcher argument; model data cannot supply flags. The call requires user, mount, PID, network, IPC and UTS namespaces, dropped payload capabilities, no-new-privileges, cleared supplementary groups/environment, and a separate payload session. Disable further user-namespace creation. Do not use namespace `-try` fallbacks or `--not-a-security-boundary`. Verify the actual namespace/PID arrangement instead of assuming it. [Bubblewrap options](https://github.com/containers/bubblewrap/blob/main/bwrap.xml).

Expose a minimal read-only runtime, required pinned libraries/fonts, the recorded script/operation descriptor and only that call's selected evidence. Do not expose the guest root, project/home/run staging trees, prepared databases, sibling work, controller records, guest control sockets or cgroup controls. Use PID-scoped `/proc` and minimal devices; never bind the guest's existing `/proc` or broad `/dev`. Namespace visibility must match the intended process boundary. [Linux PID namespaces](https://man7.org/linux/man-pages/man7/pid_namespaces.7.html).

Use a controller-mounted, fresh per-call tmpfs with finite byte and inode limits, bound into the call as its writable work area. Route output, scratch, temporary files, home/cache and required shared-memory files into that bounded area. Keep other mounts read-only. The controller retains the mount after child exit for collection, then removes it only after the lifecycle allows cleanup. A tmpfs existing solely inside bubblewrap would disappear with the namespace. Tmpfs uses memory and may use swap; account for it in memory admission rather than treating it as independent disk. [Kernel tmpfs](https://docs.kernel.org/filesystems/tmpfs.html).

Only deliberately assigned bounded data pipes reach generated code. Close setup, directory, namespace, socket, controller and status descriptors before the Python exec. The supervisor's private verdict descriptor never reaches the payload. An empty filesystem view does not revoke an inherited descriptor. [Bubblewrap descriptor/lifecycle implementation](https://raw.githubusercontent.com/containers/bubblewrap/v0.13.1/bubblewrap.c).

Keep run-level E2B internet disabled. The call's separate network namespace also excludes guest loopback/controller services; no guest sockets or traffic routes are inherited. Test IPv4/IPv6, loopback, Unix-socket and inherited-handle paths, not only a failed public HTTP request. E2B secured SDK access authenticates the guest controller, but does not itself establish per-action isolation. Tokens remain worker-owned. [E2B network controls](https://docs.e2b.dev/network/internet-access), [secured controller access](https://docs.e2b.dev/sandbox/secured-access).

### Syscall policy and protected exit supervision

Apply a checked-in, architecture-checked seccomp allowlist for the pinned runtime. It must cover alternate syscall ABIs and forbid namespace changes, mounts, cross-process introspection/memory/descriptor access, privileged kernel interfaces and mechanisms that bypass the reviewed restrictions. Permit required numerical threads and reviewed renderer subprocess/IPC behavior only. Filtering cannot inspect pointer-referenced syscall arguments; clone/clone3 handling must be explicitly tested rather than assumed equivalent. Changing this policy for a renderer requires review and regression checks, not an automatic relaxation. [Kernel seccomp](https://docs.kernel.org/userspace-api/seccomp_filter.html).

To preserve 3A's descendant-failure rule, make a trusted exit supervisor bubblewrap's initial program. It is a pinned read-only helper, not generated Python or an evaluator of its stdout. It registers as a child subreaper, keeps normal SIGCHLD handling, and launches the Python script with no inherited verdict/control handles. The helper does not import mutable payload modules or decode candidate outputs. It becomes non-dumpable before starting untrusted code. [Subreaper semantics](https://man7.org/linux/man-pages/man2/PR_SET_CHILD_SUBREAPER.2const.html), [non-dumpable process](https://man7.org/linux/man-pages/man2/PR_SET_DUMPABLE.2const.html).

The supervisor and payload may share the unprivileged executor UID inside the call namespace. This is an explicit seccomp-dependent choice, not a claim that non-dumpable prevents signals. The payload's additional inherited filter must prevent signals or process-control changes to the supervisor/init, including zero/negative/group signal targets, queued/thread signals, pidfd signaling and cross-process limit/scheduler changes. Reject unneeded asynchronous signal-delivery and kernel interfaces as well. Protect supervisor memory/FDs through the combined nondumpable, syscall and descriptor policy. A separately mapped supervisor/payload UID design would require additional mapping/transition support; it is not assumed available. [Linux signal permissions](https://man7.org/linux/man-pages/man2/kill.2.html).

Use this conservative completion algorithm: wait specifically for the main Python process; do not reap adopted descendants before deciding its completion. After the main process is reaped, any remaining child, live or zombie, fails the call. Only a zero main-process exit and the no-children condition (`ECHILD`) permit clean completion. Include all clone-child categories (`__WALL`), handle interruptions, and fail unexpected wait/setup errors. This intentionally also rejects unreaped orphan zombies; scripts must join/reap their subprocess work. Reaping descendants first and checking only those still alive could hide a child that outlived the main script briefly. [Linux wait semantics](https://man7.org/linux/man-pages/man2/waitpid.2.html).

The supervisor reports the actual main exit and its mandatory completion verdict through its protected control path. Missing, malformed, interrupted or abnormal supervisor completion is failure regardless of generated output. Bubblewrap cleanup follows that decision; the outer controller separately confirms the call cgroup is empty before collection. A zero bubblewrap/Python exit code or automatic namespace cleanup alone is insufficient. The whole arrangement, including signal/FD protection and double-fork/nonstandard-clone cases, is an enablement gate, not an asserted tested property.

### Aggregate resource enforcement and collection

Use controller-owned cgroup-v2 domains: an action parent with a leaf per serial call. Enter the leaf before untrusted execution; descendants cannot migrate or change controls. Keep the privileged controller outside action limits. Isolated output validation gets its own bounded context, charged within action/run admission.

| Resource | Approved target enforcement |
| --- | --- |
| Memory and processes | `memory.max`, `memory.swap.max=0`, `memory.oom.group=1` and `pids.max`; include writable tmpfs and validator needs in admission. Account for shared input/staging buffers at run level and reserve controller/sibling headroom. |
| CPU | `cpu.max` caps bandwidth; hierarchical `cpu.stat` usage supports cumulative call/action accounting and an early-stop watchdog. It is not a zero-overshoot total-CPU counter. Set a measured watchdog/kill allowance and finite wall bounds; reject over-budget completion. |
| Wall time and termination | Trusted deadline enforcement and `cgroup.kill` cover the tree, including detached children. Require `cgroup.events` to show `populated=0` before handling candidate outputs. |
| Writable storage and diagnostics | Kernel-enforced tmpfs byte/inode bounds plus separate declared-output size limits. Bound stdout/stderr while draining so neither pipes nor capture buffers can exhaust storage/memory. |

Cgroup controller availability, hierarchy permissions and guest resource headroom must be verified. No per-process limit or SDK command timeout substitutes for aggregate enforcement. [Kernel cgroup v2](https://docs.kernel.org/admin-guide/cgroup-v2.html).

After a clean supervisor verdict and an empty call tree, capture only the declared regular files into controller-private immutable quarantine. Use non-following, directory-relative file opens and verify file identity/type/link count and actual size; do not trust a prechecked path after following a link. Decode malformed/untrusted artifacts in a separate restricted validation context with only those candidates and bounded resources. The worker verifies integrity and publishes only after round 4 format validation and round 5 ownership/source checks. Do not expose publication authority to the decoder.

If the controller cannot confirm termination or cleanup, withhold all candidates from that call and reconcile or retire the run sandbox using the existing conservative retirement policy. Previously published sibling results survive; unresolved siblings follow their recovery contracts. This does not authorize competing replay while an old execution remains unreconciled.

### Provider feasibility and acceptance gates

E2B documents users/workdirs, network controls and background command APIs. Those pages do not establish required namespace creation, nested-userns denial, mount privileges, seccomp configuration or writable cgroup delegation. They therefore cannot serve as acceptance evidence for this profile. [E2B users/workdirs](https://docs.e2b.dev/template/user-and-workdir), [background commands](https://docs.e2b.dev/commands/background).

Before enabling the exact template/profile:

- Prove every mandatory namespace/privilege/FD restriction and userns-escape denial; deny access to other call inputs, prepared databases, controller paths/processes/sockets and alternate `/proc` routes.
- Prove tmpfs byte/inode and memory/PID/CPU/wall enforcement, placement before code runs, cumulative accounting and full-tree termination under fork/detach/resource-exhaustion cases. Show that controller and allowed sibling work survive the configured stress cases.
- Prove the protected supervisor cannot be signaled, limited, inspected, impersonated or bypassed by payload code. Test orphan zombies, double forks, unusual clone exit signals, early script exit with writers, main-process signals, supervisor death and missing verdicts.
- Prove output retention after child exit and rejection of symlink/hardlink/path races, malformed/oversized artifacts and decode bombs. Validate selected libraries/renderers within this unchanged boundary.
- Record template, guest kernel, SDK/controller, bubblewrap, supervisor, policy and dependency identities with results. Check launch readiness on each new sandbox; changed identities/profile require compatibility review and relevant re-verification. Numerical settings and the CPU overshoot allowance remain evaluation-owned.

Live gates have not run. The user approved this target profile, its conservative unreaped-child rule and refusal-to-run policy pending verification. That approval does not declare E2B feasible, mark the component implementation-ready, authorize paid tests, or approve later artifact/lifecycle contracts.

## Round 4A: approved evidence/chart formats and libraries

Round 4A selects the initial representations and supported library stack. Round 4B will define the exact declaration/metadata schemas, lineage, chart backing and terminal return contract. Nothing in this round bypasses the approved isolation gates.

### Numerical evidence

Use the same typed Parquet table contract as SQL. A scalar result is a one-row table with explicitly named, typed column(s); a series or matrix is represented as a table with meaningful index/key columns. This reuses evidence inspection and downstream SQL without a second scalar storage format. An empty table and a one-row SQL NULL result remain different outcomes.

Keep PyArrow as the authoritative interchange representation. Write ordinary typed tables using explicit schemas and the same compatible Arrow/Parquet environment as the SQL handoff; no pickle, serialized Python object, saved dataframe/interpreter or unvalidated extension object becomes evidence. Preserve supported types and original/artifact column mappings. Do not silently cast decimals, large integers, nulls or temporal values through NumPy floats merely for convenience. The exact supported-value matrix, non-finite handling and rejection/error payloads are round 4B work derived from the existing SQL boundary. [PyArrow Parquet writer](https://arrow.apache.org/docs/python/generated/pyarrow.parquet.write_table.html).

### Chart representation and alternatives

| Alternative | Benefit | Cost |
| --- | --- | --- |
| Matplotlib Agg to single-frame PNG — approved | Headless static output; fits the local demo and needs no browser-side computation. | No hover/zoom or editable vector output. |
| Plotly static PNG via Kaleido/Chrome | Passive final image with Plotly's figure API. | Adds a browser, subprocess/IPC lifecycle and more compatibility work under the OS profile. |
| Interactive Plotly HTML/JSON with a trusted frontend renderer | Hover/zoom and interactive exploration. | Adds a figure/active-content contract, embedded-data policy and frontend rendering/dependency work. |

Agg is Matplotlib's noninteractive raster backend. Current Plotly static export requires Kaleido and a separately installed compatible Chrome/Chromium; offline interactive HTML can embed Plotly.js, while CDN-based output needs network access. These are library facts, not proof that a particular renderer works inside our target sandbox. [Matplotlib backends](https://matplotlib.org/stable/users/explain/figure/backends.html), [Plotly static export](https://plotly.com/python/static-image-export/), [Plotly HTML export](https://plotly.com/python/interactive-html-export/).

**Approved choice:** publish single-frame PNG (`image/png`) produced with explicitly selected Matplotlib Agg. One declared chart output corresponds to one image. The initial chart boundary does not accept interactive HTML, figure JSON, SVG, animation or pickled figure objects. Interactivity remains a future separately reviewed requirement, not a second initial output mode.

The numerical backing remains separately inspectable. Supply an accessible text description and backing-value references with the chart; exact fields belong to 4B. Text must identify the plot's meaning and limitations, rather than treating pixels as the only explanation. Titles, axes, units, series distinctions, ordering, relevant timezone and nonstandard scales must be understandable. Do not rely on color alone. [W3C complex-image guidance](https://www.w3.org/WAI/tutorials/images/complex/).

### Minimal supported environment

Use the standard library, PyArrow, NumPy and Matplotlib, with pinned required transitive dependencies. Reuse Pillow, already required by Matplotlib, for isolated PNG decoding/normalization. Pandas is optional to PyArrow and is not needed for the initial Arrow/NumPy calculation and plotting path; do not add pandas, SciPy, seaborn, a browser or a TeX stack to this baseline. An approved later calculation can justify a separately reviewed environment change. This supported-library list does not replace OS confinement with an import filter. [Matplotlib dependencies](https://matplotlib.org/stable/install/dependencies.html), [PyArrow dependencies](https://arrow.apache.org/docs/python/install.html#dependencies).

Bundle fonts and timezone data in the read-only template. Route Matplotlib's per-call config/cache to bounded scratch. Treat source labels as literal text, disable external TeX rendering and avoid runtime downloads. Explicitly close saved figures and finish any subprocess work under the approved supervisor rule. Package/font/encoder versions must be recorded; numerical correctness and legibility take priority over a promise of identical PNG bytes across environments. Exact compatible version pins and the template manifest remain an explicit readiness item for round 6/final audit, before implementation is accepted.

### Calculate first, render published values

The approved numerical/chart split applies to plotting helpers too. Matplotlib `hist` calculates bin counts through NumPy; therefore save the chosen bin edges/counts and any density/normalization in a numerical operation, then render those values with a non-aggregating plot such as bars/stairs. Likewise, publish statistical quartiles/whiskers, fitted or smoothed values, cumulative totals, percentages and uncertainty intervals before drawing them. [Matplotlib histogram behavior](https://matplotlib.org/stable/api/_as_gen/matplotlib.pyplot.hist.html).

Ordinary tick placement, text formatting and declared coordinate geometry are rendering. They do not require a table of every pixel coordinate. New analytical quantities do require saved numerical evidence. Preserve exact backing values and declare any display conversion; plotting convenience cannot silently change precision, null meaning, population or the analytical conclusion. Format validation alone cannot prove that the right values were plotted; code/evidence and semantic fixture checks must cover that relationship.

### PNG validation and publication bytes

After the approved process/collection checks, use a restricted decoder context with no publication authority. Restrict Pillow to PNG; enforce finite compressed-byte, dimension, pixel-count, metadata, memory and time limits. Reject animated, malformed, truncated or unsupported-mode files and treat decompression-bomb warnings as failures. Verify integrity, reopen and fully decode rather than trusting `Image.open`, which is lazy. [Pillow Image API](https://pillow.readthedocs.io/en/stable/reference/Image.html).

Re-encode accepted RGB/RGBA pixels to a clean single-frame PNG without copying candidate metadata or trailing bytes. Publish the normalized bytes and compute their actual size/checksum; do not keep the candidate checksum as the identity of a different served file. Preserve pixel dimensions and record normalization/encoder identity in provenance. This uses the existing decoder dependency rather than a custom PNG parser. It does not prove analytical correctness or prevent information encoded in the visible pixels. Exact artifact metadata is round 4B.

### Round 4A acceptance and approval scope

An independent scoped consistency review found no approval-blocking format contradictions. It did not run decoder, renderer or sandbox compatibility checks.

- Round-trip a scalar one-row table, an empty table and representative SQL-compatible typed results through Parquet without silently changing values or types.
- Render line, bar, scatter and a precomputed histogram offline under the unchanged OS profile. Check long/Unicode labels, chronological ordering, null gaps, explicit units and faithful backing values.
- Reject oversized, malformed, truncated, animated and decompression-bomb PNG candidates. Check that published normalized bytes retain the intended pixels/dimensions and their recorded checksum.
- A renderer failure leaves prior numerical evidence available. Valid image decoding alone never satisfies numerical/evidence correctness checks.

The user approved typed Parquet including scalar-as-one-row representation, single-frame PNG with Matplotlib Agg, the minimal library stack/Pillow normalization, explicit saved analytical plot values, and the offline/accessibility requirements on 15 November 2026. This does not approve 4B's precise declarations, type/lineage/return schemas or claim any live compatibility checks have passed.

## Round 4B1: approved source dependencies and invalidation

Approved 15 November 2026. Remaining output contracts must implement this lineage policy.

Every newly published Python evidence item or chart inherits the runtime-verified union of Dataset dependencies of all evidence delegated to its action, including transitive dependencies. This is the action's input set, not every Dataset in the run or Project. Per-code-call selected inputs remain execution provenance; they cannot narrow invalidation dependencies after the model has received the action context.

Automatically supplied source-derived facts in the objective, constraints, original-question context, previous findings and retained messages must have recorded dependencies covered by the action inputs. The context builder must exclude unsupported retrieved context or require the supervisor to supply its backing evidence before dispatch. Independently retainable outputs require independently scoped actions and context, not merely separate code calls. Detailed conversation-context assembly remains owned by memory design, subject to this constraint. User-authored statements remain unverified request text or explicit assumptions; they are not promoted into computed project evidence.

Existing evidence referenced unchanged retains its original dependencies. A new chart inherits its action's complete dependency union, including sources that could influence labels, annotations or reference lines. Its backing numerical table does not automatically acquire the chart's additional dependencies. Numerical evidence retained after chart failure remains subject to source invalidation under its own recorded dependency set.

### Explicit behavior change to review

The PRD currently describes deleting completed outputs only when they actually used the removed source. For Python outputs, the approved policy conservatively treats all supplied source-bearing action inputs as used for invalidation. It does not claim to measure actual causal influence. A Python action supplied A and B loses its new outputs when B is removed even if its code appears to read only A. An independently scoped A-only action remains available; unchanged pre-existing A evidence also remains available.

The user explicitly approved this clarification/change; the PRD and shared SQL handoff are updated. It was not an automatic consequence of artifact-only access. SQL's parsed-query dependency contract remains unchanged. The PRD rule stopping unfinished runs whose pinned scope includes a removed Dataset also remains unchanged.

### Alternatives and checks

- **Action-wide union — recommended:** covers model-context influence without trusting generated code's claims. It can invalidate more Python outputs than strictly necessary.
- **Per-call declared/read inputs only:** finer retention, but misses source-derived model context and annotations. Python assertions, audit hooks and file-read logs cannot by themselves establish complete causal lineage.
- **Restricted deterministic transformations:** could permit finer attribution, but introduces another execution/analysis contract beyond the approved arbitrary-Python approach.

The runtime derives dependencies from validated evidence records, never model-provided source lists. Recheck authorization, publication, integrity and current source availability before input use, restoration, publication and access. A missing/invalid dependency blocks publication; no model declaration can revive removed sources. Ownership/deletion race mechanics remain round 5.

Acceptance examples: A+B action with A-only code still depends on B; A-only action with no B-derived context survives B removal; a new A+B chart can be invalidated while unchanged A backing evidence survives; intermediate Python evidence carries transitive dependencies into later actions; chart failure preserves valid numerical evidence without overriding source deletion.

An independent medium-reasoning review found this coherent provided the context boundary and deliberate broader invalidation are explicit. The user approved this lineage policy and corresponding PRD/shared-contract updates. This does not approve the remaining output schemas or claim live enforcement has been verified.

## Round 4B2: approved terminal return to the supervisor

Approved 15 November 2026. Reuse SQL's three terminal variants rather than introducing a second partial-success status system. Every variant ends this specialist invocation; none directly publishes the final user answer.

| Variant | Model-supplied fields |
| --- | --- |
| `succeeded` | `observation`, `evidence_ids`, `chart_artifact_ids`, `limitations` |
| `blocked` | `explanation`, `required_input`, `evidence_ids`, `chart_artifact_ids` |
| `failed` | Genuine structured tool/runtime `error`, `evidence_ids`, `chart_artifact_ids` |

Reference lists are unique UUIDs; either may be empty as appropriate. Evidence may reference authorized inputs or this action's published numerical outputs. Chart references must resolve to this action's published charts. Reject unknown, unpublished, invalid, stale-attempt or out-of-scope references. Preserve other valid published action outputs in runtime state even if the model omits them from its selected handoff.

Success requires fulfilling the entire delegated objective and all `required_outputs`, checked against selected valid terminal references. Omitted publications remain available for recovery/replanning but do not silently satisfy this handoff. Requiring `evidence` needs a newly computed published numerical result from this action, not an unchanged input UUID. Requiring `chart` needs a new published chart with valid inspectable numerical backing. Artifact presence alone does not establish analytical correctness, requested chart count or full objective fulfillment. A blocked/failed result can retain useful evidence without claiming success.

The runtime enriches the validated return with run/task/action identity, expected attempt and producer provenance. It resolves selected numerical references into actual bounded tables plus complete artifact references, and chart IDs into normalized PNG metadata, accessible descriptions and backing references. It also reports `unmet_required_outputs` for declared kinds not fulfilled; this list cannot be supplied or cleared by the model. Supervisor reasoning and the later answer/reviewer flow still check the original objective beyond these minimum kind checks.

Example: a calculation-and-chart action publishes its calculation, then rendering fails. Return `failed` with the genuine rendering error, the retained numerical evidence ID and no chart ID; runtime reports `unmet_required_outputs=["chart"]`. The supervisor may correct/retry within the later lifecycle limits, replan, or offer the supported partial findings through the Answer Specialist/Reviewer. The rejected chart is never described as delivered. Missing definitions or preparation instead return `blocked` with the specific needed input. Runtime stopping conditions can create terminal failures when no valid model return is available.

Source invalidation and deadline checks override every variant before publication/access. Retaining a result after rendering failure does not exempt it from the approved action-wide source dependency policy. Exact new error codes, retries and recovery transitions remain round 5; concrete evidence/chart metadata and value validation remain the next output-schema discussion.

The user approved these terminal variants, selected/retained reference handling, runtime-enriched handoff and explicit unmet-deliverable reporting on 15 November 2026. This does not approve incomplete artifact/value schemas or execution feasibility.

## Round 4B3: approved artifact declarations, values and metadata

Approved 15 November 2026. Complete the common `outputs` declarations from 3A with kind-specific fields. The model supplies analytical descriptions and expected schemas; trusted validation supplies actual artifact facts. Unknown fields, invalid references and unsupported types are errors, not silently discarded data.

### Numerical declaration and record

An `evidence` declaration has `name`, `kind="evidence"`, `description`, `shape` (`scalar` or `table`), and nonempty ordered `columns`. Each column has `name`, `type`, and Boolean `nullable`. Type is an object with a `tag` field selecting: boolean, int64, uint64, float64, string, date, time, timestamp, timestamptz, or decimal; decimal additionally declares integer precision/scale with 1 <= precision <= 38 and 0 <= scale <= precision. Temporal time/timestamp precision is microseconds; timestamptz represents UTC instants, with original/source timezone retained separately in provenance. Date-only and timezone-unspecified timestamps remain distinct. No nested, binary, interval, complex, extension or executable-object types initially.

The isolated validator scans the complete file and checks its actual ordered schema and values against the declaration, without implicit type coercion. Reject overflow, unsupported precision and non-finite floating values (NaN or infinity). SQL NULL remains a validity-mask null, not NaN; deliberate replacement of invalid values with NULL needs an explicit analytical decision and recorded count/limitation. Reject undeclared coercions rather than converting silently. Empty/all-null results require an explicit typed schema; scalars require exactly one row. A null scalar is distinct from zero rows. Wider integers require a deliberate lossless supported representation or an explicit unsupported-type failure.

Reuse the shared column normalization/collision policy, preserve submitted labels/ordinals and return the final artifact-column mapping. Any normalization/rewrite is trusted and reflected in the published schema/checksum. Downstream code uses the returned names, not a guessed mapping.

The published numerical record reuses the SQL evidence object: runtime evidence/artifact UUIDs, producer identity, exact ordered schema/count, bounded preview, Parquet media type/size/SHA-256, opaque storage reference and environment/policy versions. Python producer provenance additionally records operation and attempt, recorded script reference/hash, actual per-call input IDs, the approved action-wide input/dependency union, effective constraints, and any declared random seed/method parameters. A seed is required when the chosen calculation uses randomness; it does not promise identical results across changed environments. Exact ownership/generation transaction mechanics remain round 5.

Reuse SQL's preview encoding: typed column definitions, strings for non-null cells, JSON null for SQL NULL, explicit shortening/truncation metadata and ISO temporal display. Full Parquet values remain authoritative. Exact previews/output caps remain evaluated finite configuration.

### Chart declaration and record

A `chart` declaration has `name`, `kind="chart"`, nonempty `title` and accessible `description`, nonempty `series`, `units`, `analysis_timezone` (identifier or null), and `limitations`. Title/description are bounded strings, units is a string-to-string map, limitations is a list of bounded strings, and analysis_timezone is a timezone identifier or null. Each series has a label, `evidence_id` UUID, an `ordering` list of column/direction pairs (direction `asc` or `desc`), a `scales` map of axis role to `linear` or `log`, and a nonempty `columns` map from meaningful role names (for example x/y, category/value, bin_left/bin_right/count) to actual artifact-column names. Role names are descriptive identifiers, not executable expressions.

Every referenced backing evidence ID must be one of that rendering call's declared tabular inputs. Bind only actual columns. Series use complete backing rows, with declared ordering column/direction pairs where order matters. Record axis scales as linear/log and disclose null/unrepresentable display gaps or display conversions in limitations. Such rendering gaps cannot disguise intentional analytical row selection, which requires a newly published backing table. If plotting requires a subset, changed grain, calculated quantity or other analytical transformation, first publish the appropriate backing table; do not embed an uninspectable selection/query in the chart declaration. Ordinary tick/text/coordinate formatting remains rendering under 4A.

The runtime-published chart record contains chart artifact UUID, producer operation/attempt, normalized `image/png` size/SHA-256 and opaque reference, positive pixel width/height, encoder/normalization/environment identities, the validated analytical declaration, backing references and the approved action-wide Dataset dependency union. Persist the executed rendering script reference/hash too. The final hash identifies normalized served bytes, not the submitted candidate. No model-supplied path, hash, dimensions, row count or dependency list is authoritative.

Structural checks validate bindings, types, artifact integrity and declared limits. They do not prove that pixels faithfully show the declared data. The specialist's completion check and answer/reviewer flow must examine code/evidence for correct fields, units, ordering, missing-value handling, scales and objective fulfillment; evaluation fixtures test this semantic agreement. Data-derived titles/descriptions remain untrusted display text and require safe rendering in the later frontend.

### Acceptance and approval scope

- Reject wrong schema/nullability, overflow, non-finite numbers, unsupported types, malformed dates and lossy temporal/decimal conversions; verify representative Parquet-to-SQL round trips.
- Preserve scalar NULL versus empty table, precision-sensitive integers/decimals and column mappings in previews and complete artifacts.
- Reject chart backing outside the call inputs, nonexistent columns, hidden analytical expressions and invalid normalized-image facts. Retain complete backing references when the preview is truncated.
- Detect a semantically incorrect plot even when PNG/schema validation succeeds. Cover precomputed bins, chronological ordering, null gaps, units/scales and source invalidation.

The user approved these declaration/record/value rules on 15 November 2026, completing round 4. It would not assert tested dtype/renderer/provider compatibility. Detailed lifecycle/error codes are round 5; exact pins, finite limits and scoring fixtures are round 6; the final integrated audit must still resolve any remaining contract gaps before implementation.

## Round 5: approved lifecycle, recovery, errors and stopping

Approved 15 November 2026. Reconciles two parallel medium-reasoning investigations: recovery/publication and errors/stopping. Reuse the approved SQL persistence authority and dispatch protocol; no additional service or interpreter checkpoint.

### Identity and durable phases

Persist operation records, publication metadata, source tombstones, run invalidation, expected attempt and current ownership together in standalone SQLite; move that authority together to Postgres at application integration. Use the existing atomic file-mailbox protocol. Generated manifests remain untrusted; adoptable completion requires controller-owned records.

| Phase | Required record/behavior |
| --- | --- |
| `prepared` | Validate request and reserve budget; persist invocation key, operation UUID, request digest, recorded script, explicit input/declaration identities and policy/environment identities before dispatch. |
| `running` | Atomic request delivery binds the operation to controller and call execution incarnations. Launch under the verified profile with fresh interpreter/scratch. |
| `executed` | Trusted controller records actual main-process exit, protected supervisor verdict and confirmed empty call tree. |
| `validated` | All declared files are quarantined, checked and normalized by isolated validators; actual metadata is recorded. |
| `published` | Immutable bytes are durable; one guarded transaction registers all declared outputs, successful operation completion and replayable response. Diagnostic-only calls commit a response with no artifacts. |
| `failed` | Recorded terminal execution/validation failure publishes no candidates from this operation. Prior successful operations remain available subject to validity. |

Map `(action_id, attempt, invocation_key)` uniquely to an operation. Replay reuses its identity/digest; changed payload under the same key is rejected. A deliberate new call, even with identical code, has a new key. Code corrections create new operations within the same action attempt. Persist launch bookkeeping before waiting for completion.

An attempt changes only for a deliberate supervisor retry after recorded action failure. Owner generation changes on ownership transfer and fences obsolete publishers; it does not change logical operation identity. Physical incarnation identifies sandbox/controller/call nonce and PID separately from owner generation. A reconnect can attach to an existing physical execution under a new owner.

Bounded infrastructure retries may resume an unresolved operation or repeat it only after previous execution is reconciled/retired, preserving its identity and recording each physical execution. A terminal `failed`/`published` operation replays its recorded response, not its script. Intentional work after terminal failure needs a new invocation. Every actual execution/retry is resource/billing-accounted.

### Publication and recovery

Allocate artifact identities once per operation/output name. Transfer every validated immutable artifact first, then commit the complete output set and response together. Publication checks current generation, expected attempt, valid run/deadline and available dependencies in the same authority used for deletion. If any declared output is invalid, publish none. Lost commit acknowledgments are resolved by reading the ledger; storage uploads alone never mean publication. Normalized PNG hashes identify the served bytes.

Recovery checks durable publication first, then trusted validation/execution records, then identifiable running work. Restore a committed response and its valid references once without rerunning the calculation. Reconnect to running work where possible. Adopt completed-but-unpublished work only after rechecking identities, trusted clean completion, integrity, dependencies and ownership; repeat isolated validation if needed. Recreate unresolved execution from the complete recorded script and durable inputs, never from live variables or stale scratch paths.

Unknown execution/termination creates a durable retirement barrier independent of operation phase. Fence old publication and reconcile/retire the old process tree before replacement execution. The barrier survives failed results and later attempts. If whole-sandbox retirement is necessary, coordinate unresolved siblings and preserve their durable published results. Do not create competing execution simply because a command is unreachable.

Same-attempt recovery preserves successful numerical operations when a chart fails. Across deliberate action attempts, preserve historical publications but do not relabel them as new-attempt outputs or silently widen the immutable input request. The supervisor can explicitly delegate a new chart-only action using retained valid evidence. Input evidence from earlier producers/attempts remains eligible when explicitly delegated and valid; stale publishers cannot claim current-attempt outputs.

Deletion and publication serialize through the shared authority: deletion first blocks publication; publication first is subsequently invalidated. Loading, restoring, artifact access and final answer checks recheck current validity. The approved action-wide Python dependency union cannot be narrowed during recovery.

### Error policy

Reuse shared `ToolError(code, message, stage, operation_id?, disposition)` and sanitization. Runtime assigns dispositions; models cannot make faults retryable. Retain the existing `correct_query` enum spelling for compatibility, explicitly meaning correction of code/declarations in Python. It does not authorize a SQL query from the Python action.

| Category/codes | Runtime handling |
| --- | --- |
| `invalid_arguments`, `unknown_column`, `type_mismatch`; new `python_execution_error`, `output_validation_error`, `chart_render_error` | `correct_query` when an equivalent corrected script/declaration is possible; otherwise `replan` or `fail_action`. Include bounded safe diagnostics; never silent coercion. |
| New `execution_timeout`, `resource_limit_exceeded` | Correct only with an equivalent implementation and remaining budget; otherwise fail. No unchanged automatic retry of deterministic exhaustion or silent sampling. |
| `policy_violation`, `artifact_integrity_failure`; new `environment_unavailable` | Fail action. Do not weaken isolation, consume questionable bytes or install packages. Positively identified transient provisioning faults use infrastructure handling instead. |
| `artifact_unavailable`, `infrastructure_unavailable` | Bounded retry only for identified transient transport/storage/provisioning faults. Permanent missing inputs require replanning; unclassified/internal failures are not automatically retryable. |
| `source_unavailable` | Invalidate the run under the pinned-scope removal rule. |
| `budget_exhausted`, `no_progress`, `internal_error` | Fail action with retained valid results and actual cause. |
| `invalid_specialist_output` | Permit bounded terminal-output correction if budget remains; otherwise create a runtime terminal failure. |

Reuse `unsupported_result_type` for unsupported values/types; correct only through an explicit meaning-preserving representation, otherwise replan/fail. Missing definitions, preparation or consequential assumptions use the approved `blocked` return rather than a fabricated execution error. Stages remain validation/execution/persistence/recovery; exact user-visible wording stays outside these machine codes.

### Progress and stopping

Use the shared structured decision envelope: one of Python's two tool requests or a terminal output, plus an optional progress report for the preceding completed round. Reports identify the round and supporting recorded responses/evidence. There is no third tool or progress-only model call.

Runtime applies each round once. Reset no-progress only for usable new evidence, resolution of relevant uncertainty or completion of a required deliverable. Meaningful empty results can qualify; fresh UUIDs, cosmetic code edits, repeated errors/inspections and replayed responses do not. Missing/unsupported progress claims cannot reset counters.

Require finite model/tool/execution/correction/transient-retry/no-progress counters, token/cost/resource limits and active deadlines. Check admission before each model/tool/retry and charge actual usage afterward. Preserve counters/reservations on recovery; a new action attempt cannot erase enclosing run consumption or supervisor no-progress history. Numerical ceilings are round 6 choices.

Bound execution by the earliest operation/action/analysis cutoff. When the drafting/review reserve is reached, stop further analysis and return retained valid results with unmet deliverables for the established reviewed partial-answer path. A hard deadline or source invalidation still withholds final publication. Fresh interpreter retries do not grant fresh run budgets.

### Acceptance and scope

Cover lost acknowledgment/checkpoint after publication, disconnect during execution, completed unpublished candidates, invalid controller proof, corrupt bytes, deletion races, failed retirement, duplicate/stale delivery, and shared-sandbox sibling recovery. Verify calculation retention after chart failure and explicit redelegation across action attempts. Exercise correction/retry counters, meaningful empty results, cosmetic no-progress loops and reserve/hard-deadline behavior.

The user approved this lifecycle, shared identity/publication/retirement model, deliberate-attempt reuse rule, error dispositions and finite stopping/accounting behavior on 15 November 2026. Live enforcement/recovery remains unverified. Exact evaluation configurations/version pins/thresholds are round 6; final integrated audit is round 7.

## Round 6: approved evaluation, observability and bounded settings

Approved 15 November 2026. Two parallel medium-reasoning tracks covered fixture/scoring and configuration/cost. This defines a development-evaluation contract, not a measured pass or authorization to spend.

### Versioned fixture matrix

| Family | Observable checks |
| --- | --- |
| Numerical fidelity | Exact nullable integers/decimals, scalar NULL versus empty table, temporal semantics and column mappings survive Python/Parquet/SQL. Unsupported/lossy results fail explicitly. |
| Analytical correctness | Independent oracles check population, grain, filters, units, denominators, missing categories and prerequisite requests. Exact comparisons for discrete/decimal values; approximate methods use fixture-specific justified tolerances. |
| Charts | Line/bar/scatter/precomputed histogram fixtures check complete backing values, labels, chronological ordering, null gaps, scales and units. An incorrect plot with valid PNG/schema must fail semantic scoring. |
| Trajectory and partial results | Numerical publication precedes newly calculated plot values; stdout is not evidence; missing source preparation returns to supervisor; failed chart preserves valid calculations and reports unmet delivery. |
| Adversarial access/privacy | Actual probes test foreign IDs/files, sibling/controller/FD/network access, link/path attacks, forged manifests and instructions embedded in cells. Hosted-trace sentinels detect source-bearing payload leakage. Model refusal alone is not isolation proof. |
| Invalidation | A+B action reading A still invalidates on B removal; independently scoped A results survive; unchanged backing keeps its dependencies. Exercise deletion around load, restore, publication and access. |
| Recovery/stopping | Crash/lost acknowledgment at durable boundaries, changed digest, stale owner, failed retirement, duplicate publication, unresolved siblings, corrections/retries, meaningful empty result, cosmetic no-progress and reserve/hard deadline. |

Schema/integrity, capability enforcement, invalidation, immutable identity, publication/replay/retirement, truthful references, finite accounting and trace privacy are must-pass runtime gates. A gate failure blocks acceptance regardless of aggregate model scores.

Score model behavior separately: numerical assertions, complete chart semantic agreement and component checks, routing/prerequisites, requested-deliverable completion, supported conclusions and truthful partial reporting. Report active latency, calls, corrections, retries and actual full-scope cost. Calibrate any semantic judge against human-reviewed correct and deliberately incorrect examples; publish disagreements. No judge replaces deterministic safety/recovery probes.

Version fixtures, independent oracles, required/forbidden events and seeds. Tune only on development cases; hold out whole analytical/adversarial variations. Freeze configuration and rubric before held-out baseline/specialist comparison. Report repetitions, denominators, failure slices and uncertainty. Numerical quality/completion targets must be declared before tuning comparisons; no unmeasured target is described as achieved.

### Provisional development-evaluation ceilings

These are initial bounded candidates, not final product limits. Every value is capped by remaining enclosing run allocations. Exceeding a limit returns an explicit failure without sampling or weakening validation.

| Category | Initial candidate |
| --- | --- |
| Per-action requests | 8 model requests; 6 tool invocations; at most 4 actual code launches. Corrections/retries also consume these ordinary counters. |
| Corrections/retries/progress | 2 code/declaration corrections; 1 terminal-return correction; 1 identified transient retry; stop after 2 consecutive rounds without verified progress. |
| Tokens | 64,000 cumulative input and 8,000 cumulative output per action; at most 4,096 output tokens per request. Reserve capacity before calls; provider accounting/hidden reasoning must fit supported reported-token semantics. |
| Time | 120 seconds active action; 30 seconds code call; 10 seconds validation; at most 2 recovery/retirement reconciliation checks within 20 seconds. A separate 10-second teardown bound cannot extend answer publication deadlines; unconfirmed cleanup retains retirement fencing. |
| Resources | 1 GiB aggregate action memory including work/validation, zero swap, 32 processes/threads, one CPU bandwidth equivalent and 60 cumulative CPU-seconds. A provisional 1 CPU-second watchdog allowance needs measurement; it is not a proven hard boundary. |
| Files/work | 256 MiB total selected complete inputs per call; 128 MiB writable work and 4,096 inodes; 64 KiB script; 16 KiB stdout/stderr each, with truncation flags. |
| Outputs | At most 4 declarations per call; 16 MiB per evidence file, 8 MiB per PNG and 40 MiB published bytes per action. PNG dimensions at most 4,096 each and at most 16,000,000 decoded pixels. |

The versioned configuration must also contain finite context/history/preview, string/list/column/schema/metadata bounds, diagnostic-drain limits and monetary caps, plus concurrency and drafting/review reserves. Reject missing/unbounded or contradictory settings before execution; this proposal is not by itself an executable configuration. Fill model-dependent context/spend fields and validate resource admission before any run. Preview shortening remains labeled; complete evidence is never silently shortened.

Sibling allocations are reserved atomically with controller/staging headroom. Effective deadlines use the earliest operation/action/run-analysis cutoff. Recovery, retries and new attempts preserve run-wide consumption. A request too large for selected context or output budget is rejected before dispatch, not left to provider truncation.

### Reproducibility and exact environment identities

The evaluation manifest records configuration ID/hash, repository commit plus any archived dirty-patch hash, spec/prompt/tool-schema/policy hashes, fixture revision/split/case IDs, repetitions, seeds, concurrency and every effective limit/reserve. Record actual immutable template/image, guest kernel/architecture, Python/dependency lock hashes, fonts, Agg/PNG encoder, SQL-compatible Arrow environment, SDK/controller/bubblewrap/supervisor and seccomp identities.

Collect identities from the built and inspected environment. Exact installed pins/template hashes cannot truthfully be invented before that build; their populated manifest and compatibility checks remain a readiness gate, to be identified explicitly in the final audit. Changed environment/profile identities require the relevant gates again. This is reproducibility of inputs/configuration and measured variation, not a promise of deterministic model output.

For every model role record OpenRouter requested model, inference settings and provider/routing/fallback policy; actual provider/model metadata when exposed; request/generation IDs and dated rate snapshot with units/currency. Record unknown revision/usage as unknown, never zero. Actual route changes define a separate comparison configuration. No specific model, current price or spend allowance is selected by this proposal.

### Traces, cost and experiment admission

Hosted events use an allowlist: configuration/run/task/action/attempt/generation/operation IDs, event sequence, phase/decision label, UTC timestamp, monotonic duration, outcome/error/disposition, counter/reserve snapshots and stop reason. Exclude source-bearing prompts, code, tool payloads, previews, rows, chart labels, raw results and credentials. Retain authorized detail locally under deletion rules.

Measure queue/provisioning/inference/execution/validation/publication/recovery separately, as well as active total and clarification waits. Record per-request input/output/reasoning and cache tokens where available, actual retries, billed model cost and reconciliation status. Include sandbox/provisioning/storage/validator/judge costs within the stated scope, not only inference.

Before full-suite spending, forecast all roles × cases × repetitions with expected trajectories/tokens/retries, cold-cache and explicitly stated cache assumptions, dated verified rates and bounded worst-case exposure. Require explicit suite/run/action monetary caps and the applicable spending approval. Missing rates/configuration or unavailable cost bounds block paid evaluation. Reconcile actual bills against forecasts; unavailable usage remains an uncertainty in the report.

Run bounded development pilots first, inspect failure slices, and choose the smallest limits/configuration meeting predeclared correctness/completion targets within latency/cost constraints. Freeze before held-out comparison. Approval of this evaluation design does not authorize a paid pilot or full suite.

### Acceptance and approval scope

Check that incomplete manifests and exceeded budgets cannot dispatch; all invariant gates are reported independently of model scores; cache/retry/sandbox costs are included; trace sentinel data stays out of hosted events; and frozen held-out inputs cannot silently change during tuning. Record unrun gates explicitly.

The user approved this evaluation/scoring process, candidate ceilings, manifest/privacy/cost contract and mandatory preflight gates on 15 November 2026. This does not claim measured performance, selected final models, populated build pins or verified provider enforcement. Round 7 audits design completeness and makes these readiness gaps explicit.

## Round 7: approved final audit and handoff

Three parallel medium-reasoning audits independently examined contracts, lifecycle and readiness. Contract/lifecycle audits found no consequential new policy blocker. Readiness identified the existing context-policy dependency, incomplete runnable configuration and unrun enablement gates. This is a document audit, not execution evidence.

### Approved final clarifications

- Check `required_outputs` and runtime `unmet_required_outputs` against selected valid terminal references. Omitted publications stay available for recovery/replanning but do not silently satisfy a selected handoff. Full objective and analytical correctness checks still apply.
- Complete chart backing rows remain inspectable. Disclosed null/unrepresentable display gaps may be rendering omissions; intentional analytical filtering/subsetting requires a newly published backing table. Do not disguise population selection as a display omission.
- Candidate ceilings are intersecting maxima, not independently guaranteed allowances. Validate one configuration containing effective run/action limits, concurrency, headroom and review reserves; do not silently adopt supervisor evaluation candidates as fixed allocations.

### Remaining dependencies and gates

| Item | Owner and required point of resolution |
| --- | --- |
| Bounded context/history and compaction policy | Memory design, before coding dependent context assembly. Preserve tool pairs, runtime authority, authorized provenance and published references; cumulative token ceilings are not a substitute. |
| Correctness/completion targets, denominators and any judge-calibration criterion | Evaluation owner, declared before tuning/comparison. No achieved score is implied by approved fixture families. |
| Complete model/provider/inference/routing settings, context/payload caps and finite monetary allocations | Evaluation/configuration owner before any run; reject missing or contradictory settings. |
| Exact dependency locks, template/kernel/controller/supervisor/syscall-policy identities | Capture from the built and inspected environment, then verify compatibility before enabling the profile. Do not invent build hashes. |
| SQL/Arrow value fidelity, normalized-image correctness, private inputs, controller isolation, resource limits, descendant cleanup and reconnect/replay/publication/deletion behavior | Runtime implementers must pass the approved live gates on the exact profile before acceptance/enablement. Changed identities require relevant re-verification. |
| Spend forecast, dated verified rates, bounded exposure and approval | Evaluation owner before paid pilots/full suite; design approval does not authorize spend. |

The specification can guide subsequent component planning and deterministic fixture/harness preparation. It is not permission to implement unresolved context behavior or run generated Python with an unverified profile. Follow the project-wide design-first sequence before substantive implementation. Code-writing tasks always go to smaller-model subagents at explicit medium reasoning; planning/research delegation is used only when independent parallel tasks save time.

The user approved this final packet on 15 November 2026, closing the Python component's design-review rounds with these clarifications and assigned dependencies. This does not erase the readiness gates or claim that PRD milestones 1C, 1D or 1F have been implemented or passed. The broader memory/component designs remain necessary before the agreed implementation phase.

## Historical research findings

Three independent read-only research tracks covered contracts/data fidelity, execution/recovery, and charts/evaluation. Their initial boundary findings informed the approved round 1 decision. These findings preceded the approved contracts above; they do not supersede those choices or establish live verification.

- **Data fidelity:** default dataframe conversions can change nullable integer representation. Decimal/wide-integer precision, null versus non-finite values, date-only/naive/offset timestamps, ordering and column mappings need a pinned, tested conversion matrix. Python-to-Parquet-to-SQL compatibility must be checked, not inferred from a successful file write. [Arrow pandas integration](https://arrow.apache.org/docs/python/pandas.html), [pandas Parquet reader](https://pandas.pydata.org/docs/reference/api/pandas.read_parquet.html).
- **Isolation:** E2B documents users and working directories, not a security guarantee between action directories. Our required action boundary must prevent Python from reaching prepared databases or sibling files/processes staged elsewhere in the same run sandbox. Python explicitly says its Python-level audit hooks are unsuitable for sandboxing. Runtime/output validation cannot substitute for an OS-enforced execution boundary. [E2B users and workdirs](https://docs.e2b.dev/template/user-and-workdir), [Python audit hooks](https://docs.python.org/3/library/sys.html#sys.addaudithook).
- **Network and recovery:** E2B documents disabling outbound internet and reconnecting background commands. Neither establishes per-action filesystem isolation, descendant termination or reconstruction of unsaved Python variables. Reuse the approved action/attempt and publication-ownership concepts where applicable; rounds 3 and 5 now define Python operation/interpreter recovery, with live behavior still unverified. [E2B network controls](https://docs.e2b.dev/network/internet-access), [background commands](https://docs.e2b.dev/commands/background).
- **Rendering:** Matplotlib has noninteractive output backends. Plotly supports interactive HTML; static export requires Kaleido and compatible Chrome/Chromium. Rendering choice affects template dependencies, offline behavior and active-content handling. Round 4 selected Matplotlib Agg and PNG; the broader alternatives were not selected. [Matplotlib backends](https://matplotlib.org/stable/users/explain/figure/backends.html), [Plotly HTML API](https://plotly.com/python-api-reference/generated/plotly.io.write_html.html), [Plotly static export](https://plotly.com/python/static-image-export/).

Live library-fidelity, sandbox-enforcement and rendering checks have not run. In particular, approved artifact-only access is a required runtime policy, not something a path naming convention or model instruction can enforce.

## Current review and readiness

Rounds 1–7 are approved. The component design review is closed with the recorded clarifications and assigned dependencies. Context policy, runnable configuration and runtime enablement remain explicitly gated; no product milestone or live acceptance result is claimed.
