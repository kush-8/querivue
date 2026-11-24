"""Unit tests for graph state and wrappers."""

from __future__ import annotations

from uuid import uuid4

import pytest

from querivue_agent.runtime.graph_state import (
    RunState,
    EvidenceRegistryEntry,
    ActionOutcome,
    create_initial_run_state,
    SpecialistInput,
    SpecialistOutput,
)
from querivue_agent.runtime.wrappers import (
    build_sql_specialist_input,
    build_python_specialist_input,
    build_answer_specialist_input,
    build_reviewer_input,
    build_clarification_agent_input,
    validate_specialist_output,
    get_specialist_wrapper,
    get_input_builder,
)
from querivue_agent.contracts.actions import (
    SQLAction,
    PythonAction,
    AnswerAction,
    ClarificationAction,
    Task,
    AnalysisConstraints,
)
from querivue_agent.contracts.inputs import ReviewRequest


def test_evidence_registry_entry_creation():
    """Test creating an evidence registry entry."""
    from querivue_agent.contracts.values import CanonicalUUID
    from datetime import datetime, UTC

    entry = EvidenceRegistryEntry(
        evidence_id=CanonicalUUID(str(uuid4())),
        evidence_type="tabular",
        producer="sql",
        method="execute_query",
        schema={"col1": "int", "col2": "str"},
        row_count=100,
        source_dependencies=[CanonicalUUID(str(uuid4()))],
        integrity_hash="a" * 64,
        artifact_ref="artifact_123",
        preview={"rows": [{"col1": 1, "col2": "test"}], "coverage": "full"},
        created_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    )
    assert entry.evidence_type == "tabular"
    assert entry.producer == "sql"


def test_action_outcome_creation():
    """Test creating an action outcome."""
    from querivue_agent.contracts.values import CanonicalUUID, RuntimeUUID

    action_id = CanonicalUUID(str(uuid4()))
    outcome = ActionOutcome(
        task_id=CanonicalUUID(str(uuid4())),
        action_id=action_id,
        attempt=1,
        result_ref="result_123",
        result={"type": "tabular_evidence", "rows": 10},
        evidence_ids=[CanonicalUUID(str(uuid4()))],
    )
    assert outcome.action_id == action_id
    assert outcome.status == "succeeded"
    assert outcome.attempt == 1


def test_run_state_evidence_registration():
    """Test evidence registration in run state."""
    from querivue_agent.contracts.values import CanonicalUUID
    from datetime import datetime, UTC

    run_state = RunState(
        run_id=CanonicalUUID(str(uuid4())),
        project_id=CanonicalUUID(str(uuid4())),
        chat_id=CanonicalUUID(str(uuid4())),
        question="Test question",
        eligible_dataset_ids=[CanonicalUUID(str(uuid4()))],
    )

    entry = EvidenceRegistryEntry(
        evidence_id=CanonicalUUID(str(uuid4())),
        evidence_type="tabular",
        producer="sql",
        method="execute_query",
        schema={"col1": "int"},
        row_count=10,
        source_dependencies=[CanonicalUUID(str(uuid4()))],
        integrity_hash="a" * 64,
        artifact_ref="artifact_1",
        preview={"rows": [], "coverage": "full"},
        created_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    )

    run_state.register_evidence(entry)
    assert str(entry.evidence_id) in run_state.evidence

    # Test idempotent registration with same hash
    run_state.register_evidence(entry)  # Should not raise

    # Test integrity error on different hash
    entry2 = EvidenceRegistryEntry(
        evidence_id=entry.evidence_id,
        evidence_type="tabular",
        producer="sql",
        method="execute_query",
        schema={"col1": "int"},
        row_count=10,
        source_dependencies=[CanonicalUUID(str(uuid4()))],
        integrity_hash="b" * 64,  # Different hash
        artifact_ref="artifact_2",
        preview={"rows": [], "coverage": "full"},
        created_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    )
    with pytest.raises(ValueError, match="Evidence integrity mismatch"):
        run_state.register_evidence(entry2)


