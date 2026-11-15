# Answer Specialist design

15 November 2026. **Rounds 1–6 approved; component design review closed with explicit readiness gates.** Evidence is explicitly part of the immutable input packet. No implementation or paid run has started. Earlier round scope notes describe approval at that time; later approved rounds settle their named contracts.

[Overall architecture](overall.md) · [Supervisor](supervisor.md) · [SQL Specialist](sql-specialist.md) · [Python Specialist](python-specialist.md)

## Inherited approvals

User clarification, 15 November 2026: Answer Specialist and Reviewer act as independent agents, each deciding from its explicit supplied context and role instructions. They do not share a model conversation or implicitly access one another's internal working state/history. Linked drafts/feedback are explicit runtime handoffs, not additional computed evidence or authority to force a decision. The Answer Specialist reports unresolved gaps; the Reviewer assesses the candidate independently against its supplied evidence. This does not require different model families or guarantee independent errors.

Fresh analysis passes from supervisor evidence gathering to this specialist's draft and then Reviewer approval. Direct answers remain with the supervisor. Evidence defects return to the supervisor; draft-only defects return here; evidence defects take precedence. At most two review passes are allowed across the run. Partial fresh answers still require review. Runtime source/deadline/publication gates remain authoritative.

## Round 1: approved responsibility and evidence boundary

### Approved responsibility

Draft a clear response to the original question from the delegated, valid evidence and confirmed analytical context. Explain supported findings, assumptions, limitations and incomplete deliverables. Link project-data claims to inspectable evidence. Return a draft for review, not a final published answer.

The specialist may summarize supplied findings, compare explicitly supplied values, explain methods and describe supplied charts. A claim about a whole population requires evidence covering that population; a bounded preview cannot establish unseen rankings, distributions or totals. User statements remain request text or explicit assumptions rather than verified project facts. General explanations may help interpret results but must not invent causal conclusions or source-specific facts.

### Arithmetic alternatives

| Approach | Benefit | Cost |
| --- | --- | --- |
| Require computed evidence for every new numerical quantity — approved | Reuses SQL/Python provenance and avoids a new calculation path in drafting. | Even a missing simple difference or rate must return for upstream computation. |
| Allow a bounded deterministic inline calculator with cited operands | Can avoid an extra SQL/Python delegation for simple derived figures. | Requires an additional formula/value-validation and evidence contract, including precision, units, zero denominators and provenance. A language-model answer alone is not that calculator. |

**Approved boundary:** this specialist creates no new analytical quantities and has no SQL/Python, file, network or calculation tool. Every new total, difference, percentage change, rate, aggregate or statistical value must already exist in valid computed evidence. If absent, return the precise missing calculation to the supervisor rather than running tools, delegating directly or supplying mental arithmetic. The supervisor selects the existing SQL/Python workflow.

Formatting an existing quantity is distinct from computing a new one. Declared rounding, number/date presentation and unit display may preserve the cited value's meaning; exact formatting/validation rules are a round 3 decision. For example, an already computed share of 0.20 may display as 20%; dividing an uncomputed numerator by a denominator requires upstream evidence. Formatting cannot change precision silently, conceal uncertainty or invent a different metric.

### Examples

| Evidence/request | Approved behavior |
| --- | --- |
| Supplied revenue values 100 and 120 | State the supplied values and that the second is larger; do not introduce a difference of 20 or growth of 20% without computed evidence for those quantities. |
| Computed growth 0.20 with verified metric/filter/period | Explain the result, cite it and use the agreed percentage display policy. |
| An incomplete preview appears to have a largest region | Do not claim it is the project-wide maximum; request the necessary complete evidence or computed ranking. |
| Monthly totals exist, but a requested distribution does not | Return the missing row-level analysis requirement; do not infer a distribution from totals. |
| Values are valid but requested chart failed | Draft supported findings, identify the missing chart and mark the result partial for review. |
| Revenue fell; no attribution evidence exists | Describe the supported decline without inventing a cause; identify what analysis would be needed to answer why. |

### Evidence gaps and review routing

Missing, inconsistent, invalid or insufficient evidence is a supervisor issue. Missing assumptions that materially affect interpretation also return through the supervisor; this specialist does not ask the user directly. It may preserve supported findings in a clearly incomplete draft where useful, but must expose the missing claim/deliverable rather than imply fulfillment.

An incorrect copied value, explanation or conclusion can be corrected here when the correct computed evidence already exists. If only operands exist and a new derived quantity is needed, that is an evidence gap under this approved boundary, even if the arithmetic is simple. This clarifies the existing evidence-versus-draft return rule without adding review passes. Exact return schemas and interaction with Reviewer feedback are later rounds.

### Approval scope and remaining work

The user approved the evidence-grounded drafting role, absence of execution/calculation tools, upstream computation of new quantities, constrained display formatting and precise return-to-supervisor behavior. This does not select input/state schemas, citation locators, draft representation, Reviewer output schema, model/prompts or numerical limits.

