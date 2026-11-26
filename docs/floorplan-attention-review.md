# Floorplan attention review

Checked 26 November 2026 against HEAD `4b571892b550a15532119cbb61f4cb5a23c5b97e` plus the current working tree. Scope: the eight readiness questions and one disconnected-file item in the existing architecture blueprint. This is a focused source/test/evidence review, not a full code audit or live readiness run. Existing approvals remain effective.

## Finding and map correction

The eight medium items were manually retained implementation/verification gates encoded in Floorplan's `questions` array. Its generic UI therefore said the PRD had not answered them and invited another design decision. Their designs are already approved; passing them requires implementation and empirical evidence, not a chat answer. Move them into explicit readiness notes/cards and retain this tracked gate review rather than manufacturing unresolved design questions or claiming the gates passed. The blueprint is not an automatic scan of current runtime/security behavior.

The low item concerned `agent/src/querivue_agent/contracts/__init__.py` (empty package marker) and `agent/src/querivue_agent/__init__.py` (starter hello function). Neither needs an invented call/import edge. Omit their cards from the architecture blueprint, retain the source files and state that package markers/starter-only entry files are excluded. This resolves a map-detail false positive, not dead-code removal.

## Eight readiness gates

The statuses below concern the full declared gate. A passing focused test does not pass the whole gate. Use the existing [gate/evidence rules](architecture/evaluation-observability.md#hard-gates-and-evidence).

| Gate | Current finding / disposition | Owning accepted contract |
| --- | --- | --- |
| Import fidelity | **Not run at full gate scope.** Ingestion source and meaningful unit tests exist; the focused ten-test suite passes. Inspected all-format integration cases such as TSV/JSON/Parquet construct Scope objects rather than import those formats, so their names are not fidelity evidence. Exact built importer/Arrow/DuckDB behavior, all selected rows/types/profiles, resource limits and isolated preparation still need the specified fixtures/proof. | [Ingestion](architecture/data-ingestion.md#acceptance-and-remaining-evidence) |
| Sandbox isolation / retirement | **Blocked by an implementation mismatch; live proof unrun.** SandboxController creates a host temporary directory and `_run_command` invokes `asyncio.create_subprocess_exec`. Its Python method copies the host environment; default manifest claims network/process/cgroup/bubblewrap controls through literal true flags and a synthetic image identity. These declarations are not observed enforcement. No admitted E2B/OS-isolation/retirement proof was found in the inspected path. Do not enable this controller as the generated-code boundary without fixing the mismatch and proving the required environment. This review did not establish an end-to-end live caller or execute untrusted code. | [Sandbox](architecture/sandbox-execution.md#environment-admission-and-lifecycle-contract) |
| Model/provider/evaluation | **Not run.** Typed evaluation records/provider code exist, but targeted discovery found no actual evaluation runner/fixture-oracle suite/report. Inspected accounting-test cases validate EntryAccept or construct a ledger/authority rather than run frozen baseline/reviewer comparisons. Account/model/protocol/tokenizer identities, enforced zero-spend limits, frozen independent development/held-out data and measured/billed results remain unverified. No provider/account call ran. | [Evaluation](architecture/evaluation-observability.md#final-phase-comparison-configuration) |
| Application Postgres/storage | **Blocked: application implementation not present in inspected backend.** Backend remains Django configuration/admin scaffold with only Django declared; no domain models/migrations/adapter or real Postgres concurrent acceptance harness was found in targeted discovery. Agent SQLite code is not evidence of application ownership/deletion/migration proof. | [Storage acceptance](architecture/database-storage.md#operation-results-and-implementation-slices) |
| HTTP/WebSocket API | **Blocked: application routes/consumer absent.** Backend URLs expose admin; ASGI is the starter Django callable and no Channels/application API implementation was found. Origin/ticket/CSRF/proxy, idempotency, stream/replay/revocation and real browser tests remain implementation/acceptance work. | [API acceptance](architecture/backend-api.md#acceptance-and-remaining-gates) |
| Celery/Redis workers | **Blocked: worker integration absent.** No backend Celery/task/worker modules or dependency wiring were found. The approved control/execution/maintenance layout, bounded delivery claims, actual queue-loss/child-death handling and retirement proof remain unimplemented/unverified here. | [Worker slices](architecture/background-workers.md#implementation-slices-and-acceptance) |
| Worker checkpoint integration | **Blocked by saver/state integration gaps; real restart proof unrun.** The existing RedisProjection helper defaults to seven-day TTL and serializes a broader runtime container, rather than establishing the selected no-TTL RedisSaver/nine-field adapter/descriptor contract. Source search did not find native StateGraph/BaseCheckpointSaver/RedisSaver wiring in agent Python modules. Graph coverage leads for RedisProjection were indirect state/wrapper tests, not actual Redis worker restart proof. The accepted specification must be implemented and tested, not weakened to match the helper. | [Checkpoint slices](architecture/worker-checkpoints.md#implementation-and-acceptance-owners) |
| Combined backend verification | **Blocked: real harness/report absent.** No backend integration/browser/process harness was found; inspected agent crash/dispatch tests include shape/trivial assertions that cannot establish their named crash/adversarial behavior. B01–B13 real-stack cases, independent oracles and triangulated evidence remain unrun. This does not characterize every test in the repository. | [Backend verification](architecture/backend-integration.md#implementationverification-handoff) |

## Concrete source evidence

- `agent/src/querivue_agent/runtime/sandbox.py`: create_session, execute_python, _run_command and create_default_environment_manifest. Host subprocess/environment handling and literal manifest controls require correction before admitted generated execution; merely passing the manifest checker is not enforcement.
- `agent/src/querivue_agent/runtime/redis_projection.py`: RedisProjection constructor/create default TTL, save/latest/index and state serializer; compare the existing [standalone T07 contract](implementation/standalone-agent.md#t07--outer-graph-private-wrappers-and-redis-projection).
- `agent/tests/integration/test_all_formats.py`, `test_crash_boundaries.py`, `test_dispatch_collection.py`, `test_evaluation_accounting.py`: inspected cases do not exercise the broad capability described in their names. Replace/extend them under their owning authorized implementation slices with independently meaningful checks; do not use test counts as readiness evidence.
- `backend/config/urls.py`, `backend/config/asgi.py`, `backend/pyproject.toml` and bounded backend file discovery: scaffold rather than the planned application stack.

CRG MCP was healthy at the checked commit and narrowed RedisProjection coverage; direct source remains authoritative where graph callers are absent/unresolved. The graph's absence of a caller is not proof an execution method is unreachable.

## Check actually run

Ran the existing local environment, without installs or services:

`agent/.venv/Scripts/python.exe -m pytest agent/tests/unit/test_ingestion.py -q -p no:cacheprovider`

Result: **10 passed in 0.16 seconds**. Coverage includes actual trusted CSV/JSON inspection plus catalog/type/settings checks. This does not establish full-table/all-format parser fidelity, sandbox isolation, runtime/model quality or backend readiness. pytest-asyncio also emitted a deprecation warning about its unset default fixture-loop scope; it did not fail this run. No production source or tests were changed; no live model/sandbox call, infrastructure/fault injection or dependency install ran.

## Next implementation owners

Address the host-execution/manifest mismatch before enabling generated code; finish strict saver/state/replay conformance and replace misleadingly broad test cases with their actual accepted behavior. Then implement the approved application storage/API/worker/checkpoint slices and run the isolated backend acceptance harness. Preserve the existing build order and source/retirement/spend gates; this review does not authorize those coding or live execution batches. The current task only corrects diagnostic map metadata and records findings.
