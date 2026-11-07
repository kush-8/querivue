# Querivue PRD

PRD baseline · 7 November 2026

## Purpose

Querivue is a personal AI engineering portfolio project. It demonstrates how an agent turns tabular data into answers that can be checked against computed evidence. Hiring reviewers can follow a short walkthrough and reproduce a comparison of agent configurations. The example workflow represents a business or operations user exploring spreadsheet data.

Run the app locally as a single operator. Present it through a public repository, a recorded walkthrough under five minutes, and an evaluation report. The exact showcase dataset and cohort question can be chosen after the core works.

## Core workflow

1. Create or reopen a Project. Add a supported file and see whether the Dataset is processing, ready, or failed. For SQLite uploads, choose which source tables to import.
2. Open a Chat within that Project and ask a plain-language question. The agent can use any ready Dataset in the Project by default. A question can name specific sources. If the choice of source, join, period, or metric would materially change the answer, show a focused clarification card in the Chat.
3. Follow the current analysis stage and return to the result after closing and reopening the browser. Ingestion and analysis continue after submission in background workers. Runs have a time limit and can recover completed work from a valid checkpoint. When a run fails, explain the failure and offer Retry if the original inputs are available and the failure is eligible for retry.
4. Read the answer and inspect the supporting values, tables, charts, and executed SQL or Python. Every quantitative claim points to inspectable evidence. If a requested chart fails, show the supported findings and mark the result as partial. If there is insufficient evidence for an answer, explain what is missing.
5. Ask a follow-up or manage the Project's Datasets. Prior work remains accessible subject to the source removal rules below.

Each submitted question has its own run state. A linked clarification reply resumes that original run. A new turn creates another run and can carry relevant confirmed context from earlier work.

## Agent behavior

A bounded ReAct-style supervisor owns routing, planning, and specialist delegation. It makes the first decision for each new question and chooses the next action after a specialist returns.

| Route | When to use it | Example |
| --- | --- | --- |
| **Fresh analysis** | The question needs a new query, calculation, or visualization. Hand it to the SQL or Python workflow. | “Break down Q2 revenue by region” when that breakdown has not been computed. |
| **Direct answer** | Answer from general knowledge or sufficient verified context. Claims about project data cite computed evidence or profiles. The supervisor can compose the answer in the same model call. | “What does a left join do?” or “What was the Q2 total you just calculated?” |


The Direct answer path finishes without starting SQL or Python execution. Record general-knowledge and evidence-based answers as separate labels in traces and evaluations. If evidence is missing or stale for a data question, route to fresh analysis or ask for clarification when the intended calculation is ambiguous. Record the selected route and a short decision label in LangSmith.

When a run needs user input, the Clarification Agent asks one focused question and puts the run in **Waiting for clarification**. The question appears inside the Chat with suggested answers where useful and a **Reply to clarification** field. A reply through the card resumes the waiting run with its recorded Dataset scope. While the run waits, save its progress and release the worker and sandbox. Keep the main composer available and label it **Ask a new question**. Messages from that composer go to the supervisor as new turns.

- Profile the data before analysis. Give the agent column types, missing-value counts, relevant date ranges, and candidate join keys in a compact summary.
- Check join cardinality, analysis grain, units, date windows, and denominators. If a join changes the number of rows, verify that the calculation still counts the intended entity. Correct a clear error and ask a focused question when the intended calculation is ambiguous.
- For fresh analysis, let the supervisor gather evidence, then have an Answer Specialist draft the response. Require Reviewer approval before displaying it. Missing or incorrect computed evidence returns the run to the supervisor. Sufficient evidence with a draft calculation or conclusion error returns it to the Answer Specialist. Permit at most two review passes in total, including the initial review. If the second review rejects the answer, end with a brief explanation of the unresolved verification issue and omit the rejected analysis. If evidence is missing, explain which claim could not be supported and what evidence is needed, using the reviewer findings. When a review finds both evidence issues and draft errors, evidence issues take precedence and the run returns to the supervisor, subject to the two-pass limit. The reviewer reports only blocking problems with correctness, evidence, or fulfillment of the request. Wording and style preferences remain with the Answer Specialist.
- Treat instructions found in uploaded cells as data. Enforce access to analysis inputs and artifacts at the SQL and Python tool boundary. Reject attempts to read files outside the run's authorized scope, regardless of what the model requests.
- Carry agreed metric definitions, filters, source references, and evidence into follow-ups. Show when the user changes an assumption. Discard context that depends on a removed Dataset.
- For fresh analysis, route simple counts and comparisons to SQL. Use the Python specialist when the analysis or visualization needs it. Measure the accuracy, latency, and cost of the available routes and reviewer settings.

## Data and lifecycle