Subsequent rounds cover request/context/state; draft/claims/citations and formatting; Reviewer/revision/partial handoff; lifecycle/privacy/limits; and evaluation/final audit. The broader memory policy remains a dependency. At review completion, delete temporary plan Markdown files and repair links as requested, retaining this approved specification and decision log.

## Round 2: approved request, bounded context and state

### Supervisor request

Reuse the shared Action model and analytical constraint types. Approved `AnswerAction` fields:

| Field | Meaning |
| --- | --- |
| `action_id` | Runtime-issued UUID. |
| `type` | Literal `answer`. |
| `objective` | Nonempty focused drafting objective, preserving the actual request and required deliverables. |
| `evidence_ids` | Unique list of explicitly selected numerical/tabular evidence UUIDs. May be empty only for a missing-evidence explanation with no unsupported project-data claims. |
| `chart_artifact_ids` | Unique list of selected published chart UUIDs; may be empty. |
| `constraints` | Existing shared metric definitions, filters, date windows, analysis timezone, grain and units. They guide meaning, not access. |

No raw-upload/table/path selectors, model-chosen runtime identities or access to the entire Project. Chart references must resolve to valid numerical backing, which the runtime includes as part of the authorized packet rather than leaving a chart as the only numerical evidence. All resolved dependencies must remain within the pinned scope. A source-table reference in a confirmed constraint is contextual and does not grant data access.

### Runtime-resolved packet

Supply run/project/chat/task identity, original user question and the immutable validated request. The runtime separately owns expected attempt, remaining review passes, current deadline/reserve, budgets and environment/model configuration. The specialist cannot alter these or reset the run-wide review counter.

Resolve selected evidence into actual bounded typed values, schema/count, column mappings, producer provenance, integrity metadata and durable references. Explicitly mark whether all rows are visible and what has been shortened or truncated. A reference to a full file is not knowledge of unseen rows. If the required values cannot fit the approved bounded packet, return for a narrower computed result rather than infer from the preview.

Resolve charts into title/description, numerical backing, bindings/units/ordering/scales, limitations and validated artifact metadata. This round does not require a vision model or image input. Metadata/backing can support a description of the represented findings; the draft cannot claim that it visually inspected the image when no image was supplied. Image inclusion and citation/display schema remain later decisions.

Carry actual unmet-deliverable/error facts from runtime outcomes so a missing chart cannot disappear from the drafting objective. Distinguish confirmed definitions, user-provided assumptions, computed facts, untrusted source labels and specialist observations. Observations and user assertions do not replace numerical evidence. Reuse inherited producer dependencies; final draft/answer dependency attribution belongs to the later lifecycle/source-removal discussion.

Revision context is runtime-resolved and either absent or tied to the exact prior draft and Reviewer result by their recorded IDs. Supply the authorized prior draft, selected supporting context and blocking feedback. Reject mismatched/stale/cross-run feedback rather than treating it as a new user instruction. Exact draft-version/feedback schemas and re-entry mechanics belong to rounds 3–4. A revision is a new invocation with its own immutable packet; it does not mutate the prior draft or replenish review passes.

No unbounded chat history, raw results, storage URLs, credentials or hidden source-derived summaries are automatically included. The broader memory/context policy determines bounded selection and compaction before dependent implementation; it cannot discard validity/provenance or transform unverified statements into evidence.

### Context-delivery alternatives

- **Runtime-supplied bounded packet — approved:** deterministic authorization/context boundary and no additional tool loop; insufficient evidence goes back to the supervisor.
- **Read-only evidence lookup tool:** can fetch additional slices on demand, but adds retrieval authorization, tool budgets and recovery state to a drafting-only component. Not selected by this proposal.

The approved specialist has no tools. Its work is model drafting and bounded validation/revision, with all evidence resolution owned by the runtime/supervisor.

### State and ownership

| Field | Owner and purpose |
| --- | --- |
| `input` | Runtime-validated immutable request and resolved packet: `input.request` holds the action/evidence IDs, `input.evidence` holds resolved evidence objects with bounded actual values, and `input.charts` holds resolved chart/backing metadata, alongside the run and revision context. |
| `messages` | Bounded action-local drafting/repair messages. Recorded feedback stays linked to its draft; history is not runtime authority. |
| `draft` | Current working candidate, kept separate from a validated handoff. Exact representation is round 3. |
| `execution_status` | Runtime-owned identity/attempt, phase, deadline/reserve, budgets/counters, review-pass availability and stop reason. |
| `output` | Empty until runtime validates a terminal return. Handoff/status variants are round 4. |

Evidence is in state under `input.evidence`, not merely mentioned in messages or represented only by the request's IDs. Each entry contains its evidence identity, bounded typed values, schema/count, coverage/truncation markers, provenance and durable full-artifact reference. Full Parquet/PNG bytes stay in artifact storage. The runtime revalidates references on restoration; a cached input packet cannot revive a removed source.

