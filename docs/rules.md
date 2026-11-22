# Querivue working rules

Working agreement established 14 November 2026. This document captures the collaboration preferences agreed during planning and can be refined as we work.

## Scope and development process

- Treat Querivue as a personal AI engineering portfolio project. Keep decisions aligned with the agreed PRD and local-first development phases.
- Follow spec-driven development. Design the project and its components before substantive implementation. Derive acceptance criteria and verification from the approved specifications. TDD is optional.
- Carry forward existing approvals and constraints. Raise a consequential change when new evidence affects an agreed decision, and update the specification before implementing that change.
- Review consequential choices before dependent implementation. Reversible design-document edits are preauthorized under the review workflow below; coding scope and external/paid actions still require their applicable authorization.

## Design discussions

- Plan at the component or integration-phase level, grouping related contracts into one coherent review packet. Split only when a consequential choice genuinely blocks dependent work or the user requests a narrower discussion.
- For every phase after the current agent integration phase, create a separate phase planning Markdown document as the first phase artifact, before any other work on that phase. Use it to guide subsequent research, design, architecture edits and review; keep it current through the phase. The current agent integration phase continues from its existing approved plan/agenda; do not create a replacement phase plan retroactively.
- Explain the recommendation, relevant alternatives, and practical tradeoffs. Use concrete examples and flowcharts when they help.
- Reuse decisions already recorded. Reopen them when new evidence or a user instruction changes their basis.
- Research facts in the project and official documentation. Ask the user about preferences and consequential tradeoffs.
- Keep agreed decisions, proposals, open questions, and unverified claims visibly distinct.
- Design prompts after the component designs are complete. Refine models, prompts, and numerical limits through evaluation.
- Stop planning a component when consequential interfaces, ownership, failure paths and risks are settled and remaining work is assigned to implementation or evaluation. Move to authorized implementation rather than adding speculative rounds; tune candidate numerical limits through measured evaluation. This stopping rule does not itself authorize coding or paid runs.

## Review and document-edit authorization

- Use ordinary chat for design review and user replies; do not use approval pop-ups.
- The user preauthorizes reversible documentation edits. For new work, keep exploratory plans/proposals in a separate temporary task-specific planning Markdown document. Keep architecture guides organized by stable topics and settled contracts; transfer the final decisions there as the work settles.
- After agent integration, base architecture edits on the phase planning document. Reversible architecture edits may be prepared before approval under the standing authorization, with proposed changes clearly distinguished from approved contracts. Preserve existing approvals and unrelated edits; do not treat prepared edits as approval for dependent implementation. Phase planning documents are temporary: retain them during the phase, then transfer lasting decisions, rationale and open gates into the architecture guides/decision log, delete the planning documents when the phase is complete, and repair their links.
- Standing document-edit authorization is not a claim that the user explicitly reviewed every new choice, nor authorization for coding, paid runs or external effects. Identify unresolved consequential choices and await any answer necessary for dependent implementation.
- Chat approval needs a short acknowledgment, not a second rewritten specification or a separate file-changing approval task. Update status/decision tracking with the next substantive edit or phase handoff.
- Revise or undo only our own identified proposal changes, preserving unrelated user/agent edits. Use a targeted diff/patch; avoid whole-file or workspace rollback.
- Carry forward existing approvals and scope; do not ask again for already authorized work.

## Coding rules

Read [coding-rules.md](coding-rules.md) before every coding task and after a context handoff. It is authoritative for coding delegation, model settings, skills, implementation and verification. Planning, research and documentation stay with this chat; subagents are exclusive to coding.

## Design completeness

Before implementing a component, resolve its consequential choices and document:

- Responsibilities, boundaries, inputs, outputs, state, and ownership.
- Allowed operations, validation, authorization, and source dependencies.
- Normal execution, stopping conditions, errors, retries, concurrency, and recovery.
- Persistence, artifact lifecycle, deletion, and publication behavior.
- Observability, evaluation criteria, acceptance scenarios, and verification gaps.

Assign deferred decisions to an owning component or later design round. Review the complete flow again before calling the component implementation-ready.

## Documents and decision tracking

- PRD.md defines scope and expected behavior.
- architecture/overall.md records the overall architecture; focused files in architecture/ define component contracts and cross-component decisions.
- Component specifications define concrete contracts and acceptance scenarios.
- memory.md tracks agreed decisions, changes, outstanding work, and where to resume.
- rules.md defines how we collaborate; coding-rules.md defines coding workflow.

- At completion of the current agent integration phase, reorganize `architecture/agent-integration.md` into a topic-based architectural document rather than a chronological round-by-round planning/review record. Preserve approved contracts, ownership, interfaces, failure/recovery behavior, constraints, rationale and unresolved verification gates; retain review history in memory.md, remove superseded planning/status wording and repair affected links/anchors. Do this at phase completion, not during the remaining review rounds.

