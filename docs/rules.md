# Querivue working rules

Working agreement established 14 November 2026. This document captures the collaboration preferences agreed during planning and can be refined as we work.

## Scope and development process

- Treat Querivue as a personal AI engineering portfolio project. Keep decisions aligned with the agreed PRD and local-first development phases.
- Follow spec-driven development. Design the project and its components before substantive implementation. Derive acceptance criteria and verification from the approved specifications. TDD is optional.
- Carry forward existing approvals and constraints. Raise a consequential change when new evidence affects an agreed decision, and update the specification before implementing that change.
- Present design and implementation choices for user review before work that depends on them. During coding, bring gaps or changes in the approved plan to the user for a decision.

## Design discussions

- Discuss one major topic or contract at a time, with enough detail to understand its complete behavior.
- Group closely related choices into one reviewable proposal. Group independent questions in a numbered round when the user requests a broader review.
- Explain the recommendation, relevant alternatives, and practical tradeoffs. Use concrete examples and flowcharts when they help.
- Reuse decisions already recorded. Reopen them when new evidence or a user instruction changes their basis.
- Research facts in the project and official documentation. Ask the user about preferences and consequential tradeoffs.
- Keep agreed decisions, proposals, open questions, and unverified claims visibly distinct.
- Design prompts after the component designs are complete. Refine models, prompts, and numerical limits through evaluation.

## Approvals

- Ask for user approval or review of every new design decision. Use approval pop-ups with yes/no choices and room for written suggestions.
- Present the concrete behavior or contract being approved. Keep dependent decisions for a later round.
- Interpret approval within the scope of the displayed proposal. A request to revise leaves that proposal open.
- Wait for an actual answer before advancing work that depends on that decision.
- Follow the user's latest instruction about review pace, including one-topic-at-a-time discussion.
- Proceed with work already authorized without repeating approval requests.

## Subagents

- Explicitly set `reasoning_effort="medium"` for every subagent, including research, planning, review and implementation. Do not inherit the supervisor's reasoning level.
- For planning/research, use subagents only for independent tasks where parallel execution is expected to save time. Otherwise work in the parent, including single-topic reviews. Do not delegate merely to obtain another opinion. This restriction does not apply to writing code.
- For writing code, always delegate implementation to smaller-model subagents, even for one task. The parent supervises, integrates and reviews. Follow the coding model settings below.
- Give them bounded responsibilities, current decisions, constraints, and a clear deliverable.
- Have the parent agent reconcile their findings, check sources, and present a coherent recommendation.
- Record researched recommendations as proposals until approved. Treat capability claims as unverified until the required checks support them.

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

Update the relevant documents when decisions are accepted. When a decision changes, update affected descriptions and record what it supersedes. Keep proposed behavior clearly marked.

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

- Use the code-review-graph skill to narrow repository reading to relevant files and symbols. For code relationships and impact, start with the smallest useful graph query, then inspect the actual affected source and relevant tests; expand only when evidence requires it. For prose, literal text or files the graph does not index, use targeted `rg` searches and focused reads. Avoid broad repository scans or reading unrelated files. Graph results guide scope; source remains authoritative, and missing/unresolved relationships require targeted source checks.
- Build the smallest complete implementation that satisfies the approved specification.
- Reuse existing code and dependencies where appropriate.
- Cover the affected callers, configuration, interfaces, and failure paths.
- Run checks appropriate to the change. Use meaningful tests and evaluations derived from the specification.
- Report what changed, what was verified, and what remains unresolved. Distinguish documented support from measured behavior.
- At the end of every task that changes repository files, after the final edits and checks, update the local code-review graph and verify its status once before reporting completion. This is standing authorization for local incremental graph maintenance; use the code-review-graph skill and prefer its MCP tools. Skip updates when no repository files changed. If updating fails or is unavailable, report the gap rather than claim the graph is current. This does not authorize external embeddings or unrelated graph maintenance.
- Keep the [Floorplan](plugin://floorplan@floorplan) map current throughout development. After each task changes mapped code, structure, routes or approved architecture/agent flow, refresh the existing map and update affected descriptions, connections, guided flows, open questions and recent-work notes. Check the build output and show the refreshed map before reporting completion; disclose any refresh/validation failure. Use blueprint mode for planned pieces and accurately label what is implemented; candidate paths and unresolved choices do not become approved merely by appearing on the map. Keep approved contracts in tracked documents and the generated local map out of git. Refresh Floorplan before the final code-review-graph update; neither tool replaces the other. This is standing authorization for local map maintenance, not production coding, paid Ask/Build calls or resolution of unapproved design choices.

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
- State uncertainty and material assumptions explicitly.
- End work summaries with relevant verification gaps or risks.
