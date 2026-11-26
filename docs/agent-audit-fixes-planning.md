# Standalone agent audit fixes

User authorized implementation of the eleven findings and failing tests on 26 November 2026. Work uses the existing approved standalone contracts; this task does not authorize provider calls, paid execution, new services or a phase-completion claim.

## Work and verification

1. Repair synchronous CLI entry, broken imports, false CLI success reports and portable test paths. Replace misleading acceptance claims with meaningful checks.
2. Implement durable authority guards and accounting, including replay, source/deadline fencing, receipts and lifecycle transitions. Verify transactional failures and concurrent reservations.
3. Enforce artifact ownership, validation/publication eligibility, dependency revocation and proof-gated cleanup. Bound staging reads.
4. Replace unsafe host execution with the approved isolated transport boundary. Unsupported/unverified environments must fail before execution; trusted fixture tests cannot certify isolation.
5. Integrate accounted model calls and real role handlers. Remove fabricated approval/success and enforce configuration and capability gates.
6. Repair canonical checkpoint persistence/restoration and no-TTL behavior, then integrate CLI orchestration and lifecycle operations against shared authority.
7. Run focused and full offline checks; review actual diffs, preserve live/Redis/environment verification gaps, update durable handoff and existing local indexes once at batch closure.

## Progress

- Baseline review: default suite 802 passed / 13 failed; the reported failures use fixed `/tmp` SQLite paths. Confirmed broken installed console entry, three import failures, cross-Project artifact access, canned reviewer approval and admission-only `ask`.
- First coding worker dispatched with bounded CLI/import/test ownership, required gpt-5.6-sol medium settings. Other existing documentation and local artifacts are unrelated and must be preserved.

## Constraints

Work directly on main. Supervisor handles docs, design, integration review and verification; fresh coding workers write source. Follow spec-driven development, not TDD. Do not weaken strict contracts or replace missing real behavior with a demo. Exact operational/provider/environment choices not yet approved remain disabled. No phase-end map refresh is due merely because a repair batch closes. Context percentage/manual compaction and Headroom instrumentation are unavailable; no enforcement/savings claim is made.
