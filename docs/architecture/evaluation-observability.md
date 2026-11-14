# Agent evaluation and observability

[Overall architecture](overall.md) · [PRD](../PRD.md) · [Decision log](../memory.md)

Cross-component requirements are collected here. Component-specific acceptance and trace requirements remain in their specifications, including the [SQL Specialist](sql-specialist.md). Exact models, prompts and numerical limits retain their agreed later evaluation owners.

### Supervisor evaluation and observability

Evaluate both answer correctness and agent behavior. Use versioned fixtures with expected calculations and evidence, and check required and forbidden trajectory events for routing, evidence reuse, clarification, prerequisite ordering, retries, and review. Treat safety and recovery invariants as pass/fail gates. Compare the single-agent baseline and specialist configurations on shared fixtures for correctness, completion, active latency, tool calls, retries, and cost. Tune on development cases and use held-out cases for the final comparison.

Trace decisions, task and action dispatch, attempts, checkpoint resumes, reviews, and final outcomes. Correlate events with run, task, and action IDs and attempt numbers where applicable. Record concise decision labels, durations, outcomes, and stop reasons. Keep uploaded rows and raw results out of hosted traces. Publish a repeatable CLI evaluation and a report with configuration comparisons and annotated failure traces. Exact event fields, fixtures, and thresholds belong in the observability and evaluation specs.

### Agent inference and evaluation cost

Use OpenRouter for inference across all model-powered agent components, including the supervisor, specialists, and reviewer. Choose model configurations by role after evaluating candidates. Before running the full evaluation suite, forecast its cost using the planned cases, repetitions, expected token usage by role, and provider rates, with cache assumptions stated explicitly. After the run, report actual billed model usage and costs, including cached tokens and retries where applicable. Compare forecast with actual spend and report any separately billed evaluation costs, such as sandbox usage or external judges, within the same stated scope.

### Evaluation-driven execution limits

Choose the final supervisor execution limits from reproducible evaluation results, comparing answer quality, task completion, latency, cost, and recovery behavior. The suggested values are evaluation candidates only: 12 supervisor decisions per run, 3 concurrent specialist tasks, 1 retry of an unchanged task for transient failures, 2 consecutive action rounds without progress, and 5 minutes of active execution excluding clarification waits. These numerical values remain candidates for evaluation. Evaluation runs must still use explicit finite limits. The separately agreed maximum of two review passes remains confirmed.
