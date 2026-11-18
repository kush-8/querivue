# Querivue working rules

Working agreement established 14 November 2026. This document captures the collaboration preferences agreed during planning and can be refined as we work.

## Scope and development process

- Treat Querivue as a personal AI engineering portfolio project. Keep decisions aligned with the agreed PRD and local-first development phases.
- Follow spec-driven development. Design the project and its components before substantive implementation. Derive acceptance criteria and verification from the approved specifications. TDD is optional.
- Carry forward existing approvals and constraints. Raise a consequential change when new evidence affects an agreed decision, and update the specification before implementing that change.
- Review consequential choices before dependent implementation. Reversible design-document edits are preauthorized under the review workflow below; coding scope and external/paid actions still require their applicable authorization.

## Design discussions

- Plan at the component or integration-phase level, grouping related contracts into one coherent review packet. Split only when a consequential choice genuinely blocks dependent work or the user requests a narrower discussion.
- Explain the recommendation, relevant alternatives, and practical tradeoffs. Use concrete examples and flowcharts when they help.
- Reuse decisions already recorded. Reopen them when new evidence or a user instruction changes their basis.
- Research facts in the project and official documentation. Ask the user about preferences and consequential tradeoffs.
- Keep agreed decisions, proposals, open questions, and unverified claims visibly distinct.
- Design prompts after the component designs are complete. Refine models, prompts, and numerical limits through evaluation.
- Stop planning a component when consequential interfaces, ownership, failure paths and risks are settled and remaining work is assigned to implementation or evaluation. Move to authorized implementation rather than adding speculative rounds; tune candidate numerical limits through measured evaluation. This stopping rule does not itself authorize coding or paid runs.

## Review and document-edit authorization

- Use ordinary chat for design review and user replies; do not use approval pop-ups.
- The user preauthorizes reversible proposal edits directly in the relevant documents as the current working design. Write the design once, summarize consequential choices/tradeoffs in chat and incorporate objections or requested changes in place.
- Standing document-edit authorization is not a claim that the user explicitly reviewed every new choice, nor authorization for coding, paid runs or external effects. Identify unresolved consequential choices and await any answer necessary for dependent implementation.
- Chat approval needs a short acknowledgment, not a second rewritten specification or a separate file-changing approval task. Update status/decision tracking with the next substantive edit or phase handoff.
- Revise or undo only our own identified proposal changes, preserving unrelated user/agent edits. Use a targeted diff/patch; avoid whole-file or workspace rollback.
- Carry forward existing approvals and scope; do not ask again for already authorized work.

## Subagents

- Explicitly set `reasoning_effort="medium"` for every subagent, including research, planning, review and implementation. Do not inherit the supervisor's reasoning level.
- For planning/research, use subagents only for independent tasks where parallel execution is expected to save time. Otherwise work in the parent, including single-topic reviews. Do not delegate merely to obtain another opinion. This restriction does not apply to writing code.
- For writing code, always delegate implementation to smaller-model subagents, even for one task. The parent supervises, integrates and reviews. Follow the coding model settings below.
- Give them bounded responsibilities, current decisions, constraints, and a clear deliverable.
- Give planning agents fresh contexts, nonoverlapping questions/file ownership and minimal shared excerpts plus pointers. Default to at most two parallel planning agents. Parent owns shared context/integration; reports contain actionable findings only. Avoid repeating full specifications or assigning duplicate review without a concrete risk or disagreement.
- Have the parent agent reconcile their findings, check sources, and present a coherent recommendation.
- Record research in the authorized working design, distinguishing actual user decisions, unresolved choices and unverified capability claims.

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
- rules.md defines how we collaborate.

Maintain one authoritative contract per topic; summaries link to it rather than repeat its full contents. Edit that contract directly under the review authorization above. Keep a compact current resume section in memory.md and update it at substantive handoffs; consult historical entries only when resolving a specific decision. Actual user review status and unverified claims remain explicit.

## Coding agent workflow

These model settings govern the development agents working on this repository.

