# Continuous integration and verification automation

**Phase 8 design approved and planning closed, 27 November 2026**, at the user's request to continue after reviewing the packet. No workflow, remote setting, scheduled task or hosted baseline was created. This guide owns accepted verification automation for the local application; implementation and enablement remain separate. Hosting, deployment, public previews, release publication and paid/live agent runs remain outside scope. See the [closure record](../memory.md#ci-planning-closure--27-november-2026).

## Current evidence

- Git origin is on GitHub; there is no `.github` workflow directory in the inspected working tree. GitHub Actions is selected; no second CI service is introduced.
- `agent/` and `backend/` have separate uv projects/lockfiles and Python 3.12 declarations. The agent currently restricts Python to `>=3.12,<3.13`. Keep their environments separate.
- Agent pytest defaults exclude `live` and `redis` tests. A marker-selection regression test exists. Test collection alone and historical test names do not prove runtime behavior; do not turn the earlier Floorplan audit into current-source readiness evidence.
- Backend currently declares Django 5.2 and lacks the planned application/worker/browser integration implementation. The existence of backend source/tests elsewhere must be checked at implementation time; this packet did not audit all ongoing work.
- Frontend has an npm lockfile, `lint` and `build` scripts, but no product test script. The authorized Router/Query addition passed those existing checks on local Node 22.18.0. That starter build does not verify routes or HTTP/WebSocket integration.

The [frontend guide](frontend.md), [backend verification design](backend-integration.md) and [remaining readiness review](../floorplan-attention-review.md) retain their own acceptance owners. All new CI results are **not_run**; no pipeline baseline was executed in this planning phase.

## Selected trigger and runner policy

Run an unprivileged quality workflow for `pull_request` and pushes to `main`; include `merge_group` if a merge queue is actually enabled. Offer manual deterministic verification through `workflow_dispatch`. Start without top-level path filters so a required status cannot remain permanently pending because its workflow never ran. Small initial jobs can run for documentation changes too; optimize only after measuring cost and proving complete change coverage.

Use ephemeral GitHub-hosted Linux runners, initially an explicitly selected supported Ubuntu image. Match the approved Linux-container backend direction; do not use a developer's workstation or a privileged self-hosted runner for pull-request code. Initially target Python 3.12 and a compatible supported Node 22 patch; choose and record exact runtime/uv/action/browser/image builds at workflow implementation. Local Node 22.18.0 is historical build evidence, not a decision to freeze that patch indefinitely. Do not use moving `latest` tags or the skill's example action versions without verification.

Cancel superseded pull-request quality runs in a workflow-and-PR-scoped concurrency group. Keep main evidence runs scoped to their commit; do not let an unrelated workflow cancel them. Fault harnesses must guarantee cleanup on cancellation as well as test failure. No scheduled paid or live runs. A periodic deterministic smoke run may be discussed later if it serves an actual need.

## Stage A — checks supported by current repository tooling

| Job | Planned work and claim boundary |
| --- | --- |
| `agent-offline` | In `agent/`, validate lock with `uv sync --locked --group dev`, then `uv run --no-sync python -m pytest -m "not live and not redis"`. Record collection/execution counts and junit output; nonzero expected selection is required. Keep default marker regression coverage. Build the distributable with the locked build toolchain and smoke its installed wheel/CLI from an isolated directory. Do not call provider or real generated-execution capabilities. |
| `backend-foundation` | In `backend/`, use its own locked environment, run `manage.py check` and `makemigrations --check --dry-run` against isolated test configuration. Include genuine backend tests when present; do not report a zero-test run as backend integration coverage. Starter management checks prove only that foundation. No application database or migrations against operator data. |
| `frontend-quality` | In `frontend/`, `npm ci`, `npm run lint`, `npm run build`. `build` already performs the TypeScript project build; do not add a redundant differently configured type check. Run contract/UI tests once their runner and meaningful cases exist; absence of `npm test` is not an invisible pass for F1–F5. |
| `quality-summary` | Always evaluate the declared mandatory jobs and publish a stable aggregate check. Succeed only if all applicable mandatory jobs succeeded for the exact commit. Failure, cancellation, missing results and unexpected skips cannot turn into success. Clearly label the result as current offline/foundation quality, not application readiness. |

