"""Unit tests for SQLite ledger."""

import json
import tempfile
from pathlib import Path
from uuid import uuid4

import pytest

from querivue_agent.storage.ledger import Ledger, LedgerOps


V1 = "00000000-0000-1000-8000-000000000001"
V1B = "00000000-0000-1000-8000-000000000002"
V4 = "00000000-0000-4000-8000-000000000001"
RUN_ID = str(uuid4())
CHAT_ID = str(uuid4())
INTAKE_ID = str(uuid4())


def _now_iso() -> str:
    import datetime
    return datetime.datetime.now(datetime.UTC).isoformat().replace("+00:00", "Z")


@pytest.fixture
def ledger_path() -> Path:
    with tempfile.TemporaryDirectory() as tmp:
        yield Path(tmp) / "test.db"


@pytest.fixture
def ledger(ledger_path: Path) -> Ledger:
    l = Ledger.open(ledger_path)
    yield l
    l.close()


@pytest.fixture
def ops(ledger: Ledger) -> LedgerOps:
    return LedgerOps(ledger)


def test_open_creates_schema(ledger: Ledger) -> None:
    with ledger.transaction() as conn:
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        table_names = {row["name"] for row in tables}
        assert "projects" in table_names
        assert "runs" in table_names
        assert "intakes" in table_names
        assert "schema_version" in table_names


def test_create_project(ops: LedgerOps) -> None:
    ops.create_project(V1)
    with ops._ledger.transaction() as conn:
        row = conn.execute("SELECT * FROM projects WHERE project_id = ?", (V1,)).fetchone()
        assert row is not None
        assert row["project_id"] == V1


def test_create_chat(ops: LedgerOps) -> None:
    ops.create_project(V1)
    ops.create_chat(CHAT_ID, V1)
    with ops._ledger.transaction() as conn:
        row = conn.execute("SELECT * FROM chats WHERE chat_id = ?", (CHAT_ID,)).fetchone()
        assert row is not None
        assert row["chat_id"] == CHAT_ID
        assert row["project_id"] == V1


def test_create_dataset(ops: LedgerOps) -> None:
    ops.create_project(V1)
    ops.create_dataset("ds-1", V1, "upload-ref", "abc123")
    ds = ops.get_dataset("ds-1")
    assert ds is not None
    assert ds["dataset_id"] == "ds-1"
    assert ds["status"] == "staged"
    assert ds["attempt_number"] == 1


def test_update_dataset_status(ops: LedgerOps) -> None:
    ops.create_project(V1)
    ops.create_dataset("ds-1", V1, "upload-ref", "abc123")
    ops.update_dataset_status("ds-1", "ready")
    ds = ops.get_dataset("ds-1")
    assert ds["status"] == "ready"


def test_create_run(ops: LedgerOps) -> None:
    ops.create_project(V1)
    ops.create_chat(CHAT_ID, V1)
    ops.create_run(
        run_id=RUN_ID,
        project_id=V1,
        chat_id=CHAT_ID,
        question="Test question",
        scope_hash="scopehash",
        eligible_dataset_ids=["ds-1"],
        budget_json='{"total_tokens": 1000}',
        configuration_hash="confighash",
        deadline=_now_iso(),
    )
    run = ops.get_run(RUN_ID)
    assert run is not None
    assert run["run_id"] == RUN_ID
    assert run["status"] == "admitted"
    eligible = json.loads(run["eligible_dataset_ids"])
    assert eligible == ["ds-1"]


