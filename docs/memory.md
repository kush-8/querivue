# Querivue decision log

Last updated 7 November 2026. Record agreed decisions here as they are made. Keep proposals separate until confirmed. When a decision changes, record what it replaces.

## Agreed decisions

| Area | Decision |
| --- | --- |
| Name | Querivue. Use `querivue` for the future repository. `querivue.com` was the preferred domain. Registration has not been completed. |
| Development process | Design the project first. Refine the PRD, then write the remaining design documents before implementation. Follow spec-driven development. Acceptance criteria and verification come from the spec. TDD is not the required development workflow. |
| Audience | Hiring reviewers assessing AI engineering skills. A business or operations user asking questions about spreadsheet data is the scenario the demo illustrates. |
| Goal | Querivue is a personal résumé project that demonstrates AI engineering. The earlier public self-service product framing is superseded. Show an end-to-end analysis, inspectable agent traces, and reproducible evaluation results. The under-five-minute walkthrough remains the demo target. |
| Showcase format | Run Querivue locally for a single operator. Present it through a public repository, a recorded walkthrough, and a reproducible evaluation report. Hosted access, public signup, and account quotas are outside this baseline. |
| Local development | Use Docker Compose to run the integrated application locally. Decide the local Postgres setup, service definitions, and environment configuration in architecture.md. |
| Hosted deployment direction | After the local build, the intended hosted setup is a Vercel frontend and Supabase for Django PostgreSQL. Render and DigitalOcean are candidates for the Django API and worker. The backend host and file storage choice are open. |
| Build sequence | Finish design first. Agreed phase order is standalone agent and CLI, database and storage, backend APIs, background workers, Redis checkpoints, backend integration, React, then GitHub Actions CI. The product cohort walkthrough and exact metric are deferred. |
| Agent milestones | Build grounded SQL first, then routing and follow-ups, Python and charts, analysis verification, full input coverage, and reproducible evaluation. The PRD defines the completion check for each milestone. |
| Project model | A user creates a Project and adds Datasets to it. A Project can contain multiple Datasets. Each Chat belongs to exactly one Project. This replaces the earlier plan to bind a chat to one dataset. |
| Dataset editing | Users can add, remove, and replace Datasets after creating a Project. Each upload is a fixed snapshot. A replacement creates a new Dataset ID, even if the filename is unchanged. An analysis run records its eligible Dataset IDs at submission and a retry never substitutes newer uploads. |
| Dataset scope | A question can use any ready Dataset in its Project by default. Users can name specific sources in their question. Querivue asks for clarification when the choice of source or period could materially change the answer. |
| Upload quota | Cap combined uploads at 50 MiB per Project. Measure the sum of uploaded file sizes across its Datasets. The cap is based on bytes. |
| Dataset replacement | Prepare a replacement before removing the original Dataset. A failed replacement leaves the original and its results available. A successful replacement uses the new Dataset ID and applies the agreed source removal behavior to the original. Add the corrected file separately to keep both versions. |
| Source removal | Removing a Dataset stops queued, running, or clarification-waiting analyses whose recorded scope includes it, even before they read it. Show a source-unavailable notice and let the user submit again. For completed runs, clear only answers, evidence, and artifacts that actually used the removed source. Unrelated turns remain available. |
| Inputs and scope | Accept CSV, TSV, Excel `.xlsx`, SQLite `.sqlite` or `.db`, JSON `.json`, JSON Lines `.jsonl`, and Parquet `.parquet` for exploratory analysis. TSV uses the delimited-file importer with a tab separator. SQLite imports selected tables into a prepared Dataset inside the sandbox. Use SQL and Python for analysis and visualization. Ask a focused follow-up when an ambiguous metric or join could materially change the answer. |
| JSON and Parquet imports | JSON uses a top-level array of flat records. JSON Lines uses one flat record per line. Each record becomes a row. Parquet imports preserve supported stored column types. Each of these formats produces one table per Dataset. |
| Answer contract | Quantitative claims link to inspectable evidence. Show the answer and supporting numbers first, with executed SQL or Python available on demand. A chart is required when the user asks for one. If it fails, return supported findings and label the result as partial. |
| Demo data boundary | Use synthetic or non-sensitive data in the demo. Document sandbox processing and the limited data sent to the model. Keep full files out of model requests and uploaded content out of hosted traces. |
| Retention | Projects, Datasets, Chats, and saved content remain until user deletion, including removal of content that depends on a deleted Dataset. This supersedes the earlier 24-hour retention window. Temporary execution state can have its own cleanup schedule. |
| Application architecture | Django owns persisted Projects, Datasets, Chats, runs, and results, and exposes them through an API. Background workers use the agent package for ingestion and analysis, including after the browser closes. React with TypeScript supports the complete upload, chat, progress, and results workflow. Detailed execution inspection lives in LangSmith. |
| Agent architecture | Multiple specialists, with LangGraph orchestration, LangChain tools and model integrations, and LangSmith observability and evaluation. Use managed sandbox execution for generated SQL and Python. |
| Router agent | Classify each question before analysis. Route to fresh SQL or Python when new work is needed, reuse verified context when it covers the question, or use the LLM alone when the answer needs no project data. Ask for clarification when ambiguity changes the calculation. Context and LLM-only answers skip SQL and Python. Trace and evaluate the routing decision. |
| Clarification Agent | Ask a focused question when a run needs user input. Show a question card inside the Chat with suggested answers where useful and a field labeled Reply to clarification. Save progress and release the worker and sandbox while waiting. A reply through the card resumes the same run with its recorded Dataset scope. Keep the main composer available with the label Ask a new question and send its messages to the router as new turns. |
| Agent behavior | Profile data before analysis. Check join cardinality, analysis grain, units, date windows, and denominators. Verify numeric claims against evidence and allow one reviewer correction. Carry agreed definitions and filters into follow-ups while invalidating context from removed sources. Route simple analyses to SQL and call Python when the task needs it. Benchmark routing and reviewer settings. |
| Tool guardrails and adversarial evaluation | In 1D, treat instructions embedded in uploads as data and enforce the run's authorized data scope at the SQL and Python tool boundary. In 1F, evaluate embedded instructions, an attempt to read an out-of-scope file, and an unanswerable data question. The expected outcomes are treating the cell as data, blocking the read, and explaining the missing evidence. |
| Checkpoints | Use Redis-backed LangGraph checkpoints. Save reusable outputs separately so a new worker can reconstruct state after interruption. Recovery cannot restore unsaved sandbox state. |
| Run controls | Show the current stage, enforce a run time limit, and offer Retry for eligible failures using the original Dataset IDs. Use a valid checkpoint for recovery. Defer a manual Stop action in v1. |
| Evaluation | Run the evaluation suite through the CLI. Compare single-agent and specialist configurations against shared fixtures and safety requirements. Use a held-out suite for final comparison. Measure correctness, latency, and cost to choose the configuration. |
| Constraints | Aim for a 4–6 week build once design is complete. Budget model and sandbox usage for local runs and evaluations. The showcase is local-only. AWS hosting and continuous deployment are outside scope. |
| Deferred scope | An LLM gateway, semantic caching, a separate Streamlit interface, and the detailed cohort walkthrough. |

