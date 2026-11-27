# Standalone Agent T02-T18 Milestones Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement and verify the standalone Querivue agent/CLI through PRD milestones 1A–1G (T02-T18), without Django, application workers or frontend changes.

**Architecture:** Approved role contracts run through private LangGraph subgraphs and trusted wrappers. SQLite transactions and immutable artifacts own effects, source validity and accounting; Redis checkpoints are rebuildable progress projections. Trusted import/SQL/Python code executes only in an admitted isolated environment, while model calls stay outside it.

**Tech Stack:** Python 3.12, uv/uv_build, Pydantic, LangChain model/message/tool/structured-output integrations, LangGraph, Redis checkpoint saver, stdlib sqlite3/argparse, LangSmith under the approved trace policy, E2B, DuckDB/Arrow/SQLGlot, approved spreadsheet and Python/chart libraries, pytest.

**Spec:** [standalone-agent.md](../implementation/standalone-agent.md) — the authoritative milestone specification with all task checklists, file ownership, interfaces, and acceptance criteria.

## Global Constraints

- Keep the approved nine parent-state fields: `input`, `context`, `evidence`, `messages`, `pending_tasks`, `current_task`, `outcomes`, `execution_status`, `output`. No live connections, processes, dataframes or interpreter state in checkpoints.
- One SQLite authority for standalone ownership, budgets, deletion and publication; the authority moves together to Postgres later. No Django import, dual-write or Redis/file authority. Migration proof remains a later adapter gate.
- Source scope/cutoff is pinned at admission. Deletion of any pinned Dataset stops unfinished work; completed answers retain the approved conservative supplied-context dependency unions.
- At most two logical review passes/run; first terminal review failure stops on either pass. First draft-only rejection returns directly to Answer; evidence/mixed defects return to Supervisor. No rejected draft is displayed.
- The 50 MiB Project raw-upload cap is separate from expanded input and prepared/evidence storage caps. Publication validates all selected tables; no silent sampling, row loss, float rounding or partial readiness.
- Use Markdown prompt bundle `querivue-roles-v3`; runtime JSON data, native schemas/tools and trusted policy stay separate. Answer, Reviewer and Clarification have no analytical tools.
- Approved development candidates include 600 seconds active run time, unchanged 60-minute hard wall, at most 15-minute analytical waiting shortened by reserves, 8 SQL/Python dispatch attempts/run and 2 no-progress cycles. Transcribe every stricter role/cumulative/shape/reserve table from its authoritative guide; never invent a reset at a new action/attempt/process.
- SQL query ceiling is 30 seconds; Python code-call candidate ceiling is 60 seconds subordinate to stricter action limits. Initial execution is serial; two-action capability is not enabled without aggregate capacity/isolation proof.
- Initial session candidates: 2 vCPUs, 4 GiB RAM, 4 GiB controlled filesystem; executing action 1 vCPU/2 GiB; 1 GiB expanded input and scratch; published action outputs 128 MiB/16 files. Include all copies/overhead and remaining retirement capacity.
- Direct Google/NVIDIA/Cloudflare development is synthetic/public-data only, with paid ceilings USD 0 and no automatic fallback/recharge. Model/account/protocol/token and environment gates precede each applicable live capability. A scripted transport is not a safety or quality pass.
- Never execute generated code, SQL or untrusted upload parsers directly on the Windows controller as a fallback. Unit tests may use explicitly trusted synthetic fixtures; they cannot certify the deployment boundary.
- No dependency/model downloads, positive spend, provider calls, Docker/image builds or installs are authorized by approving this planning document alone. Future coding scope must explicitly include its ordinary package/build operations; live effects retain separate authorization.

## Review Focus

1. Killing a process after a charged request but before acknowledgment must preserve uncertain usage and prevent a free replay: T05/T06/T16.
2. Source deletion during staging, review or final publication must deny access and serialize publication in either transaction order: T04/T05/T08/T10/T15/T16.
3. A profile, preview or chart must not invent support for unseen rows or a new quantity: T07/T08/T10/T13/T14.
4. Provider-native function signatures, hidden reasoning and retries must not lose identity/accounting on repair or restart: T06/T16.
5. A Windows/local mock that passes must not enable Linux sandbox execution without process-tree, filesystem, network and validator proof: T09/T11/T14/T15.

These are additional adversarial review priorities, not substitutes for the task tests below.

## Milestone Dependency Map

`T01 → T02 → T03 → T04 → T05 → T06 → T07 → T08`; then `T09 → T10 → T11 → T12 (1A) → T13 (1B) → T14 (1C) → T15 (1D) → T16 (1E) → T17 (1F) → T18 (1G)`.

This is a conservative review order. Until the shared interfaces are accepted, run one coding worker at a time. Independent bounded work may be delegated later only with disjoint ownership and frozen consumed interfaces.

---

### Task T02: Lossless canonical encoding and compatibility vectors

**Files:**
- Create: `agent/src/querivue_agent/codec.py`
- Create: `agent/tests/unit/test_codec.py`
- Create: `agent/tests/fixtures/golden/canonical.json`

**Interfaces:**
- Consumes: validated contract records from T01
- Produces: `canonical_bytes(record: Mapping[str, object]) -> bytes`, `record_digest(family: str, version: int, record: Mapping[str, object]) -> str`, `decode_record(data: bytes, model: type[T]) -> T` where `T` is a strict contract model. Family/version domain separation and own-hash exclusion follow the approved codec; no general serializer for arbitrary Python objects.

