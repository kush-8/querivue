import json
from copy import deepcopy

import pytest
from pydantic import TypeAdapter, ValidationError

from querivue_agent.contracts.actions import (
    Action, AnalysisConstraints, AnswerAction, DateWindow, PythonAction, SQLAction,
)


ACTION_ID = "123e4567-e89b-42d3-a456-426614174000"
TABLE_ID = "123e4567-e89b-12d3-a456-426614174000"
EVIDENCE_ID = "d816d53d-eac8-4d98-978e-97c1bd81f127"
OTHER_ID = "4fda9c2e-c392-4c13-a5d8-f9230c209786"
WINDOW = {
    "source_id": TABLE_ID,
    "column": "注文 日",
    "lower": {"kind": "date", "value": "2025-01-01"},
    "upper": {"kind": "date", "value": "2025-12-31"},
    "lower_inclusive": True,
    "upper_inclusive": False,
}
CONSTRAINTS = {
    "metric_definitions": {"revenue": "  総売上  "},
    "filters": ["status = paid"],
    "date_windows": [WINDOW],
    "analysis_timezone": "Asia/Kolkata",
    "grain": "month",
    "units": {"revenue": "INR"},
}
SQL = {
    "action_id": ACTION_ID,
    "type": "sql",
    "objective": "Compute revenue",
    "table_ids": [TABLE_ID],
    "input_evidence_ids": [],
    "constraints": CONSTRAINTS,
}
PYTHON = {
    "action_id": ACTION_ID,
    "type": "python",
    "objective": "Model trend",
    "input_evidence_ids": [EVIDENCE_ID],
    "constraints": CONSTRAINTS,
    "required_outputs": ["evidence", "chart"],
}
ANSWER = {
    "action_id": ACTION_ID,
    "type": "answer",
    "objective": "Explain findings",
    "evidence_ids": [TABLE_ID],
    "chart_artifact_ids": [],
    "constraints": CONSTRAINTS,
}
ADAPTER = TypeAdapter(Action)


@pytest.mark.parametrize(
    "payload,model", [(SQL, SQLAction), (PYTHON, PythonAction), (ANSWER, AnswerAction)]
)
def test_actions_round_trip_python_and_json(payload, model):
    result = ADAPTER.validate_python(payload)
    assert isinstance(result, model)
    assert result.model_dump() == payload
    assert ADAPTER.validate_json(result.model_dump_json()) == result
    assert ADAPTER.validate_json(json.dumps(payload)) == result


@pytest.mark.parametrize("payload", [SQL, PYTHON, ANSWER])
def test_actions_reject_missing_common_and_extra_fields(payload):
    for field in ("action_id", "type", "objective", "constraints"):
        value = deepcopy(payload)
        del value[field]
        with pytest.raises(ValidationError):
            ADAPTER.validate_python(value)
    with pytest.raises(ValidationError, match="extra_forbidden"):
        ADAPTER.validate_python({**payload, "runtime_state": "ready"})


@pytest.mark.parametrize("action_type", ["query", "", None, 1])
def test_action_union_rejects_unknown_type(action_type):
    with pytest.raises(ValidationError):
        ADAPTER.validate_python({**SQL, "type": action_type})


@pytest.mark.parametrize("invalid", ["", " \t\n", 1, True, None, b"text", "\ud800"])
def test_objective_is_strict_nonblank_unicode(invalid):
    with pytest.raises(ValidationError):
        SQLAction.model_validate({**SQL, "objective": invalid})


def test_action_id_requires_canonical_uuid4_but_references_accept_other_versions():
    assert SQLAction.model_validate(SQL).table_ids == [TABLE_ID]
    with pytest.raises(ValidationError):
        SQLAction.model_validate({**SQL, "action_id": TABLE_ID})
    with pytest.raises(ValidationError):
        SQLAction.model_validate({**SQL, "table_ids": [TABLE_ID.upper()]})


def test_sql_accepts_evidence_only_and_requires_some_input():
    result = SQLAction.model_validate({**SQL, "table_ids": [], "input_evidence_ids": [TABLE_ID]})
    assert result.input_evidence_ids == [TABLE_ID]
    with pytest.raises(ValidationError, match="at least one table or evidence"):
        SQLAction.model_validate({**SQL, "table_ids": [], "input_evidence_ids": []})