- Use gpt-6.1-sol with high reasoning as the coding supervisor.
- Always delegate code-writing tasks to gpt-6-sol with explicit medium reasoning, or a smaller available model with medium reasoning for simpler tasks. Do not implement code directly in the supervisor, including single-task work.
- Give each coding subagent only the context needed for its bounded task: applicable plan/specification excerpts, relevant architecture and interfaces, affected files, constraints, and acceptance criteria. Start with a fresh context rather than inheriting the full conversation; supply additional targeted context only when needed.
- During coding, compact context when usage reaches 60% of the available context window, for the supervisor and each subagent. Before compaction, save a concise handoff covering the current task, approved decisions, affected files, completed work, verification results, unresolved issues, and next steps. If the host does not expose context usage or manual compaction, state that limitation and use a fresh agent context with the saved handoff where supported; do not claim the threshold was enforced.
- The supervisor reviews the submitted code, checks integration and verification results, and ensures the implementation follows the approved plan and architecture.
- Bring any new design or implementation decision to the user before writing dependent code. Carry forward decisions already approved.
- Select the requested model and reasoning settings when creating coding agents. If the host cannot switch the current supervisor model, disclose that limitation and obtain the user's direction before beginning coding under different settings.

## Coding and frontend skills

- For coding, use [Superpowers](plugin://superpowers@openai-curated-remote) for the applicable design, implementation, debugging and verification workflow; [mattpocock-skills](plugin://mattpocock-skills@mattpocock) for applicable domain/interface design, testing and review; [andrej-karpathy-skills](plugin://andrej-karpathy-skills@karpathy-skills) for focused changes, explicit assumptions and verifiable outcomes; and [Ponytail](plugin://ponytail@ponytail) for the smallest complete implementation without unnecessary code or dependencies.
- For frontend design, use [frontend-design](plugin://frontend-design@claude-plugins-official) for visual direction and implementation, [Impeccable](plugin://impeccable@openai-curated-remote) for design quality and refinement, [Taste Skill](plugin://taste-skill@taste-skill) for frontend design guidance, [gsap-skills](plugin://gsap-skills@gsap-skills) for applicable motion, and shadcn components/tools. Reuse the project's existing components and dependencies; use animation where it serves the interface rather than adding it solely to invoke a tool.
- Select the relevant skills within these plugins and read their `SKILL.md` instructions before applying them. Carry forward the user's approved scope, per-contract reviews, smaller-model coding delegation and explicit medium subagent reasoning. Do not run every unrelated skill in a plugin or add unnecessary workflows, packages or approval requests. Report unavailable capabilities and use the best available fallback without claiming they ran.

## Implementation and verification

- Use the code-review-graph skill to narrow code relationships and impact, then inspect affected source/tests. Use QMD for Markdown documentation as specified below; use targeted `rg` for source literals and other unindexed text. Avoid unrelated scans; source remains authoritative when graph relationships are missing or unresolved.
- Use the [QMD skill](https://skills.sh/tobi/qmd/qmd) as the default for local Markdown discovery and reading. Search the relevant configured documentation collection with keyword search (`qmd search`, normally at most 5 hits), then retrieve the relevant source range with `qmd get "<docid-or-path>:<start>:<count>"`, normally 40–80 lines. Search snippets are leads, not sufficient evidence for a decision. Expand around headings, qualifications and cross-references only as needed; reuse unchanged material already read. Prefer keyword search; semantic models, embeddings and bulk/full-document retrieval are optional, not automatic.
- If QMD or the relevant current index is unavailable, report that briefly and use targeted `rg` plus bounded file reads. Installing QMD/the skill, creating an index or downloading models requires separate authorization; this rule update alone does not claim those steps occurred.
- Read only relevant headings/sections and changed source, normally 40–80 lines at a time; reuse unchanged content already read. Keep discovery/results compact (normally at most 2,000 output tokens/call), summarize metadata rather than dump tool payloads, and narrow a query when output truncates. Expand deliberately when correctness or mandatory skill instructions require it.
- Build the smallest complete implementation that satisfies the approved specification.
- Reuse existing code and dependencies where appropriate.
- Cover the affected callers, configuration, interfaces, and failure paths.
- Run checks appropriate to the change. Use meaningful tests and evaluations derived from the specification.
- Report what changed, what was verified, and what remains unresolved. Distinguish documented support from measured behavior.
- At the end of every task that changes repository files, after the final edits and checks, update the local code-review graph and verify its status once before reporting completion. This is standing authorization for local incremental graph maintenance; use the code-review-graph skill and prefer its MCP tools. Skip updates when no repository files changed. If updating fails or is unavailable, report the gap rather than claim the graph is current. This does not authorize external embeddings or unrelated graph maintenance.
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
