# Coding rules

Read before every coding task and after a context handoff. Keep this file limited to coding rules; collaboration, documentation discovery and index/map maintenance remain in [rules.md](rules.md).

## Scope and supervision

- Implement the approved specification and architecture. Carry forward approvals; bring new design or implementation decisions to the user before dependent code. TDD is optional; derive acceptance criteria and verification from the specification.
- This chat is the coding supervisor (21 November 2026 correction). It reviews, integrates and verifies; it delegates all code writing, including single tasks. Do not launch a separate supervisor. These settings apply to development agents, not Querivue runtime models.
- Always use `gpt-5.6-sol`, `reasoning_effort="medium"`, `fork_turns="none"` for coding workers. If unavailable at dispatch, report the limitation; do not silently substitute another model or reasoning level.
- Give each worker bounded, nonoverlapping file ownership, a deliverable, relevant plan/specification excerpts, interfaces, constraints and acceptance criteria. Workers inspect assigned source/tests, not project docs. The supervisor reads docs through QMD and supplies missing targeted context; avoid full-chat/document dumps.
- Batch related contracts and similar edits into one bounded worker assignment with shared context and one review; split only for dependencies, distinct decisions or context limits. Pass lengthy scoped briefs/reports as files. Workers return changed paths, check totals and blockers, not repeated artifacts.
- Compact supervisor and worker context at 60% usage, first saving a concise handoff: task, approvals, affected files, completed work, verification, open issues and next steps. If usage/manual compaction is unavailable, disclose that limitation and use a saved handoff with fresh agent contexts where supported; do not claim the threshold was enforced.
- Prefer clean planning/debugging boundaries for earlier compaction; at 60%, checkpoint unfinished implementation before compacting. Preserve decisions and next actions, not exploratory transcripts. Resume from the handoff without repeating completed work.

## Skills and implementation

- Read applicable `SKILL.md` instructions before use. For coding, use Superpowers for design/implementation/debugging/verification, mattpocock-skills for domain/interface design/testing/review, andrej-karpathy-skills for focused changes and verifiable outcomes, and Ponytail for the smallest complete implementation.
- For frontend work, use frontend-design, Impeccable, Taste Skill, applicable gsap-skills motion, and shadcn components/tools. Reuse existing components and dependencies; animate when it serves the interface.
- Select relevant skills within each bundle. Preserve approved scope, contract reviews and delegation; avoid unrelated workflows, packages or approval requests. Report unavailable capabilities and use the best available fallback without claiming they ran.
- Use code-review-graph to select relevant code files, relationships and impact, then read only affected source/test sections. Use QMD keyword search in `querivue-docs`, then retrieve only relevant Markdown sections (normally 40–80 lines). Reuse unchanged context. Use targeted `rg` for literals/unindexed text or unavailable indexes; source remains authoritative. Follow [rules.md](rules.md#discovery-and-local-maintenance) for maintenance and fallback details.
- Build the smallest complete implementation satisfying the approved specification. Reuse code/dependencies and cover affected callers, configuration, interfaces and failure paths.
- State consequential assumptions and define observable success before coding. Make surgical edits that trace to the request; match existing conventions, avoid speculative abstractions and unrelated cleanup, and remove only newly orphaned code.
- Keep instructions in one authoritative place with short pointers stating when to read them. Load details on demand; prune duplication and stale guidance instead of copying docs, readily discoverable configuration or full tool output into context.

## Token efficiency

- Reuse unchanged rules, specs and tool schemas already read. Discover paths/headings first; retrieve exact relevant sections. Narrow truncated searches before expanding output. Print only needed tool-result fields, normally within 1,000 tokens; retain errors and verification evidence.
- Await worker completion notifications while doing independent work. When idle, use a bounded wait of up to 60 seconds; avoid repeated short polling and speculative file/status checks.
- Run focused checks during fixes and one applicable full check per completed batch. Repeat only after changes, failures or unresolved concerns. Keep reports concise; report measured token counts only when available.
- Use Headroom/headroom-skill for supported context compression and headroom-snip for supported visibility. Check host support once; do not claim hooks, compression or savings ran without evidence. Current bundled hooks target Claude Code/Copilot and snip targets Claude Code; this Codex chat has no exposed Headroom tool. Apply focused reads/output limits here. For an authorized Headroom integration, preserve instructions, recent code and errors, retain recoverable originals, use offline mode in sandboxes/CI, and report actual before/after token counts. Do not add Querivue runtime dependencies merely to optimize this coding chat.

## Review and completion

- The supervisor reviews worker code and checks integration, verification and conformance to the approved plan/architecture.
- Run checks appropriate to the change, with meaningful tests/evaluations derived from the specification. Distinguish documented support from measured behavior.
- Update handoff/docs and maintain indexes once per completed batch under [local maintenance rules](rules.md#discovery-and-local-maintenance), not after every small slice. Floorplan remains phase-end only unless requested earlier.
- Report what changed, what was verified, and unresolved gaps or risks.
