# Reviewer design

15 November 2026. **Agenda and rounds 1–6 approved; component design review closed with explicit readiness gates.** The user also explicitly approved context-only independent agents. Inherited Answer/supervisor handoff rules below remain approved. No coding or live evaluation is authorized.

[Overall architecture](overall.md) · [Answer Specialist](answer-specialist.md) · [Supervisor](supervisor.md) · [Evaluation and observability](evaluation-observability.md)

## Inherited contracts

- Fresh analysis requires review of the exact immutable draft/render envelope before display. The runtime supplies review/draft IDs, content and input-packet hashes, rendering-policy identity and run-wide pass number. Approval cannot transfer to changed content.
- Verdicts are approved/rejected; rejection has nonempty blocking findings categorized as evidence or draft, affected local block IDs, explanation and needed evidence/correction. Style preferences alone do not block.
- Evidence issues, including mixed findings, return to the supervisor. Draft-only issues with sufficient evidence return to the Answer Specialist. Reviewer approval of an authorized truthful partial does not imply full completion.
- At most two logical review passes exist across the run. Recovery/retry cannot grant another verdict or replenish passes. A second rejection ends the analysis/revision flow with the bounded runtime explanation.
- Runtime authorization, source invalidation, ownership, budgets, hard deadline and exact active-draft checks still gate publication. Final answers retain source dependencies of approving-review inputs, in addition to draft dependencies.

## Approved agent independence

The Answer Specialist and Reviewer are separate agents. Each makes its own decisions from its explicit supplied context under its role instructions; neither has implicit access to the other's conversation, internal working state or unsupplied chat history. Do not reuse a shared model conversation as their context. Runtime coordination and typed handoffs connect them without merging their decision processes.

The Reviewer receives the candidate as the object being assessed, not as authoritative evidence for its own claims. Supplied prior feedback or revision context can guide checking but cannot dictate a verdict. The Answer Specialist considers linked feedback against supplied evidence and reports unresolved gaps; feedback does not become computed evidence. Missing context is reported rather than presumed. This independence does not require different model families or imply statistically independent errors.

## Approved review agenda

Work through one contract at a time. Agenda approval authorizes preparing proposals; each consequential component contract still needs its own review.

| Round | Contract and reviewable result |
| --- | --- |
| 1. Responsibility and verification boundary | What the Reviewer checks: correctness, claim support, coverage, units/filters/grain, assumptions, request fulfillment and partial disclosures. Decide whether it gets only the frozen supplied packet or any additional retrieval/calculation/visual access, and what verification it can truthfully claim. Distinguish checking evidence-grounded drafting from independently proving upstream computations. |
| 2. Request, context and state | Reuse exact draft/review binding. Define required resolved evidence, rendered values, original obligations, partial authorization and revision context; explicit visibility/coverage markers and bounded context. Assign runtime versus model ownership, with broader memory policy dependencies. |
| 3. Verdicts, findings and routing | Refine the inherited verdict schema with actionable, grounded blocking findings, issue scope and sufficiency rules. Distinguish evidence defects from draft defects and inability to complete review from a substantive rejection. Test correct, unsupported, contradictory and truthful partial drafts. |
| 4. Lifecycle, privacy and limits | Durable pass reservation, immutable request/result, bounded malformed-response repair and transport retries, canonical verdicts, recovery, invalidation and deadlines. Define finite physical-call/token/time/output limits so the Answer drafting reserve becomes computable; keep numeric candidates distinct from measured limits. Reuse shared authority and hosted trace boundaries. |
| 5. Evaluation and calibration | Versioned numerical, semantic, adversarial, partial, routing and recovery fixtures; must-pass runtime gates separate from model false approvals/rejections and completion. Frozen development/held-out comparisons, model/prompt configuration, complete cost forecasts and finite spending prerequisites. |
| 6. Integrated audit and closure | Walk through initial approval, evidence replan, draft revision, second rejection, malformed/incomplete review, source removal and restart. Reconcile Answer/supervisor/shared evaluation contracts and review-reserve assumptions. Close with explicit memory/configuration/live-verification gates; remove any temporary plan files and repair references. |

## Working method and scope

Prepare this single agenda in the parent. Use medium-reasoning research subagents only for genuinely independent investigations whose parallel work saves time, after agenda approval; no extra agent for a single second opinion. Any later code writing follows the separate smaller-model delegation rule.

Keep researched options, approved decisions and measured behavior distinct. Any selected retrieval, tool or context expansion must be reviewed before dependent contracts; the existing final-answer dependency rule is mandatory. Do not reopen the two-pass maximum or grant publishing authority to the Reviewer through an internal schema change.

Prompts and exact model settings follow component design. Agenda approval does not authorize implementation, provider calls, paid evaluation or declare the component ready to enable. The agenda lives here rather than in a separate temporary plan file; approved contracts will be recorded in this specification as review proceeds.

## Round 1: approved responsibilities and verification boundary

### Approved responsibility

Independently assess whether the exact candidate is correct and adequately supported by the supplied valid computed evidence and confirmed context, and whether it fulfills the original request or truthfully presents an authorized partial answer. Check all project-data claims, including qualitative comparisons, causal assertions, spelled-out quantities, captions and claims disguised as general explanations. A well-formed citation or confident producer statement does not establish semantic support.