There is no second top-level mutable evidence collection: this specialist consumes computed evidence and produces drafts. Preserve draft IDs/versions, evidence references and feedback links in durable records for recovery. No live file/model-session object is checkpoint state. Invalid candidate drafts never become publishable through checkpoint restoration.

### Acceptance and approval scope

Reject unknown/duplicate/out-of-scope/invalid evidence or charts, invalid chart backing, mutable runtime identity/budgets and mismatched revision feedback. Test truncated evidence, an empty explanation-only packet, a failed requested chart, unsupported user assertions and revisions that cannot reset review count. Packet validity must be rechecked during the later lifecycle and publication gates.

The user approved the six request fields, bounded runtime packet/no-tools approach and five state fields, with evidence nesting made explicit in response to their question. This does not approve claim/citation locators, display formatting, draft/Reviewer schemas, detailed retry/recovery, broader memory policy or model/configuration limits.

## Round 3: approved draft, claims, citations and formatting

Two independent parallel medium-reasoning tracks examined claim/reference representation and typed display/validation. Their reconciled recommendation is a small ordered block format, not an unrestricted Markdown document or a general layout language.

### Representation alternatives

| Approach | Benefit | Cost |
| --- | --- | --- |
| Free Markdown plus attached citations | Easy free-form composition. | Ambiguous claim boundaries and number/citation attachment; runtime must parse generated numerical text. |
| Structured prose blocks with typed value references — approved | Explicit support per block; existing values render deterministically. | Requires a small schema/renderer and constrains prose composition. |

Approved `Draft` has nonempty ordered `blocks` and an `unmet_deliverables` list. Each missing item has bounded `description`, `reason` and `required_evidence` strings. Runtime compares this with recorded unmet-deliverable facts; the model cannot hide a failed required chart by omitting it. Draft identity/version and terminal handoff are round 4.

Each block has a unique local `block_id`, `kind`, nonempty `spans`, and `supports`. IDs are bounded local identifiers, not runtime UUIDs. Kinds are `data_claim`, `general_explanation`, `assumption`, and `limitation`. Any project-data assertion requires support regardless of block kind. General explanations cannot disguise project-specific facts. An assumption block identifies an actually supplied confirmed/user-assumption context reference; it cannot silently propose and apply a new material assumption.

Span variants:

- `text`: literal prose. No raw HTML, executable markup or model-supplied image/storage URLs. Initial rendering treats it as text, not a Markdown layout/programming language.
- `value`: an eligible cell/metadata target plus one allowed format identifier; no replacement value, formula or operands.
- `chart`: a chart artifact UUID present in `input.charts`; the runtime resolves its safe presentation reference. Captions use the same supported prose/value rules, not numbers inferred from pixels.

Project-derived numerical assertions must use value spans. Question numbering, method names, source labels and contextual years are not automatically analytical quantities; a numerical regex alone cannot prove this distinction. Reviewer checks must catch invented numbers, including quantities spelled out in prose.

### Evidence and context targets

`supports` is a list of these bounded typed targets:

| Target | Fields and eligibility |
| --- | --- |
| `cell` | Evidence UUID, `row_locator`, `column_ordinal`; must identify a complete visible cell in `input.evidence`. |
| `metadata` | Evidence UUID and `field`; initially only the runtime-supplied exact `row_count`. It is result metadata, not automatically the count of the source population. |
| `coverage` | Evidence UUID; connects a qualitative finding to the supplied result. Whole-result claims need complete visible coverage or explicit computed evidence establishing the finding. |
| `chart` | A selected valid chart artifact UUID; supports chart presentation, not a numerical claim without backing references. |
| `context` | Runtime-issued reference to an actually supplied definition, filter, assumption or limitation. No arbitrary JSON path into source text or provenance. |

The runtime packet adds a stable row locator to each visible row: a zero-based physical row position in the validated immutable artifact. `column_ordinal` is zero-based in that artifact's returned normalized schema. Locators do not change when a different preview selection includes the same row; they are not displayed ranking or source-file row numbers. The evidence UUID/artifact identity binds them to a particular immutable result. This approved extension is reflected in the shared SQL/Python packet mapping.

Reject guessed hidden row indices, unknown/stale/cross-packet targets and shortened cells even when a visible prefix contains plausible digits. A full-file reference does not authorize an unseen value insertion. Coverage/context references do not license new calculations. The runtime resolves value spans from typed input, not by parsing untrusted labels or asking the model to supply scalar types.

Support attached to a data claim includes its value-span targets automatically, plus any explicit qualitative/context support. A structurally valid citation can still support the wrong conclusion; the Reviewer checks whether the claim follows, including population, grain, period and causality. Never extrapolate from incomplete preview coverage.

### Small deterministic display policy