## Working terminology

| Term | Meaning |
| --- | --- |
| **Project** | The user's container for datasets and chats. |
| **Dataset** | A fixed snapshot of one supported uploaded file added to a Project. A workbook or SQLite upload can expose multiple tables. |
| **Chat** | A conversation within one project. |
| **Analysis run** | One attempt to answer a chat question, including any recovery of that execution. |
| **Run scope** | The Datasets eligible for an analysis when its question is submitted. |
| **Used sources** | The Datasets that a completed result actually relied on. |
| **Clarification reply** | A response to an agent question that resolves ambiguity in a waiting analysis run. |
| **Evidence** | Inspectable computed results that support an answer. |
| **Artifact** | A saved output, such as a result table or chart. |

## PRD baseline

`PRD.md` records the agreed scope, demo flow, milestones, and showcase acceptance criteria. The remaining design work is in the architecture and module specs.

Use `architecture.md` for service boundaries and infrastructure decisions.

The ingestion spec will define how to report invalid JSON record shapes, conflicting field types, and unsupported Parquet column types.

## Draft plan defaults to validate during design

- The proposed agent boundary remains an importable Python package shared by the CLI and Django workers. Django is the app's HTTP API. Use the CLI for the first demo and reproducible evaluation runs. Add a FastAPI wrapper only if an independent HTTP consumer becomes a requirement. The first graphical demo can use the React interface.
- If Celery uses Redis as its broker, bring up Redis with background execution. Add the LangGraph checkpointer in the following phase. The queue delivers work, checkpoints restore agent progress, and PostgreSQL records job status and result references.
- The existing architecture draft proposes Django REST Framework, PostgreSQL, Celery, Redis 8 with persistent storage, E2B, DuckDB, pandas, Plotly, and a paid Gemini model as the initial benchmark candidate. These are starting points for the architecture documents.
- Set bounds on local agent runs and evaluation spend in the architecture and evaluation specs.
- The draft evaluation targets 90% correctness on answerable held-out fixtures and a 90-second p95 on demo-sized runs. Confirm the evaluation definitions and thresholds in the evaluation spec.