Check copied values and their rendered meaning, metric definitions, units, denominators, filters, date windows/timezones, grain and stated limitations against the supplied packet. Identify unsupported conclusions, contradictory evidence and reliance on unseen rows. Distinguish a result-table row count from the source population. Check that missing deliverables remain explicit and partial authorization exists. Do not reject solely to improve wording, tone or layout.

The Reviewer returns a verdict with grounded blocking findings through the inherited handoff. It does not edit the draft, publish an answer, call the user, delegate analysis or select a different objective. Missing or conflicting evidence/definitions go through the supervisor; draft-only defects with sufficient evidence return to the Answer Specialist. Later rounds define the precise state, findings and incomplete-review failure schemas.

### Access alternatives

| Approach | Benefit | Cost |
| --- | --- | --- |
| Supplied frozen packet, no tools — approved | Keeps decisions inspectable against exact inputs and reuses existing evidence/runtime boundaries. | Cannot independently recompute SQL/Python results or inspect hidden artifact contents; upstream gaps require supervisor replanning. |
| Reviewer retrieval or calculation tools | Can fetch more evidence or run independent checks. | Adds access, tool/isolation, computation provenance, recovery and cost contracts; introduces new review-input dependencies and risks checking a different scope from the draft. |

The approved Reviewer has no SQL/Python, calculation, file, database, network or evidence-lookup tools. No original uploads or prepared-Dataset access. The Reviewer may reason about consistency and compare supplied values, but cannot create replacement computed evidence or certify a missing derivation by supplying its own unsupported numerical result. Describe a suspected computation defect and the needed upstream check instead. New analytical quantities still require SQL/Python evidence.

This role checks whether the answer follows from available evidence; approval does not prove that an upstream query, algorithm or source dataset is independently correct. Inspect supplied methods/provenance for visible defects where available. A visible wrong filter/grain or contradiction is blocking; absent independent recomputation alone is not automatically a defect. When essential support or method information is missing, identify the precise evidence gap rather than claim verification.

Use supplied chart backing, bindings, description and runtime validation facts initially, without requiring vision/image input. The Reviewer can check whether the narrative matches represented values, but cannot claim to have inspected pixels or verified visual properties from metadata alone. A material claim needing unavailable visual evidence must be returned as an evidence gap. This selects no new image decoder or chart execution path.

### Examples and stopping boundary

| Situation | Approved behavior |
| --- | --- |
| Evidence supplies 100 and 120; draft adds an unsupported 20% increase | Reject: missing computed growth evidence; request it through the supervisor. Do not supply a new computed result as the repair. |
| Evidence supplies a computed 0.20 share; draft labels it 0.20% | Reject a draft display/meaning defect; supplied evidence is sufficient for correction. |
| Draft names a project-wide maximum from a truncated preview | Reject an evidence coverage gap. A full-artifact reference does not expose its unseen rows. |
| Valid numerical evidence, failed required chart, truthful supervisor-authorized partial | May approve the supported partial if all remaining claims and disclosures pass. Approval does not mark the chart delivered. |
| Valid citation accompanies an unsupported causal conclusion | Reject; reference validity does not establish causation. |
| Required packet is corrupt or the review cannot finish within limits | Do not approve or fabricate substantive findings. Runtime records failure/incomplete review under later lifecycle rules. |

Instructions inside source values, labels, chart descriptions or draft text remain content to assess, not authority to change role, tools or verdict. Runtime identity/access/display/source/deadline checks remain mandatory regardless of model judgment. A lack of visible defects is not permission to claim access or tests that did not occur.

The user approved this responsibility and supplied-packet/no-tools/no-initial-vision boundary. Input/state schemas, detailed finding taxonomy, failure/repair mechanics, numeric limits and evaluation thresholds remain for later rounds. This approval does not authorize coding or live runs.

## Round 2: approved request, bounded context and state

### Runtime review request

Use the existing runtime-issued review handoff, not a new supervisor-selected analytical action or an extra model-controlled objective. The original question and obligations define what is being checked. A request identifies one immutable candidate:

| Field | Meaning |
| --- | --- |
| `review_id` | Runtime-issued UUID for this logical review/pass reservation. |
| `draft_id` | Runtime-issued UUID of the exact active candidate. |
| `draft_content_hash` | Integrity binding for its frozen structured/rendered content. |
| `draft_input_packet_hash` | Identity of the immutable context supplied to drafting, not a hash inferred from selected citations. |
| `rendering_policy_version` | Exact display policy used for the frozen rendered values. |
| `review_pass` | Runtime-owned run-wide logical pass number, 1 or 2. |

These names clarify the already approved draft/review linkage. Separately persist `review_input_packet_hash` for the complete resolved Reviewer input: it includes the review request, candidate, evidence/context and any linked revision material. Drafting and review inputs differ in purpose and must not accidentally share one ambiguous packet-hash field. Runtime-generated hashes bind content; models cannot replace them. Exact canonical serialization and record transactions remain lifecycle implementation work.

### Explicit resolved input

The runtime supplies:

- Original user question, confirmed clarifications/definitions and original requested obligations, with their supplied basis. A supervisor summary cannot silently replace or narrow the request. Distinguish confirmed context, user assumptions, computed evidence and untrusted source text.
- The complete candidate's structured blocks, resolved support/value/chart spans, frozen equivalent rendered transcript, completeness status and unmet-deliverable list. Also supply runtime-recorded actual unmet deliverables and supervisor partial authorization/reason, so the draft cannot declare its own fulfillment.
- The full bounded evidence/context packet that was supplied to this draft, including actual typed values, exact schemas, stable artifact row/column mappings, total row counts, visibility/shortening/coverage markers, producer/method provenance available in that packet, integrity identities and durable references. Evidence and candidate claims remain distinct inputs; a draft sentence is not an evidence value.
- Chart descriptions, bindings/units/scales/ordering/limitations, validation facts and supplied numerical backing, with the same no-initial-image boundary. All backing must be authorized and explicitly visible if used for numerical checking.
- For a revision, exact runtime-linked predecessor draft and recorded blocking findings, with their identities and source dependencies. Prior findings are context to assess, not binding verdict instructions; check the full current candidate, including previously unflagged claims. Reject stale/mismatched revision links before invocation.

Initially use the draft's complete bounded evidence packet rather than selecting only cited cells or silently adding new source facts for review. This preserves uncited contradictions and enables independent checking within the same evidence scope. Required contextual/provenance details absent from that packet are identified as gaps when consequential; the runtime does not infer them. Additional evidence is obtained through supervisor replanning and a newly built candidate/packet. This choice costs context tokens and can require narrower upstream evidence.

Opaque full-artifact references establish identity and inspectability, not access to hidden rows. The Reviewer has no lookup tool. Do not inject raw uploads, database paths, credentials, another agent's internal messages or unbounded chat history. Locally recorded invocation messages used for bounded output repair belong only to this review; restored context must be explicitly reconstructed and validated. Approved [integration rounds 4A–4B](agent-integration.md) preserve the full frozen drafting packet/candidate/feedback and require rendering/repair-aware preflight. Compaction cannot omit material evidence, obligations or lineage, alter the frozen candidate, or grant a new pass. Exact configuration, schemas and measured fit remain prerequisites.

Admit the entire required review input within finite limits, including candidate, full drafting packet and revision material. If it cannot fit, do not truncate the candidate or drop evidence and claim a complete review. Stop admission and return the problem through runtime/supervisor handling; exact error/result mechanics follow rounds 3–4. A different evidence scope or draft requires a new immutable candidate, not an in-place context edit. A valid empty evidence packet can support review of a missing-evidence explanation, never unsupported project-data claims.

### State and ownership

| Field | Owner and purpose |
| --- | --- |
| `input` | Immutable runtime-resolved request/context: `input.request`, `input.draft`, **`input.evidence`**, `input.charts`, obligations/partial authorization, confirmed context and linked revision material. Runtime records its packet hash and dependency union. |
| `messages` | Bounded review-local invocation/repair messages; no shared Answer conversation and no implicit extra evidence. |
| `assessment` | Working candidate verdict/findings, distinct from a validated terminal output. Detailed representation follows round 3. |
| `execution_status` | Runtime-owned invocation/attempt/phase, ownership, pass reservation, remaining budgets/reserves/deadline and stop reason. A pass number does not relax the substantive checking standard. |
| `output` | Empty until validated verdict or genuine operational failure is recorded. Detailed result variants follow round 3. |

Evidence is explicitly held in `input.evidence`, not just citation IDs or messages. Full artifact bytes remain in storage. No mutable computed-evidence collection, live model-session object or database handle is checkpoint state. Runtime validates identity, authorization, integrity, dependencies and source/deadline validity on admission/restoration; model judgments cannot change them. The Reviewer decides the substantive assessment from its supplied context, while runtime owns dispatch, validation, persistence and publication gates.

### Acceptance and approval scope

Exercise exact draft versus review packet hashes, missing cited cells, uncited contradictory supplied evidence, malformed/stale links, unauthorized partial claims, empty explanatory packets, unavailable hidden rows, and an oversized full-review packet. Verify that neither agent's private conversation becomes implicit context; feedback never overrides the current independent verdict.

The user approved this runtime request, distinct draft/review input binding, full bounded drafting-evidence context and five-field state. Shared Answer handoff hash names and review-context scope are clarified accordingly. Detailed verdict/error schemas, repair/recovery mechanics, numerical limits, context compaction, prompts/models and paid evaluation remain outside this approval.

## Round 3: approved verdicts, findings and correction routing

### Assessment versus operational outcome

Keep the inherited substantive verdicts `approved` and `rejected`. Approval means the full candidate passed this evidence-grounded review within the approved verification boundary. It does not prove upstream computations, satisfy missing deliverables or override runtime publication gates.

The model returns either a completed assessment or an explicit `cannot_complete` assessment with a bounded explanation. The latter means it did not finish judging the full candidate; it is not an approval, a rejection or permission to release partially checked claims. Essential missing support or a consequential ambiguous definition that the Reviewer can identify is instead a substantive evidence finding. Model self-report of unfinished checking, exhausted output, invalid response or a runtime/integrity failure cannot be laundered into a fabricated evidence rejection.

Runtime terminal outcomes:

| Variant | Contract |
| --- | --- |
| `reviewed` | Exact binding fields below, `verdict` and `findings`. Approved requires an empty findings list. Rejected requires at least one blocking finding. |
| `failed` | Exact binding to the attempted review and a genuine runtime-issued `error_ref`; no substantive verdict and no approval/rejection findings. An explicitly unfinished assessment is recorded as an incomplete-review failure, not an invented provider fault. |

A completed assessment echoes `review_id`, `draft_id`, `draft_content_hash`, `draft_input_packet_hash`, `review_input_packet_hash`, `rendering_policy_version` and `review_pass`. Runtime checks exact equality with its frozen request before accepting it; a malformed or stale echo cannot target a different draft. The hashes and pass remain runtime authority. Failure records obtain these bindings from runtime, never model-chosen identities. Exact repair allowance and failure recovery are round 4 work; neither failed review nor repair creates an extra logical pass.