- A Project contains Datasets and Chats. Each Chat belongs to one Project. Each Dataset is a fixed snapshot of one uploaded file.
- Accept CSV (`.csv`), TSV (`.tsv`), Excel (`.xlsx`), and SQLite (`.sqlite`, `.db`) uploads. CSV and TSV each become one table. Excel can expose multiple worksheet tables. For SQLite, validate that the file is a SQLite database and copy the selected tables into the prepared Dataset inside the sandbox.
- Accept JSON (`.json`) as a top-level array of flat records and JSON Lines (`.jsonl`) as one flat record per line. Each record becomes a row. Accept Parquet (`.parquet`) and preserve its supported stored column types. JSON, JSON Lines, and Parquet each become one table in a prepared Dataset.
- Cap combined uploaded file size at **50 MiB per Project**. The limit is based on bytes across Datasets.
- A run records its eligible Dataset IDs at submission. Subsequent project edits affect future questions. Recovery or retry uses the original inputs if they remain available.
- Users can add, remove, or replace Datasets. A replacement receives a new ID and takes effect after preparation succeeds. A failed replacement leaves the original file and its results available. A successful replacement applies source removal to the original. Adding a corrected file separately keeps both snapshots.
- Projects, Datasets, Chats, and results persist until user deletion. Removing a Dataset stops any queued, running, or clarification-waiting analysis whose recorded scope includes it, even before it reads the Dataset. Show a source-unavailable notice and let the user submit a new question against the current Datasets. For completed runs, remove answers, evidence, and artifacts only when they used the removed source. Unrelated turns remain available.
- Use synthetic or non-sensitive data. Document what goes to the managed sandbox and model. Keep full uploaded files out of model requests and upload content out of hosted traces.

## Build milestones

Finish the design documents before implementation. The order below is agreed. Service boundaries, storage choices, and infrastructure contracts belong in `architecture.md`.

| Phase | Outcome |
| --- | --- |
| **1. Standalone agent** | Run and evaluate the agent through a CLI. |
| **2. Database and storage** | Persist Projects, Datasets, Chats, run records, and saved outputs. |
| **3. Backend APIs** | Exercise Project, upload, Chat, run submission, status, and result contracts through Django. |
| **4. Background workers** | Complete a real upload-to-answer flow that survives closing the browser. |
| **5. Persistent checkpoints** | Use Redis to recover completed agent work after a worker interruption. |
| **6. Backend integration** | Verify replacement, deletion, limits, timeouts, retry, and duplicate job delivery. |
| **7. Frontend** | Complete the React workflow for Projects, uploads, Chats, progress, and evidence. |
| **8. Continuous integration** | After the local app is complete, set up GitHub Actions to verify the agent, backend, and frontend. |

### Agreed agent milestones

| Milestone | Completion check |
| --- | --- |
| **1A. Grounded SQL** | From the CLI, ingest a CSV fixture, run a sandboxed query, and return an answer linked to the result and executed SQL. Capture a trace. |
| **1B. Router and follow-ups** | Show fresh analysis and both forms of Direct answer. A matching prior result and a general question finish without tool execution. A changed filter triggers fresh analysis. Demonstrate that the CLI can ask a clarification and resume the same analysis with its original Dataset scope. |
| **1C. Python and charts** | Send a computed result to the Python specialist, produce a chart, and show a labeled partial result when chart generation fails. |
| **1D. Analysis verification and guardrails** | Catch an incorrect count caused by a join, verify the correction, and demonstrate that the tool boundary rejects unauthorized file access. |
| **1E. Full input coverage** | Import every approved format into the same prepared Dataset workflow and verify representative types and source tables. |
| **1F. Reproducible evaluation** | Run the same suite against the baseline and specialist configurations. Report routing accuracy, answer correctness, latency, cost, and outcomes on adversarial cases. |

AWS deployment, continuous deployment, hosted access, public signup, account quotas, a manual Stop action, a separate Streamlit interface, an LLM gateway, and semantic caching are outside the initial scope.

## Showcase acceptance

- Verify that an incorrect computed result returns to the supervisor, a draft-only error returns to the Answer Specialist, and a second rejected review explains the unresolved issue. For missing evidence, the response identifies the unsupported claim and needed evidence. The run never performs a third review.

- Reproduce a walkthrough that uploads data, answers a question through SQL or Python, produces a chart, and shows the evidence behind its claims.
- Demonstrate a materially ambiguous question that shows a clarification card in the Chat. Use the main composer to ask a separate question while the original run waits. Reopen the Chat and answer through the card to resume the same run. Verify that removing a Dataset from the waiting run's scope makes the clarification unavailable.
- Demonstrate that a failed chart returns a clearly labeled partial result.
- Import a TSV fixture with the expected column boundaries. Import selected tables from a SQLite fixture, then join one imported table with another ready Dataset in the same Project.
- Verify that JSON and JSON Lines fixtures with equivalent records produce the same table. Verify that a Parquet fixture preserves dates, numeric types, and null values.
- Verify on a fixture with repeated events that a join produces the expected distinct-user numerator and denominator. Check that a follow-up retains the agreed filters and that a simple SQL question completes without a Python step.
- Verify that the supervisor sends a new data question to analysis, reuses a matching verified result without executing tools, and answers a general analytics question without opening a sandbox. Verify that a new filter or removed source makes incompatible prior evidence ineligible for reuse.
- Verify three adversarial fixtures. Instructions embedded in a cell are treated as data, a tool attempt to read an out-of-scope file is blocked, and a question the data cannot answer produces a clear explanation of the missing evidence.
- Demonstrate that a submitted run survives a browser disconnect and that a worker interruption can recover completed work from a checkpoint.
- Demonstrate that an analysis timeout produces a visible failure state and that an eligible retry uses the original Dataset IDs.
- Demonstrate that a failed replacement preserves the original. Remove Dataset B while a run scoped to A and B is queued and verify the run stops. Verify that a completed result that used B is cleared and a result that used only A remains available.
- Publish a repeatable evaluation against shared fixtures and a held-out set. Compare a single-agent baseline with specialist configurations on correctness, latency, and cost. Use the results to explain the chosen configuration. Pin exact thresholds and scoring rules in the evaluation spec.