def test_run_state_outcome_commit():
    """Test committing action outcomes."""
    from querivue_agent.contracts.values import CanonicalUUID

    run_state = RunState(
        run_id=CanonicalUUID(str(uuid4())),
        project_id=CanonicalUUID(str(uuid4())),
        chat_id=CanonicalUUID(str(uuid4())),
        question="Test question",
        eligible_dataset_ids=[CanonicalUUID(str(uuid4()))],
    )

    action_id = CanonicalUUID(str(uuid4()))
    outcome = ActionOutcome(
        task_id=CanonicalUUID(str(uuid4())),
        action_id=action_id,
        attempt=1,
        result_ref="result_1",
        result={"type": "tabular_evidence", "rows": 5},
    )

    run_state.commit_outcome(outcome)
    assert str(action_id) in run_state.outcomes

    # Test idempotent commit with same attempt
    run_state.commit_outcome(outcome)  # Should not raise

    # Test error on different attempt
    outcome2 = ActionOutcome(
        task_id=CanonicalUUID(str(uuid4())),
        action_id=action_id,
        attempt=2,  # Different attempt
        result_ref="result_2",
        result={"type": "tabular_evidence", "rows": 5},
    )
    with pytest.raises(ValueError, match="Attempt mismatch"):
        run_state.commit_outcome(outcome2)


def test_create_initial_run_state():
    """Test creating initial run state."""
    from querivue_agent.contracts.values import CanonicalUUID, RuntimeUUID
    from querivue_agent.contracts.budgets import BudgetSnapshot, BudgetCounters, CounterSnapshot, MoneySnapshot, CounterAmounts, ProtectedReserve

    run_id = CanonicalUUID(str(uuid4()))
    project_id = CanonicalUUID(str(uuid4()))
    chat_id = CanonicalUUID(str(uuid4()))
    dataset_ids = [CanonicalUUID(str(uuid4())), CanonicalUUID(str(uuid4()))]

    # Create mock objects for admission_receipt, fence, budget
    from querivue_agent.contracts.records import AdmissionReceipt
    from querivue_agent.contracts.common import OwnerFence, Scope

    scope = Scope(
        project_id=project_id,
        chat_id=chat_id,
        run_id=run_id,
        eligible_dataset_ids=dataset_ids,
    )

    # Create a minimal budget
    budget = BudgetSnapshot(
        scope=scope,
        revision=0,
        counters=BudgetCounters(
            physical_requests=CounterSnapshot(limit=10, used=0, reserved=0, unknown_reserved=0),
            logical_invocations=CounterSnapshot(limit=10, used=0, reserved=0, unknown_reserved=0),
            input_tokens=CounterSnapshot(limit=50000, used=0, reserved=0, unknown_reserved=0),
            output_tokens=CounterSnapshot(limit=20000, used=0, reserved=0, unknown_reserved=0),
            tool_calls=CounterSnapshot(limit=100, used=0, reserved=0, unknown_reserved=0),
            query_executions=CounterSnapshot(limit=50, used=0, reserved=0, unknown_reserved=0),
            dispatch_attempts=CounterSnapshot(limit=8, used=0, reserved=0, unknown_reserved=0),
            active_milliseconds=CounterSnapshot(limit=600000, used=0, reserved=0, unknown_reserved=0),
            wall_milliseconds=CounterSnapshot(limit=3600000, used=0, reserved=0, unknown_reserved=0),
            output_bytes=CounterSnapshot(limit=1024*1024*128, used=0, reserved=0, unknown_reserved=0),
            output_files=CounterSnapshot(limit=16, used=0, reserved=0, unknown_reserved=0),
        ),
        cost=MoneySnapshot(limit="0.00", used="0.00", reserved="0.00", unknown_reserved="0.00", currency="USD"),
        protected_reserves=[
            ProtectedReserve(
                purpose="answer",
                counters=CounterAmounts(
                    physical_requests=10, logical_invocations=5, input_tokens=50000, output_tokens=20000,
                    tool_calls=0, query_executions=0, dispatch_attempts=0,
                    active_milliseconds=300000, wall_milliseconds=3600000,
                    output_bytes=10485760, output_files=16,
                ),
                cost_usd="0.50",
            ),
        ],
    )

    admission_receipt = AdmissionReceipt(
        receipt_id=RuntimeUUID(str(uuid4())),
        admission_id=CanonicalUUID(str(uuid4())),
        intake_id=CanonicalUUID(str(uuid4())),
        run_id=run_id,
        scope=scope,
        cutoff_sequence=0,
        budget=budget,
        configuration_hash="a" * 64,
        accepted_at="2026-01-01T00:00:00Z",
    )

    fence = OwnerFence(
        scope=scope,
        subject_kind="run",
        subject_id=run_id,
        owner_id=RuntimeUUID(str(uuid4())),
        generation=2,
        attempt=1,
        expected_revision=0,
        lease_expires_at="2099-12-31T23:59:59.999999Z",
    )

    run_state = create_initial_run_state(
        run_id=run_id,
        project_id=project_id,
        chat_id=chat_id,
        question="Test question",
        eligible_dataset_ids=dataset_ids,
        admission_receipt=admission_receipt,
        fence=fence,
        budget=budget,
        deadline="2026-12-31T23:59:59.999999Z",
    )

    assert run_state.run_id == run_id
    assert run_state.project_id == project_id
    assert run_state.chat_id == chat_id
    assert run_state.question == "Test question"
    assert run_state.eligible_dataset_ids == dataset_ids
    assert run_state.admission_receipt == admission_receipt
    assert run_state.fence == fence
    assert run_state.phase == "admitted"
    assert run_state.execution_status["phase"] == "planning"