### Minimal blocking finding

Each finding has:

| Field | Meaning |
| --- | --- |
| `finding_id` | Unique bounded local identifier within this review result, for precise feedback linkage. |
| `category` | `evidence` or `draft`, preserving the inherited routing distinction. |
| `block_ids` | Unique affected IDs in the exact candidate. Empty means a whole-draft issue, such as an omitted requested deliverable. |
| `explanation` | Specific blocking defect and why it affects correctness, support or fulfillment. No bare confidence rating or style preference. |
| `support_refs` | Bounded list of relevant existing cell/metadata/coverage/chart/context targets from this review packet, using the approved Answer target types and visibility rules. May be empty for an absence/whole-draft issue; the explanation must then identify the missing support or obligation concretely. |
| `required_change` | Needed evidence/definition/upstream check or draft correction, expressed without rewriting the answer or inventing a new computed value. |

References in feedback cannot point to hidden cells, another review packet or new evidence. Reuse existing supplied values rather than copying replacement numbers into authoritative free text. Citation/field validation confirms structure and eligibility; it cannot establish that an explanation is analytically correct. The findings themselves remain source-bearing review context under approved dependency/privacy rules.

List distinct observed blocking problems so one correction does not obscure another. A rejection does not claim that every possible defect has been found. If finite output bounds prevent a usable complete finding set, report incomplete review rather than emit a truncated result. No severity ranking, confidence score, advisory style list or alternative answer is required.

### Classification and runtime routing

Classify by what is needed to resolve the defect against the original request:

- `evidence`: required computation/support is missing or insufficient; supplied results conflict; a consequential definition/unit/grain/filter needs clarification or correction; visible upstream method/provenance is wrong. State the exact gap and needed check. Lack of routine independent recomputation alone is not evidence of a defect.
- `draft`: supplied valid evidence and confirmed context already suffice to correct a copied value, interpretation, reference, explanation, disclosure or fulfillment claim without new analysis or assumptions. Describe the correction; do not edit the candidate yourself.

Runtime derives the next step from the validated result and remaining pass, not a model-selected agent/route field. Any evidence finding, including a mixed result, returns to supervisor. Only draft findings return to Answer Specialist. After the second valid rejection, stop through the existing bounded runtime explanation; no third review. A failed/incomplete review withholds publication and follows bounded operational handling, not semantic correction of an unreviewed answer. Operational failure is never converted into an extra free pass.

### Completeness, partial answers and examples

Before approval, assess the whole candidate against the original obligations and supplied context, not only cited spans or previous findings. A second-pass candidate can introduce new defects. A truthful authorized partial can be approved only if its supported claims and explicit unmet list are correct; approval preserves its partial status. Missing required deliverables cannot silently become optional.

| Case | Finding/outcome |
| --- | --- |
| Supplied computed share is correct but the draft mislabels its meaning | Draft finding using the supplied value/context target and a precise display/interpretation correction. |
| Required growth is asserted without computed evidence | Evidence finding identifying the missing calculation and its scope. No new numerical answer in feedback. |
| Required chart is absent and draft falsely says complete | Draft disclosure/fulfillment finding if a truthful partial is already authorized; otherwise evidence/deliverable gap through supervisor. |
| A required conclusion relies on conflicting supplied results | Evidence finding with both relevant support targets; do not select one by confidence alone. |
| Answer is supported but Reviewer prefers different prose | Approve if all substantive checks pass; no style rejection. |
| Reviewer judges only half the candidate, or a provider response is unusable | No approval/rejection; incomplete/operational outcome and bounded runtime handling. |

The user approved these result variants, minimal actionable findings, grounding and evidence-first routing. The shared Answer feedback contract is updated accordingly. Round 4 still owns durable failure/retry/repair details and finite call/reserve settings; no implementation or live evaluation follows from this approval.

## Round 4: approved lifecycle, privacy, limits and reserve admission

Two independent medium-reasoning investigations covered lifecycle/privacy and finite limits/reserves. Reuse Answer's durable authority and inference accounting; no new database, sandbox or service.

### Reservation, dispatch and terminal records

Validate the complete input packet, exact active candidate, authorization, dependencies and available limits before admission. Atomically reserve `(run_id, review_pass) → review_id` with the frozen request, draft/review packet hashes, rendering identity, dependency union, configuration, owner generation and budget reservations. There is at most one reservation for each of the run's two passes. Changed content under a reserved identity is rejected; duplicate delivery restores the same record.

**Approved nonrefundable reservation:** once committed, a logical pass stays consumed even if a crash happens before dispatch. Recovery may finish that same reserved review within its remaining limits, but cannot refund it or allocate a replacement pass. Admission failure before the reservation consumes no pass. This favors auditable bounded execution over completion after an unrecoverable reservation failure.

Under each `review_id`, persist invocation keys for initial assessment and deliberate malformed-output repair; separately track every physical provider request, including transient retries and unknown-completion replacements. Reuse `prepared → dispatched → response_recorded → validated → handed_off` with a terminal failure path. Persist provider responses before checkpoint advancement. Adopt one canonical response per invocation; preserve malformed responses rather than overwrite them. Repair has a new invocation key under the same immutable review, not a new review/pass.