@pytest.mark.parametrize("field", ["table_ids", "input_evidence_ids"])
def test_sql_input_lists_are_unique(field):
    with pytest.raises(ValidationError, match="unique"):
        SQLAction.model_validate({**SQL, field: [TABLE_ID, TABLE_ID]})


@pytest.mark.parametrize("field", ["input_evidence_ids", "required_outputs"])
def test_python_requires_nonempty_unique_input_and_output_lists(field):
    with pytest.raises(ValidationError):
        PythonAction.model_validate({**PYTHON, field: []})
    value = PYTHON[field][0]
    with pytest.raises(ValidationError, match="unique"):
        PythonAction.model_validate({**PYTHON, field: [value, value]})


@pytest.mark.parametrize("outputs", [["evidence"], ["chart"], ["chart", "evidence"]])
def test_python_accepts_required_output_kinds(outputs):
    assert PythonAction.model_validate({**PYTHON, "required_outputs": outputs}).required_outputs == outputs


@pytest.mark.parametrize("outputs", [["file"], [1], "evidence", ("evidence",)])
def test_python_rejects_invalid_required_outputs(outputs):
    with pytest.raises(ValidationError):
        PythonAction.model_validate({**PYTHON, "required_outputs": outputs})


def test_answer_allows_empty_unique_reference_lists():
    result = AnswerAction.model_validate({**ANSWER, "evidence_ids": [], "chart_artifact_ids": []})
    assert result.evidence_ids == result.chart_artifact_ids == []
    for field in ("evidence_ids", "chart_artifact_ids"):
        with pytest.raises(ValidationError, match="unique"):
            AnswerAction.model_validate({**ANSWER, field: [EVIDENCE_ID, EVIDENCE_ID]})


@pytest.mark.parametrize("field", ["evidence_ids", "chart_artifact_ids"])
def test_answer_reference_fields_are_required_strict_lists(field):
    value = deepcopy(ANSWER)
    del value[field]
    with pytest.raises(ValidationError, match="Field required"):
        AnswerAction.model_validate(value)
    for invalid in (None, EVIDENCE_ID, (EVIDENCE_ID,), [1], ["bad"]):
        with pytest.raises(ValidationError):
            AnswerAction.model_validate({**ANSWER, field: invalid})


def test_constraints_round_trip_and_all_fields_are_required():
    result = AnalysisConstraints.model_validate(CONSTRAINTS)
    assert result.model_dump() == CONSTRAINTS
    for field in CONSTRAINTS:
        value = deepcopy(CONSTRAINTS)
        del value[field]
        with pytest.raises(ValidationError, match="Field required"):
            AnalysisConstraints.model_validate(value)
    with pytest.raises(ValidationError, match="extra_forbidden"):
        AnalysisConstraints.model_validate({**CONSTRAINTS, "limit": 10})


@pytest.mark.parametrize(
    "field,invalid",
    [
        ("metric_definitions", {"": "definition"}),
        ("metric_definitions", {"metric": " "}),
        ("filters", [""]),
        ("analysis_timezone", " \n"),
        ("grain", ""),
        ("units", {"revenue": " "}),
    ],
)
def test_constraint_text_fields_are_nonblank(field, invalid):
    with pytest.raises(ValidationError):
        AnalysisConstraints.model_validate({**CONSTRAINTS, field: invalid})


def test_nullable_constraint_fields_are_explicitly_nullable():
    result = AnalysisConstraints.model_validate(
        {**CONSTRAINTS, "analysis_timezone": None, "grain": None}
    )
    assert result.analysis_timezone is result.grain is None


def test_date_window_accepts_heterogeneous_bounds_without_ordering_validation():
    payload = {
        **WINDOW,
        "lower": {"kind": "int64", "value": "10"},
        "upper": {"kind": "date", "value": "2020-01-01"},
    }
    assert DateWindow.model_validate(payload).model_dump() == payload


@pytest.mark.parametrize("field", ["lower_inclusive", "upper_inclusive"])
@pytest.mark.parametrize("invalid", [0, 1, "true", None])
def test_date_window_inclusivity_is_strict_boolean(field, invalid):
    with pytest.raises(ValidationError):
        DateWindow.model_validate({**WINDOW, field: invalid})


def test_date_window_reuses_scalar_and_canonical_reference_validation():
    with pytest.raises(ValidationError):
        DateWindow.model_validate({**WINDOW, "lower": {"kind": "date", "value": "2025-02-30"}})
    with pytest.raises(ValidationError):
        DateWindow.model_validate({**WINDOW, "source_id": TABLE_ID.upper()})
