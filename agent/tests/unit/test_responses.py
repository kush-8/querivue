import json
from copy import deepcopy
from typing import get_args

import pytest
from pydantic import TypeAdapter, ValidationError

from querivue_agent.contracts.responses import (
    ActionOutcome, ErrorCode, ErrorDisposition, ErrorStage, PythonBlocked, PythonFailed,
    PythonOutcome, PythonSucceeded, SQLBlocked, SQLFailed, SQLOutcome,
    SQLSucceeded, ToolError,
)


ID = "6b085fd1-4c78-4b85-96c9-a201ce5e935c"
OTHER_ID = "d816d53d-eac8-4d98-978e-97c1bd81f127"
EXISTING_ID = "123e4567-e89b-12d3-a456-426614174000"
ERROR = dict(code="query_timeout", message="Timed out", stage="execution", disposition="retry_operation")
SUCCEEDED = dict(status="succeeded", observation="  Résultat 世界  ", evidence_ids=[ID], limitations=[])
BLOCKED = dict(status="blocked", explanation="Need a source", required_input="Choose a source", evidence_ids=[])
FAILED = dict(status="failed", error=ERROR, evidence_ids=[])
ADAPTER = TypeAdapter(SQLOutcome)
PYTHON_SUCCEEDED = dict(
    status="succeeded", observation="Computed trend", evidence_ids=[ID],
    chart_artifact_ids=[OTHER_ID], limitations=[],
)
PYTHON_BLOCKED = dict(
    status="blocked", explanation="Need a parameter", required_input="Choose a window",
    evidence_ids=[], chart_artifact_ids=[],
)
PYTHON_FAILED = dict(
    status="failed", error=ERROR, evidence_ids=[], chart_artifact_ids=[],
)
PYTHON_ADAPTER = TypeAdapter(PythonOutcome)


@pytest.mark.parametrize("payload,model", [(SUCCEEDED, SQLSucceeded), (BLOCKED, SQLBlocked), (FAILED, SQLFailed)])
def test_variants_round_trip(payload, model):
    result = ADAPTER.validate_python(payload)
    assert isinstance(result, model)
    assert ADAPTER.validate_json(result.model_dump_json()) == result
    assert ADAPTER.validate_json(json.dumps(payload)) == result
    assert model.model_validate(payload) == result
    if isinstance(result, SQLSucceeded):
        assert result.observation == payload["observation"]


@pytest.mark.parametrize("payload", [SUCCEEDED, BLOCKED, FAILED])
@pytest.mark.parametrize("field", ["status", "evidence_ids"])
def test_required_common_fields(payload, field):
    value = deepcopy(payload)
    del value[field]
    with pytest.raises(ValidationError, match="union_tag_not_found|Field required"):
        ADAPTER.validate_python(value)


@pytest.mark.parametrize("status", ["success", None, 1])
def test_wrong_discriminator(status):
    with pytest.raises(ValidationError, match="union_tag_invalid"):
        ADAPTER.validate_python({**SUCCEEDED, "status": status})


@pytest.mark.parametrize("payload", [SUCCEEDED, BLOCKED, FAILED])
@pytest.mark.parametrize("ids", [[ID, ID], ["bad"], [ID.upper()], [1], "bad", (ID,)])
def test_evidence_is_strict_unique_uuid_list(payload, ids):
    with pytest.raises(ValidationError):
        ADAPTER.validate_python({**payload, "evidence_ids": ids})


def test_success_requires_evidence():
    with pytest.raises(ValidationError, match="at least 1 item"):
        ADAPTER.validate_python({**SUCCEEDED, "evidence_ids": []})


@pytest.mark.parametrize("payload", [BLOCKED, FAILED])
def test_retains_evidence(payload):
    result = ADAPTER.validate_python({**payload, "evidence_ids": [ID, OTHER_ID]})
    assert result.evidence_ids == [ID, OTHER_ID]


@pytest.mark.parametrize("payload", [SUCCEEDED, BLOCKED, FAILED])
def test_forbids_extra_fields(payload):
    with pytest.raises(ValidationError, match="extra_forbidden"):
        ADAPTER.validate_python({**payload, "budget": 1})
    with pytest.raises(ValidationError, match="extra_forbidden"):
        ADAPTER.validate_python({**FAILED, "error": {**ERROR, "verified": True}})


@pytest.mark.parametrize("payload,field", [
    (SUCCEEDED, "observation"), (BLOCKED, "explanation"), (BLOCKED, "required_input"),
])
@pytest.mark.parametrize("invalid", ["", " \t\n\u2003", 1, True, None, b"text", "\ud800"])
def test_text_is_nonblank_strict_unicode(payload, field, invalid):
    with pytest.raises(ValidationError):
        ADAPTER.validate_python({**payload, field: invalid})