Record one terminal `reviewed` or `failed` outcome per review with idempotent feedback handoff, guarded by owner generation, expected attempt and exact active candidate. A valid verdict is immutable. Duplicate handoff cannot create another revision; neither a later provider response nor a second worker can turn recorded rejection/failure into approval. Invalidation revokes usability without rewriting historical assessment.

### Recovery and failure disposition

Read the ledger first: restore recorded responses, reservations, outcomes and handoffs before dispatching any replacement. Revalidate sources, integrity, ownership, active candidate and deadlines. An unresolved provider request with unknown completion may use a bounded accounted replacement of that same logical invocation; retain uncertain usage exposure and fence response adoption so only one canonical outcome is accepted. No Python process-retirement barrier applies to this tool-free inference role.

| Condition | Behavior |
| --- | --- |
| Identified transient transport fault or unknown completion | Accounted retry/replacement while unresolved and within all remaining limits; same immutable request and logical invocation. |
| Malformed response, invalid echo/target or unusable finding structure | At most the bounded repair allowance, preserving the same review packet/candidate and malformed response. No repair after a valid terminal verdict. |
| Valid explicit `cannot_complete` | Terminal `failed` with runtime-recorded incomplete-review reason. Do not turn this into another assessment opportunity through format repair. |
| Identifiable essential evidence/definition gap | Substantive evidence rejection under round 3, not an infrastructure failure. |
| Corrupt/unauthorized input, removed source, stale identity or changed candidate | Runtime rejects/invalidates; do not ask the model to repair authority or input bytes. A stale response cannot mutate the active flow. |
| Exhausted retries/repair/context/tokens/spend/time or unrecoverable runtime error | Terminal failure and bounded runtime notice; no unreviewed answer. |

**Approved terminal-failure rule:** a terminal failed review ends this analysis flow on either pass. Do not use pass 2 merely to repeat a failed first assessment. All allowed recovery/retry/repair must happen before terminal failure. A valid first rejection still follows the approved evidence/draft correction route and may reach pass 2. A second valid rejection uses the existing verification-issue explanation. Operational failure instead uses a runtime-owned operational notice, without rejected conclusions or raw source-bearing error text.

### Provisional development ceilings

These are finite intersecting candidates, subordinate to enclosing run allocations and unmeasured until evaluation. They are not independent guaranteed allowances; a call consuming most of a pass's time can leave no capacity for repair.

| Bound | Candidate |
| --- | --- |
| Per logical pass | One initial assessment and at most one malformed-output repair: at most 2 logical model invocations. At most 3 physical requests per pass, using at most 1 shared additional request for identified transient retry/unknown-completion replacement across the entire Reviewer run. Explicit incomplete assessment is terminal. |
| Across run | At most 2 logical passes, 4 logical model invocations and 5 physical Reviewer requests, including the shared retry/replacement. Restart, new attempt or worker cannot reset counters. |
| Per physical request | At most 32,768 input tokens including instructions, full review packet, predecessor/feedback and any repair context; 4,096 generated tokens including provider-accounted reasoning. Full model context/protocol overhead and token accounting must be enforceable for the selected model. |
| Findings/output | At most 8 findings, 64 support-reference occurrences overall, at most 16 support references per finding, and 16 block IDs per finding; local finding IDs at most 64 UTF-8 bytes; each explanation/required-change/incomplete-explanation string at most 1,024 UTF-8 bytes; complete response JSON at most 32 KiB. Token ceiling can bind sooner. No truncated findings masquerading as a completed review. |
| Time | At most 30 seconds elapsed per reserved pass, including queue/backoff, provider requests, repair, validation and recovery waiting; absolute pass deadline persisted with reservation. Individual request timeout at most 20 seconds and further bounded by remaining pass/run time. Both passes total at most 60 seconds; run hard deadline is always tighter. |

The required packet is admitted in full, including the entire bounded drafting evidence packet and candidate plus linked revision material. Admission also accounts for the anticipated bounded repair wrapper and saved malformed response within the same per-request input ceiling; fitting only the initial request is insufficient. The token ceiling does not authorize silent removal of obligations, material evidence, provenance or candidate blocks. If input or findings cannot fit, use the defined admission/incomplete failure path. Broader memory/context construction remains its owning design dependency.

### Computable reservation and accounting

Retain Answer's provisional **60 seconds for both reviews plus 5 seconds for finalization** before initial drafting. At dispatch of a review, reserve its remaining 30-second ceiling and preserve the next review's ceiling if a pass remains, together with finalization. Before a revision, preserve the remaining review/finalization capacity. Queue/recovery delay spends the persisted pass deadline rather than extending it. Work cannot start unless both role limits and the enclosing run deadline/allocation permit it. These time ceilings need measurement and may reduce completion; they do not promise that all allowed calls get a full timeout.

Reserve 2 physical requests for each unused logical pass plus the one shared extra request if still eligible. Before initial drafting this is 5 × 32,768 = **163,840 input tokens** and 5 × 4,096 = **20,480 generated tokens**, plus separately metered charges. Before revision with one review left, reserve **98,304 input / 12,288 generated tokens** if the shared extra remains, otherwise **65,536 input / 8,192 generated tokens**. Retain **35 seconds** for that remaining review and finalization, in addition to the revision time admitted under the remaining drafting/run limits. These are worst-case exposure reservations, not expected spend or fresh run budgets. Count actual requests and reconcile usage; retain uncertain reservations rather than treating unknown completion as free. Restarts preserve consumption and unresolved exposure. Release unused reservations only when their work is durably no longer eligible and potential charges remain covered.