- [ ] **Step 1: Add fixed expected-byte/hash vectors** — field order, missing/null, Unicode, signed/unsigned boundaries, decimal scale, finite float bits including negative zero, temporal offsets/microseconds, ordered/set lists and own-hash exclusion in `tests/fixtures/golden/canonical.json`.

- [ ] **Step 2: Resolve/pin rfc8785** — implement the approved tagged wire conversion using stdlib decimal/struct/hash where appropriate, then canonicalize with `rfc8785.dumps`. Reject duplicate keys before schema validation. Do not use default `str()`/float JSON or sorted stdlib JSON as the lossless/JCS policy. Record exact codec/library version in `codec.py`.

- [ ] **Step 3: Run tests** — `uv run --locked --group dev pytest tests/unit/test_codec.py -q`, including a fresh subprocess decoding/re-encoding the same vectors. Changed coverage/config/dependency must change the appropriate digest; credentials must not enter stored request bytes.

---

### Task T03: SQLite ledger and deterministic transaction ownership

**Files:**
- Create: `agent/src/querivue_agent/storage/ledger.py`
- Create: `agent/src/querivue_agent/storage/schema.sql`
- Create: `agent/tests/unit/test_ledger.py`
- Create: `agent/tests/integration/test_ledger_races.py`

**Interfaces:**
- `Ledger.open(path: Path) -> Ledger`
- `Ledger.transaction() -> ContextManager[sqlite3.Connection]`
- `Ledger.close() -> None`
- Connection/schema ownership stays here; domain transitions are T05. Use explicit short `BEGIN IMMEDIATE` writes, foreign keys, WAL and full durability on the supported local filesystem; busy waits are finite and errors remain visible.

- [ ] **Step 1: Create versioned tables/constraints** — for scopes/sources/preparation, runs/owners, immutable payloads/dependencies, intake/wait/reply, tasks/actions/outcomes, invocation/physical request, operation/incarnation, draft/review, accounting/progress and final receipts. Store canonical payload bytes/digests and guard columns in the same transaction, not independent competing representations.

- [ ] **Step 2: Add tests for core operations** — one admitted run/intake, unique invocation/operation mapping, unique `(run_id, review_pass)`, one accepted reply/question, one final result/run and exact duplicate-versus-conflicting-content handling.

- [ ] **Step 3: Add two-connection barrier tests** — competing write/owner takeover yields one committed authority; rollback leaves no partial queue/record. No external model/file-transfer/Redis wait occurs inside a transaction. Schema incompatibility fails explicitly.

- [ ] **Step 4: Run tests** — `uv run --locked --group dev pytest tests/unit/test_ledger.py tests/integration/test_ledger_races.py -q`; verify persisted bytes/revisions after reopen. Do not implement a Postgres adapter or ORM.

---

### Task T04: Immutable artifacts, quarantine and dependency invalidation

**Files:**
- Create: `agent/src/querivue_agent/storage/artifacts.py`
- Create: `agent/tests/unit/test_artifacts.py`
- Create: `agent/tests/integration/test_artifact_deletion.py`

**Interfaces:**
- `ArtifactStore.stage(source: BinaryIO, scope: Scope, byte_limit: int) -> StagedArtifact`
- `verify(candidate: StagedArtifact, expected_sha256: str) -> ValidationReceipt`
- `read(ref: ArtifactRef, scope: Scope) -> BinaryIO`
- `cleanup(ref: ArtifactRef, proof: RetirementProof) -> None`
- Only T05 registers eligibility; staging/verified bytes alone are not published.

- [ ] **Step 1: Implement bounded same-filesystem quarantine/atomic move** — and complete-byte hash verification. Paths are controller-owned under the resolved state root; model-visible refs are opaque. Reject traversal, symlink/reparse escapes, device files and oversize/partial copies.

- [ ] **Step 2: Test both orders of tombstone versus registration/read** — corrupt/missing artifact, failed cleanup and retained successful result. Authorized readers recheck transitive dependencies; deletion denies access before physical removal.

- [ ] **Step 3: Run tests** — `uv run --locked --group dev pytest tests/unit/test_artifacts.py tests/integration/test_artifact_deletion.py -q`. Process uncertainty prevents cleanup; lost registration acknowledgment reuses the same immutable bytes/ref.

---

### Task T05: Guarded authority transitions, budgets and clocks

**Files:**
- Create: `agent/src/querivue_agent/runtime/authority.py`
- Create: `agent/src/querivue_agent/runtime/budgets.py`
- Create: `agent/tests/unit/test_budgets.py`
- Create: `agent/tests/integration/test_authority.py`
- Create: `agent/tests/integration/test_budget_races.py`

**Interfaces:**
- `Authority.admit(IntakeAdmission) -> AdmissionReceipt`
- `commit_decision(run_id: UUID, proposal: SupervisorDecision, fence: OwnerFence) -> QueueReceipt`
- `reserve_model(request: ModelRequest, fence: OwnerFence) -> ModelReservation`
- `publish_evidence(candidate: EvidenceCandidate, fence: OwnerFence) -> EvidenceRef`
- `commit_preparation(candidate: PreparedCandidate, fence: OwnerFence) -> PreparedSnapshot`
- `reserve_review(request: ReviewInput, fence: OwnerFence) -> ReviewReservation`
- `accept_reply(reply: LinkedReply, fence: OwnerFence) -> ResumeReceipt`
- `finalize(candidate: FinalCandidate, fence: OwnerFence) -> FinalResult`
- `delete_dataset(dataset_id: UUID, scope: Scope) -> DeletionReceipt`
- Budget calculation: `check_reservation(current: BudgetSnapshot, request: ReservationRequest, now: ClockReading) -> BudgetDecision`, committed only under the same authority guards.

