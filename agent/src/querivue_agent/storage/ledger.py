"""SQLite ledger and deterministic transaction ownership."""

from __future__ import annotations

import contextlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class Ledger:
    """SQLite ledger with explicit short transactions and full durability."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    @classmethod
    def open(cls, path: Path) -> "Ledger":
        """Open a ledger at the given path, initializing schema if needed.

        Rejects databases with unsupported schema versions. Only version 1 is supported.
        """
        conn = sqlite3.connect(path)
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = FULL")
        conn.execute("PRAGMA busy_timeout = 1000")
        conn.row_factory = sqlite3.Row

        # Check existing schema version before any mutation
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version'"
        )
        if cursor.fetchone():
            # Database exists - check version
            version_row = conn.execute("SELECT version FROM schema_version").fetchone()
            if version_row is None:
                conn.close()
                raise RuntimeError("Database has schema_version table but no version row")
            existing_version = version_row[0]
            if existing_version != 1:
                conn.close()
                raise RuntimeError(
                    f"Unsupported schema version {existing_version}. "
                    f"Only version 1 is supported. No migration is implemented."
                )
            # Version 1 - database is compatible, no schema init needed
            return cls(conn)

        # No schema_version table - genuinely new database, initialize schema
        schema_path = Path(__file__).with_name("schema.sql")
        schema_sql = schema_path.read_text(encoding="utf-8")
        conn.executescript(schema_sql)
        conn.commit()

        return cls(conn)

    def transaction(self) -> contextlib.AbstractContextManager[sqlite3.Connection]:
        """Return a context manager for a short BEGIN IMMEDIATE transaction."""
        return _Transaction(self._conn)

    def close(self) -> None:
        """Close the ledger connection."""
        self._conn.close()


class _Transaction:
    """Short-lived BEGIN IMMEDIATE transaction context manager."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._in_transaction = False

    def __enter__(self) -> sqlite3.Connection:
        self._conn.execute("BEGIN IMMEDIATE")
        self._in_transaction = True
        return self._conn

    def __exit__(self, exc_type: type | None, exc_val: BaseException | None, exc_tb: Any) -> None:
        if self._in_transaction:
            if exc_type is None:
                self._conn.commit()
            else:
                self._conn.rollback()
            self._in_transaction = False


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _json_dumps(obj: Any) -> str:
    return json.dumps(obj, separators=(",", ":"), sort_keys=True)


def _json_loads(text: str | None) -> Any:
    if text is None:
        return None
    return json.loads(text)