@pytest.mark.parametrize("value", [None, "text", ("text",), [""], [" \t"], [1], ["\ud800"]])
def test_limitations_validation(value):
    with pytest.raises(ValidationError):
        ADAPTER.validate_python({**SUCCEEDED, "limitations": value})


@pytest.mark.parametrize("payload,field", [
    (SUCCEEDED, "observation"), (SUCCEEDED, "limitations"),
    (BLOCKED, "explanation"), (BLOCKED, "required_input"), (FAILED, "error"),
])
def test_variant_fields_required(payload, field):
    value = deepcopy(payload)
    del value[field]
    with pytest.raises(ValidationError, match="Field required"):
        ADAPTER.validate_python(value)


@pytest.mark.parametrize("field,enum", [("code", ErrorCode), ("stage", ErrorStage), ("disposition", ErrorDisposition)])
def test_error_enums(field, enum):
    for member in get_args(enum):
        assert getattr(ToolError.model_validate({**ERROR, field: member}), field) == member
    for invalid in ["unknown", 1, None]:
        with pytest.raises(ValidationError, match="literal_error"):
            ToolError.model_validate({**ERROR, field: invalid})


@pytest.mark.parametrize("field", ["code", "message", "stage", "disposition"])
def test_error_required_fields(field):
    value = dict(ERROR)
    del value[field]
    with pytest.raises(ValidationError, match="Field required"):
        ToolError.model_validate(value)


def test_optional_operation_id():
    assert ToolError.model_validate(ERROR).operation_id is None
    assert ToolError.model_validate({**ERROR, "operation_id": None}).operation_id is None
    assert ToolError.model_validate({**ERROR, "operation_id": ID}).operation_id == ID
    for invalid in ["bad", ID.upper(), 1]:
        with pytest.raises(ValidationError):
            ToolError.model_validate({**ERROR, "operation_id": invalid})


def test_message_bound_preserves_content():
    message = " 世" * 1024
    assert ToolError.model_validate({**ERROR, "message": message}).message == message
    with pytest.raises(ValidationError, match="too_long"):
        ToolError.model_validate({**ERROR, "message": message + "界"})


@pytest.mark.parametrize("message", ["", " \n\t", 1, True, None, b"text", "\ud800"])
def test_message_nonblank_unicode(message):
    with pytest.raises(ValidationError):
        ToolError.model_validate({**ERROR, "message": message})


def test_error_object_required():
    with pytest.raises(ValidationError):
        ADAPTER.validate_python({**FAILED, "error": "timeout"})


@pytest.mark.parametrize(
    "payload,model",
    [
        (PYTHON_SUCCEEDED, PythonSucceeded),
        (PYTHON_BLOCKED, PythonBlocked),
        (PYTHON_FAILED, PythonFailed),
    ],
)
def test_python_variants_round_trip(payload, model):
    result = PYTHON_ADAPTER.validate_python(payload)
    assert isinstance(result, model)
    assert PYTHON_ADAPTER.validate_json(result.model_dump_json()) == result
    assert PYTHON_ADAPTER.validate_json(json.dumps(payload)) == result
    assert model.model_validate(payload) == result


@pytest.mark.parametrize("payload", [PYTHON_SUCCEEDED, PYTHON_BLOCKED, PYTHON_FAILED])
def test_python_variants_allow_empty_reference_lists(payload):
    result = PYTHON_ADAPTER.validate_python(
        {**payload, "evidence_ids": [], "chart_artifact_ids": []}
    )
    assert result.evidence_ids == []
    assert result.chart_artifact_ids == []


@pytest.mark.parametrize("payload", [PYTHON_SUCCEEDED, PYTHON_BLOCKED, PYTHON_FAILED])
@pytest.mark.parametrize("field", ["evidence_ids", "chart_artifact_ids"])
@pytest.mark.parametrize("ids", [[ID, ID], ["bad"], [ID.upper()], [1], "bad", (ID,)])
def test_python_references_are_strict_unique_uuid_lists(payload, field, ids):
    with pytest.raises(ValidationError):
        PYTHON_ADAPTER.validate_python({**payload, field: ids})


@pytest.mark.parametrize(
    "payload,fields",
    [
        (
            PYTHON_SUCCEEDED,
            ["status", "observation", "evidence_ids", "chart_artifact_ids", "limitations"],
        ),
        (
            PYTHON_BLOCKED,
            ["status", "explanation", "required_input", "evidence_ids", "chart_artifact_ids"],
        ),
        (PYTHON_FAILED, ["status", "error", "evidence_ids", "chart_artifact_ids"]),
    ],
)
def test_all_python_fields_are_required(payload, fields):
    for field in fields:
        value = deepcopy(payload)
        del value[field]
        with pytest.raises(ValidationError, match="union_tag_not_found|Field required"):
            PYTHON_ADAPTER.validate_python(value)


