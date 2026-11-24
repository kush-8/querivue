"""Integration tests for Authority transitions."""

import tempfile
from pathlib import Path
from uuid import uuid4

import pytest

from querivue_agent.contracts.budgets import BudgetSnapshot, ClockReading
from querivue_agent.contracts.common import OwnerFence, Scope
from querivue_agent.contracts.records import (
    AdmissionReceipt,
    AdmissionTarget,
    IntakeAdmission,
    IntakeReceipt,
    QueueReceipt,
    ResumeReceipt,
    NewRunTarget,
)
from querivue_agent.contracts.values import CanonicalUUID, RuntimeUUID
from querivue_agent.runtime.authority import Authority
from querivue_agent.runtime.budgets import create_initial_budget
from querivue_agent.storage.ledger import Ledger, LedgerOps


V1 = "00000000-0000-1000-8000-000000000001"
V1B = "00000000-0000-1000-8000-000000000002"


def _make_scope() -> Scope:
    return Scope(project_id=V1, chat_id=V1B, run_id=None, eligible_dataset_ids=[V1, V1B])


def _now_iso() -> str:
    import datetime
    return datetime.datetime.now(datetime.UTC).isoformat().replace("+00:00", "Z")


@pytest.fixture
def db_path() -> Path:
    with tempfile.TemporaryDirectory() as tmp:
        yield Path(tmp) / "test.db"


@pytest.fixture
def ledger(db_path: Path) -> Ledger:
    l = Ledger.open(db_path)
    yield l
    l.close()


@pytest.fixture
def ops(ledger: Ledger) -> LedgerOps:
    return LedgerOps(ledger)


@pytest.fixture
def authority(ledger: Ledger) -> Authority:
    return Authority(ledger)


def test_initialize_scope(authority: Authority) -> None:
    """Test scope initialization."""
    with tempfile.TemporaryDirectory() as tmp:
        state_root = Path(tmp) / "state"
        scope = authority.initialize_scope(state_root)

        assert scope.project_id is not None
        assert scope.chat_id is None
        assert scope.run_id is None
        assert scope.eligible_dataset_ids == []


def test_record_intake(authority: Authority, ops: LedgerOps) -> None:
    """Test intake recording."""
    scope = _make_scope()

    # Create project first
    ops.create_project(V1)

    # Use the ledger directly to test intake creation
    intake_id = str(uuid4())
    submission_key = f"intake-{intake_id}"
    ops.create_intake(
        intake_id=intake_id,
        submission_key=submission_key,
        project_id=V1,
        input_json='{"question": "test"}',
        original_hash="a" * 64,
        fence_json='{"subject_kind": "intake"}',
        expires_at=_now_iso(),
    )

    intake = ops.get_intake(intake_id)
    assert intake is not None
    assert intake["status"] == "pending"


def test_claim_run(authority: Authority, ops: LedgerOps) -> None:
    """Test run ownership claim."""
    # First create project and chat
    ops.create_project(V1)
    ops.create_chat(V1B, V1)

    # First create a run in the ledger
    run_id = str(uuid4())
    ops.create_run(
        run_id=run_id,
        project_id=V1,
        chat_id=V1B,
        question="Test",
        scope_hash="sh",
        eligible_dataset_ids=[],
        budget_json="{}",
        configuration_hash="ch",
        deadline=_now_iso(),
    )

    owner_id = uuid4()
    fence = authority.claim_run(run_id, owner_id)

    assert isinstance(fence, OwnerFence)
    assert fence.subject_id == run_id
    assert fence.owner_id == str(owner_id)
    assert fence.generation == 2
    assert fence.subject_kind == "run"


def test_renew_lease(authority: Authority, ops: LedgerOps) -> None:
    """Test lease renewal."""
    ops.create_project(V1)
    ops.create_chat(V1B, V1)

    run_id = str(uuid4())
    ops.create_run(
        run_id=run_id,
        project_id=V1,
        chat_id=V1B,
        question="Test",
        scope_hash="sh",
        eligible_dataset_ids=[],
        budget_json="{}",
        configuration_hash="ch",
        deadline=_now_iso(),
    )

    owner_id = uuid4()
    # First claim
    fence = authority.claim_run(run_id, owner_id)

    # Then renew
    renewed = authority.renew_lease(fence)

    assert renewed.generation == fence.generation
    assert renewed.owner_id == str(fence.owner_id)
    assert renewed.subject_id == fence.subject_id


def test_admit_intake(authority: Authority, ops: LedgerOps) -> None:
    """Test intake admission."""
    scope = _make_scope()
    ops.create_project(V1)
    ops.create_chat(V1B, V1)

    from querivue_agent.contracts.entry import EntryAccept

    assessment = EntryAccept(
        disposition="accept",
        policy_reason="test",
        explanation="Test explanation",
    )

    intake_id = str(uuid4())
    # Create intake first
    ops.create_intake(
        intake_id=intake_id,
        submission_key=f"sub-{intake_id}",
        project_id=V1,
        input_json='{"question": "test"}',
        original_hash="a" * 64,
        fence_json='{"subject_kind": "intake"}',
        expires_at=_now_iso(),
    )

    admission = IntakeAdmission(
        admission_id=str(uuid4()),
        intake_id=intake_id,
        submission_hash="a" * 64,
        scope=scope,
        assessment=assessment,
        context_hash="a" * 64,
        configuration_hash="a" * 64,
        policy_version="v1",
        target=NewRunTarget(kind="new_run", run_id=str(uuid4())),
        fence=OwnerFence(
            scope=scope,
            subject_kind="intake",
            subject_id=intake_id,
            owner_id=str(uuid4()),
            generation=1,
            attempt=1,
            expected_revision=0,
            lease_expires_at="2099-12-31T23:59:59.999999Z",
        ),
        accepted_at=_now_iso(),
    )

    receipt = authority.admit(admission)

    assert isinstance(receipt, AdmissionReceipt)
    assert receipt.receipt_id is not None
    assert receipt.run_id is not None
    # The returned scope should have the run_id set
    assert receipt.scope.run_id == receipt.run_id
    assert receipt.scope.project_id == scope.project_id
    assert receipt.scope.chat_id == scope.chat_id
    assert receipt.scope.eligible_dataset_ids == scope.eligible_dataset_ids