# Convenience methods for common ledger operations
class LedgerOps:
    """High-level ledger operations."""

    def __init__(self, ledger: Ledger) -> None:
        self._ledger = ledger

    # Projects
    def create_project(self, project_id: str) -> None:
        with self._ledger.transaction() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO projects (project_id, created_at) VALUES (?, ?)",
                (project_id, _now_iso()),
            )

    # Chats
    def create_chat(self, chat_id: str, project_id: str) -> None:
        with self._ledger.transaction() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO chats (chat_id, project_id, created_at) VALUES (?, ?, ?)",
                (chat_id, project_id, _now_iso()),
            )

    # Datasets
    def create_dataset(
        self,
        dataset_id: str,
        project_id: str,
        upload_ref: str,
        upload_hash: str,
    ) -> None:
        with self._ledger.transaction() as conn:
            conn.execute(
                """INSERT INTO datasets
                   (dataset_id, project_id, upload_ref, upload_hash, status, attempt_number, created_at, updated_at)
                   VALUES (?, ?, ?, ?, 'staged', 1, ?, ?)""",
                (dataset_id, project_id, upload_ref, upload_hash, _now_iso(), _now_iso()),
            )

    def get_dataset(self, dataset_id: str) -> dict | None:
        with self._ledger.transaction() as conn:
            row = conn.execute(
                "SELECT * FROM datasets WHERE dataset_id = ?", (dataset_id,)
            ).fetchone()
            return dict(row) if row else None

    def list_datasets(self, project_id: str) -> list[dict]:
        with self._ledger.transaction() as conn:
            rows = conn.execute(
                "SELECT * FROM datasets WHERE project_id = ? ORDER BY created_at", (project_id,)
            ).fetchall()
            return [dict(row) for row in rows]

    def update_dataset_status(self, dataset_id: str, status: str, **extra: Any) -> None:
        sets = ["status = ?", "updated_at = ?"]
        vals = [status, _now_iso()]
        for k, v in extra.items():
            sets.append(f"{k} = ?")
            vals.append(_json_dumps(v) if isinstance(v, (dict, list)) else v)
        vals.append(dataset_id)
        with self._ledger.transaction() as conn:
            conn.execute(f"UPDATE datasets SET {', '.join(sets)} WHERE dataset_id = ?", vals)

    # Dataset snapshots
    def create_dataset_snapshot(
        self,
        snapshot_id: str,
        dataset_id: str,
        catalog_json: str,
    ) -> None:
        with self._ledger.transaction() as conn:
            conn.execute(
                """INSERT INTO dataset_snapshots
                   (snapshot_id, dataset_id, catalog_json, created_at)
                   VALUES (?, ?, ?, ?)""",
                (snapshot_id, dataset_id, catalog_json, _now_iso()),
            )

    def update_snapshot_prepared(
        self, snapshot_id: str, prepared_ref: str, prepared_hash: str, publication_ref: str
    ) -> None:
        with self._ledger.transaction() as conn:
            conn.execute(
                """UPDATE dataset_snapshots
                   SET prepared_ref = ?, prepared_hash = ?, publication_ref = ?
                   WHERE snapshot_id = ?""",
                (prepared_ref, prepared_hash, publication_ref, snapshot_id),
            )

    # Runs
    def create_run(
        self,
        run_id: str,
        project_id: str,
        chat_id: str,
        question: str,
        scope_hash: str,
        eligible_dataset_ids: list[str],
        budget_json: str,
        configuration_hash: str,
        deadline: str,
    ) -> None:
        with self._ledger.transaction() as conn:
            conn.execute(
                """INSERT INTO runs
                   (run_id, project_id, chat_id, question, scope_hash, eligible_dataset_ids,
                    status, budget_json, configuration_hash, deadline, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, 'admitted', ?, ?, ?, ?, ?)""",
                (
                    run_id,
                    project_id,
                    chat_id,
                    question,
                    scope_hash,
                    _json_dumps(eligible_dataset_ids),
                    budget_json,
                    configuration_hash,
                    deadline,
                    _now_iso(),
                    _now_iso(),
                ),
            )

    def get_run(self, run_id: str) -> dict | None:
        with self._ledger.transaction() as conn:
            row = conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
            return dict(row) if row else None

    def update_run_status(self, run_id: str, status: str, **extra: Any) -> None:
        sets = ["status = ?", "updated_at = ?"]
        vals = [status, _now_iso()]
        for k, v in extra.items():
            sets.append(f"{k} = ?")
            vals.append(_json_dumps(v) if isinstance(v, (dict, list)) else v)
        vals.append(run_id)
        with self._ledger.transaction() as conn:
            conn.execute(f"UPDATE runs SET {', '.join(sets)} WHERE run_id = ?", vals)

    def claim_run_ownership(
        self, run_id: str, owner_id: str, generation: int, lease_expires_at: str
    ) -> bool:
        with self._ledger.transaction() as conn:
            # Check current ownership
            current = conn.execute(
                "SELECT owner_id, generation FROM runs WHERE run_id = ?", (run_id,)
            ).fetchone()
            if current:
                # If the existing generation is >= requested generation, reject
                if current["generation"] >= generation:
                    return False
                # Allow takeover with higher generation regardless of owner_id

            conn.execute(
                """UPDATE runs SET owner_id = ?, generation = ?, updated_at = ? WHERE run_id = ?""",
                (owner_id, generation, _now_iso(), run_id),
            )
            conn.execute(
                """INSERT INTO run_owners (run_id, owner_id, generation, lease_expires_at, claimed_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (run_id, owner_id, generation, lease_expires_at, _now_iso()),
            )
            return True

    def renew_lease(self, run_id: str, owner_id: str, generation: int, lease_expires_at: str) -> bool:
        with self._ledger.transaction() as conn:
            current = conn.execute(
                "SELECT owner_id, generation FROM runs WHERE run_id = ?", (run_id,)
            ).fetchone()
            if not current or current["owner_id"] != owner_id or current["generation"] != generation:
                return False

            conn.execute(
                """UPDATE runs SET updated_at = ? WHERE run_id = ?""", (_now_iso(), run_id)
            )
            conn.execute(
                """INSERT OR REPLACE INTO run_owners (run_id, owner_id, generation, lease_expires_at, claimed_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (run_id, owner_id, generation, lease_expires_at, _now_iso()),
            )
            return True

    # Payloads
    def store_payload(
        self, payload_id: str, family: str, version: int, canonical_bytes: bytes, digest: str
    ) -> None:
        with self._ledger.transaction() as conn:
            conn.execute(
                """INSERT INTO payloads (payload_id, family, version, canonical_bytes, digest, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (payload_id, family, version, canonical_bytes, digest, _now_iso()),
            )

    def get_payload_by_digest(self, digest: str) -> dict | None:
        with self._ledger.transaction() as conn:
            row = conn.execute(
                "SELECT * FROM payloads WHERE digest = ?", (digest,)
            ).fetchone()
            return dict(row) if row else None

    def add_dependency(self, payload_id: str, dataset_id: str, snapshot_id: str) -> None:
        with self._ledger.transaction() as conn:
            conn.execute(
                """INSERT OR IGNORE INTO dependencies (payload_id, dataset_id, snapshot_id)
                   VALUES (?, ?, ?)""",
                (payload_id, dataset_id, snapshot_id),
            )

    # Intakes
    def create_intake(
        self,
        intake_id: str,
        submission_key: str,
        project_id: str,
        input_json: str,
        original_hash: str,
        fence_json: str,
        expires_at: str,
    ) -> None:
        with self._ledger.transaction() as conn:
            conn.execute(
                """INSERT INTO intakes
                   (intake_id, submission_key, project_id, input_json, original_hash,
                    fence_json, status, invocation_ids, created_at, expires_at)
                   VALUES (?, ?, ?, ?, ?, ?, 'pending', '[]', ?, ?)""",
                (intake_id, submission_key, project_id, input_json, original_hash, fence_json, _now_iso(), expires_at),
            )

    def get_intake(self, intake_id: str) -> dict | None:
        with self._ledger.transaction() as conn:
            row = conn.execute("SELECT * FROM intakes WHERE intake_id = ?", (intake_id,)).fetchone()
            return dict(row) if row else None

    def update_intake(
        self,
        intake_id: str,
        status: str,
        entry_question_id: str | None = None,
        outcome_json: str | None = None,
        invocation_ids: list[str] | None = None,
        charge_ref: str | None = None,
    ) -> None:
        sets = ["status = ?"]
        vals = [status]
        if entry_question_id is not None:
            sets.append("entry_question_id = ?")
            vals.append(entry_question_id)
        if outcome_json is not None:
            sets.append("outcome_json = ?")
            vals.append(outcome_json)
        if invocation_ids is not None:
            sets.append("invocation_ids = ?")
            vals.append(_json_dumps(invocation_ids))
        if charge_ref is not None:
            sets.append("charge_ref = ?")
            vals.append(charge_ref)
        vals.append(intake_id)
        with self._ledger.transaction() as conn:
            conn.execute(f"UPDATE intakes SET {', '.join(sets)} WHERE intake_id = ?", vals)

    # Intake admissions
    def create_intake_admission(
        self,
        admission_id: str,
        intake_id: str,
        submission_hash: str,
        scope_json: str,
        assessment_json: str,
        context_hash: str,
        configuration_hash: str,
        policy_version: str,
        target_json: str,
        fence_json: str,
    ) -> None:
        with self._ledger.transaction() as conn:
            conn.execute(
                """INSERT INTO intake_admissions
                   (admission_id, intake_id, submission_hash, scope_json, assessment_json,
                    context_hash, configuration_hash, policy_version, target_json, fence_json, accepted_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    admission_id,
                    intake_id,
                    submission_hash,
                    scope_json,
                    assessment_json,
                    context_hash,
                    configuration_hash,
                    policy_version,
                    target_json,
                    fence_json,
                    _now_iso(),
                ),
            )

    # Admission receipts
    def create_admission_receipt(
        self,
        receipt_id: str,
        admission_id: str,
        intake_id: str,
        run_id: str,
        scope_json: str,
        cutoff_sequence: int,
        budget_json: str,
        configuration_hash: str,
    ) -> None:
        with self._ledger.transaction() as conn:
            conn.execute(
                """INSERT INTO admission_receipts
                   (receipt_id, admission_id, intake_id, run_id, scope_json, cutoff_sequence,
                    budget_json, configuration_hash, accepted_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    receipt_id,
                    admission_id,
                    intake_id,
                    run_id,
                    scope_json,
                    cutoff_sequence,
                    budget_json,
                    configuration_hash,
                    _now_iso(),
                ),
            )

    # Tasks
    def create_task(self, task_id: str, run_id: str, task_json: str) -> None:
        with self._ledger.transaction() as conn:
            conn.execute(
                "INSERT INTO tasks (task_id, run_id, task_json, status, created_at) VALUES (?, ?, ?, 'pending', ?)",
                (task_id, run_id, task_json, _now_iso()),
            )

    def update_task_status(self, task_id: str, status: str) -> None:
        with self._ledger.transaction() as conn:
            conn.execute("UPDATE tasks SET status = ? WHERE task_id = ?", (status, task_id))

    # Actions
    def create_action(
        self,
        action_id: str,
        task_id: str,
        run_id: str,
        action_json: str,
        attempt: int = 1,
        execution_generation: int = 1,
    ) -> None:
        with self._ledger.transaction() as conn:
            conn.execute(
                """INSERT INTO actions
                   (action_id, task_id, run_id, action_json, status, attempt, execution_generation, created_at, updated_at)
                   VALUES (?, ?, ?, ?, 'pending', ?, ?, ?, ?)""",
                (action_id, task_id, run_id, action_json, attempt, execution_generation, _now_iso(), _now_iso()),
            )

    def update_action_status(
        self, action_id: str, status: str, attempt: int | None = None, execution_generation: int | None = None
    ) -> None:
        sets = ["status = ?", "updated_at = ?"]
        vals = [status, _now_iso()]
        if attempt is not None:
            sets.append("attempt = ?")
            vals.append(attempt)
        if execution_generation is not None:
            sets.append("execution_generation = ?")
            vals.append(execution_generation)
        vals.append(action_id)
        with self._ledger.transaction() as conn:
            conn.execute(f"UPDATE actions SET {', '.join(sets)} WHERE action_id = ?", vals)

    # Outcomes
    def record_outcome(
        self,
        outcome_id: str,
        action_id: str,
        run_id: str,
        attempt: int,
        execution_generation: int,
        outcome_json: str,
    ) -> None:
        with self._ledger.transaction() as conn:
            conn.execute(
                """INSERT INTO outcomes
                   (outcome_id, action_id, run_id, attempt, execution_generation, outcome_json, recorded_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (outcome_id, action_id, run_id, attempt, execution_generation, outcome_json, _now_iso()),
            )

    def get_outcome(
        self, action_id: str, attempt: int, execution_generation: int
    ) -> dict | None:
        with self._ledger.transaction() as conn:
            row = conn.execute(
                """SELECT * FROM outcomes
                   WHERE action_id = ? AND attempt = ? AND execution_generation = ?""",
                (action_id, attempt, execution_generation),
            ).fetchone()
            return dict(row) if row else None

    # Invocations
    def create_invocation(
        self,
        invocation_id: str,
        run_id: str | None,
        intake_id: str | None,
        role: str,
        attempt: int,
        invocation_key: str,
        packet_hash: str,
        request_json: str,
    ) -> None:
        with self._ledger.transaction() as conn:
            conn.execute(
                """INSERT INTO invocations
                   (invocation_id, run_id, intake_id, role, attempt, invocation_key,
                    packet_hash, request_json, status, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'reserved', ?)""",
                (invocation_id, run_id, intake_id, role, attempt, invocation_key, packet_hash, request_json, _now_iso()),
            )

    def complete_invocation(
        self,
        invocation_id: str,
        status: str,
        completion_json: str | None = None,
    ) -> None:
        sets = ["status = ?", "completed_at = ?"]
        vals = [status, _now_iso()]
        if completion_json is not None:
            sets.append("completion_json = ?")
            vals.append(completion_json)
        vals.append(invocation_id)
        with self._ledger.transaction() as conn:
            conn.execute(f"UPDATE invocations SET {', '.join(sets)} WHERE invocation_id = ?", vals)

    # Model reservations
    def create_model_reservation(
        self,
        reservation_id: str,
        invocation_id: str,
        max_input_tokens: int,
        max_output_tokens: int,
        cost_usd: str,
        expires_at: str,
    ) -> None:
        with self._ledger.transaction() as conn:
            conn.execute(
                """INSERT INTO model_reservations
                   (reservation_id, invocation_id, max_input_tokens, max_output_tokens, cost_usd, admitted_at, expires_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (reservation_id, invocation_id, max_input_tokens, max_output_tokens, cost_usd, _now_iso(), expires_at),
            )

    # Model completions
    def record_model_completion(
        self,
        completion_id: str,
        reservation_id: str,
        request_hash: str,
        status: str,
        response_ref: str | None,
        provider_request_id: str | None,
        observed_model_revision: str | None,
        stop_reason: str | None,
        usage_json: str,
        error_ref: str | None,
    ) -> None:
        with self._ledger.transaction() as conn:
            conn.execute(
                """INSERT INTO model_completions
                   (completion_id, reservation_id, request_hash, status, response_ref, provider_request_id,
                    observed_model_revision, stop_reason, usage_json, error_ref, recorded_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    completion_id,
                    reservation_id,
                    request_hash,
                    status,
                    response_ref,
                    provider_request_id,
                    observed_model_revision,
                    stop_reason,
                    usage_json,
                    error_ref,
                    _now_iso(),
                ),
            )

    # Operations
    def create_operation(
        self,
        operation_id: str,
        run_id: str | None,
        task_id: str | None,
        action_id: str | None,
        attempt: int,
        execution_generation: int,
        invocation_key: str,
        request_hash: str,
        kind: str,
        request_json: str,
        input_artifacts_json: str,
        deadline: str,
        environment_manifest_id: str,
    ) -> None:
        with self._ledger.transaction() as conn:
            conn.execute(
                """INSERT INTO operations
                   (operation_id, run_id, task_id, action_id, attempt, execution_generation,
                    invocation_key, request_hash, kind, request_json, input_artifacts_json, deadline,
                    environment_manifest_id, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    operation_id,
                    run_id,
                    task_id,
                    action_id,
                    attempt,
                    execution_generation,
                    invocation_key,
                    request_hash,
                    kind,
                    request_json,
                    input_artifacts_json,
                    deadline,
                    environment_manifest_id,
                    _now_iso(),
                ),
            )

    # Operation outcomes
    def record_operation_outcome(
        self,
        outcome_id: str,
        operation_id: str,
        attempt: int,
        execution_generation: int,
        request_hash: str,
        status: str,
        evidence_json: str,
        charts_json: str,
        diagnostics_json: str,
    ) -> None:
        with self._ledger.transaction() as conn:
            conn.execute(
                """INSERT INTO operation_outcomes
                   (outcome_id, operation_id, attempt, execution_generation, request_hash,
                    status, evidence_json, charts_json, diagnostics_json, completed_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    outcome_id,
                    operation_id,
                    attempt,
                    execution_generation,
                    request_hash,
                    status,
                    evidence_json,
                    charts_json,
                    diagnostics_json,
                    _now_iso(),
                ),
            )

    def get_operation_outcome(
        self, operation_id: str, attempt: int, execution_generation: int
    ) -> dict | None:
        with self._ledger.transaction() as conn:
            row = conn.execute(
                """SELECT * FROM operation_outcomes
                   WHERE operation_id = ? AND attempt = ? AND execution_generation = ?""",
                (operation_id, attempt, execution_generation),
            ).fetchone()
            return dict(row) if row else None

    # Drafts
    def create_draft(
        self,
        draft_id: str,
        run_id: str,
        action_id: str,
        draft_json: str,
        content_hash: str,
        input_packet_hash: str,
        dependencies_json: str,
        source_input_hash: str,
        completeness: str,
        rendering_policy_version: str,
        originating_invocation_id: str,
    ) -> None:
        with self._ledger.transaction() as conn:
            conn.execute(
                """INSERT INTO drafts
                   (draft_id, run_id, action_id, draft_json, content_hash, input_packet_hash,
                    dependencies_json, source_input_hash, completeness, rendering_policy_version,
                    originating_invocation_id, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    draft_id,
                    run_id,
                    action_id,
                    draft_json,
                    content_hash,
                    input_packet_hash,
                    dependencies_json,
                    source_input_hash,
                    completeness,
                    rendering_policy_version,
                    originating_invocation_id,
                    _now_iso(),
                ),
            )

    # Reviews
    def create_review(
        self,
        review_id: str,
        run_id: str,
        draft_id: str,
        review_pass: int,
        assessment_json: str,
        verdict: str,
        draft_content_hash: str,
        draft_input_packet_hash: str,
        rendering_policy_version: str,
        deadline: str,
    ) -> None:
        with self._ledger.transaction() as conn:
            conn.execute(
                """INSERT INTO reviews
                   (review_id, run_id, draft_id, review_pass, assessment_json, verdict,
                    draft_content_hash, draft_input_packet_hash, rendering_policy_version, reserved_at, deadline, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    review_id,
                    run_id,
                    draft_id,
                    review_pass,
                    assessment_json,
                    verdict,
                    draft_content_hash,
                    draft_input_packet_hash,
                    rendering_policy_version,
                    _now_iso(),
                    deadline,
                    _now_iso(),
                ),
            )

    def get_review(self, run_id: str, review_pass: int) -> dict | None:
        with self._ledger.transaction() as conn:
            row = conn.execute(
                "SELECT * FROM reviews WHERE run_id = ? AND review_pass = ?", (run_id, review_pass)
            ).fetchone()
            return dict(row) if row else None

    # Review reservations
    def create_review_reservation(
        self,
        reservation_id: str,
        review_id: str,
        max_physical_requests: int,
        max_input_tokens: int,
        max_output_tokens: int,
        cost_usd: str,
        deadline: str,
    ) -> None:
        with self._ledger.transaction() as conn:
            conn.execute(
                """INSERT INTO review_reservations
                   (reservation_id, review_id, max_physical_requests, max_input_tokens, max_output_tokens, cost_usd, reserved_at, deadline)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    reservation_id,
                    review_id,
                    max_physical_requests,
                    max_input_tokens,
                    max_output_tokens,
                    cost_usd,
                    _now_iso(),
                    deadline,
                ),
            )

    # Budget snapshots
    def record_budget_snapshot(self, snapshot_id: str, run_id: str, budget_json: str) -> None:
        with self._ledger.transaction() as conn:
            conn.execute(
                "INSERT INTO budget_snapshots (snapshot_id, run_id, budget_json, recorded_at) VALUES (?, ?, ?, ?)",
                (snapshot_id, run_id, budget_json, _now_iso()),
            )

    # Progress accounting
    def record_progress(
        self,
        accounting_id: str,
        run_id: str,
        action_id: str | None,
        invocation_id: str | None,
        operation_id: str | None,
        counter_name: str,
        counter_value: int,
    ) -> None:
        with self._ledger.transaction() as conn:
            conn.execute(
                """INSERT INTO progress_accounting
                   (accounting_id, run_id, action_id, invocation_id, operation_id, counter_name, counter_value, recorded_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (accounting_id, run_id, action_id, invocation_id, operation_id, counter_name, counter_value, _now_iso()),
            )

    # Final results
    def record_final_result(
        self,
        result_id: str,
        run_id: str,
        route: str,
        candidate_id: str,
        content_hash: str,
        completeness: str,
        rendered_text: str,
        rendering_policy_version: str,
        evidence_ids: list[str],
        chart_artifact_ids: list[str],
        dependencies_json: str,
        review_status: str,
    ) -> None:
        with self._ledger.transaction() as conn:
            conn.execute(
                """INSERT INTO final_results
                   (result_id, run_id, route, candidate_id, content_hash, completeness,
                    rendered_text, rendering_policy_version, evidence_ids, chart_artifact_ids,
                    dependencies_json, review_status, published_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    result_id,
                    run_id,
                    route,
                    candidate_id,
                    content_hash,
                    completeness,
                    rendered_text,
                    rendering_policy_version,
                    _json_dumps(evidence_ids),
                    _json_dumps(chart_artifact_ids),
                    dependencies_json,
                    review_status,
                    _now_iso(),
                ),
            )

    # Deletion receipts
    def record_deletion_receipt(
        self,
        deletion_id: str,
        project_id: str,
        dataset_id: str,
        tombstone_revision: int,
        invalidated_run_ids: list[str],
        removed_result_ids: list[str],
        deferred_artifact_ids: list[str],
        retirement_pending_incarnation_ids: list[str],
    ) -> None:
        with self._ledger.transaction() as conn:
            conn.execute(
                """INSERT INTO deletion_receipts
                   (deletion_id, project_id, dataset_id, tombstone_revision, invalidated_run_ids,
                    removed_result_ids, deferred_artifact_ids, retirement_pending_incarnation_ids, committed_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    deletion_id,
                    project_id,
                    dataset_id,
                    tombstone_revision,
                    _json_dumps(invalidated_run_ids),
                    _json_dumps(removed_result_ids),
                    _json_dumps(deferred_artifact_ids),
                    _json_dumps(retirement_pending_incarnation_ids),
                    _now_iso(),
                ),
            )

    # Queue receipts
    def record_queue_receipt(
        self,
        receipt_id: str,
        run_id: str,
        invocation_id: str,
        proposal_hash: str,
        decision_type: str,
        previous_queue_revision: int,
        queue_revision: int,
        run_revision: int,
        task_mapping: dict[str, str],
        action_mapping: dict[str, str],
        tasks: list[dict],
        withdrawn_task_ids: list[str],
    ) -> None:
        with self._ledger.transaction() as conn:
            conn.execute(
                """INSERT INTO queue_receipts
                   (receipt_id, run_id, invocation_id, proposal_hash, decision_type,
                    previous_queue_revision, queue_revision, run_revision,
                    task_mapping_json, action_mapping_json, tasks_json, withdrawn_task_ids_json, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    receipt_id,
                    run_id,
                    invocation_id,
                    proposal_hash,
                    decision_type,
                    previous_queue_revision,
                    queue_revision,
                    run_revision,
                    _json_dumps(task_mapping),
                    _json_dumps(action_mapping),
                    _json_dumps(tasks),
                    _json_dumps(withdrawn_task_ids),
                    _now_iso(),
                ),
            )

    # Resume receipts
    def record_resume_receipt(
        self,
        resume_id: str,
        run_id: str,
        question_id: str,
        reply_id: str,
        entry_intake_id: str,
        run_revision: int,
        owner_generation: int,
        original_deadline: str,
        scope_json: str,
    ) -> None:
        with self._ledger.transaction() as conn:
            conn.execute(
                """INSERT INTO resume_receipts
                   (resume_id, run_id, question_id, reply_id, entry_intake_id,
                    run_revision, owner_generation, accepted_at, original_deadline, scope_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    resume_id,
                    run_id,
                    question_id,
                    reply_id,
                    entry_intake_id,
                    run_revision,
                    owner_generation,
                    _now_iso(),
                    original_deadline,
                    scope_json,
                ),
            )

    # Sandbox tickets
    def create_sandbox_ticket(
        self,
        ticket_id: str,
        run_id: str,
        sandbox_id: str,
        incarnation_id: str,
        action_id: str,
        attempt: int,
        generation: int,
        environment_manifest_id: str,
        expires_at: str,
    ) -> None:
        with self._ledger.transaction() as conn:
            conn.execute(
                """INSERT INTO sandbox_tickets
                   (ticket_id, run_id, sandbox_id, incarnation_id, action_id, attempt, generation,
                    environment_manifest_id, state, created_at, expires_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'prepared', ?, ?)""",
                (
                    ticket_id,
                    run_id,
                    sandbox_id,
                    incarnation_id,
                    action_id,
                    attempt,
                    generation,
                    environment_manifest_id,
                    _now_iso(),
                    expires_at,
                ),
            )

    def update_sandbox_ticket(
        self, ticket_id: str, state: str, command_id: str | None = None, operation_id: str | None = None
    ) -> None:
        sets = ["state = ?"]
        vals = [state]
        if command_id is not None:
            sets.append("command_id = ?")
            vals.append(command_id)
        if operation_id is not None:
            sets.append("operation_id = ?")
            vals.append(operation_id)
        vals.append(ticket_id)
        with self._ledger.transaction() as conn:
            conn.execute(f"UPDATE sandbox_tickets SET {', '.join(sets)} WHERE ticket_id = ?", vals)

    # Retirement proofs
    def record_retirement_proof(
        self,
        retirement_id: str,
        sandbox_id: str,
        incarnation_id: str,
        method: str,
        proof_ref: str,
        environment_manifest_id: str,
    ) -> None:
        with self._ledger.transaction() as conn:
            conn.execute(
                """INSERT INTO retirement_proofs
                   (retirement_id, sandbox_id, incarnation_id, confirmed_at, method, process_tree_terminated, proof_ref, environment_manifest_id)
                   VALUES (?, ?, ?, ?, ?, 1, ?, ?)""",
                (retirement_id, sandbox_id, incarnation_id, _now_iso(), method, proof_ref, environment_manifest_id),
            )

    # Preparation attempts
    def create_preparation_attempt(
        self,
        attempt_id: str,
        dataset_id: str,
        attempt_number: int,
        settings_json: str,
        settings_hash: str,
        upload_ref: str,
        upload_hash: str,
        owner_generation: int,
        deadline: str,
    ) -> None:
        with self._ledger.transaction() as conn:
            conn.execute(
                """INSERT INTO preparation_attempts
                   (attempt_id, dataset_id, attempt_number, settings_json, settings_hash,
                    upload_ref, upload_hash, owner_generation, phase, retirement_state, deadline, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'staged', 'not_started', ?, ?, ?)""",
                (attempt_id, dataset_id, attempt_number, settings_json, settings_hash,
                 upload_ref, upload_hash, owner_generation, deadline, _now_iso(), _now_iso()),
            )

    def update_preparation_attempt(
        self,
        attempt_id: str,
        phase: str | None = None,
        environment_manifest_id: str | None = None,
        incarnation_id: str | None = None,
        retirement_state: str | None = None,
        limits_profile: str | None = None,
        diagnostic_ref: str | None = None,
        candidate_ref: str | None = None,
        publication_ref: str | None = None,
    ) -> None:
        sets = ["updated_at = ?"]
        vals = [_now_iso()]
        if phase is not None:
            sets.append("phase = ?")
            vals.append(phase)
        if environment_manifest_id is not None:
            sets.append("environment_manifest_id = ?")
            vals.append(environment_manifest_id)
        if incarnation_id is not None:
            sets.append("incarnation_id = ?")
            vals.append(incarnation_id)
        if retirement_state is not None:
            sets.append("retirement_state = ?")
            vals.append(retirement_state)
        if limits_profile is not None:
            sets.append("limits_profile = ?")
            vals.append(limits_profile)
        if diagnostic_ref is not None:
            sets.append("diagnostic_ref = ?")
            vals.append(diagnostic_ref)
        if candidate_ref is not None:
            sets.append("candidate_ref = ?")
            vals.append(candidate_ref)
        if publication_ref is not None:
            sets.append("publication_ref = ?")
            vals.append(publication_ref)
        vals.append(attempt_id)
        with self._ledger.transaction() as conn:
            conn.execute(f"UPDATE preparation_attempts SET {', '.join(sets)} WHERE attempt_id = ?", vals)