| Format | Meaning |
| --- | --- |
| `exact` | Preserve the authoritative scalar representation, including integer/decimal precision. NULL is explicitly missing, never zero; booleans/strings are not numerical metrics. |
| `fixed_0`, `fixed_1`, `fixed_2` | Display a finite numeric value at the named decimal precision. |
| `percent_0`, `percent_1`, `percent_2` | Display an already computed explicitly identified dimensionless share/rate as a percentage; no numerator/denominator calculation. |
| `currency_2` | Two decimals plus the confirmed currency code; reject missing/ambiguous currency identity. No currency conversion. |
| `iso` | Preserve the temporal type, supported precision and explicit offset/timezone semantics. No implicit timezone change or timestamp-to-date conversion. |

Use one versioned display policy: decimal round-half-even, decimal point `.`, no locale-dependent grouping or compact thousand/million suffixes, and normalize rounded negative zero to zero. Integers/decimals never pass through binary float. For finite float64 formatting, use its canonical shortest round-trip decimal representation as the decimal display basis, then apply the same rounding rule; this does not increase its analytical precision. Exact float representations and tie cases must be fixed by compatibility fixtures for the pinned renderer.

The runtime supplies allowed format IDs from the typed value and explicitly confirmed unit metadata. It must not infer share-versus-percentage-points or a currency from ambiguous prose. Unknown unit meaning requires upstream clarification; a plainly incorrect format choice with adequate metadata is a draft error. A NULL may display as missing under `exact` but numeric formatting of NULL, strings, booleans or non-finite values is rejected. Unsupported values return an evidence requirement, not a fabricated replacement.

Chosen precision is inspectable and the original exact value remains available through its citation. Rounded text must not hide distinctions or uncertainty material to the conclusion. Ordinary supplied units can accompany a value; scaling/currency/temporal conversions beyond this initial display policy require separately computed evidence or a later reviewed policy extension.

### Rendering, partial answers and validation

The runtime renders spans and citation markers; the model cannot choose authoritative URLs, target values or storage paths. Keep a text transcript equivalent to the structured draft for CLI/review; it must use the same resolved values/citations, not independently generated numerical prose. Exact UI styling and serving mechanics remain later application work.

An explanation-only empty packet may contain grounded missing-evidence limitations and general explanations, not unsupported data claims. Partial drafts retain supported blocks/citations and explicitly name missing calculations/charts; their complete/partial/blocked handoff and Reviewer feedback linkage are round 4 decisions.

Deterministic validation checks schema, local ID uniqueness, span/target eligibility, format compatibility, missing deliverables and current artifact validity. It proves a rendered value matches an allowed source/format, not that the selected source answers the question or that the conclusion is true. Semantic review still checks numerical claims hidden in prose, citation relevance, coverage, rounding implications, units and unsupported causal explanations.

Acceptance cases include large integers/decimal ties, scalar NULL versus empty result, share versus percentage points, incorrect currency/temporal formatting, non-finite or hidden/shortened cells, reordered previews, chart references without numerical backing, empty/partial packets, and correct displayed values paired with a false conclusion.

The user approved this block/span/target schema, stable packet row locators, runtime value rendering and the initial display policy. This does not select the later Reviewer/result schemas, lifecycle dependency attribution, context compaction, prompts/models, evaluation thresholds or final UI layout.

## Round 4: approved draft identity, Reviewer handoff and revision

### Immutable draft and review identity

The runtime assigns a fresh `draft_id` UUID to each structurally valid candidate and persists its blocks, rendered transcript, resolved references, input-packet identity/hash and render-policy version. Content hashes bind the reviewed content. A revision has a new UUID and `revision_of_draft_id`; do not add an independent version counter or edit an existing draft in place. Local block IDs are interpreted only within their draft.

The review request supplies runtime-owned `review_id`, exact `draft_id`/`draft_content_hash`, `draft_input_packet_hash`, `rendering_policy_version` and run-wide `review_pass` (1 or 2), together with the structured draft, equivalent rendered transcript, complete bounded drafting evidence/context, original obligations, recorded unmet deliverables, partial authorization and exact linked revision material. Reviewer round 2 additionally binds its complete resolved input using a distinct runtime-owned `review_input_packet_hash`. This full required review packet must fit its finite admission limits; do not silently drop supplied evidence or truncate the candidate. Draft and Reviewer packet hashes serve different purposes. See [Reviewer](reviewer.md). No inference from a full artifact unseen by the drafter is silently inserted into that draft. Evidence sufficiency issues return through the existing supervisor path.

Reviewer round 3 defines `reviewed` outcomes with exact review/draft identities, both input-packet hashes, rendering-policy version and pass, plus an `approved` or `rejected` verdict. Approval has empty findings; rejection has nonempty blocking findings with local `finding_id`, `category` (`evidence` or `draft`), affected `block_ids` (empty for a whole-draft issue), bounded `explanation`, eligible supplied `support_refs` and `required_change`. Runtime derives evidence-first correction routing. Wording/style preferences alone do not block. Incomplete or unusable reviews instead produce runtime `failed` outcomes with genuine error references and no substantive verdict; they cannot permit publication or grant extra logical passes. See [Reviewer](reviewer.md) for the approved request/state/assessment contract; round 4 now defines durable recovery, nonrefundable pass reservations, stop-on-terminal-review-failure behavior and provisional physical-call/reserve bounds.