Exact commands must be exercised from a fresh checkout before making this status required. Check available wheel-build/schema commands against the source and approved implementation guide rather than inventing a script name. Pin any added development-only build/schema/audit tooling; do not silently resolve new versions during checks. `uv run --no-sync` is used only after successful locked sync in the same job.

Do not add Ruff, another Python checker, a second JavaScript linter or a formatting migration merely to make the job table look complete. Add a check when its enforceable repository configuration and purpose exist. Check generated public schema/types for drift once their authoritative generator exists; do not hand-author a second schema to satisfy CI.

## Stage B — real services and product verification

Introduce these as their prerequisites are implemented and independently verified, not as placeholder green jobs:

| Job family | Required environment and evidence |
| --- | --- |
| Agent Redis integration | Isolated compatible Redis build with the required JSON/search capabilities; plain Redis without those modules is not an equivalent service. Override pytest selection explicitly for the intended Redis cases while continuing to exclude live cases. Verify meaningful nonempty collection. Restore/replay/no-TTL behavior must be asserted against real service state. |
| Backend L1 | Actual Postgres constraints/migrations/services and Channels boundary tests for the declared scenarios; no SQLite substitute for Postgres concurrency semantics. |
| Backend L2 | Real isolated Postgres, shared private file storage, correct Redis, ASGI/Channels, Celery roles and browser/native protocol client. Use deterministic adapters at approved external model/sandbox boundaries. Reuse B01–B13 oracles, controlled fault barriers and strict evidence classifications. |
| Product frontend | Real React app through the same-origin ingress against L2, covering F1–F5: navigation/import, exact clarification targeting, command uncertainty/reconnect, publication/evidence/revocation, themes/motion/focus and responsive behavior. Pin the browser runner and browser build; the existing verification guide selects Python Playwright, so prefer reusing that harness over adding a second driver by default. |

Service/container definitions, health/readiness probes, migration/setup and fixture lifecycle need to exist before these jobs become mandatory. Use unique test IDs/directories/databases and private ephemeral credentials per run. Bound fixture/process lifetime and disk use; collect sanitized evidence before destroying only that run's resources. Avoid fixed sleeps as readiness proof. A CI job timeout is a failure/cleanup bound, never an analytical deadline reset or proof of safe sandbox retirement.

Run cancellation, cross-process failure, malformed/missing events and source revocation against the actual combined path; do not replace them with mocks of the very boundary under test. Test-generated untrusted SQL/Python must remain inside the admitted sandbox boundary. Scripted external adapters cannot enable or certify the currently unproven live execution capability. A container alone does not establish the sandbox's required controls.

## Required status and readiness policy

Use a stable `quality-summary` required check **after** its fresh-checkout baseline succeeds and the user chooses to enable the remote rule. Track B/F/live readiness separately with explicit `not_run`/`blocked` reasons. A green foundation check means exactly the implemented foundation passed; it is never a release badge for missing product behavior.

Promote each Stage B job to mandatory when its owning slice is claimed implemented or the corresponding capability is enabled. Once mandatory, it cannot silently disappear behind a feature flag, an empty matrix, an unrecognized path or `continue-on-error`. Required scope is an explicit reviewed manifest/job contract, not inferred only from whether tests happen to exist. Missing scenarios/tooling fail that promoted gate. The summary must evaluate the planned-versus-observed job set; `always()` alone does not make this comparison correct.

If later using change detection, keep the summary workflow always triggered, include both shared contracts and reverse dependencies, and test documentation-only changes, renamed/deleted files, empty selections, failed detection and unavailable base commits. Detection uncertainty runs the conservative superset. Report intentionally inapplicable jobs separately; do not use “skipped” as a synonym for “passed.” Merge-queue and PR results must refer to the commit actually evaluated.