- [ ] **Step 1: Implement whole-proposal validation/commit receipts** — expected revision/attempt/generation checks and source/deadline guards at every effect boundary. A failed proposal changes none of its memory/queue/accounting projection.

- [ ] **Step 2: Add tests for all approved finite buckets/reserves** — no refund on unknown dispatch/review/crash, no reset on retry/new action/process, once-only progress/settlement and clock rollback/downtime handling. Test simultaneous reservations cannot spend protected terminal capacity.

- [ ] **Step 3: Test source-delete/finalize and accepted-reply/expiry races** — in both orders. Unknown physical completion remains reserved; two nonrefundable review slots cannot become three through retry or changed IDs.

- [ ] **Step 4: Run tests** — `uv run --locked --group dev pytest tests/unit/test_budgets.py tests/integration/test_authority.py tests/integration/test_budget_races.py -q`. No external effects while holding the ledger write lock.

---

### Task T06: Markdown prompts, accounted model gateway and trace boundary

**Files:**
- Create: `agent/src/querivue_agent/runtime/{models,prompts,trace}.py`
- Create: ten `agent/prompts/*.md` resources
- Create: `agent/src/querivue_agent/providers/{google,nvidia,openrouter,cloudflare}.py`
- Create: `agent/.env.example`
- Create: `agent/tests/unit/test_prompts.py`
- Create: `agent/tests/unit/test_gateway.py`
- Create: `agent/tests/unit/test_trace_redaction.py`
- Create: `agent/tests/integration/test_provider_protocols.py`

**Interfaces:**
- `load_prompt(role: str) -> str` hashes approved common plus role resources
- `ModelGateway.invoke(request: ModelRequest, fence: OwnerFence) -> ModelCompletion` is the only graph-facing model call and invokes a configured LangChain BaseChatModel
- Provider modules configure maintained integration classes and exact profiles; token/metadata handling stays behind the gateway
- Use LangChain SystemMessage/HumanMessage/AIMessage/ToolMessage and StructuredTool/schema bindings at this boundary, with supported explicit structured output and raw AIMessage metadata retained
- `trace_event(event: Mapping[str, object], *, hosted: bool) -> None` enforces the approved allowlist; full local records remain protected artifacts, not hosted payloads

- [ ] **Step 1: Copy the ten approved Markdown templates verbatim** — preserving the separate JSON-data/native schema/tool layers. Test source text containing `## Rules` cannot alter template bytes/hash or become trusted instructions.

- [ ] **Step 2: Bind only each role's approved tools through LangChain schemas** — keep invocation under existing runtime guards/counters. Use the integration's supported structured-output mode while preserving strict local validation. The approved outer graph/private loops retain their transitions; framework retry/fallback/tool auto-execution cannot add unaccounted calls or bypass review. F1 explicitly selects the Gemini Developer API without environment-driven switching to a billed cloud backend.

- [ ] **Step 3: Implement reserve-before-send, physical IDs, full payload/token/output admission** — strict whole-response JSON/duplicate-key/schema/reference validation, bounded repair and one canonical completion adoption. No Markdown/substring scraping. Disable SDK auto function execution and implicit SDK/HTTP retries; expose each actual replacement to T05 accounting. Preserve provider thought signatures/call linkage in role-local history. Verify the token counter covers the exact system/schema/tool/history payload; character heuristics are not an admission counter. Account preflight/token-count requests separately under finite intake/operator controls; unsupported or unavailable counting blocks dispatch.

- [ ] **Step 4: Use mocked integration/SDK transcripts to test** — timeout/429/unknown completion, malformed/refused/truncated output, changed served identity, hidden reasoning and tool-call schema variants. Assert one authorized physical request causes exactly one wire call, including on 429/parser errors; retry setting semantics can differ by integration. Preserve Google thought signatures and role-local message metadata through canonical checkpoint serialization without arbitrary object/pickle restoration. Do not double-count reasoning already included in normalized output usage; missing vendor usage remains unknown even if a wrapper presents zeros. Unsupported full-payload token counting/protocol blocks dispatch.

- [ ] **Step 5: Add synthetic credential/question/cell/path/URL sentinels** — inspect actual hosted serialization, stdout and exceptions. Automatic raw LangGraph/LangSmith tracing stays off. Optional hosted export has a separate explicit activation/cost gate.

- [ ] **Step 6: Run tests** — `uv run --locked --extra providers --group dev pytest tests/unit/test_prompts.py tests/unit/test_gateway.py tests/unit/test_trace_redaction.py tests/integration/test_provider_protocols.py -q`. No real request. Optional F2/F3/P1 remain disabled until their own tokenizer/schema/account checks pass.

---

### Task T07: Outer graph, private wrappers and Redis projection