Reject mismatched, stale, superseded or cross-run feedback before it can change state. A new input packet or any change to reviewed draft content requires a new candidate; approval never transfers to a different draft or rendering-policy version.

### Specialist return variants

| Return | Fields/meaning |
| --- | --- |
| `draft_ready` | `draft` using the approved schema, and `completeness` (`complete` or `partial`). Ready for validation and review, not publication or semantic approval. |
| `blocked` | Bounded `explanation` and nonempty `requirements`: each has `kind` (`evidence`, `definition`, `conflict`) and precise `description`. No publishable draft accompanies this return. |
| `failed` | Genuine runtime/model/validation error reference supplied by orchestration. No invented failure code or publishable draft. Detailed error/retry policy is round 5. |

If a useful supported partial response is appropriate, use `draft_ready/partial` rather than attaching an unreviewed draft to `blocked`. A no-evidence explanation may still be drafted and reviewed under the same supervisor partial-authorization rule when it contains no unsupported project-data assertion; absent evidence is not permission to fabricate an answer.

### Partial authorization and correction routing

The runtime-resolved packet carries supervisor-authorized `partial_answer_allowed` and a recorded reason such as exhausted analysis reserve, failed deliverable or insufficient available evidence. This is orchestration context, not another model-controlled action field. The model cannot change a requested deliverable to optional. A partial draft must preserve the original objective, name its unanswered portions and reconcile its unmet list with actual runtime facts. If partial handoff is not authorized and full drafting is impossible, return `blocked` for supervisor replanning.

Reviewer approval of a truthful authorized partial means the supported partial draft may proceed to final checks, not that the original request was fully fulfilled. Missing requested charts remain visible. The Reviewer can still reject unsupported findings, incorrect values or hidden gaps in a partial draft.

| Review result | Next step |
| --- | --- |
| Approved | Final runtime checks may publish only that exact active draft and its recorded complete/partial status. |
| Rejected, evidence issue (including mixed evidence/draft findings) | Supervisor replans evidence gathering or clarification. The Answer Specialist cannot generate the missing calculation or silently change assumptions. |
| Rejected, draft-only issue with sufficient evidence | Invoke Answer Specialist again with the exact rejected draft, feedback and authorized packet. Produce a new candidate linked to its predecessor. |
| Second rejection | Stop analysis/revision review flow; omit rejected analysis and produce the bounded terminal explanation described below. |

Evidence changes after replanning produce a newly resolved packet and candidate. Revising draft prose alone does not widen its evidence access. Stale feedback referencing a predecessor cannot overwrite a later candidate.

### Two-pass accounting and terminal explanation

The runtime durably reserves a logical review pass before dispatch, keyed by `review_id`. Under approved Reviewer round 4, a committed reservation is nonrefundable, including a crash before dispatch; recovery uses that same reservation. Terminal failed/incomplete review stops the flow on either pass; do not spend pass 2 to repeat a terminal failed first review. Bounded recovery/repair happens before terminalization. Duplicate delivery/recovery of the same immutable review request reuses the reservation and recorded response. Transport retry or bounded malformed-response repair cannot change the reviewed draft or turn a recorded rejection into a new free review. Actual model calls still consume their finite budgets. A different draft/review requires the next available pass; a new action/attempt does not reset the run's two-pass maximum. Detailed recovery mechanics follow in round 5.

After the second valid rejection, no third review or new analysis draft is allowed. Use a runtime-owned bounded explanation populated from the validated blocking findings: identify the unresolved verification problem and missing evidence where relevant, without copying rejected conclusions or numerical analysis. It must not become a new generative answer disguised as an error notice. Likewise, if budgets/deadlines cannot accommodate review, do not publish an unreviewed partial; use the applicable bounded failure notice.

Immediately before publication, recheck that the approved draft is the active immutable candidate, with no conflicting superseding revision, current authorized sources and an unexpired hard deadline. Reviewer approval does not override source invalidation or timeout. Exact draft dependency attribution and transactional publication ownership remain round 5.

### Acceptance and approval scope

Test copied/modified draft under an old approval, mismatched feedback IDs/hashes, missing chart falsely labeled complete, unauthorized partial handoff, evidence-and-draft mixed findings, revision over stale evidence, duplicate review dispatch, malformed review response, and a third review attempt. Verify the second-rejection explanation identifies missing evidence without reproducing rejected analysis.

The user approved the immutable draft/review handoff minimum, three specialist returns, supervisor authorization for partial drafts, feedback routing and durable two-pass accounting. This does not finalize Reviewer internals, lifecycle/error details, source-dependency attribution or evaluation settings.

## Round 5: approved lifecycle, dependencies, privacy and limits

Two independent parallel medium-reasoning tracks covered durable lifecycle/source attribution and errors/budgets/privacy. Reuse the existing standalone SQLite authority, moved together to Postgres at integration; no new service or sandbox is needed for drafting.

### Invocation, candidate and review records

