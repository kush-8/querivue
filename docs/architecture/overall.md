# Querivue overall architecture

Organized 14 November 2026. Confirmed foundations and remaining design work; component specifications contain the detailed contracts.

## Focused architecture documents

| Document | Scope |
| --- | --- |
| [Project status review](../status-review.md) | Current design/implementation status, outstanding owners and recommended sequence. |
| [Data ingestion](data-ingestion.md) | Upload preparation, import confirmation, formats and immutable dataset publication. |
| [Sandbox execution](sandbox-execution.md) | Execution isolation, storage handoff and the E2B assessment. |
| [Supervisor](supervisor.md) | Planning, state, delegation, outcomes and review flow. |
| [Agent graph, memory and integration](agent-integration.md) | Agenda, rounds 1–2/evidence registry and entry guardrails 2B1–2B2 approved, including intake records and candidate limits; memory/context policy next. |
| [SQL Specialist](sql-specialist.md) | Approved SQL contracts, safety, recovery and tabular handoff. |
| [Python Specialist](python-specialist.md) | Design review closed: rounds 1–7 approved; context/configuration dependencies and runtime gates remain. |
| [Answer Specialist](answer-specialist.md) | Rounds 1–6 approved; design review closed with explicit readiness gates. |
| [Reviewer](reviewer.md) | Rounds 1–6 approved; design review closed with explicit context/runtime/evaluation gates. |
| [Evaluation and observability](evaluation-observability.md) | Supervisor evaluation, traces, execution limits, inference and cost. |

## System boundaries

The React frontend communicates with Django APIs. Background workers import the independent agent package. Application metadata lives in Postgres; uploaded and generated files live in shared persistent storage. Sandboxes process authorized files, while model calls run in the worker. Detailed backend, worker and frontend designs remain in their agreed later phases.

## Confirmed foundations

### Agent boundary

The agent is an independent Python package in `agent/`. Its CLI and the Django background worker import the same package. The package owns routing, clarification, specialist coordination, analysis tools, and verification. Django owns application persistence and the HTTP API.

Keep the agent callable without starting Django. The CLI supplies its inputs directly. The application worker resolves the run's recorded dataset scope and passes the relevant inputs to the agent. Interface types and lifecycle contracts will be defined as this document is refined.

Persistent Redis-backed LangGraph checkpoints belong to the standalone agent milestones, including recovery in a fresh CLI process without Django. Later worker checkpoint integration reuses that agent capability. Checkpoints restore graph progress; durable artifacts and the shared transactional authority retain their approved publication, invalidation and accounting responsibilities.

### Local and hosted Postgres

Docker Compose runs Postgres locally. The eventual hosted setup uses Supabase Postgres. Django migrations define the application schema in both environments.

Postgres holds Projects, Datasets, Chats, messages, run records, source relationships, and references to saved files. The agent performs analytical queries over prepared uploads inside the execution sandbox.

### Shared local storage

Use a persistent Docker volume for uploaded files, prepared datasets, and artifacts. The Django API and background worker mount the same volume. Store file references and metadata in Postgres.

Retain stored data until the user deletes it under the PRD's source-removal rules. Give each sandbox only the inputs authorized for its run. Keep persistent output copies outside the sandbox so later runs and recovery can retrieve them.

## Current project layout

| Directory | Responsibility |
| --- | --- |
| `agent/` | Independent agent package, CLI, and evaluation suite. |
| `backend/` | Django API, persistence, and background task integration. |
| `frontend/` | React and TypeScript interface. |
| `docs/` | PRD, decision log, architecture, and later specifications. |

Backend and agent dependencies use separate uv projects and virtual environments.

## Design completion checklist

Before implementing a component, resolve its consequential design choices and obtain agreement on its spec. Keep decisions visibly marked as agreed, proposed, or open. Record explicit defaults and their rationale. Describe request and result contracts, allowed actions, state transitions, data scope, dependencies, parallel result handling, failure and retry behavior, completion checks, limits, and acceptance scenarios. Settle each item in the component that owns it.

Specialist payloads, fresh-answer handoff, correction routing and the two-review policy are approved in the component specifications. Remaining supervisor work covers shared task/control/outcome contracts, Direct answer and clarification transitions, dependencies/recovery, runtime budget admission and model configuration. Shared agent/application memory and canonical runtime contracts remain separate prerequisites. See the [status review](../status-review.md) for the current outstanding-work map.

A new constraint discovered during implementation must be checked against the agreed spec. Record and resolve any consequential design change before coding that change.

## Decisions still open

- Background execution framework and broker configuration. Celery with Redis is the current proposal.
- Progress delivery. Polling run status is the initial proposal. Decide whether the frontend needs live streamed events.
- Concrete shared run/attempt/control transitions, clarification resume, retry/checkpoint integration and implementation of the approved source deletion/publication semantics.
- Exact sandbox manifests/configuration, measured resource limits and live verification of approved access/isolation/artifact policies.
- Shared agent/runtime interfaces and executable model/prompt/evaluation/observability configuration; component-specific handoffs and privacy policies are approved.
- A later detailed memory discussion covering the agent loop and the application, recent turns and older summaries, persisted history retrieval, checkpoint state, and Chat versus Project scope.
- Detailed Docker Compose services and environment configuration.

The PRD defines the agreed behavior and build phases. This draft records confirmed choices while the remaining architecture is discussed.