**Files:**
- Create: `agent/src/querivue_agent/graph.py`
- Create: `agent/src/querivue_agent/dispatch.py`
- Create: `agent/src/querivue_agent/entry.py`
- Create: `agent/src/querivue_agent/context.py`
- Create: `agent/src/querivue_agent/supervisor.py`
- Create: `agent/src/querivue_agent/runtime/{checkpoints,recovery}.py`
- Create: `agent/compose.yaml`
- Create: `agent/tests/unit/test_packets.py`
- Create: `agent/tests/integration/test_graph.py`
- Create: `agent/tests/integration/test_checkpoints.py`

**Interfaces:**
- `build_graph(*, authority: Authority, handlers: RoleHandlers, checkpointer: BaseCheckpointSaver, config: RunConfig) -> CompiledStateGraph`
- `build_packet(role: str, run_id: UUID, scope: Scope, fence: OwnerFence) -> RoleInput`
- `restore_run(run_id: UUID, *, authority: Authority, checkpointer: BaseCheckpointSaver, config: RunConfig) -> GraphProjection`
- Use the public `langgraph.checkpoint.base.BaseCheckpointSaver` and `langgraph.graph.state.CompiledStateGraph` types; production composition passes RedisSaver, while explicitly labeled offline tests may supply an in-memory/fake saver. Bound private handlers are assembled by trusted runtime code; unavailable roles fail explicitly until their owning task implements them. Do not create dummy production agents to make this task green.

- [ ] **Step 1: Compile the approved serial control/mandatory edge graph** — with wrapper-mapped private subgraphs; keep model/tool side effects behind T05/T06. Parent updates replace only runtime-owned projections, with approved identity-aware collection rather than blanket dictionary/message reducers.

- [ ] **Step 2: Set checkpoint `thread_id` from run UUID** — never Chat UUID; use role invocation/attempt-bound child namespaces and test no private-history leakage. Serialize/validate canonical tagged values with pickle fallback disabled. Incompatible/untrusted checkpoints never instantiate arbitrary Python objects.

- [ ] **Step 3: Configure RedisSaver setup against Redis 8 JSON/search** — with persistence and no TTL, then test saved/read state, missing/stale/ahead projection and unavailable saver. Ledger reconciliation gates graph advancement; an interrupt re-entering its node cannot repeat a committed effect or change the waiting question.

- [ ] **Step 4: Run tests** — `uv run --locked --group dev pytest tests/unit/test_packets.py tests/integration/test_graph.py -q`. Separately authorized local Redis check: `uv run --locked --group dev pytest tests/integration/test_checkpoints.py -m redis -q`. Missing Redis is explicitly not_run/blocked, never an in-memory pass for 1E.

---

### Task T08: Typed drafting, independent review and final rendering

**Files:**
- Create: `agent/src/querivue_agent/specialists/answer.py`
- Create: `agent/src/querivue_agent/specialists/reviewer.py`
- Create: `agent/src/querivue_agent/runtime/finalize.py`
- Create: `agent/tests/unit/test_rendering.py`
- Create: `agent/tests/integration/test_review_flow.py`

**Interfaces:**
- `draft(request: AnswerInput, *, model: ModelGateway) -> AnswerOutcome`
- `review(request: ReviewInput, *, model: ModelGateway) -> ReviewAssessment`
- `render(candidate: FinalCandidate) -> str`
- Wrappers commit immutable candidate/pass/verdict identities and call `Authority.finalize`; rendering cannot grant eligibility or perform new calculations.

- [ ] **Step 1: Implement strict span/value/claim/chart validation** — and deterministic approved display formatting of supplied cells. Test shortened/invisible cells, incompatible coverage, invalid chart backing and new arithmetic are rejected/blocked rather than invented.

- [ ] **Step 2: Script independent full drafting/review packets** — test first draft-only versus evidence/mixed rejection, second rejection, terminal failure on either pass, late approval and lost acknowledgment. Original obligations and actual partial gaps reach Reviewer.

- [ ] **Step 3: Run tests** — `uv run --locked --group dev pytest tests/unit/test_rendering.py tests/integration/test_review_flow.py -q`. Exactly one eligible final result or bounded notice; no warning banner attached to a rejected draft.

---

### Task T09: Exact environment, sandbox controller and validator gates

**Files:**
- Create: `agent/src/querivue_agent/execution/sandbox.py`
- Create: `agent/src/querivue_agent/execution/validate.py`
- Create: `agent/sandbox/{pyproject.toml,uv.lock,Dockerfile,environment-manifest.json}`
- Create: `agent/tests/unit/test_sandbox_protocol.py`
- Create: `agent/tests/live/test_environment_gates.py`

**Interfaces:**
- `SandboxController.admit(scope: Scope, manifest_id: str) -> SandboxTicket`
- `execute(ticket: SandboxTicket, request: OperationRequest) -> OperationOutcome`
- `retire(ticket: SandboxTicket) -> RetirementProof`
- `validate_outputs(ticket: SandboxTicket, request: OperationRequest) -> tuple[ValidationReceipt, ...]`
- The controller records incarnation/operation identity before waiting; these methods do not publish.

- [ ] **Step 1: Build/version the Linux image and lock after build scope is authorized** — Preinstall approved packages, browser, bubblewrap/cgroup-v2 policy and protected supervision; record actual effective controls/digests separately from requested settings. Match producer/consumer DuckDB and codec/profile versions.

- [ ] **Step 2: Mock command/file transports to test** — partial launch, disconnect/reconnect, traversal/symlink/oversize files, validator failure and unconfirmed retirement. Unreachable work retains reservations; a command timeout or SIGKILL acknowledgment alone is not whole-tree proof.