Before dispatch persist `(action_id, attempt, invocation_key) → model_call_id`, request digest, immutable authorized input packet/hash, model/prompt/config identities, budget reservation and current owner generation. Replay reuses this mapping; changed payload under one key is rejected. Deliberate repair/revision calls receive new keys. Track actual provider requests separately so transport retries remain visible and charged.

Invocation phases are `prepared → dispatched → response_recorded → validated → handed_off`, with a terminal failure path. Record the received response before checkpoint advancement. Adopt one canonical response per logical invocation; late duplicate provider responses cannot overwrite it. Malformed canonical output requires a new bounded repair invocation, not replacement of the saved record. Runtime allocates one immutable draft per validated candidate, then atomically records handoff and the active-candidate pointer, guarded by expected attempt/generation/predecessor. A late response cannot supersede a newer revision.

Freeze blocks, exact rendered transcript, resolved values/formats/citations, immutable evidence/chart identities/hashes, input packet, completeness/unmet facts, dependency set and rendering-policy identity in the reviewed envelope. Finalization does not rerender against newer data or a changed policy. Safe authorized artifact access may be resolved afresh without changing approved analytical content.

Review reservations/results use round 4's durable `review_id`, exact envelope and run-wide pass count. A validated verdict is terminal for that review. Duplicate feedback creates no extra revision; a rejection cannot be replaced by a later approval under the same ID. Changed content needs a new candidate and an available pass. Persist accepted feedback before checkpoint changes. Any additional source-derived facts introduced during later Reviewer design must be explicitly scoped/recorded; they cannot silently extend an old approved envelope.

### Recovery and publication

Recovery reads ledger records before requesting another model response. Restore committed handoffs/reviews/publication and missing checkpoint updates once, after current authorization/source/integrity checks. Adopt recorded uncommitted responses only under current ownership/attempt/predecessor guards. Unknown model-call completion can use an accounted replacement provider request under the unresolved logical invocation; generation fencing permits only one adopted outcome. This is an inference call with no execution side effects, so do not import Python's sandbox process-retirement barrier.

Store immutable draft bytes before committing visibility. One publication transaction checks exact active draft, matching approved review/envelope, current ownership/attempt, authorized complete/partial state, valid run, available dependencies and unexpired hard deadline, and records an idempotent final-answer identity. Serialize this with source tombstones/run invalidation. Deletion first blocks publication; publication first is subsequently invalidated and access revoked. Lost acknowledgments read the existing result. Uploaded bytes/checkpoints alone grant no visibility.

### Approved conservative dependencies — explicit PRD refinement

Derive each draft's dependencies from the union of all source-bearing evidence and context actually supplied to its invocation, including chart backing, transitive evidence lineage, prior drafts and feedback. Selected citations express support but do not prove which supplied information influenced prose. A revision cannot discard predecessor dependencies while retaining predecessor/feedback content. Independently retainable A-only work requires a fresh independently scoped packet/context without B-derived material.

The final answer also retains any runtime-recorded source dependencies of its approving review. These are derived from authorized review inputs, never from a model-supplied dependency list. Detailed Reviewer context construction remains its component's work, subject to this minimum. Unchanged source evidence/charts retain their own dependency sets; producing a draft does not broaden those original records.

This deliberately refines the PRD's completed-answer 'actually used' rule: an answer produced from an A+B packet can be removed when B is deleted even if it cites only A. It is conservative invalidation, not proof of causal influence. Unfinished-run pinned-scope invalidation is unchanged. The user approved this broader answer-retention rule; the PRD/shared contracts are updated.

Automatically supplied source-derived context must have known authorized dependencies; unknown or unsupported retrieved context is excluded or returned to the supervisor. User statements remain unverified request text/assumptions, not computed facts. Original user wording is preserved without pretending it establishes verified source lineage.

### Errors, repair and stopping

| Condition | Behavior |
| --- | --- |
| Missing calculation/value, insufficient coverage, ambiguous definition/unit or conflicting valid evidence | `blocked` with a precise requirement, or an authorized supported `draft_ready/partial`; no evidence fabrication or expansion. |
| Malformed candidate, wrong locator/format, unsupported markup or omitted recorded deliverable | Bounded candidate repair with the same authorized packet. An unknown candidate target does not by itself mean the input artifact is corrupt. |
| Corrupt input, unauthorized reference, unavailable runtime dependency or invalid runtime contract | Runtime fails before consumption; identified transient retrieval faults may retry within limits. Do not ask the model to repair bytes/authorization. |
| Removed pinned source | Invalidate the run; no repaired prose can revive it. |
| Stale/cross-run/mismatched feedback | Reject before model invocation/state mutation; recover the correct recorded result or fail orchestration rather than guess. |
| Identified transient model transport fault | Retry the identical logical request within finite limits; count every physical request. |
| Exhausted transport/repair/context/token/cost/time budget or unknown internal fault | Runtime-created `failed` with a genuine error reference and bounded failure notice. No unreviewed draft is displayed. |

