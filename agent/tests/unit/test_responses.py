import pytest
from pydantic import TypeAdapter, ValidationError

from querivue_agent.contracts.responses import (
    ActionOutcome,
    PythonBlocked,
    PythonFailed,
    PythonOutcome,
    PythonSucceeded,
    SQLBlocked,
    SQLFailed,
    SQLOutcome,
    SQLSucceeded,
    ToolError,
)


ID = "6b085fd1-4c78-4b85-96c9-a201ce5e935c"
OTHER_ID = "d816d53d-eac8-4d98-978e-97c1bd81f127"
EXISTING_ID = "123e4567-e89b-12d3-a456-426614174000"
ERROR = {"code": "query_timeout", "message": "Timed out", "stage": "execution", "disposition": "retry_operation"}
SUCCEEDED = {"status": "succeeded", "observation": "Résultat 世界", "evidence_ids": [ID], "limitations": []}
BLOCKED = {"status": "blocked", "explanation": "Need a source", "required_input": "Choose a source", "evidence_ids": []}
FAILED = {"status": "failed", "error": ERROR, "evidence_ids": []}
PYTHON_SUCCEEDED = {
    "status": "succeeded",
    "observation": "Computed trend",
    "evidence_ids": [ID],
    "chart_artifact_ids": [OTHER_ID],
    "limitations": [],
}
PYTHON_BLOCKED = {
    "status": "blocked",
    "explanation": "Need a parameter",
    "required_input": "Choose a window",
    "evidence_ids": [],
    "chart_artifact_ids": [],
}
PYTHON_FAILED = {"status": "failed", "error": ERROR, "evidence_ids": [], "chart_artifact_ids": []}


@pytest.mark.parametrize(
    "adapter,payload,model",
    [
        (TypeAdapter(SQLOutcome), SUCCEEDED, SQLSucceeded),
        (TypeAdapter(SQLOutcome), BLOCKED, SQLBlocked),
        (TypeAdapter(SQLOutcome), FAILED, SQLFailed),
        (TypeAdapter(PythonOutcome), PYTHON_SUCCEEDED, PythonSucceeded),
        (TypeAdapter(PythonOutcome), PYTHON_BLOCKED, PythonBlocked),
        (TypeAdapter(PythonOutcome), PYTHON_FAILED, PythonFailed),
    ],
)
def test_sql_and_python_result_discriminators_round_trip(adapter, payload, model):
    result = adapter.validate_python(payload)
    assert isinstance(result, model)
    assert adapter.validate_json(result.model_dump_json()) == result


def test_result_boundaries_reject_runtime_authority_and_wrong_branch_fields():
    sql_adapter = TypeAdapter(SQLOutcome)
    python_adapter = TypeAdapter(PythonOutcome)
    with pytest.raises(ValidationError, match="extra_forbidden"):
        sql_adapter.validate_python({**SUCCEEDED, "budget": 1})
    with pytest.raises(ValidationError, match="extra_forbidden"):
        python_adapter.validate_python({**PYTHON_BLOCKED, "observation": "wrong branch"})
    with pytest.raises(ValidationError, match="union_tag_invalid"):
        python_adapter.validate_python({**PYTHON_SUCCEEDED, "status": "success"})


def test_reference_projection_and_sql_success_requirement_are_enforced():
    sql_adapter = TypeAdapter(SQLOutcome)
    with pytest.raises(ValidationError, match="at least 1 item"):
        sql_adapter.validate_python({**SUCCEEDED, "evidence_ids": []})
    with pytest.raises(ValidationError, match="unique"):
        sql_adapter.validate_python({**SUCCEEDED, "evidence_ids": [ID, ID]})
    result = TypeAdapter(PythonOutcome).validate_python({
        **PYTHON_SUCCEEDED,
        "evidence_ids": [EXISTING_ID],
        "chart_artifact_ids": [EXISTING_ID],
    })
    assert result.evidence_ids == [EXISTING_ID]
    assert result.chart_artifact_ids == [EXISTING_ID]


@pytest.mark.parametrize(
    "code",
    [
        "python_execution_error",
        "output_validation_error",
        "chart_render_error",
        "execution_timeout",
        "resource_limit_exceeded",
        "environment_unavailable",
    ],
)
def test_python_failure_round_trips_approved_python_error_codes(code):
    payload = {**PYTHON_FAILED, "error": {**ERROR, "code": code, "disposition": "correct_query"}}
    result = TypeAdapter(PythonOutcome).validate_python(payload)
    assert isinstance(result.error, ToolError)
    assert result.error.code == code
    assert result.error.disposition == "correct_query"


def test_unapproved_python_error_name_and_error_authority_are_rejected():
    with pytest.raises(ValidationError, match="literal_error"):
        ToolError.model_validate({**ERROR, "code": "python_timeout"})
    with pytest.raises(ValidationError, match="extra_forbidden"):
        ToolError.model_validate({**ERROR, "retry_authorized": True})


def test_action_outcome_projects_sql_references_exactly():
    payload = {
        "task_id": "00000000-0000-4000-8000-000000000001",
        "action_id": "00000000-0000-4000-8000-000000000002",
        "attempt": 1,
        "result_ref": "00000000-0000-4000-8000-000000000003",
        "result": SUCCEEDED,
        "evidence_ids": [ID],
        "chart_artifact_ids": [],
    }
    outcome = ActionOutcome.model_validate(payload)
    assert ActionOutcome.model_validate_json(outcome.model_dump_json()) == outcome
    with pytest.raises(ValidationError):
        ActionOutcome.model_validate({**payload, "evidence_ids": []})


def test_action_outcome_projects_draft_evidence_and_charts():
    chart_id = "00000000-0000-4000-8000-000000000099"
    payload = {
        "task_id": "00000000-0000-4000-8000-000000000001",
        "action_id": "00000000-0000-4000-8000-000000000002",
        "attempt": 1,
        "result_ref": "00000000-0000-4000-8000-000000000003",
        "result": {
            "status": "draft_ready",
            "draft": {
                "blocks": [{
                    "block_id": "claim",
                    "kind": "data_claim",
                    "spans": [
                        {"kind": "value", "target": {"kind": "cell", "evidence_id": ID, "row_locator": 0, "column_ordinal": 0}, "format": "exact"},
                        {"kind": "chart", "chart_artifact_id": chart_id},
                    ],
                    "supports": [],
                }],
                "unmet_deliverables": [],
            },
            "completeness": "complete",
        },
        "evidence_ids": [ID],
        "chart_artifact_ids": [chart_id],
    }
    assert ActionOutcome.model_validate(payload).chart_artifact_ids == [chart_id]
    with pytest.raises(ValidationError):
        ActionOutcome.model_validate({**payload, "chart_artifact_ids": []})


def test_action_outcome_projects_clarification_value_references_only():
    payload = {
        "task_id": "00000000-0000-4000-8000-000000000001",
        "action_id": "00000000-0000-4000-8000-000000000002",
        "attempt": 1,
        "result_ref": "00000000-0000-4000-8000-000000000003",
        "result": {
            "status": "question_ready",
            "question": {
                "spans": [{"kind": "value", "target": {"kind": "metadata", "evidence_id": ID, "field": "row_count"}, "format": "exact"}],
                "supports": [],
            },
            "suggestions": [],
        },
        "evidence_ids": [ID],
        "chart_artifact_ids": [],
    }
    assert ActionOutcome.model_validate(payload).evidence_ids == [ID]