- [ ] **Step 3: Before live generated execution, verify applicable controls** — read-only/namespace/FD/syscall/network/process-tree/CPU/RAM/disk/expanded-output/validator controls on the exact image and provider. Test an escaping child and malicious output parser separately. No unsupported control is silently disabled.

- [ ] **Step 4: Run offline tests** — `uv run --locked --extra execution --group dev pytest tests/unit/test_sandbox_protocol.py -q`. Only with separate live/spend scope: `uv run --locked --extra execution --group dev pytest tests/live/test_environment_gates.py -m live -q`. An unexecuted or failed environment gate blocks that capability.

---

### Task T10: CSV inspection, confirmation and atomic preparation

**Files:**
- Create: `agent/src/querivue_agent/ingestion.py`
- Create: `agent/src/querivue_agent/execution/importer.py`
- Create: `agent/tests/unit/test_import_lifecycle.py`
- Create: `agent/tests/integration/test_csv_preparation.py`
- Create: `agent/tests/fixtures/imports/meaning.csv`

**Interfaces:**
- `inspect_upload(upload_id: UUID, scope: Scope) -> ImportPreview`
- `prepare_dataset(dataset_id: UUID, settings: ImportSettings, scope: Scope) -> PreparedSnapshot`
- T01 owns strict `ImportSettings`/`ImportPreview` contract models. The controller owns staging/attempt/confirmation and guarded commit; the guest importer returns only a complete validated `PreparedCandidate` through T09/T04. An import preview is not an eligible Dataset.

- [ ] **Step 1: Stage immutable bytes, enforce upload cap and type-specific entry admission** — inspect in isolation, return bounded preview/settings proposals and release the inspection session. Persist preview/settings/confirmation identity; do not pass full uploads to an entry model.

- [ ] **Step 2: Implement CSV with exact quoted-empty/unquoted-null/whitespace and meaningful-leading-zero behavior** — Validate every selected row/type, stable column naming and typed profiles; bad data beyond preview cannot disappear. Unsupported parser fidelity blocks readiness rather than enables ignore-errors.

- [ ] **Step 3: Test source header `a,a,a_2` maps to `a,a_3,a_2`** — copied logical values remain unchanged, exact row/null counts and typed locators resolve. Test conflicting attempts/settings, duplicate delivery, deletion/replacement race and crashes before/after transfer/ready commit. A failed replacement leaves the original usable.

- [ ] **Step 4: Run tests** — `uv run --locked --extra execution --group dev pytest tests/unit/test_import_lifecycle.py tests/integration/test_csv_preparation.py -q` using trusted deterministic fixtures and explicit simulated controller transports. Separately capture real isolated preparation evidence only after the T09 capability gate. All other accepted formats remain explicitly not enabled until T17, not silently interpreted as CSV.

---

### Task T11: Positive SQL policy, persistent action runner and evidence handoff

**Files:**
- Create: `agent/src/querivue_agent/execution/sql_runner.py`
- Create: `agent/src/querivue_agent/specialists/sql.py`
- Create: `agent/tests/unit/test_sql_policy.py`
- Create: `agent/tests/unit/test_sql_bindings.py`
- Create: `agent/tests/integration/test_sql_action.py`

**Interfaces:**
- `run_sql(request: SQLInput, *, model: ModelGateway, tools: SQLTools) -> SQLOutcome`
- `SQLTools.inspect_table(table_id: UUID) -> TableCatalog`
- `preview_rows(table_id: UUID, columns: list[str] | None, limit: int) -> TabularPreview`
- `inspect_evidence(evidence_id: UUID) -> TabularEvidence`
- `execute_query(sql: str, parameters: Mapping[str, TypedScalar]) -> TabularEvidence`
- These are the approved tools; T01 models retain exact schema/coverage/provenance fields. Guest operation identity and evidence publication use T05/T09, not SQL model output.

- [ ] **Step 1: Implement SQLGlot positive AST/relation/function policy** — trusted read-only attachments and binder checks; disable extensions/network/path functions and settings changes. Execute one analytical statement/call with supported explicit typed parameters. A parse-only allow decision is insufficient.

- [ ] **Step 2: Implement one persistent runner subprocess/connection per SQL action attempt** — serialized mailbox operations with atomic request/completion files and distinct physical incarnation IDs. Save complete typed Parquet evidence before returning its tool result; bounded previews retain exact physical locators and shortened-cell flags.

- [ ] **Step 3: Test count/join/grouping/evidence-only query, CTEs and approved window functions** — reject ATTACH/DDL/DML/multiple statements/unauthorized tables/functions and text pretending to be policy. Typed decimal/int64/date/offset bindings must round-trip; a valid empty result still publishes evidence. Corrections/no-progress/retries share the action/run buckets.

- [ ] **Step 4: Run tests** — `uv run --locked --extra execution --group dev pytest tests/unit/test_sql_policy.py tests/unit/test_sql_bindings.py tests/integration/test_sql_action.py -q`. Record actual SQL-environment gate applicability before any live query; unknown execution cannot be replayed until reconciled/retired.

---

### Task T12: CLI grounded-SQL vertical slice and inspectable result (1A)

**Files:**
- Create: `agent/src/querivue_agent/__main__.py`
- Create: `agent/src/querivue_agent/cli.py`
- Create: `agent/tests/integration/test_cli_1a.py`
- Create: `agent/tests/acceptance/test_1a_grounded_sql.py`
- Modify: package script declaration and root `README.md` only for working commands