Runtime error references identify persisted error records with enumerated code/category, safe message, stage, related invocation/review IDs and disposition. Reuse shared applicable codes (invalid arguments/output, unavailable/integrity/source, budget/infrastructure/internal); keep drafting repair distinct from evidence replanning. Error prose never determines retry permission. Missing-evidence conditions take precedence over cosmetic draft repair.

Require finite counters for drafting invocations, physical model calls, transport retries and response/candidate repairs, plus bounded packet/history/output sizes, input/output tokens, spend and deadlines. Reserve before dispatch, charge actual usage afterward and restore consumption after restart. New action attempts do not replenish enclosing run budgets or review passes. Uncertain provider usage is not zero: retain a conservative reservation until reconciled and refuse more dispatch when bounded exposure cannot fit.

Admit a draft/revision only when its packet fits and sufficient bounded capacity remains for required review and finalization. Malformed response repair changes neither the evidence scope nor review count; Reviewer response repair must keep the same immutable review request. A recorded rejection cannot be retried for a free new verdict. Deadline/reserve exhaustion stops further calls and uses the appropriate bounded notice. Numeric ceilings and measured reserve adequacy are round 6 work; broader context/compaction policy remains memory-owned.

### Hosted trace and local detail boundary

Allow only opaque correlation/configuration IDs, role/phase, attempt/review counters, enumerated error/disposition/stop categories, timing, token/cache/cost accounting and bounded size/count metrics in hosted traces. Exclude prompts, drafts/rendered answers, feedback prose, evidence values, labels/source names, code/queries, paths/URLs, credentials, provider bodies and raw exceptions. A decision/error label cannot embed source text.

Authorized detailed packets, model responses, drafts and feedback stay in governed local storage with references/dependencies and the PRD deletion rules. Local retention is not a justification for uploading them through automatic model/framework tracing. Tests must exercise actual trace serialization with sentinel source data.

### Acceptance and approval scope

Cover lost checkpoint/acknowledgment, duplicate/late provider response, stale predecessor/feedback, changed rendered values/policy under approval, publication/deletion race and deadline expiry after review. Verify whole-packet A+B invalidation, retained feedback dependencies and independent A-only survival. Test malformed candidate repair versus missing evidence, preserved exhaustion on restart, bounded uncertain usage and hosted-error privacy.

The user approved this lifecycle/publication model, conservative draft/answer dependency refinement, repair/error boundaries, finite admission/accounting, trace privacy and corresponding PRD/shared-contract updates. This does not authorize numerical settings, live inference, implementation or paid evaluation.

## Round 6: approved evaluation and readiness audit

### Fixtures and acceptance

Reuse [evaluation and observability](evaluation-observability.md). Version each fixture's immutable packet, expected rendering, obligations, dependency set and required/forbidden events. Use scripted candidates/verdicts to test runtime invariants independently of model quality.

| Family | Required cases |
| --- | --- |
| Locators and scope | Artifact row 17 retains locator 17 in differently ordered previews. Reject hidden/shortened cells, stale/cross-packet references and invalid chart backing. A full-file reference does not expose unseen values. |
| Display | Decimal 2.345 rounds to 2.34 and 2.355 to 2.36 under fixed_2; negative rounded zero becomes 0.00. Confirmed share 0.125 becomes 12% under percent_0. Pin integer/decimal/float tie behavior, confirmed currency, NULL, nonfinite rejection, temporal type and offset preservation. Reject inferred units/conversions. |
| Arithmetic and semantic grounding | With only 100 and 120 supplied, reject new difference/growth quantities, including spelled-out prose. With precomputed growth, permit its value span. Test misleading causal explanations, truncated-preview rankings, result-row versus source-population confusion and data claims disguised as general explanations. Ordinary years or method numbering are not automatically analytical quantities. |
| Partial answers and review | Missing required chart stays unmet; partial needs supervisor authorization and review. Mixed findings route to supervisor; draft-only findings revise. Two valid rejections stop with the runtime notice. Style preferences alone do not block. |
| Identity and recovery | Reject changed packet/rendering/draft approvals and stale feedback. Inject failure around response persistence, candidate handoff, review reservation/result and publication commit/ack. Recover one canonical outcome, preserve counters and fence late responses. |
| Invalidation and privacy | A+B citing only A still depends on B, including B retained through drafts, feedback, chart backing or approving review. Fresh independent A-only work survives. Exercise deletion/publication orderings and expiry after approval. Serialize actual trace/error payloads with sentinel source values, labels, paths, URLs, feedback and credentials; none may escape. |

Every deterministic authorization, integrity, visibility, lineage, publication, review-count, budget and privacy assertion must pass. Report assertions passed/total and cases passed/total by family; any such violation fails the configuration regardless of prose quality. Include prompt-injection instructions in evidence/context as untrusted data and verify that they cannot expand authority or bypass the evidence boundary.