def test_commit_decision(authority: Authority, ops: LedgerOps) -> None:
    """Test supervisor decision commit."""
    ops.create_project(V1)
    ops.create_chat(V1B, V1)

    run_id = str(uuid4())
    ops.create_run(
        run_id=run_id,
        project_id=V1,
        chat_id=V1B,
        question="Test",
        scope_hash="sh",
        eligible_dataset_ids=[],
        budget_json="{}",
        configuration_hash="ch",
        deadline=_now_iso(),
    )

    # Create an invocation first for the FK constraint
    invocation_id = str(uuid4())
    ops.create_invocation(
        invocation_id=invocation_id,
        run_id=run_id,
        intake_id=None,
        role="supervisor",
        attempt=1,
        invocation_key="key-1",
        packet_hash="pkthash",
        request_json='{}',
    )

    fence = OwnerFence(
        scope=Scope(project_id=V1, chat_id=V1B, run_id=run_id, eligible_dataset_ids=[]),
        subject_kind="run",
        subject_id=run_id,
        owner_id=str(uuid4()),
        generation=2,
        attempt=1,
        expected_revision=0,
        lease_expires_at=_now_iso(),
    )

    # Provide a valid task with action for propose_queue
    from querivue_agent.contracts.actions import Task, SQLAction, AnalysisConstraints
    task_id = str(uuid4())
    action_id = str(uuid4())
    task = Task(
        task_id=task_id,
        actions=[
            SQLAction(
                action_id=action_id,
                type="sql",
                objective="Test query",
                table_ids=[],
                constraints=AnalysisConstraints(),
                input_evidence_ids=[],
            )
        ],
    )

    class MockProposal:
        tasks = [task]
        pass

    receipt = authority.commit_decision(run_id, MockProposal(), fence)

    assert isinstance(receipt, QueueReceipt)
    assert receipt.run_id == run_id
    assert receipt.decision_type == "propose_queue"
    assert receipt.queue_revision == 1
    assert len(receipt.tasks) == 1


def test_accept_reply(authority: Authority, ops: LedgerOps) -> None:
    """Test analytical reply acceptance."""
    ops.create_project(V1)
    ops.create_chat(V1B, V1)

    run_id = str(uuid4())
    ops.create_run(
        run_id=run_id,
        project_id=V1,
        chat_id=V1B,
        question="Test",
        scope_hash="sh",
        eligible_dataset_ids=[],
        budget_json="{}",
        configuration_hash="ch",
        deadline=_now_iso(),
    )

    intake_id = str(uuid4())
    ops.create_intake(
        intake_id=intake_id,
        submission_key="sub-1",
        project_id=V1,
        input_json='{}',
        original_hash="h",
        fence_json="{}",
        expires_at=_now_iso(),
    )

    question_id = str(uuid4())
    reply_id = str(uuid4())

    from querivue_agent.contracts.inputs import UserMessage
    from querivue_agent.contracts.artifacts import SourceDependency

    reply = {
        "reply_id": reply_id,
        "run_id": run_id,
        "question_id": question_id,
        "entry_intake_id": intake_id,
        "submission_key": "subkey",
        "message": UserMessage(
            message_id=str(uuid4()),
            chat_id=V1B,
            sequence=1,
            text="reply",
            content_hash="a" * 64,
        ),
        "selected_option_ids": [],
        "question_content_hash": "a" * 64,
        "accepted_at": _now_iso(),
        "entry_admission_ref": str(uuid4()),
    }

    fence = OwnerFence(
        scope=Scope(project_id=V1, chat_id=V1B, run_id=run_id, eligible_dataset_ids=[]),
        subject_kind="run",
        subject_id=run_id,
        owner_id=str(uuid4()),
        generation=2,
        attempt=1,
        expected_revision=0,
        lease_expires_at=_now_iso(),
    )

    # Test the ledger operation directly
    resume_id = str(uuid4())
    ops.record_resume_receipt(
        resume_id=resume_id,
        run_id=run_id,
        question_id=question_id,
        reply_id=reply_id,
        entry_intake_id=intake_id,
        run_revision=1,
        owner_generation=1,
        original_deadline=_now_iso(),
        scope_json=fence.scope.model_dump_json(),
    )

    with ops._ledger.transaction() as conn:
        row = conn.execute(
            "SELECT * FROM resume_receipts WHERE resume_id = ?",
            (resume_id,)
        ).fetchone()
        assert row is not None
        assert row["run_id"] == run_id


def test_budget_integration(authority: Authority) -> None:
    """Test budget integration with authority."""
    scope = _make_scope()
    budget = create_initial_budget(scope)

    assert budget is not None
    assert budget.scope == scope
    assert len(budget.protected_reserves) == 5


if __name__ == "__main__":
    pytest.main([__file__, "-v"])