Derive monetary reservations from the exact configured model/provider rates, routing/fallback policy and separately billed charges. Missing rates, enforceable token semantics or finite action/run/suite spending caps block runnable configuration. Do not assume cache savings. The run must also fund drafting/revision and other roles; reviewers do not borrow their reserves silently. With Answer's existing five physical drafting requests, the combined candidate maximum is 10 physical requests, 245,760 input tokens and 40,960 generated tokens, priced separately by role. Drafting/review/finalization ceilings total 60 + 60 + 5 = 125 seconds before other phases, without extending the run deadline. No exact model, spend amount or paid run is selected here.

### Privacy, dependencies and publication

Review dependencies are runtime-derived from all supplied source-bearing input, including draft/evidence, predecessor/feedback and repair context. Final answers retain these in union with draft dependencies under the approved conservative rule. Reference subsets cannot narrow that union. No newly retrieved evidence is introduced through repair or recovery.

Reuse the Answer hosted-trace allowlist: opaque correlation/configuration IDs, role/phase, counters, enumerated error/stop/disposition categories, timings, bounded sizes and token/cache/cost accounting only. Exclude packets, rendered drafts, findings, incomplete-review explanations, labels, values, paths/URLs, credentials, provider bodies and raw exceptions. Detailed authorized records remain in governed local storage with source dependencies and deletion rules. After invalidation, use generic runtime notices rather than copying stale source-bearing findings.

Reviewer approval itself never publishes. Reuse the shared transaction checking exact active approved envelope, current ownership, authorized complete/partial status, valid sources and hard deadline; serialize it with source invalidation. Lost publication acknowledgments restore the same recorded answer. A committed approval cannot revive deleted dependencies or permit expired publication.

### Approval scope and unrun gates

Exercise reservation/dispatch crashes, response persistence versus lost checkpoint, unknown-completion replacement and late response, malformed repair versus explicit incomplete outcome, terminal first/second-pass failure, counter/deadline recovery, full-packet admission, source deletion/publication ordering and actual hosted trace serialization. Round 5 specifies evaluation fixtures and scoring; these checks have not run.

The user approved lifecycle/recovery, nonrefundable reservations, stop-on-terminal-failure behavior, bounded repair, privacy and candidate ceilings/reserve arithmetic. Shared Answer/supervisor/evaluation contracts are clarified accordingly, retaining the two-review maximum. Compatible model/configuration, memory policy, spending authorization and live correctness/recovery/privacy/deadline checks remain readiness gates; no code or paid/live tests are authorized.

## Round 5: approved evaluation and calibration

Two independent medium-reasoning investigations covered fixtures/runtime gates and scoring/calibration. Reuse [shared evaluation requirements](evaluation-observability.md) and the Answer fixtures, while distinguishing runtime invariants from semantic judgment quality. This round selects an evaluation contract, not a model, measured score or new runtime limit.

### Frozen fixtures and expected behavior

Each semantic fixture binds the immutable full review input, exact candidate/rendered transcript, original obligations, gold approval/rejection, gold blocking issues/categories/targets and expected route. Use matched valid and minimally defective candidates, plus mixed-defect cases; template ancestry belongs to one split. Gold judgment is limited to supplied context and the approved verification boundary, not unseen source truth.

| Family | Required pairs/cases |
| --- | --- |
| Numbers and display | A computed share displayed correctly versus mislabeling its meaning; supplied 100/120 compared correctly versus new unsupported growth in digits or words. Include decimal ties, NULL, temporal/unit interpretation and ordinary year/method-number controls. |
| Coverage and provenance | Computed complete ranking versus a maximum inferred from a truncated preview; source population versus result-row count; wrong upstream filter/grain visible in provenance. An opaque full-file reference never exposes unseen rows. |
| Conclusions and conflicting evidence | Supported comparison/association versus unsupported causal attribution, and uncited supplied evidence contradicting the candidate. Gold category states whether supplied evidence already permits correction or an essential evidence gap remains. |
| Definitions and scope | Correct period/timezone/filter/denominator/unit/grain versus misinterpretation with sufficient context (draft issue) or consequential missing/ambiguous context (evidence issue). |
| Partial and empty packets | Truthful authorized partial with missing chart versus falsely complete/unauthorized partial. An empty packet may support a truthful authorized missing-evidence explanation, not project-data conclusions. |
| Independence and revision | Source/draft instructions demanding approval, irrelevant confidence assertions, style-only variations, prior feedback demanding a verdict, and a pass-2 draft introducing a new defect. Private agent history cannot be implicit context; all current claims still need checking. |
| Operational boundaries | Script malformed outputs/invalid echoes versus valid explicit incomplete assessment; test repair exhaustion, oversize full input/output and terminal first-pass failure without a second assessment. These do not become semantic gold rejections. |

### Must-pass runtime gates

Use scripted model responses and fault injection to isolate enforcement: exact IDs/hashes/rendering/pass binding; complete packet admission including repair capacity; authorized visible support references; atomic nonrefundable pass reservation; crashes around reservation, dispatch, response persistence, checkpoint, terminal outcome and handoff; ledger-first recovery; one canonical response and terminal result; unknown-completion exposure/replacement and late-response fencing; no free pass after failure; preserved invocation/request/token/size/time/spend counters; persisted pass/run deadlines; full supplied dependency unions and deletion/publication orderings; actual hosted trace/error serialization with sentinel values, labels, paths, URLs, credentials and findings.

