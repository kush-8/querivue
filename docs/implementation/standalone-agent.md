# Standalone Agent Implementation Plan

> **For agentic workers:** Use `superpowers:subagent-driven-development` for authorized coding, with the repository's fresh-context, smaller-model, explicit medium-reasoning worker rules. The supervisor supplies bounded specification excerpts; workers read assigned code/tests, not project documentation. Steps use checkboxes. This document authorizes no execution.

**Goal:** Implement and verify the standalone Querivue agent/CLI through PRD milestones 1A–1G, without Django, application workers or frontend changes.

**Architecture:** Approved role contracts run through private LangGraph subgraphs and trusted wrappers. SQLite transactions and immutable artifacts own effects, source validity and accounting; Redis checkpoints are rebuildable progress projections. Trusted import/SQL/Python code executes only in an admitted isolated environment, while model calls stay outside it.

**Tech Stack:** Python 3.12, uv/uv_build, Pydantic, LangChain model/message/tool/structured-output integrations, LangGraph, Redis checkpoint saver, stdlib sqlite3/argparse, LangSmith under the approved trace policy, E2B, DuckDB/Arrow/SQLGlot, approved spreadsheet and Python/chart libraries, pytest.

**Spec:** [PRD milestones](../PRD.md#agreed-agent-milestones), [shared integration](../architecture/agent-integration.md), [ingestion](../architecture/data-ingestion.md#ingestion-integration-contract), [sandbox](../architecture/sandbox-execution.md#environment-admission-and-lifecycle-contract), [SQL](../architecture/sql-specialist.md), [Python](../architecture/python-specialist.md), [Answer](../architecture/answer-specialist.md), [Reviewer](../architecture/reviewer.md), [Markdown prompts/provider policy](../architecture/role-prompts-models.md), [acceptance/evaluation](../architecture/evaluation-observability.md).

**Current checkpoint — 27 November 2026:** the [source/evidence checkpoint](standalone-checkpoint-2026-11-27.md) supersedes the old T01-complete/T02-next resume note. T02 codec implementation and fixed-vector/subprocess tests exist and pass; substantial later modules also exist. The current offline suite reports 809 passed and 10 skipped. The earliest confirmed unmet prerequisite is T03: `Ledger.open()` accepts and mutates an unsupported future-version database, while the schema-incompatibility-named test checks a different guarantee. Repair that boundary before continuing prerequisite integration; do not restart T02 or mass-mark T03–T18 complete. The plan was prepared 20 November and self-reviewed 21 November; its temporary planning document is no longer present. Architecture approvals and current user instructions carry forward. No live service, inference, sandbox or evaluation readiness is claimed. The LangChain stack remains selected; historical workflow details remain in [coding-rules.md](../coding-rules.md) subject to current user instructions. The blueprint's candidate paths were illustrative.

## Global constraints

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

## Review focus

1. Killing a process after a charged request but before acknowledgment must preserve uncertain usage and prevent a free replay: T05/T06/T16.
2. Source deletion during staging, review or final publication must deny access and serialize publication in either transaction order: T04/T05/T08/T10/T15/T16.
3. A profile, preview or chart must not invent support for unseen rows or a new quantity: T07/T08/T10/T13/T14.
4. Provider-native function signatures, hidden reasoning and retries must not lose identity/accounting on repair or restart: T06/T16.
5. A Windows/local mock that passes must not enable Linux sandbox execution without process-tree, filesystem, network and validator proof: T09/T11/T14/T15.

These are additional adversarial review priorities, not substitutes for the task tests below.

## Implementation decisions for review

Recommend one synchronous CLI/process per active run initially. It can stop in a durable waiting state and resume in another process; this is not a continuously running server. Use stdlib argparse and sqlite3 rather than adding a CLI framework or ORM. The user explicitly selected the LangChain stack on 21 November: use its chat-model integrations, message types, tool schemas and structured outputs with the approved LangGraph orchestration/private subgraphs. This corrects the earlier native-SDK/custom-HTTP proposal and aligns the existing architecture decision. First build shared authority and offline transports, then an actual gated SQL vertical slice; do not build a demo around in-memory authority and retrofit persistence later.

Keep Python 3.12 as the initial tested host/guest target. Propose declaring `>=3.12,<3.13` for the first lock rather than claiming untested future Python support; broadening it is a later compatibility change. Preserve uv_build and the existing `hello()` export until a caller explicitly needs its removal. Add no new public agent API beyond the CLI and the typed entry functions below.

Do not force a live milestone through a zero-spend conflict. If E2B/account capacity cannot meet both the approved enforcement profile and authorized cost envelope, record code/tests separately from blocked live acceptance and bring a concrete compatibility/cost decision to the user. Do not substitute local unrestricted execution or spend trial credits without authorization.

## Files and ownership

All source paths below are relative to `agent/src/querivue_agent/`. Package `__init__.py` files contain exports only where required; do not create a re-export hierarchy. This layout becomes binding only after plan review.

| Files | Responsibility / first owner |
| --- | --- |
| Existing `__init__.py`, `py.typed`; new `__main__.py`, `cli.py`, `config.py` | Preserve importability; argparse/entry/configuration, T01/T12. |
| `contracts/values.py`, `evidence.py`, `actions.py`, `responses.py`, `records.py` | Strict approved typed scalars, evidence, requests/results, state and ledger records, T01. Split by contract ownership, with no second set of role schemas. |
| `codec.py` | Approved lossless canonical bytes/hash and decode validation, T02. |
| `storage/ledger.py`, `storage/schema.sql` | SQLite connection, schema/version and short transactions, T03. |
| `storage/artifacts.py` | Immutable staged/verified bytes, authorized access and deletion, T04. |
| `runtime/authority.py`, `runtime/budgets.py` | Guarded domain transitions and pure admission/reserve arithmetic committed together, T05. |
| `runtime/models.py`, `runtime/trace.py` | Physical model-call lifecycle, token/cost accounting and protected/local versus redacted trace output, T06. |
| `providers/{google,nvidia,openrouter,cloudflare}.py` | Configure LangChain ChatGoogleGenerativeAI for F1, ChatNVIDIA for F2, ChatOpenRouter for optional P1 and ChatCloudflareWorkersAI for optional F3, T06/T18. Keep only profile/metadata mapping here; do not implement a parallel generation transport or retry/control plane. |
| `runtime/prompts.py`, `prompts/{common,entry,supervisor,sql,python,answer,reviewer,clarification,repair,baseline}.md` | Load/hash the ten approved Markdown resources without inserting runtime data, T06. |
| `graph.py`, `dispatch.py`, `entry.py`, `context.py`, `supervisor.py`, `clarification.py` | Outer graph, explicit wrappers/collection, packet construction, planning and wait handoff, T07/T13. |
| `specialists/{sql,python,answer,reviewer}.py` | Private role graphs/loops with approved tools and return unions, T08/T11/T14. |
| `runtime/checkpoints.py`, `runtime/recovery.py` | Canonical Redis projection and ledger-first restore/reconciliation, T07/T16. |
| `runtime/finalize.py` | Deterministic typed-value rendering and final publication handoff, T08. |
| `execution/sandbox.py`, `execution/validate.py` | E2B session/transfer/retirement control and isolated output validator, T09. |
| `ingestion.py`, `execution/importer.py` | Controller preparation lifecycle versus trusted guest parsing/profiles, CSV first T10; remaining formats T17. |
| `execution/sql_runner.py`, `execution/python_runner.py` | Guest SQL mailbox/connection and fresh Python-call process trees, T11/T14. |
| `evaluation/runner.py`, `baseline.py`, `oracle.py` | Frozen manifest execution, bounded alternate analysis wiring and independent deterministic gold calculations, T18. |

Other proposed files: modify `agent/pyproject.toml`, `agent/uv.lock` and root `.gitignore` for generated state only; create `agent/.python-version`, `agent/.env.example`, `agent/config/development.toml`, `agent/compose.yaml` (Redis only), `agent/sandbox/pyproject.toml`, `agent/sandbox/uv.lock`, `agent/sandbox/Dockerfile`, `agent/sandbox/environment-manifest.json`, `agent/evals/manifest.json`, `agent/evals/gates.json`, and tests listed per task. Generated state/builds/reports stay ignored. Update the root README only when the corresponding command works. Do not edit backend/frontend or add CI in phase 1.

Task path convention: `agent/...` and explicitly marked root files are repository-relative. `tests/...`, `evals/...`, `sandbox/...`, `config/...`, `uv.lock`, `.env.example` and `.python-version` are relative to `agent/`. `src/...` is also relative to `agent/`; other source-style paths such as `runtime/...`, `contracts/...` and `cli.py` are relative to `agent/src/querivue_agent/`. Brace lists enumerate individual exact files. The supervisor resolves this convention into full assigned paths in every worker handoff.

## Dependency and build strategy

Public PyPI version metadata was read on 20 November, with the requested LangChain integrations checked 21 November 2026. These are candidate pins, **not a resolved compatible lock or security certification**. T01/T06/T09/T14/T17 resolve and test their owned group; a changed candidate is recorded with the reason and compatibility result before dependent acceptance. No resolution/install ran during planning.

| Group | Dated candidates / use |
| --- | --- |
| Core | pydantic 2.14.4; langchain 1.5.2; langchain-core 1.8.4; langgraph 1.2.24; langgraph-checkpoint-redis 0.6.0; redis 8.1.0. |
| Canonical codec | rfc8785 0.1.4 (metadata checked 21 November). Use its JCS implementation after Querivue's lossless typed conversion; stdlib sorted JSON is not an RFC 8785 substitute. |
| Provider extra | langchain-google-genai 4.5.2 for F1 using ChatGoogleGenerativeAI. Native SDK versions are resolved/pinned with the integration and used underneath it, rather than a separate generation stack. |
| Comparator extra | langchain-nvidia-ai-endpoints 1.5.0, langchain-openrouter 0.3.0 and langchain-cloudflare 0.4.3, for their already approved optional configurations. Install/enable only under the owning task's scope; account/schema/tokenizer checks still gate calls. |
| Execution/test extra and guest | duckdb 2.0.0; pyarrow 26.0.1; sqlglot 30.33.0; e2b 2.64.0 on controller only. Exactly the same DuckDB build in preparation and analysis; round-trip typed artifacts with the pinned Arrow build. |
| Full formats | openpyxl 3.1.5; defusedxml 0.7.1. Native JSON/decimal/SQLite support uses stdlib where needed for the agreed semantics. |
| Python/charts | pandas 3.1.1; plotly 7.1.0; kaleido 1.5.2; pillow 13.0.0. The guest image separately pins Chrome/Chromium and OS isolation tools; no runtime download. |
| Dev / optional hosted trace | pytest 9.2.0; langsmith 0.15.1 candidate for explicit redacted hosted export. LangSmith may also arrive through LangChain dependencies; installation does not authorize transmission. Full-payload auto-tracing is off. |

Use optional `providers`, `comparators`, `execution`, `hosted-trace` extras and the `dev` dependency group. Keep guest runtime dependencies in its own lock without model credentials/SDKs, Redis or Django. Host-side execution dependencies support trusted fixture/schema tests, not a fallback execution path. Store the effective wheel/image/browser/syscall/validator identities in the environment manifest, including platform and lock hashes. Version strings alone do not prove equivalent builds. If latest DuckDB/Arrow or another candidate fails a required fixture, halt its acceptance and resolve the concrete compatibility change instead of coercing data.

Redis Compose is a standalone-agent support service, not application deployment: Redis 8 JSON/search capability, durable volume, loopback-only binding and explicit protected connection configuration; no TTL on retained graph progress. T07 must verify installed modules and storage/restart behavior. Docker executable availability was observed; daemon health, images and services were not checked or started.

Official API leads: [LangGraph checkpoints](https://docs.langchain.com/oss/python/langgraph/persistence), [subgraphs](https://docs.langchain.com/oss/python/langgraph/use-subgraphs), [Redis saver](https://github.com/redis-developer/langgraph-redis), [E2B network switch](https://docs.e2b.dev/network/internet-access), [Google SDK](https://github.com/googleapis/python-genai), [Google token counting](https://ai.google.dev/gemini-api/docs/tokens), [Plotly rendering](https://plotly.com/python/static-image-export/). Public versions use `https://pypi.org/pypi/<package>/json`. These support API research, not our build/enforcement claims. In particular graph interruption may re-enter a node, so effects still require ledger idempotency; Redis saver setup creates its search structures; E2B command timeout/kill is not proof of full-tree retirement; Kaleido needs an external compatible browser.

The approved codec specifically requires JCS, including its key ordering and number serialization. Prefer the small [RFC 8785 implementation](https://github.com/trailofbits/rfc8785.py) to a new home-grown canonicalizer. Exact analytical integers/decimals/floats are encoded by the approved tagged wire layer first; the library then canonicalizes the resulting validated envelope. Its accepted input domain and error behavior are checked by T02 vectors, not inferred from package import success.

LangChain primary references checked 21 November: [model/structured-output interfaces](https://docs.langchain.com/oss/python/langchain/models), [Google integration](https://docs.langchain.com/oss/python/integrations/chat/google_generative_ai), [NVIDIA integration](https://docs.langchain.com/oss/python/integrations/chat/nvidia_ai_endpoints), [OpenRouter integration](https://docs.langchain.com/oss/python/integrations/chat/openrouter) and [Cloudflare-maintained integration](https://github.com/cloudflare/langchain-cloudflare). These document available interfaces, not compatibility with every selected model/schema or our accounting/serialization guarantees. Provider SDKs remain implementation dependencies underneath these integrations; narrowly required token/metadata access may use a native client without a parallel generation path.

## Shared interface vocabulary

T01 defines the exact approved models under these implementation names; a name below is a Python placement/alias, not a new product field. Model definitions use the linked authoritative fields, strict unknown-field rejection, discriminated variants and canonical UUID/value rules. Existing component names are retained where specified. Task tests carry representative valid and invalid payloads from those contracts.

| Type / owner | Meaning |
| --- | --- |
| `Scope`, `OwnerFence` — common; `RunConfig` — config | Validated Project/Chat/run scope; current owner/generation/attempt/revision guards; finite configuration and identities. They are runtime inputs, not model-editable state patches. |
| `TypedScalar` — values; `EvidenceRef`, `EvidenceCandidate` — evidence; `PreparedCandidate`, `PreparedSnapshot` — catalog | Approved exact scalar, governed evidence identity and complete validated candidate publication sets. A candidate is never eligible evidence. |
| `SQLAction`, `PythonAction` — actions; `SQLInput`, `PythonInput` — inputs; `SQLOutcome`, `PythonOutcome` — responses | Existing component request/resolved packet/terminal union, including genuine error refs, coverage and limitations. |
| Role inputs — inputs; `SupervisorDecision` — control; `EntryAssessment` — entry; Answer/Review/Clarification outcomes — responses | Concrete `SupervisorInput`, `AnswerInput`, `ReviewInput`, `ClarificationInput`, `EntryInput`, `AnswerOutcome`, `ReviewAssessment`, `ClarificationOutcome` and existing role-specific output discriminators. No separate route selector or added parent field. |
| `ModelRequest`, `ModelCompletion`, `ModelReservation`, `IntakeReceipt`, `IntakeAdmission`, `AdmissionReceipt`, `QueueReceipt`, `ReviewReservation`, `LinkedReply`, `ResumeReceipt`, `FinalCandidate`, `FinalResult`, `DeletionReceipt` — records | Typed implementation names for approved durable request/response/reservation/receipt families. IntakeReceipt identifies the durable pre-run entry chain and its owner fence; initial screening is accounted before a run exists. Trust fields are supplied by runtime and checked at every guarded transition. |
| `RunState`, `GraphProjection`, `RunHandle` — state | Exactly nine-field checkpointable parent projection; version/run/revision-bound serialized checkpoint; durable CLI run identity/status/reference, not a live graph/process handle. |
| `Role` — common; `RoleInput`, `RoleHandlers` — inputs; `RoleOutcome` — responses | Finite role discriminator; unions of the approved role inputs/results; runtime-built mapping from Role to `Callable[[RoleInput], RoleOutcome]`. Bound handlers own their private child graph/model/tool dependencies. No user-configured executable import or arbitrary plugin registry. |
| `ImportSettings`, `ImportPreview`, `TableCatalog` — catalog; `TabularPreview`, `TabularEvidence`, `OutputDeclaration` — evidence | Existing import confirmation/catalog/typed-preview/evidence/Python output-declaration contracts. SQL evidence inspection includes its authorized runtime relation; other roles do not inherit SQL access from the generic evidence metadata. |
| `FixtureCase`, `OracleResult`, `EvaluationReport` — evaluation | Approved case obligations/bytes/schema/oracle/split/fault metadata and failure-inclusive report schema, with exact fixture data authored/frozen by T18. |
| `BudgetSnapshot`, `ReservationRequest`, `BudgetDecision`, `ClockReading` — budgets | Approved intersecting counters, physical exposures, reserves and active/wall/lease clock inputs. Monetary amounts are decimal strings/Decimal, never binary money floats. |
| `SandboxTicket`, `OperationRequest`, `OperationOutcome`, `RetirementProof` — records; `StagedArtifact`, `ArtifactRef`, `ValidationReceipt` — artifacts | Existing sandbox incarnation, durable operation, retirement and artifact lifecycle identities, with complete digests/scope. No uploaded executable schema or raw path can create one. |

No task may introduce an undefined replacement type/name. An executor needing a contract field absent from the linked spec returns the question to the supervisor before dependent code. It does not silently add fields or mark a placeholder complete.

`RoleHandlers`, `Authority`, `ModelGateway`, `SQLTools`, `PythonTools`, checkpointers and native client objects are runtime-only dependencies, never serialized contract/state fields. Handlers are bound by trusted composition code. Their union annotations do not allow a role wrapper to accept another role's input/result variant.

## Milestone dependency map

`T01 → T02 → T03 → T04 → T05 → T06 → T07 → T08`; then `T09 → T10 → T11 → T12 (1A) → T13 (1B) → T14 (1C) → T15 (1D) → T16 (1E) → T17 (1F) → T18 (1G)`.

This is a conservative review order, not a promise every task needs every preceding implementation detail. Until the shared interfaces are accepted, run one coding worker at a time. Independent bounded work may be delegated later only with disjoint ownership and frozen consumed interfaces; there are no planning/research subagents.

Passing a task means its declared code-level checks passed. A milestone also needs its actual acceptance evidence. Report `not_run`, `blocked`, `passed` or `failed` per capability rather than treating an offline mock or unavailable paid service as a pass.

## Task checklist

Commands below run from `agent/`. Every task starts by inspecting its exact owned files plus supervisor-supplied spec excerpts, and ends with supervisor diff/integration review. Follow the current [coding rules](../coding-rules.md): implement the approved specification on `main`, then use selective high-value verification; no test-first/TDD workflow or exhaustive field-by-field tests of library behavior. Commit only reviewed task files when committing is authorized; never stage unrelated edits.

### T01 — Strict contracts, configuration and package test harness

**Completed — 24 November 2026.** All shared vocabulary above has concrete strict definitions, resolved role packets preserve actual supplied material and source lineage, and the parent projection has exactly nine fields. `config.py` loads an explicit nonsecret TOML file, preserves unknown settings as missing, isolates credentials from public serialization and refuses incomplete live settings. The canonical [development configuration](../../agent/config/development.toml) is offline; pending operational/provider/build choices were not silently adopted.

Core/dev pins are frozen for Python 3.12: Pydantic 2.14.4, LangChain 1.5.2, langchain-core 1.8.4, LangGraph 1.2.24, langgraph-checkpoint-redis 0.6.0, Redis 8.1.0 and pytest 9.2.0. The lock resolves 53 packages without changing the approved candidates. Offline SDK compatibility covers private-child wrapper mapping, message/tool signatures, strict local tools and RedisSaver API imports; it is not Redis-server or live-provider proof. Numeric defaults come from the approved [shared/run ceilings](../architecture/agent-integration.md#candidate-shared-and-sql-budgets), [context caps](../architecture/agent-integration.md#candidate-selector-and-preview-caps), [Python limits](../architecture/python-specialist.md#provisional-development-evaluation-ceilings), [Answer limits](../architecture/answer-specialist.md#provisional-development-ceilings) and [Reviewer limits](../architecture/reviewer.md#provisional-development-ceilings). Explicit zero spending caps retain the approved no-paid-spend profile; unset timeouts/builds/accounts remain blockers for live enablement.

Verification: the required locked scalar/config command and retained unit suite pass; all 63 serializable vocabulary types generate JSON Schemas, with `RoleHandlers` deliberately runtime-only. Source distribution/wheel contents include all contract modules, `py.typed` and the canonical offline TOML. The wheel was installed into a separate environment constrained to locked runtime versions; isolated Python imports, legacy `hello()`, packaged configuration and nine-field state passed with socket access denied. Missing cached public wheels were downloaded at those fixed versions for installation; no model, Redis, sandbox or other runtime service was called. The example installs at `<venv>/development.toml` through uv_build's data scheme. One nonblocking Pydantic field-name warning remains for the wire field `ToolDeclaration.schema`.

Per the user's correction, implementation follows SDD on `main`, with simple focused code and selective verification. Redundant per-field/library-behavior test matrices were removed; test count is not an acceptance target. Runtime ledger transitions, canonical encoding, execution isolation, provider calls and measured evaluation remain T02 onward. Earlier partial progress notes below are historical and superseded by this completion record.

**Progress — 22 November 2026:** The initial scalar/test-harness slice is implemented: eleven strict scalar variants and canonical runtime UUID validation, Pydantic 2.14.4/pytest 9.2.0 resolved in `uv.lock`, and live/Redis tests excluded by default. All 119 scalar tests pass on Python 3.12.1; wheel build/contents and marker exclusion are verified. Focused code review passed. Full T01 remains incomplete: configuration, parent/action/result/evidence/ledger models, remaining core dependencies and their acceptance tests are outstanding. No live execution or milestone acceptance is claimed.

**Second slice — 22 November 2026:** Added strict `SQLSucceeded`, `SQLBlocked`, `SQLFailed`, discriminated `SQLOutcome`, and `ToolError` in `contracts/responses.py`, reusing scalar UUID/Unicode validation. The response suite passes 86 tests; all unit tests pass (205). This chat reviewed the implementation directly. Error messages use a tunable implementation ceiling of 2,048 characters and reject excess instead of truncating. Runtime sanitization, error provenance and evidence authorization remain separate enforcement work. Other T01 contracts/configuration remain outstanding; no dependencies added or live calls made.

**Third slice — 23 November 2026:** Added `PythonSucceeded`, `PythonBlocked`, `PythonFailed` and discriminated `PythonOutcome`, with strict unique evidence/chart UUID lists and the approved empty-list allowance. A fresh `gpt-5.6-sol` medium worker implemented the slice; this chat reviewed source/tests against the approved terminal-return contract. All 269 unit tests pass (64 added). Runtime objective/required-output fulfillment, provenance and authorization remain separate enforcement work. Full T01 remains partial.

**Fourth slice — 23 November 2026:** Added SQL `InspectTableRequest`, `PreviewRowsRequest`, `InspectEvidenceRequest` and `ExecuteQueryRequest` in `contracts/tools.py`, with 56 tests in `tests/unit/test_tools.py`. All 325 unit tests pass; supervisor reviewed the fresh `gpt-5.6-sol` medium worker's changes. Models validate shape only; SQL policy, access, source validity and budgets remain runtime work. Full T01 remains partial.

**Consolidated contract batch — 23 November 2026:** Recovered the interrupted shared-contract work and fixed the remaining SQL success-reference UUIDv4 restriction. Canonical supplied references retain their version; new action identities remain UUIDv4. Added missing evidence/chart declaration and Python-request tests, then structured draft/citation content, Answer/Reviewer outcomes, Direct/Clarification actions and outcomes, identity-free component requests and committed tasks with bounded prerequisites/new-action/retry proposals. `contracts/content.py` owns reusable content/target models; consumers import from owning modules. Local IDs use nonblank UTF-8 text capped at 64 bytes; literal text spans are nonempty, preserve whitespace/codepoints and have the approved UTF-8 byte ceiling. The approved support targets/value formats and their field semantics remain in the component guides; implementation field names map to those contracts without adding lookup or execution capability. Root directly reviewed four fresh `gpt-5.6-sol` medium workers. Full unit suite: **641 passed**; offline sdist/wheel build and contract-module/`py.typed` contents passed; `hello` import preserved. No dependencies or services added. Runtime reference eligibility, authorization, exact packet binding, semantic completeness, retries and publication remain unimplemented. `TaskProposal` is not a complete `SupervisorDecision`: whole-queue, obligation and interpretation validation remain outstanding. Full T01 still needs resolved inputs, parent/published-evidence/durable/accounting/configuration schemas and remaining dependency acceptance. Runtime-settings proposals await user review; all live gates remain closed.

**Files:** `agent/pyproject.toml`, `uv.lock`, `.python-version`, `config/development.toml`, `src/querivue_agent/config.py`; `contracts/{values,common,artifacts,catalog,evidence,content,actions,responses,tools,control,entry,budgets,inputs,state,manifests,records,evaluation}.py`; focused contract/config/compatibility suites. Existing `__init__.py`/`py.typed` behavior is preserved. Type ownership is mapped above; no barrel or alternate role schema was introduced.

**Interfaces:** Produces all shared vocabulary above, using existing approved payload fields/unions; `load_config(path: Path, env: Mapping[str, str]) -> RunConfig`. Consumers import models from their owning contract module, not a barrel. Config excludes secret values from hashes/serialization and defaults live execution to disabled.

- [x] Resolve/freeze core and dev candidates for Python 3.12; record compatibility results and the approved numeric configuration sources. No runtime service contact.
- [x] Register `live` and `redis` pytest markers with both excluded by default; explicit `-m` selection is required for those test groups. Test-module import/collection must not start services, download browsers or call providers.
- [x] Add `test_exact_scalar_and_extra_fields`: preserve int64 `9223372036854775807`, decimal `1.00` scale and offset timestamp; reject overflow, nonfinite values, malformed UUIDs and model-supplied owner/budget fields. Verify action/result discriminators and exactly nine parent fields with focused protocol checks.
- [x] Implement strict models/config and assert missing provider/build/accounting settings cannot become zero, unlimited or an implicit live default. Check original `hello()` import still works and packaged data is included in the wheel.
- [x] Run `uv run --locked --group dev pytest tests/unit/test_contracts.py tests/unit/test_config.py -q`; all assertions pass. Inspect the lock/wheel contents before reviewing this task.

### T02 — Lossless canonical encoding and compatibility vectors

**Files:** Create `src/querivue_agent/codec.py`, `tests/unit/test_codec.py`, `tests/fixtures/golden/canonical.json`.

**Interfaces:** Consumes validated contract records; produces `canonical_bytes(record: Mapping[str, object]) -> bytes`, `record_digest(family: str, version: int, record: Mapping[str, object]) -> str`, `decode_record(data: bytes, model: type[T]) -> T` where `T` is a strict contract model. Family/version domain separation and own-hash exclusion follow the approved codec; no general serializer for arbitrary Python objects.

- [ ] Add fixed expected-byte/hash vectors for field order, missing/null, Unicode, signed/unsigned boundaries, decimal scale, finite float bits including negative zero, temporal offsets/microseconds, ordered/set lists and own-hash exclusion.
- [ ] Resolve/pin rfc8785, implement the approved tagged wire conversion using stdlib decimal/struct/hash where appropriate, then canonicalize with `rfc8785.dumps`. Reject duplicate keys before schema validation. Do not use default `str()`/float JSON or sorted stdlib JSON as the lossless/JCS policy. Record exact codec/library version.
- [ ] Run `uv run --locked --group dev pytest tests/unit/test_codec.py -q`, including a fresh subprocess decoding/re-encoding the same vectors. Changed coverage/config/dependency must change the appropriate digest; credentials must not enter stored request bytes.

### T03 — SQLite ledger and deterministic transaction ownership

**Files:** Create `storage/ledger.py`, `storage/schema.sql`, `tests/unit/test_ledger.py`, `tests/integration/test_ledger_races.py`.

**Interfaces:** `Ledger.open(path: Path) -> Ledger`; `Ledger.transaction() -> ContextManager[sqlite3.Connection]`; `Ledger.close() -> None`. Connection/schema ownership stays here; domain transitions are T05. Use explicit short `BEGIN IMMEDIATE` writes, foreign keys, WAL and full durability on the supported local filesystem; busy waits are finite and errors remain visible.

- [ ] Create versioned tables/constraints for scopes/sources/preparation, runs/owners, immutable payloads/dependencies, intake/wait/reply, tasks/actions/outcomes, invocation/physical request, operation/incarnation, draft/review, accounting/progress and final receipts. Store canonical payload bytes/digests and guard columns in the same transaction, not independent competing representations.
- [ ] Add tests for one admitted run/intake, unique invocation/operation mapping, unique `(run_id, review_pass)`, one accepted reply/question, one final result/run and exact duplicate-versus-conflicting-content handling.
- [ ] Add two-connection barrier tests: competing write/owner takeover yields one committed authority; rollback leaves no partial queue/record. No external model/file-transfer/Redis wait occurs inside a transaction. Schema incompatibility fails explicitly.
- [ ] Run `uv run --locked --group dev pytest tests/unit/test_ledger.py tests/integration/test_ledger_races.py -q`; verify persisted bytes/revisions after reopen. Do not implement a Postgres adapter or ORM.

### T04 — Immutable artifacts, quarantine and dependency invalidation

**Files:** Create `storage/artifacts.py`, `tests/unit/test_artifacts.py`, `tests/integration/test_artifact_deletion.py`.

**Interfaces:** `ArtifactStore.stage(source: BinaryIO, scope: Scope, byte_limit: int) -> StagedArtifact`; `verify(candidate: StagedArtifact, expected_sha256: str) -> ValidationReceipt`; `read(ref: ArtifactRef, scope: Scope) -> BinaryIO`; `cleanup(ref: ArtifactRef, proof: RetirementProof) -> None`. Only T05 registers eligibility; staging/verified bytes alone are not published.

- [ ] Implement bounded same-filesystem quarantine/atomic move and complete-byte hash verification. Paths are controller-owned under the resolved state root; model-visible refs are opaque. Reject traversal, symlink/reparse escapes, device files and oversize/partial copies.
- [ ] Test both orders of tombstone versus registration/read, corrupt/missing artifact, failed cleanup and retained successful result. Authorized readers recheck transitive dependencies; deletion denies access before physical removal.
- [ ] Run `uv run --locked --group dev pytest tests/unit/test_artifacts.py tests/integration/test_artifact_deletion.py -q`. Process uncertainty prevents cleanup; lost registration acknowledgment reuses the same immutable bytes/ref.

### T05 — Guarded authority transitions, budgets and clocks

**Files:** Create `runtime/authority.py`, `runtime/budgets.py`, `tests/unit/test_budgets.py`, `tests/integration/test_authority.py`, `tests/integration/test_budget_races.py`.

**Interfaces:** `Authority.admit(IntakeAdmission) -> AdmissionReceipt`; `commit_decision(run_id: UUID, proposal: SupervisorDecision, fence: OwnerFence) -> QueueReceipt`; `reserve_model(request: ModelRequest, fence: OwnerFence) -> ModelReservation`; `publish_evidence(candidate: EvidenceCandidate, fence: OwnerFence) -> EvidenceRef`; `commit_preparation(candidate: PreparedCandidate, fence: OwnerFence) -> PreparedSnapshot`; `reserve_review(request: ReviewInput, fence: OwnerFence) -> ReviewReservation`; `accept_reply(reply: LinkedReply, fence: OwnerFence) -> ResumeReceipt`; `finalize(candidate: FinalCandidate, fence: OwnerFence) -> FinalResult`; `delete_dataset(dataset_id: UUID, scope: Scope) -> DeletionReceipt`. Budget calculation is `check_reservation(current: BudgetSnapshot, request: ReservationRequest, now: ClockReading) -> BudgetDecision`, committed only under the same authority guards.

The same Authority owns `accept_model(reservation_id: UUID, completion: ModelCompletion, fence: OwnerFence) -> ModelCompletion`, `record_operation(request: OperationRequest, fence: OwnerFence) -> UUID`, `record_retirement(proof: RetirementProof, fence: OwnerFence) -> None` and `register_outcome(action_id: UUID, outcome: RoleOutcome, fence: OwnerFence) -> UUID`. These return the existing canonical completion/receipt identity on exact replay and reject conflicting content. No gateway/controller writes domain state through raw Ledger SQL. Retirement/cleanup reconciliation can finish an invalidated run without reopening source access or permitting publication.

Scope/intake/control entry points are `initialize_scope(state_root: Path) -> Scope`, `record_intake(request: EntryInput, scope: Scope) -> IntakeReceipt`, `claim_run(run_id: UUID, owner_id: UUID) -> OwnerFence`, `renew_lease(fence: OwnerFence) -> OwnerFence`, `read_projection(run_id: UUID, scope: Scope) -> GraphProjection`, `reserve_dispatch(task_id: UUID, fence: OwnerFence) -> Task`, `commit_wait(action_id: UUID, outcome: ClarificationOutcome, fence: OwnerFence) -> UUID` and `commit_review(review_id: UUID, assessment: ReviewAssessment, fence: OwnerFence) -> UUID`. `Task` is the existing committed-task model in actions.py. IntakeReceipt's fence is intake-scoped; run admission creates the separate run scope. These are implementations of approved transitions, not added model tools. Waiting/review receipts commit before visibility or follow-on dispatch.

- [ ] Implement whole-proposal validation/commit receipts, expected revision/attempt/generation checks and source/deadline guards at every effect boundary. A failed proposal changes none of its memory/queue/accounting projection.
- [ ] Add tests for all approved finite buckets/reserves, no refund on unknown dispatch/review/crash, no reset on retry/new action/process, once-only progress/settlement and clock rollback/downtime handling. Test simultaneous reservations cannot spend protected terminal capacity.
- [ ] Test source-delete/finalize and accepted-reply/expiry races in both orders. Unknown physical completion remains reserved; two nonrefundable review slots cannot become three through retry or changed IDs.
- [ ] Run `uv run --locked --group dev pytest tests/unit/test_budgets.py tests/integration/test_authority.py tests/integration/test_budget_races.py -q`. No external effects while holding the ledger write lock.

### T06 — Markdown prompts, accounted model gateway and trace boundary

**Files:** Create `runtime/{models,prompts,trace}.py`, ten `prompts/*.md` resources, `providers/{google,nvidia,openrouter,cloudflare}.py`, `.env.example`, `tests/unit/test_prompts.py`, `tests/unit/test_gateway.py`, `tests/unit/test_trace_redaction.py`, `tests/integration/test_provider_protocols.py`. Add provider/comparator/optional trace groups and lock changes only as their owning routes are implemented.

**Interfaces:** `load_prompt(role: str) -> str` hashes approved common plus role resources; `ModelGateway.invoke(request: ModelRequest, fence: OwnerFence) -> ModelCompletion` is the only graph-facing model call and invokes a configured LangChain BaseChatModel. Provider modules configure maintained integration classes and exact profiles; token/metadata handling stays behind the gateway. Use LangChain SystemMessage/HumanMessage/AIMessage/ToolMessage and StructuredTool/schema bindings at this boundary, with supported explicit structured output and raw AIMessage metadata retained. `trace_event(event: Mapping[str, object], *, hosted: bool) -> None` enforces the approved allowlist; full local records remain protected artifacts, not hosted payloads.

- [ ] Copy the ten approved Markdown templates verbatim, preserving the separate JSON-data/native schema/tool layers. Test source text containing `## Rules` cannot alter template bytes/hash or become trusted instructions.
- [ ] Bind only each role's approved tools through LangChain schemas and keep invocation under existing runtime guards/counters. Use the integration's supported structured-output mode while preserving strict local validation. The approved outer graph/private loops retain their transitions; framework retry/fallback/tool auto-execution cannot add unaccounted calls or bypass review. F1 explicitly selects the Gemini Developer API without environment-driven switching to a billed cloud backend.
- [ ] Implement reserve-before-send, physical IDs, full payload/token/output admission, strict whole-response JSON/duplicate-key/schema/reference validation, bounded repair and one canonical completion adoption. No Markdown/substring scraping. Disable SDK auto function execution and implicit SDK/HTTP retries; expose each actual replacement to T05 accounting. Preserve provider thought signatures/call linkage in role-local history. Verify the token counter covers the exact system/schema/tool/history payload; character heuristics are not an admission counter. Account preflight/token-count requests separately under finite intake/operator controls; unsupported or unavailable counting blocks dispatch.
- [ ] Use mocked integration/SDK transcripts to test timeout/429/unknown completion, malformed/refused/truncated output, changed served identity, hidden reasoning and tool-call schema variants. Assert one authorized physical request causes exactly one wire call, including on 429/parser errors; retry setting semantics can differ by integration. Preserve Google thought signatures and role-local message metadata through canonical checkpoint serialization without arbitrary object/pickle restoration. Do not double-count reasoning already included in normalized output usage; missing vendor usage remains unknown even if a wrapper presents zeros. Unsupported full-payload token counting/protocol blocks dispatch.
- [ ] Add synthetic credential/question/cell/path/URL sentinels; inspect actual hosted serialization, stdout and exceptions. Automatic raw LangGraph/LangSmith tracing stays off. Optional hosted export has a separate explicit activation/cost gate.
- [ ] Run `uv run --locked --extra providers --group dev pytest tests/unit/test_prompts.py tests/unit/test_gateway.py tests/unit/test_trace_redaction.py tests/integration/test_provider_protocols.py -q`. No real request. Optional F2/F3/P1 remain disabled until their own tokenizer/schema/account checks pass.

### T07 — Outer graph, private wrappers and Redis projection

**Files:** Create `graph.py`, `dispatch.py`, `entry.py`, `context.py`, `supervisor.py`, `runtime/{checkpoints,recovery}.py`, `compose.yaml`, `tests/unit/test_packets.py`, `tests/integration/test_graph.py`, `tests/integration/test_checkpoints.py`.

**Interfaces:** `build_graph(*, authority: Authority, handlers: RoleHandlers, checkpointer: BaseCheckpointSaver, config: RunConfig) -> CompiledStateGraph`; `build_packet(role: str, run_id: UUID, scope: Scope, fence: OwnerFence) -> RoleInput`; `restore_run(run_id: UUID, *, authority: Authority, checkpointer: BaseCheckpointSaver, config: RunConfig) -> GraphProjection`. Use the public `langgraph.checkpoint.base.BaseCheckpointSaver` and `langgraph.graph.state.CompiledStateGraph` types; production composition passes RedisSaver, while explicitly labeled offline tests may supply an in-memory/fake saver. Bound private handlers are assembled by trusted runtime code; unavailable roles fail explicitly until their owning task implements them. Do not create dummy production agents to make this task green.

- [ ] Compile the approved serial control/mandatory edge graph with wrapper-mapped private subgraphs; keep model/tool side effects behind T05/T06. Parent updates replace only runtime-owned projections, with approved identity-aware collection rather than blanket dictionary/message reducers.
- [ ] Set checkpoint `thread_id` from run UUID, never Chat UUID; use role invocation/attempt-bound child namespaces and test no private-history leakage. Serialize/validate canonical tagged values with pickle fallback disabled. Incompatible/untrusted checkpoints never instantiate arbitrary Python objects.
- [ ] Configure RedisSaver setup against Redis 8 JSON/search with persistence and no TTL, then test saved/read state, missing/stale/ahead projection and unavailable saver. Ledger reconciliation gates graph advancement; an interrupt re-entering its node cannot repeat a committed effect or change the waiting question.
- [ ] Unit/scripted checks: `uv run --locked --group dev pytest tests/unit/test_packets.py tests/integration/test_graph.py -q`. Separately authorized local Redis check: `uv run --locked --group dev pytest tests/integration/test_checkpoints.py -m redis -q`. Missing Redis is explicitly not_run/blocked, never an in-memory pass for 1E.

### T08 — Typed drafting, independent review and final rendering

**Files:** Create `specialists/answer.py`, `specialists/reviewer.py`, `runtime/finalize.py`, `tests/unit/test_rendering.py`, `tests/integration/test_review_flow.py`.

**Interfaces:** `draft(request: AnswerInput, *, model: ModelGateway) -> AnswerOutcome`; `review(request: ReviewInput, *, model: ModelGateway) -> ReviewAssessment`; `render(candidate: FinalCandidate) -> str`. Wrappers commit immutable candidate/pass/verdict identities and call `Authority.finalize`; rendering cannot grant eligibility or perform new calculations.

- [ ] Implement strict span/value/claim/chart validation and deterministic approved display formatting of supplied cells. Test shortened/invisible cells, incompatible coverage, invalid chart backing and new arithmetic are rejected/blocked rather than invented.
- [ ] Script independent full drafting/review packets; test first draft-only versus evidence/mixed rejection, second rejection, terminal failure on either pass, late approval and lost acknowledgment. Original obligations and actual partial gaps reach Reviewer.
- [ ] Run `uv run --locked --group dev pytest tests/unit/test_rendering.py tests/integration/test_review_flow.py -q`. Exactly one eligible final result or bounded notice; no warning banner attached to a rejected draft.

### T09 — Exact environment, sandbox controller and validator gates

**Files:** Create `execution/sandbox.py`, `execution/validate.py`, `sandbox/{pyproject.toml,uv.lock,Dockerfile,environment-manifest.json}`, `tests/unit/test_sandbox_protocol.py`, `tests/live/test_environment_gates.py`. Add controller execution extra only as needed. The guest has no credentials/provider clients.

**Interfaces:** `SandboxController.admit(scope: Scope, manifest_id: str) -> SandboxTicket`; `execute(ticket: SandboxTicket, request: OperationRequest) -> OperationOutcome`; `retire(ticket: SandboxTicket) -> RetirementProof`; `validate_outputs(ticket: SandboxTicket, request: OperationRequest) -> tuple[ValidationReceipt, ...]`. The controller records incarnation/operation identity before waiting; these methods do not publish.

- [ ] Build/version the Linux image and lock after build scope is authorized. Preinstall approved packages, browser, bubblewrap/cgroup-v2 policy and protected supervision; record actual effective controls/digests separately from requested settings. Match producer/consumer DuckDB and codec/profile versions.
- [ ] Mock command/file transports to test partial launch, disconnect/reconnect, traversal/symlink/oversize files, validator failure and unconfirmed retirement. Unreachable work retains reservations; a command timeout or SIGKILL acknowledgment alone is not whole-tree proof.
- [ ] Before live generated execution, verify applicable read-only/namespace/FD/syscall/network/process-tree/CPU/RAM/disk/expanded-output/validator controls on the exact image and provider. Test an escaping child and malicious output parser separately. No unsupported control is silently disabled.
- [ ] Run offline `uv run --locked --extra execution --group dev pytest tests/unit/test_sandbox_protocol.py -q`. Only with separate live/spend scope: `uv run --locked --extra execution --group dev pytest tests/live/test_environment_gates.py -m live -q`. An unexecuted or failed environment gate blocks that capability.

### T10 — CSV inspection, confirmation and atomic preparation

**Files:** Create `ingestion.py`, `execution/importer.py`, `tests/unit/test_import_lifecycle.py`, `tests/integration/test_csv_preparation.py`, `tests/fixtures/imports/meaning.csv`; extend the owned ledger/config tests as needed. Guest parsing runs only through T09's approved execution profile.

**Interfaces:** `inspect_upload(upload_id: UUID, scope: Scope) -> ImportPreview`; `prepare_dataset(dataset_id: UUID, settings: ImportSettings, scope: Scope) -> PreparedSnapshot`. T01 owns strict `ImportSettings`/`ImportPreview` contract models. The controller owns staging/attempt/confirmation and guarded commit; the guest importer returns only a complete validated `PreparedCandidate` through T09/T04. An import preview is not an eligible Dataset.

- [ ] Stage immutable bytes, enforce upload cap and type-specific entry admission, inspect in isolation, return bounded preview/settings proposals and release the inspection session. Persist preview/settings/confirmation identity; do not pass full uploads to an entry model.
- [ ] Implement CSV with exact quoted-empty/unquoted-null/whitespace and meaningful-leading-zero behavior. Validate every selected row/type, stable column naming and typed profiles; bad data beyond preview cannot disappear. Unsupported parser fidelity blocks readiness rather than enables ignore-errors.
- [ ] Test source header `a,a,a_2` maps to `a,a_3,a_2`, copied logical values remain unchanged, exact row/null counts and typed locators resolve. Test conflicting attempts/settings, duplicate delivery, deletion/replacement race and crashes before/after transfer/ready commit. A failed replacement leaves the original usable.
- [ ] Run `uv run --locked --extra execution --group dev pytest tests/unit/test_import_lifecycle.py tests/integration/test_csv_preparation.py -q` using trusted deterministic fixtures and explicit simulated controller transports. Separately capture real isolated preparation evidence only after the T09 capability gate. All other accepted formats remain explicitly not enabled until T17, not silently interpreted as CSV.

### T11 — Positive SQL policy, persistent action runner and evidence handoff

**Files:** Create `execution/sql_runner.py`, `specialists/sql.py`, `tests/unit/test_sql_policy.py`, `tests/unit/test_sql_bindings.py`, `tests/integration/test_sql_action.py`.

**Interfaces:** `run_sql(request: SQLInput, *, model: ModelGateway, tools: SQLTools) -> SQLOutcome`. `SQLTools.inspect_table(table_id: UUID) -> TableCatalog`; `preview_rows(table_id: UUID, columns: list[str] | None, limit: int) -> TabularPreview`; `inspect_evidence(evidence_id: UUID) -> TabularEvidence`; `execute_query(sql: str, parameters: Mapping[str, TypedScalar]) -> TabularEvidence`. These are the approved tools; T01 models retain exact schema/coverage/provenance fields. Guest operation identity and evidence publication use T05/T09, not SQL model output.

- [ ] Implement SQLGlot positive AST/relation/function policy, trusted read-only attachments and binder checks; disable extensions/network/path functions and settings changes. Execute one analytical statement/call with supported explicit typed parameters. A parse-only allow decision is insufficient.
- [ ] Implement one persistent runner subprocess/connection per SQL action attempt, serialized mailbox operations with atomic request/completion files and distinct physical incarnation IDs. Save complete typed Parquet evidence before returning its tool result; bounded previews retain exact physical locators and shortened-cell flags.
- [ ] Test count/join/grouping/evidence-only query, CTEs and approved window functions; reject ATTACH/DDL/DML/multiple statements/unauthorized tables/functions and text pretending to be policy. Typed decimal/int64/date/offset bindings must round-trip; a valid empty result still publishes evidence. Corrections/no-progress/retries share the action/run buckets.
- [ ] Run `uv run --locked --extra execution --group dev pytest tests/unit/test_sql_policy.py tests/unit/test_sql_bindings.py tests/integration/test_sql_action.py -q`. Record actual SQL-environment gate applicability before any live query; unknown execution cannot be replayed until reconciled/retired.

### T12 — CLI grounded-SQL vertical slice and inspectable result (1A)

**Files:** Create `__main__.py`, `cli.py`, `tests/integration/test_cli_1a.py`, `tests/acceptance/test_1a_grounded_sql.py`; modify package script declaration and root `README.md` only for working commands.

**Interfaces:** `cli.main(argv: Sequence[str] | None = None) -> int`; `submit(request: EntryInput, *, scope: Scope, config: RunConfig) -> RunHandle` in `graph.py`. It first persists intake and performs accounted entry assessment, then calls Authority.admit after acceptance; callers cannot supply an already-approved admission verdict. CLI invokes shared typed entry functions, not SQL/Python directly. Its scope commands are defined below. JSON output includes bounded rendered final content and evidence refs; local evidence inspection resolves executed SQL/provenance through governed access.

- [ ] Wire init/stage-inspect/prepare/ask/status/evidence/delete with explicit IDs, config validation and redacted errors. Questions reach entry then Supervisor, SQL, Answer, Reviewer and final gates. Zero permitted live configuration fails preflight without spending or invoking another backend.
- [ ] Add a trusted fixture with regional amounts 10 and 15; independently expected total is 25. The scripted flow must show one published query result, an independent supported draft/review, exact output reference and local trace. Wrong/stale evidence cannot be rendered as a final answer.
- [ ] Run `uv run --locked --extra providers --extra execution --group dev pytest tests/integration/test_cli_1a.py -q`, including wheel-installed `python -m querivue_agent --help` and no-Django import checks. Fake model/sandbox responses are explicitly marked scripted and never count as live acceptance.
- [ ] After separate authorization and applicable account/environment gates, run `uv run --locked --extra providers --extra execution --group dev pytest tests/acceptance/test_1a_grounded_sql.py -m live -q` with the approved explicit config, and capture a real isolated CSV→SQL→Answer→Reviewer result with executed SQL and trace. Until then 1A remains not_run/blocked even if code-level tests pass.

### T13 — Direct routing, Chat follow-ups and linked clarification (1B)

**Files:** Complete `context.py`, `supervisor.py`, `clarification.py`, `entry.py`, `dispatch.py`; create `tests/unit/test_context.py`, `tests/unit/test_supervisor_decisions.py`, `tests/integration/test_cli_1b.py`.

**Interfaces:** Extends T07's `build_packet(role: str, run_id: UUID, scope: Scope, fence: OwnerFence) -> RoleInput`; `decide(request: SupervisorInput, *, model: ModelGateway) -> SupervisorDecision`; `ask_clarification(request: ClarificationInput, *, model: ModelGateway) -> ClarificationOutcome`; `assess_entry(request: EntryInput, *, model: ModelGateway) -> EntryAssessment`. `RoleInput` is T01's union of existing resolved role input models. Dispatch commits exact already-resolved inputs; there are no future-evidence bindings.

- [ ] Implement same-Chat/cutoff selection, explicit user-basis interpretation/obligation records, bounded optional history, whole-exchange deterministic compaction and exact full-payload admission. No generated summarizer or copied child conversation. Preserve required conflicting/qualifying evidence rather than trim it to fit.
- [ ] Add faithful knowledge and prior-value/profile Direct reuse with zero analysis, no new arithmetic, complete obligations and conservative dependencies. A changed filter/rate requires compatible fresh evidence; any SQL/Python dispatch permanently sets the latch before execution. Direct is not a route after rejected/failed review.
- [ ] Implement one focused clarification and durable waiting/question/expiry, entry-screened exact linked reply and once-only same-run resume. Test short valid reply, two competing replies, rejected/unavailable reply, accepted nonresolving reply, late new Chat definition, expiry and removed source. Never expand the pinned scope on resume.
- [ ] Run `uv run --locked --extra providers --group dev pytest tests/unit/test_context.py tests/unit/test_supervisor_decisions.py tests/integration/test_cli_1b.py -q`. Real routing quality remains a separate authorized 1B acceptance capture; structural success is not semantic correctness.

### T14 — Fresh Python calls, numerical publication and PNG charts (1C)

**Files:** Create `execution/python_runner.py`, `specialists/python.py`, `tests/unit/test_python_declarations.py`, `tests/integration/test_python_action.py`, `tests/acceptance/test_1c_charts.py`; extend the owned guest image/lock/manifest.

**Interfaces:** `run_python(request: PythonInput, *, model: ModelGateway, tools: PythonTools) -> PythonOutcome`; `PythonTools.inspect_evidence(evidence_id: UUID) -> TabularEvidence`; `execute_python(code: str, input_evidence_ids: list[UUID], outputs: list[OutputDeclaration]) -> OperationOutcome`. T01 defines `OutputDeclaration` using the approved evidence/chart metadata. Tool outcomes expose only eligible published refs/diagnostics, not arbitrary guest filenames.

- [ ] Run each code call in a fresh child interpreter, scratch/output mount and approved bubblewrap/cgroup/supervisor boundary. Only exact per-call selected complete evidence inputs are staged read-only. No original uploads/prepared databases, package install, network, extra model-facing file browser or host fallback.
- [ ] Validate simple output names and supported declarations; reject mixed evidence/chart kinds in a nonempty call. Publish new computed Parquet values first, then chart rendering in a separate call with explicit backing. Normalize/validate PNG in the isolated validator and retain numerical evidence when rendering fails.
- [ ] Test no variables/files transfer between calls; undeclared/symlink/oversize/malicious chart output, forbidden source/FD/network access, backed chart-only reuse and required-output fulfillment. A failed requested chart leads only to an explicitly authorized useful partial reviewed by Answer/Reviewer.
- [ ] Run `uv run --locked --extra providers --extra execution --group dev pytest tests/unit/test_python_declarations.py tests/integration/test_python_action.py -q`. Only after real Python/renderer environment proof and live authorization run `uv run --locked --extra providers --extra execution --group dev pytest tests/acceptance/test_1c_charts.py -m live -q`; capture both a valid chart and the labeled reviewed partial failure case.

### T15 — Adversarial full-flow verification and guardrails (1D)

**Files:** Create `tests/acceptance/test_1d_guardrails.py`, `tests/integration/test_dispatch_collection.py`, `tests/integration/test_privacy.py`; modify only the owning implementation modules implicated by failures.

**Interfaces:** Consumes the full current graph/CLI and recorded outcomes; produces gate evidence keyed by exact config/build/commit. No new role or bypass API is introduced.

- [ ] Freeze a small duplicate-key join fixture with independently enumerated correct rows/totals. Supply the per-key/diagnostic evidence and query/grain provenance needed to inspect the injected defect; do not expect the tool-free Reviewer to recompute hidden source rows or see the harness's private gold. Inject wrong evidence versus a wrong draft separately; assert evidence-first versus direct-to-Answer correction, pass-2 cap and withholding after second rejection/terminal failure.
- [ ] Exercise invalid references, hostile cell instructions, missing required context/packet overflow, Direct arithmetic/latch escape, unsafe entry intent, all-sibling collection and a partial fan-out launch. Successful sibling evidence survives, and dispatch order does not turn sibling outputs into authorized inputs.
- [ ] Inspect actual serialized local/hosted trace events using synthetic secret/value/path/URL sentinels. Hosted allowlists must exclude raw prompts, cells, code, credentials and private role histories. A model's safe-sounding answer cannot pass technical access assertions.
- [ ] Run `uv run --locked --extra providers --extra execution --group dev pytest tests/integration/test_dispatch_collection.py tests/integration/test_privacy.py tests/acceptance/test_1d_guardrails.py -m 'not live' -q`. Applicable actual OS boundary checks run separately under T09 authorization; no unsafe publication is tolerated regardless of quality rate.

### T16 — Fresh-process restore, uncertain execution and deletion races (1E)

**Files:** Complete `runtime/{checkpoints,recovery}.py`; create `tests/integration/test_crash_boundaries.py`, `tests/integration/test_recovery_matrix.py`, `tests/acceptance/test_1e_restart.py`; change only owning ledger/gateway/controller modules when a failing case proves a defect.

**Interfaces:** Completes T07's `restore_run(run_id: UUID, *, authority: Authority, checkpointer: BaseCheckpointSaver, config: RunConfig) -> GraphProjection`; `resume_run(run_id: UUID, *, config: RunConfig) -> RunHandle`. Reconstruction revalidates records, builds the same nine-field projection and adopts only canonical outcomes. It never treats a Redis thread as an alternate run or new Chat.

- [ ] Use subprocess/barrier fault injection before/after physical dispatch, response save, evidence registration, outcome collection, review reservation/verdict, wait acceptance, checkpoint write and final acknowledgment. Restart must reuse identical committed result/pass/call identities and charges.
- [ ] Test missing/stale/ahead/unavailable Redis, incompatible schema/graph/config, owner takeover and stale completion, no state reconstruction from unauthorized artifacts, expired deadlines, source removal and clock rollback/downtime. Explicit operator restore cannot replenish budgets or enable an unproven profile.
- [ ] Test unresolved SQL/Python incarnations across attempts; replacement remains blocked until exact retirement proof. Half-launched two-action tasks preserve descriptors and completed siblings even when the initial execution profile runs them serially. Test concurrent reservations separately from enabling concurrent execution.
- [ ] Run `uv run --locked --extra providers --extra execution --group dev pytest tests/integration/test_crash_boundaries.py tests/integration/test_recovery_matrix.py -q`; then separately authorized Redis/fresh-process `uv run --locked --extra providers --extra execution --group dev pytest tests/acceptance/test_1e_restart.py -m redis -q`. This Redis test uses a scripted sandbox/model unless also explicitly admitted to live scope; actual interrupted isolated execution needs that separate evidence. Postgres/worker cross-adapter proof is deferred to application phases, with portable canonical vectors retained.

### T17 — Every approved import format and fidelity/cleanup matrix (1F)

**Files:** Extend `ingestion.py`, `execution/importer.py` and their owned locks/manifest; create `tests/integration/test_all_formats.py`, `tests/integration/test_profile_evidence.py`, deterministic fixtures under `tests/fixtures/imports/` for TSV/JSON/JSONL/Parquet/XLSX/SQLite and `tests/acceptance/test_1f_formats.py`.

**Interfaces:** Reuses T10's inspection/preparation functions and T01's versioned settings/catalog/profile types; no format-specific ready-state or alternate publication path.

- [ ] Add explicit per-format readers/inspection preserving accepted behavior: duplicate JSON keys/nested values/decimal lexemes; Parquet native type compatibility; workbook saved formula results, missing/error caches, hidden sheets, merged/range selection and date epoch; SQLite stored scalar values only with forbidden executable schema/virtual tables/views and missing-WAL failure.
- [ ] Test known-schema empty versus undiscoverable schema, all-null/mixed values, leading zeros, integer/decimal precision, timezone-free/offset/DST/sub-microsecond conversions, full-range errors beyond previews and archive/parser expansion limits. ZIP/XML checks happen before workbook library parsing; no recalculation or external links.
- [ ] Verify profile summary/column row schema, actual immutable locators, exact row/null/bounds, separate source key hint/check status and eight-candidate key bound. Fixture selection, name collisions, deselection, failed/successful replacement and uncertain cleanup all use the shared lifecycle.
- [ ] Run `uv run --locked --extra execution --group dev pytest tests/integration/test_all_formats.py tests/integration/test_profile_evidence.py -q`. Preserve source fixture/generator hashes. Only actual isolated successful imports under the approved image pass `uv run --locked --extra execution --group dev pytest tests/acceptance/test_1f_formats.py -m live -q`; unsupported cases return precise bounded failures, not a changed import meaning.

### T18 — Frozen comparisons, independent oracles and reproducible report (1G)

**Files:** Create `evaluation/{runner,baseline,oracle}.py`, `evals/{manifest,gates}.json`, `evals/development/`, separately protected `evals/heldout/`, `tests/unit/test_evaluation_manifest.py`, `tests/integration/test_evaluation_accounting.py`, `tests/acceptance/test_1g_report.py`; finish optional provider-only comparisons in their T06-owned adapters.

**Interfaces:** `run_suite(manifest_path: Path, *, config: RunConfig, mode: Literal['scripted', 'live']) -> EvaluationReport`; `oracle(case: FixtureCase) -> OracleResult`; `build_baseline(*, authority: Authority, handlers: RoleHandlers, checkpointer: BaseCheckpointSaver, config: RunConfig) -> CompiledStateGraph`. T01 defines `FixtureCase`, `OracleResult`, `EvaluationReport` from the approved manifest/report contract. Baseline phase changes remain runtime-owned; its Answer/Reviewer stay independent and it receives no extra budget.

- [ ] Author/review the finite D01–D24/H01–H24 templates, independently calculated numeric gold, scripted replies/fault points and G01–G10 assertion register. Separate generation/template families, not just seeds or renamed data. Freeze hashes/targets/configuration before held-out use; exposed held-out cases move to development. No second person/judge is claimed when unavailable.
- [ ] Implement manifest admission/reporting, exact provider/renderer/codec/build/source/dirty-patch identities and failure-inclusive denominators. Schedule only the approved 8 smoke +48 development +144 held-out full flows and 72 matched Reviewer assessments; optional F3/P1 need a separately declared batch. A quota/unsupported capability makes a stage incomplete, not a selective rerun or paid fallback.
- [ ] Test counts 200/72, correct-outcome denominator 72/configuration, complete-eligible denominator 66, thresholds 65/72 and 60/66, partial/invalidation separation and no-verdict Reviewer accounting. Use Decimal/Fraction/explicit enumerated/temporal references, not the tested DuckDB query or model as its own sole oracle. Restore cases keep the same original fixture/run identity under their declared policy.
- [ ] Run `uv run --locked --extra providers --extra comparators --extra execution --group dev pytest tests/unit/test_evaluation_manifest.py tests/integration/test_evaluation_accounting.py tests/acceptance/test_1g_report.py -m 'not live' -q`. Live scheduling remains off until every applicable gate/config/spend prerequisite and separate authorization is satisfied. Export exact forecast/actual/unknown charges, family slices, repeats, intervals, active/wall latency and all planned-versus-completed counts. Never claim a winning model or 1G completion from the scripted report.

## CLI contract for review

Use stdlib argparse subcommands with abbreviation disabled; all operations stay single-operator/local and validate stored Project/Chat/run/source relationships. Global `--state-dir` names the governed state root (default `.querivue`, ignored by git); `--config PATH` selects an explicit reviewed nonsecret TOML configuration. Without a complete configuration, only local setup/help/status paths work; model/execution preflight fails closed. Credentials come from environment and are excluded from all digests/output. No auto-loading arbitrary shell files or runtime executable config. Initialization refuses an unrelated nonempty directory; retries use the existing Querivue state manifest.

| Command | Required effect / important restriction |
| --- | --- |
| `querivue init` | Create a new local Project and Chat identity and initialized ledger, or return the recorded initialized scope on identical retry. Never overwrite an existing state directory or reset its counters. |
| `querivue import --project ID --file PATH [--replace DATASET]` | Stage immutable bytes and inspect under intake/ingestion limits; return Dataset/preview/settings identities. Replacement is explicit, never filename matching. This does not make a Dataset ready. |
| `querivue prepare --project ID --dataset ID --preview ID --settings PATH --confirm` | Confirm exact preview/settings and prepare under a new current attempt if needed. Retry a retained failed upload without recharging raw bytes; commit all selected tables together. |
| `querivue ask --project ID --chat ID [--dataset ID ...] --question TEXT` | Submit a new question/run with explicitly pinned selected sources. No Dataset flags selects no new Dataset scope; it never silently includes another Project or newly uploaded source. Data-dependent work without sufficient scope returns a precise issue/new-submission instruction; clarification cannot add a source to an existing run. |
| `querivue reply --run ID --question ID --text TEXT` | Entry-screen and atomically accept one exact linked analytical reply, retaining scope/cutoff/counters. Entry-policy questions use their distinct intake identity, not this analytical question ID. |
| `querivue resume --run ID` | Reconcile ledger/projection and resume the same run; no supplied new question, Dataset list or new budgets. |
| `querivue status --run ID` | Read bounded durable status, remaining issue and recorded refs; no model call. |
| `querivue evidence --run ID --id EVIDENCE` | Resolve authorized eligible evidence/provenance/executed SQL through current source checks. Display actual coverage and truncation; no unsafe raw-path download. |
| `querivue delete-dataset --project ID --dataset ID` | Tombstone/access denial transaction first, invalidation/deferred physical cleanup second; no unretired process cleanup. |
| `querivue evaluate --manifest PATH --mode scripted|live` | Explicitly labeled comparison/report mode. Live is gated and disabled by default. Never use scripted output as a real user's verified analysis. |

Default CLI output is a stable JSON result envelope with status/completeness, bounded `rendered_text` where eligible, record/evidence refs and sanitized errors. It is a CLI envelope, not an added model output schema. Exit 0 for command success/eligible complete or partial output, 2 for invalid arguments/configuration, 3 for durable waiting, 4 for a bounded analytical/verification stop, 5 for operational unavailability; interrupted process uses standard 130 after best-effort durable reconciliation without asserting retirement. Human-wait and operational failures remain distinct. Trace records stay local and protected; hosted export is an explicit redacted operation, not full graph auto-tracing.

## Capability gates and acceptance ownership

| Approved gate / scenario | Primary tasks and proof boundary |
| --- | --- |
| G01 supported imports; G02 lexical/type fidelity | T10 then T17. Unit fixtures do not replace isolated successful format imports. |
| G03 workbook/SQLite hostile input | T09 validation boundary and T17 format rules. No uploaded schema execution or host fallback. |
| G04 catalog/profile/temporal and Direct grounding | T01/T02/T10/T13/T17. Check actual typed artifact cells/locators, not reference syntax alone. |
| G05 preparation authority | T03–T05/T10/T16. Both source-delete/publication orders and all crash boundaries. |
| G06 actual SQL/Python/environment enforcement | T09/T11/T14/T15 on the exact built provider environment. Every applicable assertion passes before enablement. |
| G07 retirement and uncertain work | T05/T09/T11/T14/T16. Provider pause/kill/timeout is not enough. |
| G08 context/access/privacy | T04/T06/T07/T08/T13/T15/T16. Inspect actual packets/traces, not labels. |
| G09 counters/control/final publication | T05–T08/T11/T13/T15/T16. No reset through IDs, SDKs, retries, branches or restart. |
| G10 persistence | All ten shared acceptance families map to T02–T08/T13/T16. SQLite-to-Postgres/worker-specific proof remains not applicable to the current CLI milestone and pending its application-phase owner; retain export-compatible records/vectors without pretending that adapter exists. |
| SQL-only, SQL→Python, mixed sibling outcomes | T07/T11/T12/T14/T15/T16. No automatic specialist-to-specialist delegation. |
| Complete/partial/Direct/clarify/correction/withholding | T08/T12–T16/T18. Full original obligations, independent review and failure-inclusive results. |

No capability is enabled by a provider's marketing claim, a successfully imported SDK, a checkpoint label, a generated UUID, a happy-path mock or Reviewer approval alone. Exact configuration/commit and evidence applicability are checked before reusing an earlier pass.

## Worker handoffs and review procedure

For each coding task, the supervisor supplies: task ID, bounded file ownership, exact interfaces above, required specification excerpts/field definitions, finite config values, allowed dependency changes, named fixture/assertions, commands and expected outcomes, security/data boundaries and explicit excluded scope. Workers start with fresh contexts, inspect owned code/tests and return a changed-file summary, actual checks/results and any missing contract information. They do not browse project docs or expand scope to backend/UI.

Current coding method is defined once in [coding-rules.md](../coding-rules.md#scope-and-supervision): this chat supervises directly and delegates code writing to fresh `gpt-5.6-sol` medium workers. Do not launch a separate supervisor or silently substitute an unavailable worker. Earlier supervisor/model proposals are superseded; Querivue runtime role/model allocations are unchanged.

Use the suggested plugins at the applicable step: Superpowers for spec-driven implementation, delegation, debugging and verification; mattpocock-skills for interface/domain/review work; Karpathy guidelines for focused changes and explicit assumptions; Ponytail for the smallest complete implementation. Follow the [coding skill instructions](../coding-rules.md#skills-and-implementation), reading the specific skill before use rather than invoking every unrelated workflow. User instructions against TDD and excessive tests take precedence. QMD/code-review-graph remain the context tools and Floorplan remains phase-end maintenance. Frontend plugins remain assigned to the later frontend phase. No plugin installation or product dependency is added merely to invoke a plugin.

The parent reviews implementations/integration and source evidence. No planning/research subagents are authorized. Do not mechanically add a second fresh review agent for each task if that conflicts with the repository's workflow; the supervisor owns the review. Save a concise handoff at the required context threshold when the host exposes it; otherwise disclose that limitation and use bounded fresh worker contexts. No claim that a hidden context percentage was enforced.

Each completed task updates its checkboxes and actual acceptance evidence, checks the targeted diff and performs the authorized QMD/code-graph maintenance. Update the blueprint at the agreed phase boundary, not on every task. Full-project frontend/backend tests and CI/deployment are out of phase-1 scope; run them only if a changed shared file warrants it. A commit is not a verification result.

## Verification commands and meaning

- Unit/offline task checks: the exact per-task pytest files above. They must run without provider credentials or real sandbox requests; all external transports are explicit test doubles. No implicit download/browser startup in an unmarked unit test.
- Offline integrated suite, after all groups are implemented: `uv run --locked --extra providers --extra comparators --extra execution --group dev pytest -m 'not live and not redis' -q`.
- Local Redis tests, only when its service operations are authorized: same command with `-m redis`; require the actual persistent Redis configuration and fresh-process checks.
- Applicable live environment/acceptance tests: `-m live`, explicit approved config/manifest/account limits and separate authorization. Fail closed when unavailable. Metadata/token-count requests still count as external account activity and need applicable permission/accounting.
- Package verification: `uv build`, inspect wheel resources/entry point, then run import/CLI smoke in an isolated installed-wheel environment under the coding/build scope. The source checkout working is insufficient.
- A failure reopens only the owning code task or the consequential contract actually contradicted by evidence; do not begin another speculative architecture round or rerun unrelated suites.

## Plan self-review and current completion boundary

Self-review on 21 November 2026 maps the approved component/acceptance families to T01–T18 and the gate table, checks the five failure priorities, and reconciles repeated packet/restore/graph signatures. Corrections made before handoff include an RFC 8785 implementation instead of sorted JSON, explicit pre-run intake accounting, runtime-only typed handler/checkpointer boundaries, canonical authority acceptance methods, explicit path conventions, full future test commands and a visible-evidence requirement for the join-defect Reviewer case. Relative links, task numbering/checklist completeness and unchanged source scope receive documentation checks. These are plan checks, not executed product tests or measured compatibility.

Planning is complete when these implementation proposals are reviewed and the initial file/interface/dependency/task sequence is accepted. That does not complete T01–T18, satisfy any live gate or authorize starting code. The temporary phase document remains until that review; approved durable execution instructions remain here for subsequent coding tasks. Next action for the user is review of this single coherent plan, with the existing delegation method preserved.
