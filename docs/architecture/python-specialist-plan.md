# Python Specialist design-review plan

14 November 2026. **Review plan and bounded subagent research approved by the user.** Python-specific contracts and implementation choices below are questions to resolve, not approved decisions.

## Goal

Produce a decision-complete Python Specialist specification for the standalone agent. It must explain how a delegated calculation or chart request becomes inspectable evidence, how failures return to the supervisor, and how execution respects the run's data scope and limits.

The immediate deliverable is the design, followed by a separate implementation plan after approval. Follow the existing design-first process and discuss one major contract at a time.

## Existing decisions to carry forward

- The supervisor owns planning and delegation. Python returns results to it; fresh answers still pass through the Answer Specialist and Reviewer, with at most two review passes.
- Simple analyses go to SQL. Python handles analysis or visualization that needs it. Define the precise dispatch boundary in round 1.
- SQL supplies complete authorized Parquet artifacts, typed metadata, original-to-artifact column mappings, and direct and transitive source dependencies. A bounded preview is not the complete dataset.
- Execution uses the run sandbox, with a separate subprocess/interpreter and output directory per action. Saved artifacts carry data between actions; unsaved interpreter state cannot be assumed recoverable.
- Model calls run in the worker through OpenRouter. Sandbox credentials stay outside generated-code execution; outbound internet is disabled, analysis inputs are read-only, and outputs require trusted validation.
- Source scope is pinned at run submission. Source removal, deadlines, bounded retries, preservation of successful sibling outcomes, and evidence validity apply to Python too.
- A failed requested chart must permit supported findings to survive as a visibly partial result through the existing answer/review flow.

Sources: [PRD](../PRD.md), [Supervisor](supervisor.md), [Sandbox execution](sandbox-execution.md), and the approved [SQL Specialist contract](sql-specialist.md). SQL-specific runner and persistence mechanisms are reuse candidates; Python support must be reviewed and verified.

## Review sequence

| Round | Decisions to resolve | Reviewable deliverable |
| --- | --- | --- |
| 1. Responsibility and dispatch | Which calculations and visualizations belong here? Is Python allowed to read prepared Dataset tables directly, or only authorized evidence artifacts? What requires returning to SQL, replanning, or clarification? | Responsibility statement, allowed inputs/operations, and concrete dispatch examples. |
| 2. Request, context, and state | Define the Python action payload, resolved runtime inputs, confirmed analytical constraints, specialist state and ownership, evidence references, and output expectations. Define the bounded model context and leave broader compaction policy to memory design. | Request/state schemas and a supervisor-to-specialist mapping, with validation failures. |
| 3. Tools and execution boundary | Choose the minimum tool surface and code execution protocol. Settle interpreter state within an action, code correction behavior, authorized input loading, package/template policy, filesystem/process isolation, resource enforcement, and generated-code versus trusted-runtime responsibilities. | Tool request/response contracts, execution flow, and enforceable safety requirements with verification gaps. |
| 4. Evidence, charts, and return contract | Define computed tables/scalars, chart formats, rendering and dependencies, labels/units/order, provenance, lineage, previews, supported data types and precision, and compatibility with downstream SQL. Decide how chart success, chart failure, and retained calculations appear in terminal outcomes. | Evidence/artifact schemas and complete supervisor handoff examples, including a partial result. |
| 5. Publication, recovery, and stopping | Adapt the existing action/attempt identity and publication rules. Resolve operation identity, durable outputs, checkpoint boundaries, disconnects, lost interpreter state, retirement, duplicate/stale completion, source deletion races, retries, no-progress accounting, and cleanup. | Lifecycle/state transitions and a failure/recovery matrix, with finite limit categories. |
| 6. Acceptance, traces, and evaluation | Define correctness checks for calculations and charts, safety/recovery gates, runtime trace fields, data privacy, version recording, and metrics for latency and model/sandbox cost. | Fixture and acceptance matrix; development/held-out separation; live verification checklist and cost-forecast inputs. |
| 7. Integrated specification audit | Walk through normal execution, correction, chart failure, interruption, and source removal against the approved SQL/supervisor contracts. Resolve consequential gaps and assign explicitly deferred work to its owner. | Audited Python Specialist specification ready for final user review. |

Approve each concrete contract before using it as the basis for dependent design. Findings can send a proposal back for revision; an earlier approval is reopened only when new evidence changes its basis.

## Research after plan approval

Use bounded subagent investigations, scheduled as their prerequisite decisions become available:

1. **Contracts and data fidelity:** Inspect SQL/Arrow/Parquet handoffs, dataframe conversion choices, decimals and wide integers, nulls and non-finite values, temporal semantics, duplicate labels, and Python-produced tables consumed by SQL.
2. **Execution and recovery:** Investigate generated-code isolation, per-action filesystem and process boundaries within a shared sandbox, interpreter lifetime, output validation, publication fencing, reconnect/replay behavior, and resource exhaustion.
3. **Charts and evaluation:** Compare the smallest viable plotting/rendering approaches against local display, reproducibility, dependency and active-content risks. Propose chart evidence checks, partial-result cases, tracing, and evaluation coverage.

Each investigation receives only relevant contracts, constraints, and questions. Its output must distinguish project decisions, official-source findings, proposals, and claims needing a live test. The parent reconciles findings and presents one coherent proposal per review round. Research does not approve a library, tool, chart format, or execution mechanism.

## Acceptance scenarios to make concrete

- SQL result to Python calculation and chart, with evidence behind the plotted values and correct labels, units, filters, ordering, and source lineage.
- A Python-only calculation that demonstrates the dispatch rule approved in round 1.
- Empty input, all-null columns, invalid/non-finite values, decimal and integer precision, dates/timezones, and an input larger than the preview.
- A code error followed by a bounded correction; missing analytical assumptions returned to the supervisor without silently changing the question.
- A valid calculation with a failed chart; retain the published calculation and expose the missing deliverable for a reviewed partial answer.
- Network and unauthorized read/write attempts, sibling-action access, child processes, output path traversal/symlinks, malformed outputs, and CPU/memory/disk/output exhaustion.
- Worker disconnect before and after output publication, lost interpreter state, duplicate/stale delivery, failed checksums, source deletion, deadline expiration, and preservation of successful sibling evidence.

The final spec must turn these into fixtures with observable expected outcomes. Capability claims remain unverified until the relevant live checks pass.

## Documents and affected contracts

- Create `docs/architecture/python-specialist.md` as the reviewed specification develops.
- Maintain this plan's status, the architecture index in `overall.md`, and accepted decisions/resume notes in `../memory.md`.
- Update `sql-specialist.md`, `supervisor.md`, `sandbox-execution.md`, and `evaluation-observability.md` only where reviewed contracts require a corresponding clarification. Update ingestion contracts only if source loading depends on them.
- Keep the PRD behavior intact unless a separately reviewed scope change is necessary. Runtime callers, tests, fixtures, dependencies, configuration, and exports are mapped in the later implementation plan; none change in this planning step.

## Deferred owners and completion check

Exact prompts follow component design. Exact model selections and numerical ceilings come from evaluation, with explicit finite limits required for any execution. Conversation memory and compaction belong to the later memory design. Backend delivery, Postgres integration, Redis checkpoints, and frontend display remain in their agreed phases, while their required handoffs must be documented here.

This design is complete when all seven rounds have reviewed deliverables, every consequential choice is approved or explicitly deferred to an owner without leaving an implementation blocker, and the integrated audit finds no unresolved contract gaps. Record unrun live checks as implementation acceptance gates. Then write the implementation plan derived from the approved spec.
