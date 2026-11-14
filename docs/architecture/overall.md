# Querivue overall architecture

Organized 14 November 2026. Confirmed foundations and remaining design work; component specifications contain the detailed contracts.

## Focused architecture documents

| Document | Scope |
| --- | --- |
| [Data ingestion](data-ingestion.md) | Upload preparation, import confirmation, formats and immutable dataset publication. |
| [Sandbox execution](sandbox-execution.md) | Execution isolation, storage handoff and the E2B assessment. |
| [Supervisor](supervisor.md) | Planning, state, delegation, outcomes and review flow. |
| [SQL Specialist](sql-specialist.md) | Approved SQL contracts, safety, recovery and tabular handoff. |
| [Python Specialist plan](python-specialist-plan.md) | Approved design-review sequence; Python-specific decisions await review. |
| [Evaluation and observability](evaluation-observability.md) | Supervisor evaluation, traces, execution limits, inference and cost. |

## System boundaries

The React frontend communicates with Django APIs. Background workers import the independent agent package. Application metadata lives in Postgres; uploaded and generated files live in shared persistent storage. Sandboxes process authorized files, while model calls run in the worker. Detailed backend, worker and frontend designs remain in their agreed later phases.

## Confirmed foundations

### Agent boundary

The agent is an independent Python package in `agent/`. Its CLI and the Django background worker import the same package. The package owns routing, clarification, specialist coordination, analysis tools, and verification. Django owns application persistence and the HTTP API.

Keep the agent callable without starting Django. The CLI supplies its inputs directly. The application worker resolves the run's recorded dataset scope and passes the relevant inputs to the agent. Interface types and lifecycle contracts will be defined as this document is refined.

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

Confirm the supervisor's completion and reviewer policy, delegation contracts, specialist observations, partial failures, budgets, and model configuration during the remaining supervisor rounds. The broader agent and application memory policy has its own deferred discussion.

A new constraint discovered during implementation must be checked against the agreed spec. Record and resolve any consequential design change before coding that change.
## Decisions still open



- Background execution framework and broker configuration. Celery with Redis is the current proposal.
- Progress delivery. Polling run status is the initial proposal. Decide whether the frontend needs live streamed events.
- Run and attempt state transitions, source deletion, retries, clarification resume, and checkpoint recovery.
- Execution sandbox configuration, resource limits, data access restrictions, and artifact validation.
- Agent interfaces, model configuration, and observability.
- A later detailed memory discussion covering the agent loop and the application, recent turns and older summaries, persisted history retrieval, checkpoint state, and Chat versus Project scope.
- Detailed Docker Compose services and environment configuration.

The PRD defines the agreed behavior and build phases. This draft records confirmed choices while the remaining architecture is discussed.