Every declared runtime assertion must pass. Report assertions passed/total and cases passed/total by family; any authority, identity, privacy, invalidation, publication or enforced-budget violation fails that configuration regardless of semantic score. Keep corrupt/unauthorized/oversized input fixtures in these gates, outside semantic verdict denominators. A model's incorrect substantive verdict remains a model-quality error; a structurally valid citation does not prove a finding correct.

### Semantic metrics without abstention gaming

For admitted semantic fixtures, count every scheduled attempt/repetition once, including failed/incomplete/timeout/no-verdict outcomes. Freeze whether each candidate should be approved or rejected before comparison. Never count failure as a correct rejection.

| Metric | Numerator / denominator |
| --- | --- |
| False approval | Approvals on gold-reject candidates / all admitted gold-reject attempts. |
| Correct rejection | Rejections on gold-reject candidates / the same gold-reject denominator. |
| False rejection | Rejections on gold-approve candidates / all admitted gold-approve attempts. |
| Correct approval | Approvals on gold-approve candidates / the same gold-approve denominator. |
| No-verdict and completion | Failed/incomplete/no-verdict attempts, and separately valid completed verdicts / all attempts, also broken down by gold class. |
| Incorrect-or-no-verdict | Wrong verdicts plus no-verdict attempts / all attempts in each gold class. Joint targets with completion prevent a system that always fails from looking accurate. |
| Finding precision | One-to-one matched grounded, actionable, correctly scoped/categorized findings / all emitted findings in valid rejected outcomes. Duplicate, unnecessary and style-only findings receive no match. |
| Blocking-issue recall | Matched gold blocking issues / all gold issues across admitted gold-reject attempts; approval or failure detects zero. Match requires materially correct support/gap, block scope, category and needed correction. |
| Routing | Correct runtime-derived routes / all gold routing opportunities; separately report accuracy among valid rejected outcomes and approval/failure non-routing. Any evidence finding routes to supervisor, draft-only to Answer, second rejection to stop. |

Report zero denominators as N/A, counts alongside rates, gold-class sizes, scenario-family slices, and diagnostic verdict-conditional error rates. Include complete versus authorized-partial, evidence versus draft, qualitative/causal/spelled-out claims and style-only controls. Preflight rejects an incompatible evaluation configuration rather than silently excluding inconvenient cases; report admission failures separately. Unexpected admission failures in a semantic suite block a complete comparison claim until resolved or explicitly reported under the frozen protocol.

Score first-pass decisions separately from full-flow runs using the actual correction/replan/revision and runtime routes. Full-flow outcomes distinguish correct complete publication, correct authorized-partial publication, correct second-rejection stop, terminal operational stop, incorrect publication and incorrect withholding. A correct first rejection is not a failed run; a correct second-rejection stop is not completion of the user's analysis. Measure elapsed/pass time, physical calls, repairs, retries, tokens and full cost. Include new second-pass defects and shared-model/shared-evidence correlated mistakes. Separate agents do not justify multiplying accuracy estimates as if their errors were independent.

### Calibration and comparison protocol

Tune prompts/models/limits on versioned development cases; freeze scenario-family/template-separated held-out cases and sealed labels for the declared final comparison. Freeze gold issues/obligations, rubric, renderer/policy and expected events. Compare configurations on the same cases/repetitions, blind semantic adjudication to model/configuration labels, document disagreements and resolve them under the rubric. Do not rely solely on the assessed model judging its own output; any automated semantic judge needs a declared validated rubric and independent adjudication. Structural checks use deterministic oracles.

Calibration here means choosing configuration and acceptance targets from development evidence; the Reviewer has no confidence-probability field. Predeclare numerical false-approval, false-rejection, completion, incorrect-or-no-verdict, finding/routing and full-flow acceptance targets before each applicable run. Development revisions are versioned and disclosed; final targets and comparison plan freeze before held-out evaluation. Missing targets/repetitions/judge settings block runnable acceptance evaluation. Do not choose targets after seeing held-out scores; subsequent tuning treats exposed held-out material as development and requires fresh held-out cases. No unmeasured numerical quality target or winning configuration is selected now.

### Reproducibility, cost and approval scope

Before runs, record commit/dirty-patch identity; fixture/gold/split/rubric hashes; exact built runtime/renderer/dependency and prompt/schema/configuration identities; requested model/provider/routing/fallback/inference/reasoning settings and exposed actual model/provider metadata; repetitions/seeds/concurrency; limits/reserves and token-accounting semantics. Missing required identities or enforceable accounting block the configuration. Govern detailed evidence/output/judgment records locally; hosted traces retain round 4's allowlist only.

Forecast every role × case × repetition, retries, uncertainty, cache/cold assumptions, separately billed judges and infrastructure. Reviewer candidate exposure remains five physical requests/run, 163,840 input/20,480 generated tokens; price drafting, supervisor and other roles separately. Use dated verified rates/conservative enabled-provider bounds and finite numeric action/run/suite monetary caps with applicable authorization before paid execution. Reconcile actual usage and billed spend; unknown completion is not free. Round 4's time/output ceilings stay unmeasured candidates whose completion impact must be reported.