def test_specialist_input_builders():
    """Test building specialist inputs."""
    from querivue_agent.contracts.values import CanonicalUUID, RuntimeUUID

    run_state = RunState(
        run_id=CanonicalUUID(str(uuid4())),
        project_id=CanonicalUUID(str(uuid4())),
        chat_id=CanonicalUUID(str(uuid4())),
        question="Test question",
        eligible_dataset_ids=[CanonicalUUID(str(uuid4()))],
    )

    # Test SQL specialist input builder
    from querivue_agent.contracts.actions import Task, SQLAction, AnalysisConstraints, DateWindow
    from querivue_agent.contracts.values import Int64Scalar

    constraints = AnalysisConstraints(
        metric_definitions={"count": "count(*)"},
        filters=[],
        date_windows=[
            DateWindow(
                source_id=CanonicalUUID("00000000-0000-1000-8000-000000000001"),
                column="created_at",
                lower=Int64Scalar(kind="int64", value="0"),
                upper=Int64Scalar(kind="int64", value="9223372036854775807"),
                lower_inclusive=True,
                upper_inclusive=True,
            )
        ],
        analysis_timezone="UTC",
        grain="day",
        units={"count": "rows"},
    )

    action = SQLAction(
        action_id=RuntimeUUID(str(uuid4())),
        type="sql",
        objective="Test query",
        table_ids=[CanonicalUUID(str(uuid4()))],
        constraints=constraints,
        input_evidence_ids=[CanonicalUUID(str(uuid4()))],
    )

    input_ = build_sql_specialist_input(run_state, Task(
        task_id=CanonicalUUID(str(uuid4())),
        type="analysis",
        requires=[],
        actions=[action],
    ), action, RuntimeUUID(str(uuid4())), 1)

    assert input_.role == "sql_specialist"
    assert input_.invocation_id is not None
    assert input_.attempt == 1
    assert input_.objective == "Test query"


def test_validate_specialist_output():
    """Test validating specialist output."""
    output = SpecialistOutput(
        role="sql_specialist",
        invocation_id=uuid4(),
        attempt=1,
        status="succeeded",
        result={"type": "tabular_evidence"},
    )

    validate_specialist_output(output, "sql_specialist")  # Should not raise

    # Test role mismatch
    with pytest.raises(ValueError, match="Role mismatch"):
        validate_specialist_output(output, "python_specialist")

    # Test invalid status
    output2 = SpecialistOutput(
        role="sql_specialist",
        invocation_id=uuid4(),
        attempt=1,
        status="invalid",
        result=None,
    )
    with pytest.raises(ValueError, match="Invalid status"):
        validate_specialist_output(output2, "sql_specialist")

    # Test missing result on success
    output3 = SpecialistOutput(
        role="sql_specialist",
        invocation_id=uuid4(),
        attempt=1,
        status="succeeded",
        result=None,
    )
    with pytest.raises(ValueError, match="Succeeded output must have result"):
        validate_specialist_output(output3, "sql_specialist")


def test_get_specialist_wrapper():
    """Test getting specialist wrapper functions."""
    wrapper = get_specialist_wrapper("sql_specialist")
    assert wrapper is not None

    wrapper = get_specialist_wrapper("python_specialist")
    assert wrapper is not None

    wrapper = get_specialist_wrapper("answer_specialist")
    assert wrapper is not None

    wrapper = get_specialist_wrapper("reviewer")
    assert wrapper is not None

    wrapper = get_specialist_wrapper("clarification_agent")
    assert wrapper is not None

    with pytest.raises(ValueError, match="No wrapper for role"):
        get_specialist_wrapper("unknown_role")


def test_get_input_builder():
    """Test getting input builder functions."""
    builder = get_input_builder("sql_specialist")
    assert builder is not None

    builder = get_input_builder("python_specialist")
    assert builder is not None

    builder = get_input_builder("answer_specialist")
    assert builder is not None

    builder = get_input_builder("reviewer")
    assert builder is not None

    builder = get_input_builder("clarification_agent")
    assert builder is not None

    with pytest.raises(ValueError, match="No input builder for role"):
        get_input_builder("unknown_role")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])