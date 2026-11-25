# Phase 3: backend APIs — working plan

Started 25 November 2026 at the user's request to continue planning after approval of database/storage design. Planning and reversible documentation edits are authorized. Application implementation, dependency changes, services, live/paid execution and migration are not authorized by this phase.

## Objective and boundaries

Define Django API requests, responses and lifecycle behavior for Projects, uploads/import confirmation, Datasets, Chats, submission/clarification, status/results/evidence and deletion. Reuse the approved single authority, scope/cutoff, storage/deletion and runtime policies. No application endpoint, job broker or React workflow is assumed implemented.

Phase 4 owns worker framework/job delivery and Phase 5 owns worker checkpoint integration; this phase defines the durable handoff and service interfaces they consume. Frontend implementation and CI retain their later owners. Preserve the agreed build order and unrelated ongoing standalone implementation.

## Work and review sequence

- [x] Retrieve relevant approved product/storage/intake/lifecycle contracts and inspect current backend configuration/routes.
- [x] Prepare an opening API approach covering protocol/style, admission/idempotency, public states, progress delivery and access boundaries, distinguishing approved constraints from new proposals.
- [x] Opening direction approved, including same-run Retry; WebSocket replaces Chat polling. Detailed endpoint/transport/security choices remain under review.
- [x] Prepare the concrete endpoint/schema/error/access, upload/import, clarification, evidence/download, WebSocket and deletion review packet with acceptance scenarios.
- [x] Record the approved direction and prepare clearly marked concrete proposals in the topic API guide and decision log; final review/closure remains outstanding.
- [ ] At closure remove this temporary phase plan and repair links, refresh/show the local blueprint and perform due index maintenance.

## Completion boundary

Settle request/response types, identity and idempotency, ownership/authorization, state transitions, concurrency, failures/recovery, privacy/publication/download behavior and cross-phase handoff ownership before implementation. Resolve runtime numerical settings through their owned implementation/evaluation gates rather than inventing measured limits. Existing approvals remain effective; new proposals are not approved until reviewed.

## Current status

The user approved the opening direction with WebSocket Chat replacing the polling proposal. The [concrete HTTP/WebSocket packet](architecture/backend-api.md) is prepared for review; Channels, connection-ticket admission, event/chunk replay and exact resource/protocol details are proposed implementation choices. Backend inspection found only the admin URL and Django 5.2 dependency; this is not a fresh audit of standalone implementation. No application code/services changed. Unrelated ongoing agent edits remain untouched.

## Opening direction — approved with WebSocket correction

### Protocol and implementation approach

Recommend a small REST-style JSON API under `/api/v1/`, using ordinary Django views/responses and explicit strict request/response schemas. Reuse the agent's strict contract library at its public boundary, but define separate application DTOs rather than exposing raw owner fences, budget state, prompts or ledger rows. Use snake_case fields and lowercase state labels to align with the established Python contracts. A named response schema covers every endpoint; schema generation and examples belong with implementation. Lists use bounded cursor pagination with stable ordering; numerical limits are configuration gates, not measured values invented during planning.

Django REST Framework is a viable alternative for serializers, viewsets and browsable documentation, but introduces another framework/validation layer for this small fixed API. Prefer ordinary Django plus shared strict validation here; the contract still requires uniform errors, pagination, authentication/access checks and documented endpoints. GraphQL offers no demonstrated benefit for the bounded local workflows. Do not add dependencies merely to prepare this plan; exact public DTO/schema library wiring remains an implementation task.

### Local access, without an account system

Recommend the existing single-operator local trust boundary, with no login/signup screen or account management. Bind the host-facing application entry point only to loopback; both normal and development UI use a same-origin HTTP/WebSocket proxy. Strict allowed Host and browser Origin checks, Django CSRF checks on unsafe methods, no broad CORS, and a required custom application request header on HTTP data API requests prevent ordinary cross-site browser requests from becoming local API calls. That header is not a secret or a substitute for authentication. CSRF bootstrap has a defined same-origin fetch path, not a public content endpoint. Download buttons fetch through this same authorized path rather than navigating to a permanent storage URL.

The trusted operator is the local OS user/process environment; another local process able to reach and emulate these requests is inside this boundary. This design does not protect a shared/untrusted host or provide LAN/hosted access. If that deployment becomes a requirement, real operator authentication and deployment review must precede it. Alternative: require a pre-provisioned operator login/session now, which adds a login workflow outside the accepted no-account-system direction. Do not infer login approval merely because Django's starter auth/session middleware exists.

Every resolved Project/Chat/run/source/evidence ID still passes the approved ownership, lifecycle and dependency checks. Missing and out-of-scope IDs receive the same bounded not-found response; owning the local session does not bypass source revocation. Reject malformed UUIDs and unknown request fields. Credentials, payloads and source text never enter access logs/hosted traces.

### Durable asynchronous requests and WebSocket Chat