Maintain one authoritative architectural contract per topic; summaries link to it rather than repeat its full contents. Planning documents are temporary working material, separate from architecture guides. At job completion, ensure decisions, constraints, open gates and needed rationale are captured in the durable guides/decision log, then delete the task's planning document and repair its links. Preserve existing information and unrelated files. Keep a compact current resume section in memory.md and update it at substantive handoffs; consult historical entries only for specific decisions. Actual user review status and unverified claims remain explicit.

## Discovery and local maintenance

- Use the code-review-graph skill to narrow code relationships and impact, then inspect affected source/tests. Use QMD for Markdown documentation as specified below; use targeted `rg` for source literals and other unindexed text. Avoid unrelated scans; source remains authoritative when graph relationships are missing or unresolved.
- Use the [QMD skill](https://skills.sh/tobi/qmd/qmd) as the default for local Markdown discovery and reading. Search the relevant configured documentation collection with keyword search (`qmd search`, normally at most 5 hits), then retrieve the relevant source range with `qmd get "<docid-or-path>:<start>:<count>"`, normally 40–80 lines. Search snippets are leads, not sufficient evidence for a decision. Expand around headings, qualifications and cross-references only as needed; reuse unchanged material already read. Prefer keyword search; semantic models, embeddings and bulk/full-document retrieval are optional, not automatic.
- QMD is configured with collection `querivue-docs` for this repository's `docs/**/*.md`. Scope documentation searches to it. Local maintenance of that existing collection is authorized after doc edits; before global `qmd update`, verify the configured scope and absence of update hooks. Additional collections, hook execution and model downloads require separate authorization.
- If QMD or the relevant current index is unavailable, report that briefly and use targeted `rg` plus bounded file reads. Installing QMD/the skill, creating an index or downloading models requires separate authorization; this rule update alone does not claim those steps occurred.
- Read only relevant headings/sections and changed source, normally 40–80 lines at a time; reuse unchanged content already read. Keep discovery/results compact (normally at most 2,000 output tokens/call), summarize metadata rather than dump tool payloads, and narrow a query when output truncates. Expand deliberately when correctness or mandatory skill instructions require it.
- Batch handoff/documentation and index maintenance once after each completed coding batch or review round, before reporting completion; a batch may include multiple related contract slices. Refresh QMD when documentation changed and code-review-graph when source changed, then verify each refreshed index once. Refresh earlier only when a subsequent lookup needs changed content. Skip unchanged indexes and routine refreshes for read-only work. This supersedes the earlier per-task/both-index refresh cadence. Standing authorization covers existing local Querivue indexes only, not embeddings, model downloads or unrelated indexes. Report failures explicitly. Complete any due phase-end Floorplan refresh before final graph maintenance.
- Update the [Floorplan](plugin://floorplan@floorplan) map only after completion of an agreed phase, unless the user explicitly requests an earlier refresh. Accumulate map-relevant changes during the phase instead of refreshing after individual tasks or edits. At phase completion, refresh the existing map and update affected descriptions, connections, guided flows, open questions and recent-work notes; check the build output and show the refreshed map, disclosing any refresh/validation failure. Use blueprint mode for planned pieces and accurately label what is implemented; candidate paths and unresolved choices do not become approved merely by appearing on the map. Keep approved contracts in tracked documents and the generated local map out of git. When a phase-end Floorplan refresh is due, do it before the final code-review-graph update; the separate end-of-task code-review-graph rule remains unchanged. This is standing authorization for local map maintenance, not production coding, paid Ask/Build calls or resolution of unapproved design choices.

## Evaluation and cost

- Evaluate answer correctness and agent behavior separately. Treat safety and recovery invariants as pass/fail gates.
- Use development cases for tuning and held-out cases for final comparisons.
- Choose exact model configurations and numerical limits from reproducible evaluation results.
- Forecast the full evaluation cost before running the suite, including all model roles and separately billed sandbox or judge usage.
- Compare the forecast with actual billed spend. State cache assumptions, repetitions, retries, and the scope of each cost figure.
- Preserve the agreed boundary for uploaded content and credentials in model requests, traces, and shared artifacts.

## Communication

- Explain architectural decisions in plain language, supported by concrete examples.
- Keep progress updates concise and focused on findings and remaining work.
- Avoid repeating the same proposal in documents, commentary, review wording and final recap. Present decisions/tradeoffs once; use brief change summaries and approval acknowledgments. Report verification results once per completed task and preserve required graph/Floorplan maintenance cadence.
- Subsequent reviews explain only changed decisions, consequences and unresolved blockers, linking to the authoritative contract. Restate unchanged contracts only when the user asks or a consequential inconsistency requires it.
- Prefer a fresh chat at a completed phase or substantial context handoff, using the compact resume section and targeted specification pointers. A new chat for every small approval can cost more reload/handoff work; do not fork or create chats without the user's request.
- State uncertainty and material assumptions explicitly.
- End work summaries with relevant verification gaps or risks.