@pytest.mark.parametrize("payload", [PYTHON_SUCCEEDED, PYTHON_BLOCKED, PYTHON_FAILED])
def test_python_variants_forbid_extra_fields(payload):
    with pytest.raises(ValidationError, match="extra_forbidden"):
        PYTHON_ADAPTER.validate_python({**payload, "runtime_verified": True})


@pytest.mark.parametrize("status", ["success", None, 1])
def test_python_wrong_discriminator(status):
    with pytest.raises(ValidationError, match="union_tag_invalid"):
        PYTHON_ADAPTER.validate_python({**PYTHON_SUCCEEDED, "status": status})


@pytest.mark.parametrize(
    "model,payload,status",
    [
        (PythonSucceeded, PYTHON_SUCCEEDED, "blocked"),
        (PythonBlocked, PYTHON_BLOCKED, "failed"),
        (PythonFailed, PYTHON_FAILED, "succeeded"),
    ],
)
def test_python_models_reject_wrong_status(model, payload, status):
    with pytest.raises(ValidationError, match="literal_error"):
        model.model_validate({**payload, "status": status})


@pytest.mark.parametrize(
    "payload,field,invalid",
    [
        (PYTHON_SUCCEEDED, "observation", 1),
        (PYTHON_SUCCEEDED, "limitations", "none"),
        (PYTHON_BLOCKED, "explanation", None),
        (PYTHON_BLOCKED, "required_input", True),
        (PYTHON_FAILED, "error", "timeout"),
    ],
)
def test_python_variant_fields_are_strictly_typed(payload, field, invalid):
    with pytest.raises(ValidationError):
        PYTHON_ADAPTER.validate_python({**payload, field: invalid})


@pytest.mark.parametrize(
    "payload",
    [
        {**PYTHON_SUCCEEDED, "explanation": "wrong branch"},
        {**PYTHON_BLOCKED, "observation": "wrong branch"},
        {**PYTHON_FAILED, "required_input": "wrong branch"},
    ],
)
def test_python_discriminator_rejects_fields_from_other_branches(payload):
    with pytest.raises(ValidationError, match="extra_forbidden"):
        PYTHON_ADAPTER.validate_python(payload)


def test_python_failure_reuses_structured_tool_error():
    result = PYTHON_ADAPTER.validate_python(PYTHON_FAILED)
    assert isinstance(result, PythonFailed)
    assert isinstance(result.error, ToolError)
    assert result.error.code == "query_timeout"


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
    payload = {**PYTHON_FAILED, "error": {**ERROR, "code": code}}
    result = PYTHON_ADAPTER.validate_python(payload)
    assert result.error.code == code
    assert PYTHON_ADAPTER.validate_json(result.model_dump_json()) == result


@pytest.mark.parametrize("code", ["python_timeout", "chart_error", "environment_missing"])
def test_unapproved_python_error_names_remain_rejected(code):
    with pytest.raises(ValidationError, match="literal_error"):
        ToolError.model_validate({**ERROR, "code": code})


def test_outcome_references_accept_existing_non_v4_ids():
    assert ADAPTER.validate_python({**SUCCEEDED, "evidence_ids": [EXISTING_ID]}).evidence_ids == [EXISTING_ID]
    result = PYTHON_ADAPTER.validate_python(
        {**PYTHON_SUCCEEDED, "evidence_ids": [EXISTING_ID], "chart_artifact_ids": [EXISTING_ID]}
    )
    assert result.evidence_ids == [EXISTING_ID]
    assert result.chart_artifact_ids == [EXISTING_ID]


def test_sql_success_still_requires_nonempty_evidence():
    with pytest.raises(ValidationError, match="at least 1 item"):
        ADAPTER.validate_python({**SUCCEEDED, "evidence_ids": []})


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
                    "block_id": "claim", "kind": "data_claim",
                    "spans": [
                        {"kind": "value", "target": {
                            "kind": "cell", "evidence_id": ID,
                            "row_locator": 0, "column_ordinal": 0,
                        }, "format": "exact"},
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
                "spans": [{"kind": "value", "target": {
                    "kind": "metadata", "evidence_id": ID, "field": "row_count",
                }, "format": "exact"}],
                "supports": [],
            },
            "suggestions": [],
        },
        "evidence_ids": [ID],
        "chart_artifact_ids": [],
    }
    assert ActionOutcome.model_validate(payload).evidence_ids == [ID]