**Interfaces:**
- `cli.main(argv: Sequence[str] | None = None) -> int`
- `submit(request: EntryInput, *, scope: Scope, config: RunConfig) -> RunHandle` in `graph.py`
- It first persists intake and performs accounted entry assessment, then calls Authority.admit after acceptance; callers cannot supply an already-approved admission verdict. CLI invokes shared typed entry functions, not SQL/Python directly. Its scope commands are defined in the spec. JSON output includes bounded rendered final content and evidence refs; local evidence inspection resolves executed SQL/provenance through governed access.

- [ ] **Step 1: Wire init/stage-inspect/prepare/ask/status/evidence/delete** — with explicit IDs, config validation and redacted errors. Questions reach entry then Supervisor, SQL, Answer, Reviewer and final gates. Zero permitted live configuration fails preflight without spending or invoking another backend.

- [ ] **Step 2: Add a trusted fixture with regional amounts 10 and 15** — independently expected total is 25. The scripted flow must show one published query result, an independent supported draft/review, exact output reference and local trace. Wrong/stale evidence cannot be rendered as a final answer.

- [ ] **Step 3: Run integration tests** — `uv run --locked --extra providers --extra execution --group dev pytest tests/integration/test_cli_1a.py -q`, including wheel-installed `python -m querivue_agent --help` and no-Django import checks. Fake model/sandbox responses are explicitly marked scripted and never count as live acceptance.

- [ ] **Step 4: Live acceptance** — After separate authorization and applicable account/environment gates, run `uv run --locked --extra providers --extra execution --group dev pytest tests/acceptance/test_1a_grounded_sql.py -m live -q` with the approved explicit config, and capture a real isolated CSV→SQL→Answer→Reviewer result with executed SQL and trace. Until then 1A remains not_run/blocked even if code-level tests pass.

---

### Task T13: Direct routing, Chat follow-ups and linked clarification (1B)

**Files:**
- Complete: `agent/src/querivue_agent/context.py`, `supervisor.py`, `clarification.py`, `entry.py`, `dispatch.py`
- Create: `agent/tests/unit/test_context.py`
- Create: `agent/tests/unit/test_supervisor_decisions.py`
- Create: `agent/tests/integration/test_cli_1b.py`

**Interfaces:**
- Extends T07's `build_packet(role: str, run_id: UUID, scope: Scope, fence: OwnerFence) -> RoleInput`
- `decide(request: SupervisorInput, *, model: ModelGateway) -> SupervisorDecision`
- `ask_clarification(request: ClarificationInput, *, model: ModelGateway) -> ClarificationOutcome`
- `assess_entry(request: EntryInput, *, model: ModelGateway) -> EntryAssessment`
- `RoleInput` is T01's union of existing resolved role input models. Dispatch commits exact already-resolved inputs; there are no future-evidence bindings.

- [ ] **Step 1: Implement same-Chat/cutoff selection, explicit user-basis interpretation/obligation records** — bounded optional history, whole-exchange deterministic compaction and exact full-payload admission. No generated summarizer or copied child conversation. Preserve required conflicting/qualifying evidence rather than trim it to fit.

- [ ] **Step 2: Add faithful knowledge and prior-value/profile Direct reuse** — with zero analysis, no new arithmetic, complete obligations and conservative dependencies. A changed filter/rate requires compatible fresh evidence; any SQL/Python dispatch permanently sets the latch before execution. Direct is not a route after rejected/failed review.

- [ ] **Step 3: Implement one focused clarification and durable waiting/question/expiry** — entry-screened exact linked reply and once-only same-run resume. Test short valid reply, two competing replies, rejected/unavailable reply, accepted nonresolving reply, late new Chat definition, expiry and removed source. Never expand the pinned scope on resume.

- [ ] **Step 4: Run tests** — `uv run --locked --extra providers --group dev pytest tests/unit/test_context.py tests/unit/test_supervisor_decisions.py tests/integration/test_cli_1b.py -q`. Real routing quality remains a separate authorized 1B acceptance capture; structural success is not semantic correctness.

---

### Task T14: Fresh Python calls, numerical publication and PNG charts (1C)

**Files:**
- Create: `agent/src/querivue_agent/execution/python_runner.py`
- Create: `agent/src/querivue_agent/specialists/python.py`
- Create: `agent/tests/unit/test_python_declarations.py`
- Create: `agent/tests/integration/test_python_action.py`
- Create: `agent/tests/acceptance/test_1c_charts.py`

**Interfaces:**
- `run_python(request: PythonInput, *, model: ModelGateway, tools: PythonTools) -> PythonOutcome`
- `PythonTools.inspect_evidence(evidence_id: UUID) -> TabularEvidence`
- `execute_python(code: str, input_evidence_ids: list[UUID], outputs: list[OutputDeclaration]) -> OperationOutcome`
- T01 defines `OutputDeclaration` using the approved evidence/chart metadata. Tool outcomes expose only eligible published refs/diagnostics, not arbitrary guest filenames.

- [ ] **Step 1: Run each code call in a fresh child interpreter** — scratch/output mount and approved bubblewrap/cgroup/supervisor boundary. Only exact per-call selected complete evidence inputs are staged read-only. No original uploads/prepared databases, package install, network, extra model-facing file browser or host fallback.