Workflow files/check names can be prepared locally in the later implementation task. Changing branch rules, required-check settings, repository permissions or secrets is a separate remote action; none is performed by this planning turn. No automatic merge, push, release tag or deployment is included.

## Trust, reproducibility and artifacts

- Untrusted PR code runs only in the unprivileged `pull_request` context with minimum token permissions (normally `contents: read`); disable persisted checkout credentials. Do not execute PR code with `pull_request_target`, privileged `workflow_run` secrets or inherited deployment credentials. Fork PRs need no application/provider secrets.
- Pin reviewed third-party actions to full commit SHAs, record their release names, and use fixed tool/image/browser builds. Routine version updates are reviewed changes. Install from lockfiles and fail if a check would rewrite them. Cache download stores keyed by platform/runtime/lock hash, not mutable project virtual environments, operator files or live credentials. Cache misses must work; cached state is not evidence of a successful check.
- Offline jobs receive no model/sandbox/tracing credentials and explicitly disable hosted tracing/live configuration. Marker exclusion is an additional gate, not the only network/cost boundary. Dependency installation may reach approved registries; the test phase must fail unexpected provider/external capability access. Keep deterministic scripted transports separate from live adapters.
- Evidence records commit, test/config/fixture versions, runtime/service/browser builds, scenario IDs, layer, observed status and oracle result. Retain bounded junit/failure logs and, where safe, browser screenshots/traces. Use synthetic fixtures; do not upload operator datasets, model prompts/private traces, tickets, secrets or local database/volume dumps. Redact before artifact upload, including failure paths; GitHub masking is not a sanitizer.
- Proposed retention is short and bounded, with exact days/size/log/job timeout/resource limits selected before workflow enablement. Do not invent performance budgets or a blanket coverage threshold without a measured baseline. Dependency advisory checks distinguish a scan failure from “zero vulnerabilities”; triage relevant findings with time-bounded reviewed exceptions rather than permanent suppression.

## Live capability remains separate

L3 provider/sandbox evaluation remains opt-in after its established capability, isolation, accounting and forecast prerequisites and separate live authorization. It is not a PR default, a merge-quality retry, a manual-dispatch loophole or a nightly schedule. Live evidence does not overwrite deterministic failures, and deterministic green does not claim inference quality or sandbox enforcement. Any future live workflow must require an explicit environment/credential/spend approval path; this packet does not create one.

## Implementation sequence and remaining gates

1. Record exact tools/limits and executable command contracts for the accepted job/stage/trust design.
2. Implement Stage A workflow and reusable local commands; verify fresh lock-only install, nonempty offline test selection, build/wheel smoke and aggregate failure/cancellation behavior. Preserve reported preexisting failures rather than weakening checks to get a badge.
3. Run an actual hosted baseline and inspect sanitized artifacts before enabling any required remote status. Local command success is not a hosted run.
4. Add Stage B jobs alongside their owning backend/frontend slices; prove scope promotion, service cleanup and negative scenarios. Preserve all existing runtime gates.

Planning closure does not execute these steps or authorize workflow implementation, remote changes or live calls. The actual build order remains standalone agent → storage → API → workers → checkpoints → backend integration → frontend → CI wiring, with focused checks used throughout development. The sequence above is internal to the CI implementation slice; it does not move that slice ahead of the agreed build order. Check the current source/evidence state before selecting the next unfinished implementation task; older milestone notes are not a current audit.

## Official-source basis

Reviewed 27 November 2026: [GitHub workflow syntax and job conditions](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax), [workflow concurrency](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency), [GitHub Actions security reference](https://docs.github.com/en/actions/reference/security/secure-use), and [uv lock/sync semantics](https://docs.astral.sh/uv/concepts/projects/sync/). Current documentation supports the proposed mechanics; it does not select this repository's pinned builds or prove hosted execution.
