# Frontend workspace and client architecture

**Phase 7 design approved and planning closed, 27 November 2026**, at the user's request to continue to CI planning. The concept's layout foundation, named-site visual direction, recorded UI refinements and client architecture are accepted. Final production styling must go further in the requested direction. F1–F5 remain not_run; design closure is not implementation/readiness approval. See the [closure record](../memory.md#frontend-planning-closure--27-november-2026).

The [PRD](../PRD.md), [HTTP/WebSocket contract](backend-api.md), [storage lifecycle](database-storage.md), [ingestion](data-ingestion.md) and [backend verification](backend-integration.md) own domain behavior. The [reference synthesis](../design-references/README.md) owns visual rationale and the previously observed prototype behavior. The earlier concept directory is no longer present in the shared workspace at CI closure; its accepted requirements and limited historical observations remain recorded here. The React/Vite application is still a starter; the standalone concept is not production application code.

## Client direction and dependencies

Retain React, TypeScript and Vite. The user approved adding React Router and TanStack Query on 27 November: `react-router` **7.18.7** and `@tanstack/react-query` **5.108.4** are now exact frontend dependencies with the npm lockfile updated. Their selected usage is declarative nested routing and HTTP resource fetching/cancellation/invalidation respectively. A small Chat session store consumed through React's `useSyncExternalStore` owns the ordered Chat projection. Do not add a second global state library, an offline mutation queue or a second Chat transport.

Use semantic CSS custom properties and component-scoped CSS for the product design system, native CSS/Web Animations for transitions, and View Transitions for the requested theme reveal. Tailwind's website is a visual reference; that does not require installing Tailwind or copying its generated theme. Start with semantic tables and governed chart images/backing values rather than an editable grid or new chart engine. Other dependency/schema-tooling choices and integrated compatibility remain implementation gates. The authorized package addition passed the existing starter production build and lint; it does not establish router/provider/Chat integration or complete F1–F5. npm reported zero audit vulnerabilities at installation. No product UI source was changed by that addition.

## Routes and navigation

UI paths below are browser routes, separate from `/api/v1/` and `/ws/v1/`.

| Browser route | Owner and behavior |
| --- | --- |
| `/` | Project list and first-run empty state. Creating a Project goes to its home; no login or signup. |
| `/projects/:projectId` | Project home: title, dataset readiness and recent chats, with a Project-scoped new-question composer. |
| `/projects/:projectId/data` | Retained Dataset list, quota, explicit Add/Replace, preparation/failure/deletion state. |
| `/projects/:projectId/data/:datasetId` | Dataset details and bounded preview for a currently authorized source. |
| `/projects/:projectId/data/:datasetId/import` | Preview/settings/confirmation for that exact Dataset preparation revision. |
| `/projects/:projectId/chats/:chatId` | Chat history, independently active run/card states and new-question composer. |
| Chat URL plus `?publication=:id&evidence=:id` | Evidence selection in its owning Chat/publication. Same URL opens a side inspector or full-width phone view. |

Keep evidence identity in the URL; pane width, code-fold state and scroll anchors stay in memory. Opening a claim creates a history entry so Back closes that inspection; changing inspector tabs/layout replaces local state rather than producing history spam. Direct evidence links always fetch and validate current ownership; unknown/mismatched/revoked identities render unavailable without exposing foreign content. Closing a directly loaded link replaces its evidence parameters with the base Chat path rather than unexpectedly navigating out of the app.

No unowned global Chat is introduced. New Chat opens a local empty workspace scoped to a Project. First submission creates a Chat through the approved HTTP endpoint, resolves that creation's stable receipt if uncertain, then submits the question once over its socket. A Project-home composer uses this same flow. A new question in an existing Chat remains in that Chat. Do not implement ChatGPT sharing, instructions, account, memory or collaboration features merely because its navigation inspired the layout.

For an uncertain HTTP creation, reconcile using the original operation's exact body/idempotency key through the existing duplicate-resolution contract; do not invent a lookup endpoint or create another Chat with a fresh key. HTTP replay is an explicit command-service reconciliation path, not a generic query-library retry.

Data navigation retains a return-to-Chat location in memory; a direct Data link uses Project home as its fallback. Route parsing validates IDs, never constructs a trusted file path from a URL, and never puts questions, source names, tickets, code or answer text in search parameters. Configure the existing same-origin ingress to serve the SPA for browser routes while preserving API, socket, asset and real 404 behavior.

## Component and module ownership

| Boundary | Responsibilities |
| --- | --- |
| `app` | Bootstrap/client context, router, providers, error boundary and design tokens. One composition root owns service lifetimes. |
| `workspace` | Project navigation, top bar, one theme button, responsive pane layout, focus and scroll restoration. |
| `projects` / `data` | Project/Chat management, source selection, upload intent, Dataset preparation and deletion receipts. |
| `chat` | ChatSession controller/store, transcript, submission/run cards, committed answer renderer, composer and clarification forms. Components call typed intents, not raw socket sends. |
| `evidence` | Authorized evidence fetches, typed table/coverage/locators, governed chart/code/artifact display and object-URL disposal. |
| `transport` | Validated HTTP client, ticket/bootstrap, socket state machine, event/chunk decoding, command reconciliation and bounded reconnect. No JSX. |
| `contracts` | Generated public DTO/types and runtime validators from the final API schemas; no importing private Python runtime state. |
| `ui` | Small shared controls, field/error/status primitives and accessible overlays, styled by Querivue tokens. No product policy. |

These are logical boundaries; do not create empty folders or abstractions for every table row. Keep domain operations explicit: submit new question, reply to the exact entry/analysis card, request same-run recovery, confirm exact import, revoke a resource. A generic Send action must not infer which operation the user meant from whatever run happens to be waiting.

## State and cache ownership

| State | Single client owner and persistence |
| --- | --- |
| Projects, Chat metadata/lists, Datasets/import previews, evidence pages, deletion receipts | TanStack Query, memory only. Keys include complete Project/Chat scope as applicable, resource identity, revision and row cursor/selection. Never share evidence keys across Chats. |
| Transcript, active submissions/runs/cards, publication assembly, delivery cursor, socket state | ChatSession store, one active Chat session per browser tab. Immutable cached snapshots for subscribers; no duplicate transcript in the HTTP query cache. Canonical server data remains authoritative. |
| Drafts, source picker, exact-card reply drafts, pane/focus/scroll state | Scoped in-memory UI state. Composer draft keyed by Project/Chat or Project-new state; replies additionally keyed by submission/run/question identity. Switching Chat never moves a reply into another card. |
| Theme preference | Only explicit light/dark preference in localStorage; first visit follows system preference. No content in this key. |
| Unresolved command identities | Minimal sessionStorage journal: scope IDs, command/idempotency IDs and operation kind only. No text/payload, token, answer, source bytes or private trace. Write before sending; storage failure blocks dispatch with an actionable error rather than sending an untrackable command. |

No persisted query cache, service worker/offline response cache or browser-storage answer history. No offline send queue. Drafts survive ordinary in-app navigation but do not promise survival across reload/browser restart. A fresh page resolves journaled identities through status/snapshot queries; without the original in-memory payload it cannot automatically reconstruct or resend the command. Remove resolved journal entries; apply finite retention/size limits and clear affected entries on confirmed scope erasure. Record those non-content limits in implementation configuration.

HTTP calls use the approved application header, same-origin credentials, masked CSRF token for unsafe methods, strict public schemas and `cache: no-store`. Revisions and `If-Match` follow the API contract. Consume cancellation signals. Explicitly disable generic mutation retries and background/offline mutation replay. Configure read retry/refetch behavior per resource; no library default may silently retry tickets, writes, revoked resources or a question. No continuous Chat polling. Query caching is a transient application projection, never permission to use a stale resource without current authorization.

## Chat connection and publication delivery

Connection states are `idle → bootstrap → connecting → synchronizing → live`, with `reconnecting`, `unavailable`, `protocol_error` and `disposed` exits. Keep transport status separate from submission/run/publication states. Navigator online status is a hint, not evidence of a working socket or server.

1. Obtain approved client context and a new one-use ticket for the selected Project/Chat. Connect with `querivue.chat.v1`; send `hello` carrying ticket and the last fully applied delivery cursor. Ticket stays in memory and out of URLs/logging/storage. Until authorization and synchronization complete, disable command dispatch and source-bearing actions.
2. Use the backend's subscription/snapshot/watermark handshake. An HTTP initial/history snapshot is preparatory; do not race an independently authoritative snapshot against live events. Adopt the backend-provided cursor and consistent baseline, then reduce ordered events. Delivery sequence and semantic conversation cutoff are distinct fields with distinct purposes.
3. Validate envelope, scope, resource revision and schema before reducing. Ignore known duplicate event identities/ordinals; detect gaps or inconsistent identities and enter synchronization. Unknown protocol versions, impossible revisions and invalid payloads produce a bounded visible protocol failure, not partial trusted state. Never acknowledge a corrupt event to skip past it.
4. Public stages may render immediately. On `publication_start`, allocate one assembly keyed by event/publication/hash. Append only expected validated chunk ordinals; duplicate frames cannot duplicate paragraphs or citations. Render only the server's committed public representation, preserving typed value/citation atoms. Complete/hash-verify according to the final wire schema at `publication_end` before advancing that event's delivery cursor. No private token or candidate-answer stream is rendered.
5. Advance `ack` only after a whole event is applied or its explicit revoked/aborted disposition is applied. A dropped connection halfway through an answer resumes/replaces that same representation through server recovery. It never requests another model execution to complete a stream.
6. On `resync_required`, scope change or uncertain ordering, increment a session generation, cancel obsolete fetches/assemblies and adopt a fresh authorized baseline. Old-generation callbacks cannot repaint discarded content. Mark the transcript unavailable/stale as appropriate and gate evidence access while current authorization is unknown. Returning from suspension must synchronize before treating cached source-bearing content as current.

The session owns socket, subscriptions, timers and pending fetches independently of transcript rendering. Theme changes, pane expansion and ordinary rerenders do not reconnect. React development setup/cleanup must not produce two live sockets, duplicate sends or leaked listeners. Leaving a Chat disposes its transport; returning synchronizes. Work continues on the server when the socket closes. Project/Data screens have no invented Project-wide socket endpoint; their visible asynchronous upload/preparation views may perform bounded HTTP status refreshes, stopped on exit/terminal state. This does not replace Chat streaming with polling.

Use finite configured jittered reconnect/backoff, liveness/queue/frame/chunk/assembly limits. Do not invent numerical transport limits in UI code. Deduplication history is bounded by the server recovery window; insufficient history forces resync. Coalesce render notifications where useful, never erase intermediate required event semantics. Each tab has its own cursor; an advisory same-origin non-content invalidation message may accelerate local cache clearing but cannot admit work or substitute for server authorization.

## Commands, uncertainty and recovery

Create command and idempotency IDs once at user intent, bind them to exact typed payload/revision and keep that payload immutable in memory until resolved. Prevent a second click on that same unresolved intent; do not block genuinely separate questions or unrelated runs. Show Sending/Checking separately from admitted Queued/Running. A receipt means the command committed, not that a run was admitted or succeeded.

If acknowledgment is lost, resolve the original command ID through the approved lookup and authorized snapshot. Do not issue another send on socket reconnect or create a fresh key. A lookup's temporary absence is not proof of non-commit while the original operation may be in flight. Retain an unresolved disposition until the backend can establish an outcome; any explicit same-intent retransmission must preserve original IDs/payload and satisfy the server contract. A reloaded client with identities but no original payload performs lookup only. Clear the submitted draft only on confirmed receipt, and only if the user has not edited it since that intent; otherwise preserve the newer draft.

Clarification replies target the exact original submission/run and question identity with their own field and pending state. The main composer always creates a new question. Before-admission entry cards and analytical cards remain distinct internally even when visually similar. Suggestions require explicit selection. Expired/revoked/replied cards cannot accept another reply.

Retry is visible only from current backend recovery eligibility and carries the original run ID plus expected revision. An eligibility/precondition conflict refreshes that state and explains it; it does not create a replacement run. Terminal, expired, exhausted or source-unavailable work stays closed. There is no manual Stop or cancel-run action. A new analysis is an explicit new-question intent.

## Upload, evidence and deletion

Uploads follow reservation → complete binary transfer → status reconciliation → ingestion receipt → Dataset admission/preparation. Hash/size, format choices, settings/preview hashes and replacement identities follow existing contracts. No resumable-chunk protocol is invented. Reconcile an uncertain upload before retransferring; interrupted HTTP transfer is not proof that reserved space was released. Only an unadmitted upload is eligible for its upload-delete path. Cancelling a local picker is not cancellation of a server run.

Display whole-file transfer status separately from preparation status. Confirmation submits the exact preview/hash/settings revision. If the preview changes or replacement target disappears, fetch the current state and request an explicit user choice. Never reinterpret Replace as Add; a failed replacement leaves the old source available. Only ready server snapshots enter eligible new-question source selection; recorded historical scope never follows later picker changes.

Evidence rendering preserves server types, units, coverage and row/column locators. Fetch bounded rows by approved cursor/selection; do not compute new aggregates or silently sort/filter an incomplete table as if it were the full source. Charts use authorized governed images with meaningful alternatives and backing tables; no arbitrary HTML/SVG execution. Code is escaped text. Render the contracted public text/structured representation safely; do not enable raw HTML or load remote assets from generated content. Final publication block/wire schemas must be settled before choosing any Markdown-specific tooling.

On revocation or an authoritative 410, immediately fence the affected generation, remove transcript/evidence/artifact bodies, cancel associated requests, evict query/mutation payloads and revoke object URLs. Cache cancellation alone is insufficient: late successful responses must fail generation/revision/revocation guards. Where precise closure cannot be established locally, clear the affected Chat's source-bearing projection and resynchronize rather than estimating dependencies. Clear affected linked UI references and exact-card drafts; Chat/Project deletion also clears their drafts and routes to an authorized parent. Already delivered or user-copied bytes cannot be recalled.

Revocation bypasses decorative exit delays: end/skip an active theme View Transition, discard its old-content snapshots, cancel source-bearing pane exits and clear immediately. Smooth movement must never keep revoked content visible while waiting for an animation callback.

Successful delete receipt means revocation is accepted even if cleanup is pending. Render cleanup status without continuing to expose content. Chat deletion retains Project Datasets; result/Dataset deletion follows server dependency closure. No optimistic resurrection on network error, query refetch or Undo; this version does not promise reversible deletion. Inactive tabs may learn through their own socket, non-content invalidation or resynchronization on return; never claim immediate removal of bytes from a disconnected browser.

## Visual and interaction acceptance

The user approved the layout foundation and explicitly requires visible inspiration from AI Engineering from Scratch (warm paper/ink/cobalt, rules, technical detail), Tailwind (alignment, typography, refined controls/code surfaces), and Designed to Scale (button-origin circular theme reveal). The final frontend needs a fuller design pass and visual comparison against the reviewed concept; the concept is a baseline, not permission to stop at starter styling.

- One theme toggle in the top bar at every responsive size. Its sun/moon state and accessible name track the theme. The new theme expands from the button center in a viewport-covering circle; the reviewed candidate is 560ms with the observed reference easing. Reduced motion switches immediately; an unsupported API has a restrained fallback. Guard interrupted/repeated toggles and preserve focus, draft, source selection and active delivery.
- Semantic light/dark tokens cover text, surfaces, controls, focus, code, tables, chart alternatives and overlays. First paint uses the saved non-content preference; system changes do not overwrite an explicit preference. Verify contrast and font loading locally; the reference extracts and prototype scores are not application accessibility proof.
- Panel entry and exit retain continuous motion; do not remove closing content before the exit completes. Sidebar/pane width changes and code folds settle smoothly, remain interruptible and do not queue stale completion callbacks. A resumed user action cannot leave a pane inert or hidden by an earlier transition. Streaming text has no per-character entrance animation.
- The composer is the bottom-most content. **Nothing appears beneath it:** no footer, disclaimer, helper text or concept controls. Remove visible “Ask a new question” and “Reply to this clarification” labels as requested; retain descriptive placeholders and programmatic labels. Inline validation/status belongs within the relevant field/card area, not below the composer. Prototype controls are not shipped in product UI.
- Desktop supports collapsible Project navigation and expandable evidence; narrower layouts use a drawer and full-width evidence with focus restore. Preserve draft, selected claim and reading position. Do not auto-scroll someone reading history; show Jump to latest above/within the conversation. Native keyboard controls, clear focus, modal focus management, bounded live announcements and table semantics are required.
- Support empty/loading/failed/partial/Direct/reviewed/clarification/reconnecting/revoked states with real contract wording and actions. A chart-only failure may leave supported values; labels must describe the actual publication variant. Never turn progress into fictional percentages or a terminal notice into a successful answer.

## Implementation slices and verification gates

| Slice | Reviewable result and meaningful checks |
| --- | --- |
| F1 shell/design system | Route skeleton, Project navigation, responsive panes and final tokens/fonts/controls. Compare light/dark desktop/tablet/phone views against accepted references/concept; keyboard, reduced motion, circular origin, no-flash path and empty composer bottom. |
| F2 resources/import | Real Project/Chat/Data management and exact import flow. Verify whole-file uncertainty, quota/preview conflicts, failed replacement preservation and stale response fencing. |
| F3 Chat session/commands | Real ticket/Upgrade/bootstrap/replay, typed store and exact operation targeting. Verify duplicate frames, lost receipts, reconnect at chunk boundaries, StrictMode lifecycle and multiple independent runs/cards. |
| F4 public results/evidence | Typed committed answer/partial/Direct/notice renderers, rows, chart/code and governed downloads. Verify exact citation/locator values and midstream/midfetch revocation with old-response suppression. |
| F5 integrated product acceptance | Real product browser through same-origin ingress against the existing L2 backend harness, with deterministic external transports. Add real visual/state/focus checks; separately admitted L3 remains necessary for live capability claims. |

Reuse the [B01–B13 backend scenario families](backend-integration.md) for applicable lifecycle/transport failures; do not duplicate those with an entirely mocked frontend and claim equivalent proof. Focus reducer/assembly tests on gaps, duplicate/partial events, generation changes and command uncertainty. Browser tests cover actual ownership/security/proxy/cookie behavior and user-visible results. Record each scenario as pass/fail/not_run/blocked with its declared layer and independent expected outcome. **All new F1–F5 results are not_run.** Prototype observations establish only the stated concept behavior.

Before enabling the product frontend: finalize/pin remaining compatible dependencies and public schemas; set finite client resource/retry limits; prove ingress deep links and Upgrade; complete the relevant backend prerequisites and F1–F5 checks. Font licenses/delivery, token refinements and measured layout/stream limits remain implementation gates. Design approval and the separate authorized Router/Query package addition do not authorize product implementation, backend services or live agent execution. Next planning phase: CI; actual implementation follows the approved build order.

## Official-source basis

Reviewed 27 November 2026: [React Router declarative routing](https://reactrouter.com/start/declarative/routing), [TanStack Query defaults](https://tanstack.com/query/latest/docs/framework/react/guides/important-defaults), [query cancellation](https://tanstack.com/query/latest/docs/framework/react/guides/query-cancellation), [React external-store subscriptions](https://react.dev/reference/react/useSyncExternalStore) and [native View Transitions](https://developer.mozilla.org/en-US/docs/Web/API/View_Transition_API/Using). These support the mechanisms, not repository compatibility. Context7 supplied current React docs because it had no indexed 19.3.1-specific version; the package manifest's declared version is not a verified installed build.