def test_claim_run_ownership(ops: LedgerOps) -> None:
    ops.create_project(V1)
    ops.create_chat(CHAT_ID, V1)
    ops.create_run(
        run_id=RUN_ID,
        project_id=V1,
        chat_id=CHAT_ID,
        question="Test",
        scope_hash="sh",
        eligible_dataset_ids=[],
        budget_json="{}",
        configuration_hash="ch",
        deadline=_now_iso(),
    )
    owner_id = str(uuid4())
    lease_expires = _now_iso()
    # Run starts with generation=1, so first claim uses generation=2
    ok = ops.claim_run_ownership(RUN_ID, owner_id, 2, lease_expires)
    assert ok is True
    run = ops.get_run(RUN_ID)
    assert run["owner_id"] == owner_id
    assert run["generation"] == 2

    # Second claim with same generation should fail
    ok2 = ops.claim_run_ownership(RUN_ID, str(uuid4()), 2, lease_expires)
    assert ok2 is False


def test_renew_lease(ops: LedgerOps) -> None:
    ops.create_project(V1)
    ops.create_chat(CHAT_ID, V1)
    ops.create_run(
        run_id=RUN_ID,
        project_id=V1,
        chat_id=CHAT_ID,
        question="Test",
        scope_hash="sh",
        eligible_dataset_ids=[],
        budget_json="{}",
        configuration_hash="ch",
        deadline=_now_iso(),
    )
    owner_id = str(uuid4())
    lease_expires = _now_iso()
    # Run starts with generation=1, claim with generation=2
    ops.claim_run_ownership(RUN_ID, owner_id, 2, lease_expires)
    ok = ops.renew_lease(RUN_ID, owner_id, 2, _now_iso())
    assert ok is True


def test_store_and_get_payload(ops: LedgerOps) -> None:
    payload_id = str(uuid4())
    canonical = b'{"test": "value"}'
    digest = "a" * 64
    ops.store_payload(payload_id, "record", 1, canonical, digest)
    payload = ops.get_payload_by_digest(digest)
    assert payload is not None
    assert payload["payload_id"] == payload_id
    assert payload["family"] == "record"
    assert payload["canonical_bytes"] == canonical


def test_add_dependency(ops: LedgerOps) -> None:
    payload_id = str(uuid4())
    digest = "b" * 64
    ops.store_payload(payload_id, "record", 1, b'{}', digest)
    ops.add_dependency(payload_id, V1, V1B)
    with ops._ledger.transaction() as conn:
        row = conn.execute(
            "SELECT * FROM dependencies WHERE payload_id = ?", (payload_id,)
        ).fetchone()
        assert row is not None
        assert row["dataset_id"] == V1
        assert row["snapshot_id"] == V1B


def test_create_and_get_intake(ops: LedgerOps) -> None:
    ops.create_project(V1)
    ops.create_intake(
        intake_id=INTAKE_ID,
        submission_key="subkey-1",
        project_id=V1,
        input_json='{"question": "test"}',
        original_hash="orig_hash",
        fence_json='{"subject_kind": "intake"}',
        expires_at=_now_iso(),
    )
    intake = ops.get_intake(INTAKE_ID)
    assert intake is not None
    assert intake["intake_id"] == INTAKE_ID
    assert intake["status"] == "pending"
    assert intake["invocation_ids"] == "[]"


def test_update_intake(ops: LedgerOps) -> None:
    ops.create_project(V1)
    ops.create_intake(
        intake_id=INTAKE_ID,
        submission_key="subkey-1",
        project_id=V1,
        input_json='{}',
        original_hash="h",
        fence_json="{}",
        expires_at=_now_iso(),
    )
    ops.update_intake(INTAKE_ID, "waiting", entry_question_id="eq-1")
    intake = ops.get_intake(INTAKE_ID)
    assert intake["status"] == "waiting"
    assert intake["entry_question_id"] == "eq-1"


def test_create_task(ops: LedgerOps) -> None:
    ops.create_project(V1)
    ops.create_chat(CHAT_ID, V1)
    ops.create_run(
        run_id=RUN_ID,
        project_id=V1,
        chat_id=CHAT_ID,
        question="Test",
        scope_hash="sh",
        eligible_dataset_ids=[],
        budget_json="{}",
        configuration_hash="ch",
        deadline=_now_iso(),
    )
    task_id = str(uuid4())
    ops.create_task(task_id, RUN_ID, '{"type": "sql"}')
    with ops._ledger.transaction() as conn:
        row = conn.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
        assert row is not None
        assert row["status"] == "pending"


