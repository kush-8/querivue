# Standalone codebase recheck · 27 November 2026

**Substantial progress exists, but the current CLI integration is not ready.** This targeted review supersedes the earlier checkpoint's current-status conclusions where source has since changed. Historical test/probe results remain historical, not claims about the new implementation.

## Snapshot and verification

HEAD at review: `3accd5d4ce8d785a214956d19215c29a9daac4b7`. Since `bec805e`, the agent gained native graph/checkpoint modules, specialist/review integration, environment admission/sandbox scaffolding, CSV inspection/preparation, SQL changes and tests. Working-tree CLI/controller/test edits were active during the review; they were preserved. This is not a comprehensive semantic audit of the roughly ten thousand added source/test lines.

CRG matched HEAD and narrowed the changed areas. Its broad change analysis reached its 500-function cap; absence of a graph warning cannot establish coverage. Actual source and executions support the findings below.

- Full offline suite during the first inspected state: **9 failed, 1,031 passed, 10 skipped, 11 deselected, 2 reported warnings in 24.68s**. Command: `.venv/Scripts/python.exe -m pytest tests -m "not live and not redis" -q -rs -p no:cacheprovider`, with hosted tracing disabled.
- Initial CLI failures included help/version exit expectations and missing pytest fixture injection. Concurrent edits corrected those cases; do not carry them forward as current product defects.
- Latest focused CLI run after those edits: **5 failed, 9 passed, 1 reported warning in 0.62s** using `tests/integration/test_cli_1a.py -q --tb=line -p no:cacheprovider`. Import, preparation, accepted/rejected ask and status tests fail at the common CSV import prerequisite. Their failure count is not five independently demonstrated runtime defects.
- A focused import rerun also confirmed the model-conversion failure as the controller was being edited. The latest error requires `source_position` and a structured `requested_type`, and rejects `source_ordinal`/`sql_name` in the public column DTO.
- Isolated SQLite probes confirmed mixed schema admission and journal-mode mutation on rejection. No operator database was opened.

Ten skipped tests still identify unimplemented ingestion/archive/recovery/evaluation cases. Live and Redis cases were excluded. The warning/deprecation output includes model field/config deprecations and pytest-asyncio fixture-loop configuration. No live/provider call, service, package installation or production/test fix was performed by this review.

Final inspected SHA-256 prefixes: controller `fa916fdc5bd9ce89`, ledger `a3291a573df54c76`, CLI `cc1881a694fb0eaa`, CLI integration tests `0a5451eb4cbbeaad`. The earlier full-suite result is not asserted to describe this exact final working-tree snapshot. Another full suite is warranted after the active repairs stabilize.

## Findings

### P1 — CSV preview conversion violates the public model contract

Location: `agent/src/querivue_agent/ingestion/controller.py`, `_inspection_to_import_preview`, column construction around line 68 and selection construction around line 91.

A valid regional CSV fails the actual CLI import test before it can be prepared. Internal ingestion settings and public catalog DTOs have different shapes despite sharing similar names. The latest controller constructs the public column type with internal fields/string type values; its strict schema rejects them. Earlier intermediate edits also passed incompatible source/selection models. Convert fields and tagged source/type representations deliberately at this boundary, or use one approved public schema consistently; do not relax strict validation to hide the mismatch. Recheck the whole import→confirmation→prepare boundary, not only the class name being constructed.

### P1 — Preparation deletes its generated database before returning success

Location: `agent/src/querivue_agent/ingestion/controller.py:270–272`, then the success path at 278–291; producer `ingestion/preparation.py:69` and 100–118.

The controller prepares `prepared.duckdb` inside a `TemporaryDirectory`, exits that context and deletes it, then marks the attempt validated and returns `status: prepared`. The producer returns snapshot metadata with a synthetic artifact reference; the inspected path does not move/register the database into retained artifact storage before cleanup. Even once import conversion is fixed, the returned snapshot cannot be used as a durable prepared dataset through this path. Verify and retain/register the immutable bytes before releasing scratch space, and publish success only after the accepted authority transition. This finding is source-confirmed; a full successful CLI preparation was blocked by the earlier import failure, so no end-to-end success is claimed.

### P1 — Schema admission accepts conflicting version metadata

Location: `agent/src/querivue_agent/storage/ledger.py:38–50`.

The new guard correctly rejects a database containing only version 999, and its test now exercises that case. However, `fetchone()` checks only the first version row. An actual supported database with an additional version-999 row reopens successfully with `[1, 999]`. That mixed state is also the state produced by the previous initializer defect, so the new guard does not reject an already affected database. Validate the complete version metadata and supported shape before accepting the connection; do not use the first row as a compatibility decision.

### P2 — Rejected schemas are modified before the compatibility check

Location: `agent/src/querivue_agent/storage/ledger.py:27`, before the version check at 32–47.

On a disposable future-version database, the guard raised RuntimeError as intended, but its persistent journal mode changed from `delete` to `wal`. The opener still runs the mutating PRAGMA before deciding whether it may open that schema. Inspect compatibility first and verify the rejected database is preserved; the source comment “before any mutation” currently overstates the guarantee. Ensure error paths close connections too.

## Current boundary and next work

The prior claim that native graph files are absent is obsolete: `graph.py` and `runtime/checkpoints.py` now exist. Existence does not prove native saver/replay acceptance. Likewise, Docker/admission definitions are progress but do not prove isolation: the inspected execution controller still creates local directories and invokes host subprocesses, and its factory can select the older default manifest. Do not claim admitted generated execution until the exact boundary passes its required live environment checks. No live isolation experiment was run here.

Prioritize the shared CSV contract conversion and retained preparation/publication path for the active CLI vertical slice, while finishing the two ledger-admission gaps. Keep independent current edits intact. Then rerun focused real CLI/ledger tests, followed by the offline suite. Preserve the ten explicit unimplemented-test skips and outstanding Redis/environment/end-to-end gates in readiness reporting.