The user approved fixtures, must-pass runtime gates, failure-inclusive semantic denominators, actionable finding/routing scores, blind frozen comparisons and reproducibility/spending prerequisites. The shared evaluation contract is updated. This approval does not authorize paid runs, code or a measured readiness claim. Round 6 remains the integrated audit and closure; memory/context policy, exact configuration/targets/spend caps and live checks remain explicit gates.

## Round 6: approved integrated audit and closure

This is a document consistency audit against the approved Answer, supervisor and shared evaluation contracts. It is not execution evidence. The parent performs this single integrated check; no additional second-opinion agent is needed.

### Approved binding and timing clarifications

1. **Frozen review versus invocation payload:** `review_input_packet_hash` binds the immutable base review packet: request, candidate, evidence/context, obligations, authorization and linked revision material. It excludes its own hash field. Each model invocation additionally has a request digest binding that base hash, prompt/configuration and exact invocation-local messages, including any malformed response/repair diagnostics. A repair changes that invocation digest, not the review packet, candidate, pass or allowed evidence. Save both identities. No new source facts or another agent's private history enter through repair. The shared runtime must freeze compatible canonical typed serialization/hashing before dependent code; approval here does not choose an unbuilt codec.
2. **Capacity versus pass reservation:** before drafting, reserve future review token/cost/time capacity without allocating a logical pass or starting its clock. Only successful admission and atomic reservation of a particular `review_id` consume its nonrefundable pass and start its persisted 30-second elapsed deadline. A second pass starts only when its revised candidate is admitted/reserved. Revision/between-pass time still consumes the enclosing run deadline and relevant role budgets.
3. **Pending work versus restored verdict:** the pass deadline bounds unresolved assessment/repair/validation work. A terminal verdict committed while valid does not become a new model request or lose its recorded identity merely because recovery later reads it. Restore the recorded outcome/handoff idempotently; do not restart the timer. Current source, ownership, exact active-candidate and run hard-deadline checks still gate routing/publication. A response that was not validly terminalized before expiry cannot become a late approval.

### Integrated walkthroughs

| Trigger | Audited contract path |
| --- | --- |
| Complete supported first candidate | Independent Reviewer sees full required packet; pass 1 is reserved; completed approval is recorded once; exact authorized active envelope may publish after final runtime checks. |
| Truthful authorized partial | Same review and publication gates; unmet deliverables and partial status survive approval. No chart or calculation becomes delivered through wording alone. |
| First rejection, evidence or mixed findings | Runtime routes to supervisor; new computed evidence/definitions require a newly built candidate/packet, retaining inherited dependencies. Admit pass 2 only within remaining role/run limits. |
| First rejection, draft-only findings | Answer independently revises from supplied evidence and exact linked feedback; new draft ID/packet; Reviewer checks the full new candidate, not just old findings. |
| Second valid rejection | No further analysis draft or review; use bounded verification-issue explanation without rejected analysis. |
| Malformed response versus explicit incomplete assessment | At most one format repair for that pass, within shared request/time limits; valid explicit incomplete assessment is terminal failure, not a repair opportunity. |
| Terminal operational failure on either pass | Stop the flow with an operational notice; no unreviewed answer and no use of pass 2 to repeat terminal failed pass 1. |
| Crash or uncertain provider completion | Ledger first; recover the same reservation/response/outcome or use the one accounted shared replacement allowance while unresolved. Fence late/duplicate responses and preserve uncertain exposure. |
| Packet too large or essential visible support missing | Oversized required input fails admission without silent reduction; a specific missing essential support in admitted context is an evidence finding. Neither is an approval. |
| Source removal, changed candidate or deadline after approval | Approval never overrides invalidation/publication guards; revoke visibility or withhold publication. Recorded bytes/verdict do not establish current access. |

The component contract keeps model judgment separate from runtime authority and preserves the run-wide two-pass maximum. Conservative review dependencies include all supplied source-bearing context; citation subsets cannot narrow them. The candidate review reserve is computable under round 4, but its adequacy remains unmeasured. Round 5 separately measures false judgments, failure/completion and full-flow results; a correct operational stop is not a completed analysis.

### Remaining owners and gates

| Before | Required owner/deliverable |
| --- | --- |
| Dependent implementation | Memory/context design: bounded explicit packet/revision construction and compaction preserving material evidence, obligations and lineage. Shared runtime contract: canonical typed packet/digest encoding and concrete durable identity/error/publication records under approved semantics. Role prompts and implementation plan follow component review; code is not authorized by this audit. |
| Runnable evaluation | Exact compatible models/provider settings/accounting; built runtime/renderer/dependency identities; versioned fixtures/gold/splits/rubric/judge settings; repetitions/concurrency; predeclared quality/completion targets; dated rates and finite numeric action/run/suite spend caps plus applicable authorization. |
| Enablement | Actual identity/admission/formatting/authorization checks, recovery/fencing, nonrefundable counters, aggregate limits/reserves/deadlines, full lineage/source deletion/publication and hosted trace/error serialization must pass. Measure semantic quality, completion, latency and total cost under the frozen evaluation protocol. |

No code, live model/provider call, fault-injection test or paid evaluation has run for this review. No runtime milestone has passed. Final cleanup found no temporary plan Markdown files; approved specifications and the decision log are retained. Shared links/statuses are updated.

The user approved the three clarifications and closed Reviewer component design review with these explicit gates. Shared-contract/status updates and final cleanup are complete. Approval does not declare implementation-ready or authorize coding, paid tests or relaxed budgets. Next recommended design dependency is the shared memory/context policy for supervisor, Answer and Reviewer.