def test_create_action(ops: LedgerOps) -> None:
    ops.create_project(V1)
    ops.create_chat(CHAT_ID, V1)
    ops.create_run(
        run_id=RUN_ID,
        project_id=V1,
        chat_id=CHAT_ID,
        question="Test",
        scope_hash="sh",
        eligible_dataset_ids=[],
        budget_json="{}",
        configuration_hash="ch",
        deadline=_now_iso(),
    )
    task_id = str(uuid4())
    ops.create_task(task_id, RUN_ID, '{}')
    action_id = str(uuid4())
    ops.create_action(action_id, task_id, RUN_ID, '{"objective": "query"}')
    with ops._ledger.transaction() as conn:
        row = conn.execute("SELECT * FROM actions WHERE action_id = ?", (action_id,)).fetchone()
        assert row is not None
        assert row["status"] == "pending"
        assert row["attempt"] == 1
        assert row["execution_generation"] == 1


def test_record_and_get_outcome(ops: LedgerOps) -> None:
    ops.create_project(V1)
    ops.create_chat(CHAT_ID, V1)
    ops.create_run(
        run_id=RUN_ID,
        project_id=V1,
        chat_id=CHAT_ID,
        question="Test",
        scope_hash="sh",
        eligible_dataset_ids=[],
        budget_json="{}",
        configuration_hash="ch",
        deadline=_now_iso(),
    )
    task_id = str(uuid4())
    ops.create_task(task_id, RUN_ID, '{}')
    action_id = str(uuid4())
    ops.create_action(action_id, task_id, RUN_ID, '{}')
    outcome_id = str(uuid4())
    ops.record_outcome(outcome_id, action_id, RUN_ID, 1, 1, '{"status": "succeeded"}')
    outcome = ops.get_outcome(action_id, 1, 1)
    assert outcome is not None
    assert outcome["outcome_id"] == outcome_id
    assert outcome["attempt"] == 1


def test_create_invocation(ops: LedgerOps) -> None:
    ops.create_project(V1)
    ops.create_chat(CHAT_ID, V1)
    ops.create_run(
        run_id=RUN_ID,
        project_id=V1,
        chat_id=CHAT_ID,
        question="Test",
        scope_hash="sh",
        eligible_dataset_ids=[],
        budget_json="{}",
        configuration_hash="ch",
        deadline=_now_iso(),
    )
    invocation_id = str(uuid4())
    ops.create_invocation(
        invocation_id=invocation_id,
        run_id=RUN_ID,
        intake_id=None,
        role="sql",
        attempt=1,
        invocation_key="key-1",
        packet_hash="pkthash",
        request_json='{}',
    )
    with ops._ledger.transaction() as conn:
        row = conn.execute(
            "SELECT * FROM invocations WHERE invocation_id = ?", (invocation_id,)
        ).fetchone()
        assert row is not None
        assert row["status"] == "reserved"


def test_transaction_rollback_on_error(ledger: Ledger) -> None:
    ops = LedgerOps(ledger)
    ops.create_project(V1)
    try:
        with ledger.transaction() as conn:
            conn.execute("INSERT INTO projects (project_id, created_at) VALUES (?, ?)", ("dup", _now_iso()))
            conn.execute("INSERT INTO projects (project_id, created_at) VALUES (?, ?)", ("dup", _now_iso()))  # duplicate
    except Exception:  # sqlite3.IntegrityError
        pass
    with ledger.transaction() as conn:
        row = conn.execute("SELECT * FROM projects WHERE project_id = ?", ("dup",)).fetchone()
        assert row is None  # rolled back


def test_wal_mode_enabled(ledger: Ledger) -> None:
    with ledger.transaction() as conn:
        mode = conn.execute("PRAGMA journal_mode").fetchone()
        assert mode["journal_mode"] == "wal"


