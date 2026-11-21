# Standalone agent implementation planning — working document

Started 20 November; review draft completed 21 November 2026, at the user's request to complete implementation planning before coding. Agent architecture is approved and closed. This phase authorizes repository inspection, official-source research and reversible planning-document edits only; no production code, dependency installation, inference, sandbox session or paid run.

## Objective

Prepare one reviewable implementation plan for the standalone agent/CLI milestones, preserving approved ingestion, graph/state, specialist, provider, persistence, isolation and evaluation contracts. Pin ownership, file placement, internal interfaces, dependency order, verification and stop gates. Application API/worker/UI work remains separate.

## Work sequence

1. Retrieve approved milestone/acceptance contracts and inspect the starter agent package, relevant configuration and graph inventory.
2. Define the smallest complete package layout, dependency/build strategy and task interfaces. Distinguish architectural decisions already approved from implementation proposals and measured external gates.
3. Order independently verifiable tasks through local scripted execution, isolated provider integration, persistence/recovery and reproducible comparisons. Map requirements and failure modes to their owning task/checks.
4. Self-review coverage, type/interface consistency, safety/cost boundaries and worker handoff context. Prepare a coherent plan for user review, preserving the existing coding-agent requirements.
5. On approved completion, transfer the executable plan/rationale/open gates to a durable implementation guide and decision log, remove this temporary planning document and repair references. Refresh the existing blueprint only at that phase boundary, then update/verify QMD and the code graph.

## Scope and stopping rule

The plan ends at the standalone agent capability and evaluation/report handoff. It does not invent backend routes, redesign approved agent behavior, claim live compatibility/safety or authorize coding. Exact built identities and enforcement are verified in bounded implementation tasks before dependent capabilities; unsupported controls stop those capabilities. Further architecture discussion is needed only if implementation evidence contradicts an approved contract.

## Review and evidence

Repository audit: `agent/pyproject.toml` requires Python >=3.12, uses uv_build and has no runtime dependencies/CLI entry; `__init__.py` only exposes hello(). No agent tests exist. Backend/frontend remain separate starters. The existing graph lags a newer repository commit; direct source/manifests are authoritative and final index maintenance will refresh it. No code relationships justify reusing a nonexistent runtime.

Implementation proposals for the review plan:

- Cover all standalone milestones 1A–1G in the agreed order, with canonical ledger/artifact/accounting/checkpoint infrastructure before the first end-to-end SQL slice. Wire recovery ownership early; prove its full crash matrix at 1E. Preserve stricter approved gates throughout incremental delivery.
- Use stdlib argparse/sqlite3/pathlib/json/logging and pytest, with no Django, ORM, CLI framework or extra summarizer. The user explicitly selected the LangChain stack on 21 November: LangChain chat models/messages/tools/structured output, maintained provider integrations and LangGraph orchestration/private subgraphs. This supersedes the earlier native-SDK/custom-HTTP proposal. The existing authority/gateway still owns accounting, guarded tool execution and publication; framework defaults cannot create a second control plane.
- Keep prompts as packaged Markdown v3 resources; input data is never interpolated into trusted templates. LangGraph checkpoint thread_id maps to run_id, not Chat ID; private invocation namespaces cannot mix agent histories. Canonical records remain ledger-owned and checkpoint serializer tests must prohibit arbitrary pickle restoration.
- Start with scripted/offline model and sandbox transports for deterministic runtime checks. No scripted result proves 1A sandbox execution or model quality. Real generated execution requires the exact applicable environment gates and its own live/spend authorization; there is no host-process fallback.
- Treat public package versions as dated candidates, not a resolved compatible lock. The owning implementation tasks resolve/freeze hashes and run compatibility assertions before dependent code is accepted. Do not silently upgrade/downgrade dependencies or relax isolation to make a build pass.

Primary-source checks on 20 November 2026: [LangGraph persistence](https://docs.langchain.com/oss/python/langgraph/persistence), [private subgraphs](https://docs.langchain.com/oss/python/langgraph/use-subgraphs), [Redis checkpointer](https://github.com/redis-developer/langgraph-redis), [E2B network switch](https://docs.e2b.dev/network/internet-access), [Google SDK](https://github.com/googleapis/python-genai), [token counting](https://ai.google.dev/gemini-api/docs/tokens), [Plotly static rendering](https://plotly.com/python/static-image-export/), Python 3.12 [sqlite3](https://docs.python.org/3.12/library/sqlite3.html) and [argparse](https://docs.python.org/3.12/library/argparse.html). These support candidate API choices only. RedisSaver setup/search modules, graph interrupt replay, provider token/retry semantics and renderer/browser compatibility still need exact-build tests. Public PyPI JSON metadata was read without downloads/installations or inference.

The user has not yet approved the file layout, dependency/build strategy, implementation sequence or execution start. The full checklist/interface plan is prepared in `docs/implementation/standalone-agent.md`, marked pending review. Retain this phase document until that review and closure; no phase-end Floorplan refresh yet.

## Review draft — 21 November 2026

The [standalone implementation plan](implementation/standalone-agent.md) is prepared and self-reviewed: 18 ordered tasks, proposed source/test/resource placement, typed consumed/produced interfaces, CLI commands/statuses, dependency/build strategy, milestone 1A–1G checks, G01–G10 ownership and coding-agent handoff rules. Checkboxes refer to future implementation and remain unchecked. Additional public metadata/source check: rfc8785 0.1.4 for the already approved JCS requirement; no custom sorted-JSON substitute.

Consequential implementation choices for one review: foundations before the first SQL slice; stdlib CLI/SQLite with the user-selected LangChain/LangGraph private-subgraph runtime; Python 3.12-only initial lock; staged dependency groups and an exact Linux guest/browser manifest; explicit CLI scope/confirmation/resume behavior; offline/scripted checks separated from actual environment/provider acceptance. Existing architecture and Markdown prompt/provider policies are unchanged. Coding workflow is now explicitly selected: GPT 6 Astra (`gpt-6-astra`) medium supervisor, lower available medium-reasoning code writers, with the suggested plugins. A fresh-context delegated coding supervisor handles that model when the current chat cannot switch; no coding agents are launched during planning.

After user acceptance, close this planning phase by retaining the executable checklist/rationale in the implementation guide, recording acceptance in memory, deleting this temporary document/repairing its links, refreshing/validating/showing the blueprint and then the indexes. Do not begin coding merely because the review draft is complete or accepted; carry forward the user's explicit instruction to finish planning before a separately authorized start.

Documentation checks passed on 21 November: exactly T01–T18 in order; all tasks include file/interface ownership and at least three unchecked implementation steps; superseded inconsistent packet/restore signatures are absent; relative file/anchor links resolve in all five affected documents; whitespace check passes. Changes remain documentation-only. No task test command, dependency resolver, build, Docker daemon/service, provider or sandbox execution was run. Local QMD/code-graph refresh/status verification follows the final edits.

User-directed revision, 21 November: replace the selected "No LangChain provider-agent stack" exclusion with LangChain and its maintained Google/NVIDIA/OpenRouter/Cloudflare integrations, preserving all existing role/tool/retry/privacy/spend gates. Official integration docs and public PyPI candidates were checked, with no install/inference. Task T06 now tests one authorized invocation versus actual physical wire calls, raw/normalized usage (including unknown/zero distinction and reasoning), tool/signature preservation, safe message serialization and explicit Developer API routing. The user corrected coding supervisor wording from Astra Light to GPT 6 Astra medium; current rules/plan use that final choice. Other plan choices remain pending review and coding remains unstarted.