- [ ] **Step 2: Validate simple output names and supported declarations** — reject mixed evidence/chart kinds in a nonempty call. Publish new computed Parquet values first, then chart rendering in a separate call with explicit backing. Normalize/validate PNG in the isolated validator and retain numerical evidence when rendering fails.

- [ ] **Step 3: Test no variables/files transfer between calls** — undeclared/symlink/oversize/malicious chart output, forbidden source/FD/network access, backed chart-only reuse and required-output fulfillment. A failed requested chart leads only to an explicitly authorized useful partial reviewed by Answer/Reviewer.

- [ ] **Step 4: Run tests** — `uv run --locked --extra providers --extra execution --group dev pytest tests/unit/test_python_declarations.py tests/integration/test_python_action.py -q`. Only after real Python/renderer environment proof and live authorization run `uv run --locked --extra providers --extra execution --group dev pytest tests/acceptance/test_1c_charts.py -m live -q`; capture both a valid chart and the labeled reviewed partial failure case.

---

### Task T15: Adversarial full-flow verification and guardrails (1D)

**Files:**
- Create: `agent/tests/acceptance/test_1d_guardrails.py`
- Create: `agent/tests/integration/test_dispatch_collection.py`
- Create: `agent/tests/integration/test_privacy.py`
- Modify: only the owning implementation modules implicated by failures

**Interfaces:** Consumes the full current graph/CLI and recorded outcomes; produces gate evidence keyed by exact config/build/commit. No new role or bypass API is introduced.

- [ ] **Step 1: Freeze a small duplicate-key join fixture** — with independently enumerated correct rows/totals. Supply the per-key/diagnostic evidence and query/grain provenance needed to inspect the injected defect; do not expect the tool-free Reviewer to recompute hidden source rows or see the harness's private gold. Inject wrong evidence versus a wrong draft separately; assert evidence-first versus direct-to-Answer correction, pass-2 cap and withholding after second rejection/terminal failure.

- [ ] **Step 2: Exercise invalid references, hostile cell instructions, missing required context/packet overflow** — Direct arithmetic/latch escape, unsafe entry intent, all-sibling collection and a partial fan-out launch. Successful sibling evidence survives, and dispatch order does not turn sibling outputs into authorized inputs.

- [ ] **Step 3: Inspect actual serialized local/hosted trace events** — using synthetic secret/value/path/URL sentinels. Hosted allowlists must exclude raw prompts, cells, code, credentials and private role histories. A model's safe-sounding answer cannot pass technical access assertions.

- [ ] **Step 4: Run tests** — `uv run --locked --extra providers --extra execution --group dev pytest tests/integration/test_dispatch_collection.py tests/integration/test_privacy.py tests/acceptance/test_1d_guardrails.py -m 'not live' -q`. Applicable actual OS boundary checks run separately under T09 authorization; no unsafe publication is tolerated regardless of quality rate.

---

### Task T16: Fresh-process restore, uncertain execution and deletion races (1E)

**Files:**
- Complete: `agent/src/querivue_agent/runtime/{checkpoints,recovery}.py`
- Create: `agent/tests/integration/test_crash_boundaries.py`
- Create: `agent/tests/integration/test_recovery_matrix.py`
- Create: `agent/tests/acceptance/test_1e_restart.py`

**Interfaces:**
- Completes T07's `restore_run(run_id: UUID, *, authority: Authority, checkpointer: BaseCheckpointSaver, config: RunConfig) -> GraphProjection`
- `resume_run(run_id: UUID, *, config: RunConfig) -> RunHandle`
- Reconstruction revalidates records, builds the same nine-field projection and adopts only canonical outcomes. It never treats a Redis thread as an alternate run or new Chat.

- [ ] **Step 1: Use subprocess/barrier fault injection** — before/after physical dispatch, response save, evidence registration, outcome collection, review reservation/verdict, wait acceptance, checkpoint write and final acknowledgment. Restart must reuse identical committed result/pass/call identities and charges.

- [ ] **Step 2: Test missing/stale/ahead/unavailable Redis** — incompatible schema/graph/config, owner takeover and stale completion, no state reconstruction from unauthorized artifacts, expired deadlines, source removal and clock rollback/downtime. Explicit operator restore cannot replenish budgets or enable an unproven profile.

- [ ] **Step 3: Test unresolved SQL/Python incarnations across attempts** — replacement remains blocked until exact retirement proof. Half-launched two-action tasks preserve descriptors and completed siblings even when the initial execution profile runs them serially. Test concurrent reservations separately from enabling concurrent execution.

- [ ] **Step 4: Run tests** — `uv run --locked --extra providers --extra execution --group dev pytest tests/integration/test_crash_boundaries.py tests/integration/test_recovery_matrix.py -q`; then separately authorized Redis/fresh-process `uv run --locked --extra providers --extra execution --group dev pytest tests/acceptance/test_1e_restart.py -m redis -q`. This Redis test uses a scripted sandbox/model unless also explicitly admitted to live scope; actual interrupted isolated execution needs that separate evidence. Postgres/worker cross-adapter proof is deferred to application phases, with portable canonical vectors retained.

---

### Task T17: Every approved import format and fidelity/cleanup matrix (1F)

**Files:**
- Extend: `agent/src/querivue_agent/ingestion.py`, `execution/importer.py` and their owned locks/manifest
- Create: `agent/tests/integration/test_all_formats.py`
- Create: `agent/tests/integration/test_profile_evidence.py`
- Create: deterministic fixtures under `agent/tests/fixtures/imports/` for TSV/JSON/JSONL/Parquet/XLSX/SQLite
- Create: `agent/tests/acceptance/test_1f_formats.py`