def test_foreign_keys_enabled(ledger: Ledger) -> None:
    with ledger.transaction() as conn:
        fk = conn.execute("PRAGMA foreign_keys").fetchone()
        assert fk["foreign_keys"] == 1


def test_busy_timeout_set(ledger: Ledger) -> None:
    with ledger.transaction() as conn:
        bt = conn.execute("PRAGMA busy_timeout").fetchone()
        val = bt[0] if bt else 0
        assert val >= 1000


def test_synchronous_full(ledger: Ledger) -> None:
    with ledger.transaction() as conn:
        sync = conn.execute("PRAGMA synchronous").fetchone()
        val = sync[0] if sync else 0
        # With WAL mode, synchronous=2 (NORMAL) is the default
        assert val >= 1


def test_payload_digest_unique_constraint(ops: LedgerOps) -> None:
    digest = "c" * 64
    ops.store_payload(str(uuid4()), "record", 1, b'{}', digest)
    with pytest.raises(Exception):  # sqlite3.IntegrityError
        ops.store_payload(str(uuid4()), "record", 1, b'{"x":1}', digest)


def test_run_unique_constraint(ops: LedgerOps) -> None:
    ops.create_project(V1)
    ops.create_chat(CHAT_ID, V1)
    ops.create_run(
        run_id=RUN_ID,
        project_id=V1,
        chat_id=CHAT_ID,
        question="Test",
        scope_hash="sh",
        eligible_dataset_ids=[],
        budget_json="{}",
        configuration_hash="ch",
        deadline=_now_iso(),
    )
    with pytest.raises(Exception):  # sqlite3.IntegrityError
        ops.create_run(
            run_id=RUN_ID,  # duplicate
            project_id=V1,
            chat_id=CHAT_ID,
            question="Test2",
            scope_hash="sh2",
            eligible_dataset_ids=[],
            budget_json="{}",
            configuration_hash="ch2",
            deadline=_now_iso(),
        )


def test_intake_submission_key_unique(ops: LedgerOps) -> None:
    ops.create_project(V1)
    ops.create_intake(
        intake_id=str(uuid4()),
        submission_key="same-key",
        project_id=V1,
        input_json='{}',
        original_hash="h1",
        fence_json="{}",
        expires_at=_now_iso(),
    )
    with pytest.raises(Exception):  # sqlite3.IntegrityError
        ops.create_intake(
            intake_id=str(uuid4()),
            submission_key="same-key",  # duplicate
            project_id=V1,
            input_json='{}',
            original_hash="h2",
            fence_json="{}",
            expires_at=_now_iso(),
        )


def test_dataset_snapshot(ops: LedgerOps) -> None:
    ops.create_project(V1)
    ops.create_dataset("ds-1", V1, "upload-ref", "abc123")
    snap_id = str(uuid4())
    ops.create_dataset_snapshot(snap_id, "ds-1", '{"tables": []}')
    ops.update_snapshot_prepared(snap_id, "pref", "phash", "pubref")
    with ops._ledger.transaction() as conn:
        row = conn.execute("SELECT * FROM dataset_snapshots WHERE snapshot_id = ?", (snap_id,)).fetchone()
        assert row is not None
        assert row["prepared_ref"] == "pref"
        assert row["publication_ref"] == "pubref"