The user explicitly selected WebSockets for seamless Chat streaming, superseding the earlier polling-only recommendation. Chat commands and streaming progress/cards/committed publications use a per-Chat socket; HTTP handles management, upload/download, initial snapshots and reconnect/status lookup. The [API guide](architecture/backend-api.md#websocket-admission-and-command-protocol) owns the proposed admission, command and event schemas; its [delivery contract](architecture/backend-api.md#streaming-ordering-and-reconnect) owns reconnect cursors, replay, chunking, backpressure and revocation.

Preserve durable receipt-before-acceptance and entry-before-run admission. Stream public progress immediately and answer content only after approved publication. Socket reconnect, dropped Redis notifications and lost command acknowledgments must not duplicate work or reset budgets. Semantic Chat visibility cutoffs stay distinct from transport cursors. Browser WebSocket security requires explicit Origin/Host checks and a proposed short-lived single-use ticket from protected HTTP; the ordinary HTTP custom-header check cannot be imposed on a browser WebSocket constructor. Channels on ASGI and channels_redis notification transport are proposals, not installed dependencies or a chosen background-worker framework.

### Idempotency and concurrency

Require an Idempotency-Key generated once per user intent and reused across transport retries for create/command requests. Atomically bind the key to operator/Project, operation, validated exact request digest and response identity; the same key with different content is a conflict. An in-flight duplicate returns the same durable receipt, not another admission/dispatch. A replay reauthorizes current state and cannot return erased cached content. Keep non-content deduplication records as long as the operation can be replayed; deletion policy still governs stored hashes/IDs. No arbitrary short TTL is proposed.

Mutable metadata/settings/deletion commands carry the expected revision/precondition. Duplicate identity is checked before rejecting a revision made stale by that same successful command. Separate conflicting intents do not overwrite silently. Source/deadline/owner/budget validation remains inside the storage transaction; HTTP idempotency does not replace runtime guards. The detailed packet will define exact headers, response codes and deletion replay behavior.

### Retry: recover the same run rather than fund another run

Recommend making the user-visible Retry command request reconciliation/resumption of the **same run** after a recoverable interruption, while its original inputs, deadline, budgets, review counts and retirement constraints remain valid. Persist a recovery-request receipt and use the current run/owner generation; do not add a new user message, refresh Chat context or rerun successful terminal work. Runtime decides the next legal transition, including whether an eligible action may be retried. A queued duplicate recovery request cannot become a second coordinator.

Expose a distinct `interrupted` public state when durable work is recoverable and no terminal publication exists; it is an operational state, not a new field in the nine-field parent RunState. A terminal publication, expired hard deadline, exhausted budget/reviews, removed source or unresolved retirement barrier cannot be reopened by Retry. Eligibility can change between display and click and must be revalidated. Operation timeouts with remaining legal recovery may offer Retry; a hard run deadline remains terminal. Starting another analysis is a separate explicit question/submission, not an automatically newly funded Retry.

Alternative: a new linked run for every user Retry, with renewed deadline/allocations. That would need a new root retry-chain accounting/publication contract and limits to avoid bypassing the already approved finite run controls. It is a consequential expansion, not assumed by the PRD's Retry wording. The same-run recovery recommendation preserves the existing authority/recovery design and distinguishes transport retry, recoverable interruption and deliberate new analysis.

## Proposed resource surface for the detailed packet

| Family | Contract to define |
| --- | --- |
| Projects / Chats | Create/list/read/rename/delete, bounded pagination and expected revisions; Chat deletion retains Project sources. |
| Uploads / Dataset preparation | Reserve an upload, transfer bounded binary bytes, finish validation and screen/admit ingestion; inspect proposed import settings/tables/ranges, confirm a versioned preparation and read progress/failed diagnostics. Explicit replacement target uses the approved atomic new-ID lifecycle. |
| Submissions | Record exact new question, requested source selection and explicit follow-up target; return/read entry receipt, handle entry-policy clarification through its original intake chain and expose admitted run identity only after admission. |
| Runs / analytical clarification | Read public state; read/reply to the exact committed analytical card using the original run; create/read idempotent same-run recovery requests. New composer messages always remain new submissions. |
| Results / evidence | Read only committed approved/Direct/notice output and labels; inspect bounded typed values/tables/charts and exact recorded executed SQL/Python with current dependency checks. Delete a result under the approved dependent-erasure rule. |
| Private artifact content | Governed binary/PNG/plain-text delivery with current authorization, bounded revocation rechecks, safe media/disposition/nosniff headers and no persistent public volume URL. Range/cache/partial-transfer behavior must be explicit. |

## Source checks and remaining owners

- Approved constraints: [PRD](PRD.md#core-workflow), [Chat basis/intake](architecture/agent-integration.md#submission-snapshots-and-concurrent-turns), [canonical authority/recovery](architecture/agent-integration.md#persistent-recovery-and-concurrency) and [database/storage](architecture/database-storage.md). The PRD asks for eligible Retry using original sources; it does not specify renewed run budgets or a login workflow.
- [Django JSON responses](https://docs.djangoproject.com/en/5.2/ref/request-response/#jsonresponse-objects) support the ordinary-view option; [DRF serializers](https://www.django-rest-framework.org/api-guide/serializers/) support the alternative, without selecting a dependency here.
- [Django CSRF](https://docs.djangoproject.com/en/5.2/ref/csrf/) and [AJAX CSRF use](https://docs.djangoproject.com/en/5.2/howto/csrf/) describe token/Origin handling. These protect browser requests within the proposed local trust boundary; CSRF is not operator authentication.
- [HTTP semantics](https://www.rfc-editor.org/rfc/rfc9110.html) governs status, safe methods and preconditions. Querivue must still implement its durable receipt/idempotency semantics explicitly. Official-source checks were read 25 November 2026; no endpoint or security behavior is tested here.

Next: review the [concrete HTTP/WebSocket protocol and endpoint packet](architecture/backend-api.md), including Channels/ASGI, ticket bootstrap, durable replay/chunking and Phase 4 handoff. The user-selected WebSocket transport and already accepted local access/Retry direction do not need renewed approval. Real backend/storage/worker behavior remains unimplemented or unverified by this planning work.

- WebSocket source checks: [browser API](https://websockets.spec.whatwg.org/#the-websocket-interface), [Channels origin security](https://channels.readthedocs.io/en/stable/topics/security.html), [channel-layer loss/capacity](https://channels.readthedocs.io/en/stable/channel_layer_spec.html). These motivate browser-compatible ticket admission and database-led replay, not a guarantee of implemented reliability.