**Interfaces:** Reuses T10's inspection/preparation functions and T01's versioned settings/catalog/profile types; no format-specific ready-state or alternate publication path.

- [ ] **Step 1: Add explicit per-format readers/inspection preserving accepted behavior** — duplicate JSON keys/nested values/decimal lexemes; Parquet native type compatibility; workbook saved formula results, missing/error caches, hidden sheets, merged/range selection and date epoch; SQLite stored scalar values only with forbidden executable schema/virtual tables/views and missing-WAL failure.

- [ ] **Step 2: Test known-schema empty versus undiscoverable schema** — all-null/mixed values, leading zeros, integer/decimal precision, timezone-free/offset/DST/sub-microsecond conversions, full-range errors beyond previews and archive/parser expansion limits. ZIP/XML checks happen before workbook library parsing; no recalculation or external links.

- [ ] **Step 3: Verify profile summary/column row schema** — actual immutable locators, exact row/null/bounds, separate source key hint/check status and eight-candidate key bound. Fixture selection, name collisions, deselection, failed/successful replacement and uncertain cleanup all use the shared lifecycle.

- [ ] **Step 4: Run tests** — `uv run --locked --extra execution --group dev pytest tests/integration/test_all_formats.py tests/integration/test_profile_evidence.py -q`. Preserve source fixture/generator hashes. Only actual isolated successful imports under the approved image pass `uv run --locked --extra execution --group dev pytest tests/acceptance/test_1f_formats.py -m live -q`; unsupported cases return precise bounded failures, not a changed import meaning.

---

### Task T18: Frozen comparisons, independent oracles and reproducible report (1G)

**Files:**
- Create: `agent/src/querivue_agent/evaluation/{runner,baseline,oracle}.py`
- Create: `agent/evals/{manifest,gates}.json`
- Create: `agent/evals/development/`, separately protected `agent/evals/heldout/`
- Create: `agent/tests/unit/test_evaluation_manifest.py`
- Create: `agent/tests/integration/test_evaluation_accounting.py`
- Create: `agent/tests/acceptance/test_1g_report.py`

**Interfaces:**
- `run_suite(manifest_path: Path, *, config: RunConfig, mode: Literal['scripted', 'live']) -> EvaluationReport`
- `oracle(case: FixtureCase) -> OracleResult`
- `build_baseline(*, authority: Authority, handlers: RoleHandlers, checkpointer: BaseCheckpointSaver, config: RunConfig) -> CompiledStateGraph`
- T01 defines `FixtureCase`, `OracleResult`, `EvaluationReport` from the approved manifest/report contract. Baseline phase changes remain runtime-owned; its Answer/Reviewer stay independent and it receives no extra budget.

- [ ] **Step 1: Author/review the finite D01–D24/H01–H24 templates** — independently calculated numeric gold, scripted replies/fault points and G01–G10 assertion register. Separate generation/template families, not just seeds or renamed data. Freeze hashes/targets/configuration before held-out use; exposed held-out cases move to development. No second person/judge is claimed when unavailable.

- [ ] **Step 2: Implement manifest admission/reporting** — exact provider/renderer/codec/build/source/dirty-patch identities and failure-inclusive denominators. Schedule only the approved 8 smoke +48 development +144 held-out full flows and 72 matched Reviewer assessments; optional F3/P1 need a separately declared batch. A quota/unsupported capability makes a stage incomplete, not a selective rerun or paid fallback.

- [ ] **Step 3: Test counts 200/72, correct-outcome denominator 72/configuration** — complete-eligible denominator 66, thresholds 65/72 and 60/66, partial/invalidation separation and no-verdict Reviewer accounting. Use Decimal/Fraction/explicit enumerated/temporal references, not the tested DuckDB query or model as its own sole oracle. Restore cases keep the same original fixture/run identity under their declared policy.

- [ ] **Step 4: Run tests** — `uv run --locked --extra providers --extra comparators --extra execution --group dev pytest tests/unit/test_evaluation_manifest.py tests/integration/test_evaluation_accounting.py tests/acceptance/test_1g_report.py -m 'not live' -q`. Live scheduling remains off until every applicable gate/config/spend prerequisite and separate authorization is satisfied. Export exact forecast/actual/unknown charges, family slices, repeats, intervals, active/wall latency and all planned-versus-completed counts. Never claim a winning model or 1G completion from the scripted report.

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-11-26-standalone-agent-milestones.md`.**

Please review the plan. Which execution approach would you prefer?

- **Subagent-driven** — A fresh subagent implements each task and a fresh reviewer checks it before the next one starts, then a whole-branch review at the end. Most thorough; costs a fresh context per task and per review.
- **Native** — I implement every task myself in this session, the way this harness runs work, then one fresh reviewer on the most capable model checks the whole branch. Cheapest and fastest; no independent review until the end. Runs well with a mid-tier session model, since the plan carries the design.

**For this plan I recommend Subagent-driven**, because the tasks have well-defined interfaces and acceptance criteria, the milestone dependency map is linear (T02→T03→...→T18), and a shipped mistake in any authority/budget/checkpoint layer would cascade through all subsequent milestones. The per-task review gate is the most cost-effective safety net here. Does the plan capture what you want, and which approach should we use?