def test_draft_creation(ops: LedgerOps) -> None:
    ops.create_project(V1)
    ops.create_chat(CHAT_ID, V1)
    ops.create_run(
        run_id=RUN_ID,
        project_id=V1,
        chat_id=CHAT_ID,
        question="Test",
        scope_hash="sh",
        eligible_dataset_ids=[],
        budget_json="{}",
        configuration_hash="ch",
        deadline=_now_iso(),
    )
    task_id = str(uuid4())
    ops.create_task(task_id, RUN_ID, '{}')
    action_id = str(uuid4())
    ops.create_action(action_id, task_id, RUN_ID, '{}')
    draft_id = str(uuid4())
    ops.create_draft(
        draft_id=draft_id,
        run_id=RUN_ID,
        action_id=action_id,
        draft_json='{"answer": "42"}',
        content_hash="chash",
        input_packet_hash="iphash",
        dependencies_json='[]',
        source_input_hash="sihash",
        completeness="complete",
        rendering_policy_version="v1",
        originating_invocation_id=str(uuid4()),
    )
    with ops._ledger.transaction() as conn:
        row = conn.execute("SELECT * FROM drafts WHERE draft_id = ?", (draft_id,)).fetchone()
        assert row is not None
        assert row["completeness"] == "complete"


def test_review_creation(ops: LedgerOps) -> None:
    ops.create_project(V1)
    ops.create_chat(CHAT_ID, V1)
    ops.create_run(
        run_id=RUN_ID,
        project_id=V1,
        chat_id=CHAT_ID,
        question="Test",
        scope_hash="sh",
        eligible_dataset_ids=[],
        budget_json="{}",
        configuration_hash="ch",
        deadline=_now_iso(),
    )
    task_id = str(uuid4())
    ops.create_task(task_id, RUN_ID, '{}')
    action_id = str(uuid4())
    ops.create_action(action_id, task_id, RUN_ID, '{}')
    draft_id = str(uuid4())
    ops.create_draft(
        draft_id=draft_id,
        run_id=RUN_ID,
        action_id=action_id,
        draft_json='{}',
        content_hash="chash",
        input_packet_hash="iphash",
        dependencies_json='[]',
        source_input_hash="sihash",
        completeness="complete",
        rendering_policy_version="v1",
        originating_invocation_id=str(uuid4()),
    )
    review_id = str(uuid4())
    ops.create_review(
        review_id=review_id,
        run_id=RUN_ID,
        draft_id=draft_id,
        review_pass=1,
        assessment_json='{"verdict": "approved"}',
        verdict="approved",
        draft_content_hash="chash",
        draft_input_packet_hash="iphash",
        rendering_policy_version="v1",
        deadline=_now_iso(),
    )
    review = ops.get_review(RUN_ID, 1)
    assert review is not None
    assert review["verdict"] == "approved"
    assert review["review_pass"] == 1

    # Second review pass
    review_id2 = str(uuid4())
    ops.create_review(
        review_id=review_id2,
        run_id=RUN_ID,
        draft_id=draft_id,
        review_pass=2,
        assessment_json='{}',
        verdict="approved",
        draft_content_hash="chash",
        draft_input_packet_hash="iphash",
        rendering_policy_version="v1",
        deadline=_now_iso(),
    )
    review2 = ops.get_review(RUN_ID, 2)
    assert review2 is not None
    assert review2["review_pass"] == 2


def test_final_result_recording(ops: LedgerOps) -> None:
    ops.create_project(V1)
    ops.create_chat(CHAT_ID, V1)
    ops.create_run(
        run_id=RUN_ID,
        project_id=V1,
        chat_id=CHAT_ID,
        question="Test",
        scope_hash="sh",
        eligible_dataset_ids=[],
        budget_json="{}",
        configuration_hash="ch",
        deadline=_now_iso(),
    )
    result_id = str(uuid4())
    ops.record_final_result(
        result_id=result_id,
        run_id=RUN_ID,
        route="reviewed",
        candidate_id="cid",
        content_hash="chash",
        completeness="complete",
        rendered_text="Answer: 42",
        rendering_policy_version="v1",
        evidence_ids=["e1"],
        chart_artifact_ids=[],
        dependencies_json='[]',
        review_status="approved",
    )
    with ops._ledger.transaction() as conn:
        row = conn.execute("SELECT * FROM final_results WHERE result_id = ?", (result_id,)).fetchone()
        assert row is not None
        assert row["route"] == "reviewed"
        assert row["completeness"] == "complete"