Measure model behavior separately: unsupported atomic claims / all project-data claims; correctly supported claims / all project-data claims; satisfied obligations / requested obligations; correct routing / routing opportunities; correct missing-evidence explanations / gap cases. Include qualitative, causal and spelled-out claims. Zero denominators are N/A. Pair answerable cases with gap cases to penalize blanket abstention. Report complete success separately from authorized-partial success, plus latency and total cost. Semantic judgments require blind adjudication and reported disagreement; structural citation validity alone cannot prove a conclusion.

Freeze fixture IDs, gold claims/obligations, rubric, scenario-family/template-separated development and held-out splits, and renderer identity before comparisons. Keep held-out labels sealed until final evaluation. Numerical model-quality acceptance targets, repetitions and judge configuration must be fixed before runs; missing targets block a release claim. This approval selects no unmeasured winning model or quality score.

### Provisional development ceilings

These are intersecting candidate ceilings, not product promises or extra run allocations. They include initial drafting, evidence-replanned drafting and post-review revision across the run; new attempts/actions cannot reset them.

| Bound | Candidate |
| --- | --- |
| Drafting requests | At most 4 logical invocations, with at most one malformed-output repair for each initial/revision candidate; all repairs count within 4. At most one transient retry or unknown-completion replacement across drafting, and at most 5 physical requests total. |
| Per physical request | 16,384 input tokens including instructions, packet, prior draft and feedback; 4,096 generated tokens including provider-accounted reasoning. The exact model/protocol must enforce compatible accounting and context capacity. |
| Draft shape | At most 16 blocks, 128 total spans, 32 spans/block, 128 distinct support/value/chart targets and 16 unmet-deliverable items. |
| Payload sizes | Candidate JSON at most 64 KiB; rendered text at most 32 KiB; each literal span at most 2,048 UTF-8 bytes; local block ID at most 64 bytes; each unmet-item string at most 1,024 bytes. |
| Packet | At most 8 evidence objects and 4 charts, with chart backing counted among evidence; at most 128 visible rows and 32 columns per evidence. Supplied cell text at most 2,048 UTF-8 bytes; shortened cells are ineligible citation targets. Token admission may bind sooner. |
| Drafting time | At most 60 seconds cumulative active drafting, including retries/repairs; 30-second request timeout further bounded by remaining drafting time and enclosing hard deadline. Waiting/recovery does not extend the hard deadline. |
| Review/finalization reserve | Before initial drafting, provisionally retain 60 seconds for review and 5 seconds for finalization, plus worst-case token/cost capacity for both remaining logical reviews. Before revision, retain capacity for the remaining review and finalization. Reviewer round 4 bounds this to two 30-second elapsed passes and at most five physical requests/run (one shared retry), each at most 32,768 input/4,096 generated tokens. Initial review capacity is 163,840 input/20,480 generated tokens plus configured charges; before revision retain 35 seconds and 98,304 input/12,288 generated tokens if the shared extra remains, otherwise 65,536/8,192. Exact rates, spending caps and model accounting remain required. These ceilings do not guarantee time for every allowed retry. |

Oversized packets return for narrower upstream evidence; do not silently drop material evidence, required deliverables or provenance to fit. Oversized/truncated model output is a bounded repair/failure, never a publishable truncated draft. Complete token, monetary and review allocations are mandatory even though their exact configured values depend on the selected model/Reviewer contract. These candidates remain subordinate to all enclosing run limits. Reserve adequacy and practical latency require measurement.

### Reproducibility, spending and remaining gates

Before a runnable evaluation, freeze a manifest containing commit plus dirty-patch identity, configuration/prompt/schema/display-policy hashes, exact built runtime/renderer/dependency identities, requested model, provider routing/fallback and inference/reasoning settings, exposed actual provider/model metadata, repetitions/seeds/concurrency, limits and reserves. Missing token-accounting semantics or required identities block that configuration's run; preparatory fixture authoring can proceed.

Forecast every role, case and repetition, including retries, cache/cold assumptions, separately billed judges and infrastructure. Require dated verified rates, finite action/run/suite monetary caps and applicable spending authorization before paid execution. Reconcile actual usage and billed spend; uncertain usage retains bounded exposure. Hosted evaluation traces obey round 5's allowlist.

The integrated design keeps the supervisor responsible for missing computations, scoped evidence and authorized partial answers; runtime owns identities, rendering, counters, dependency unions and publication; Reviewer owns semantic verdicts under the exact immutable handoff. No new database, execution tool or dependency is selected here.

Remaining dependencies: memory-owned bounded context/compaction and revision packet construction before dependent code; implementation and measurement of Reviewer round 4's approved candidate call/repair/output bounds and reserve admission; complete model/configuration/quality targets/spend caps before evaluation; built identities and actual formatter, privacy, ledger/recovery, invalidation/publication and deadline checks before enablement. No runtime milestone has passed. The user approved round 6 and closed this component's design review with those explicit gates. This does not declare implementation-ready or authorize coding/paid tests. Temporary plan Markdown files have been removed and their references repaired; this specification and the decision log retain the approved contracts.
