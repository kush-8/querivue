import json

import pytest
from pydantic import ValidationError

from querivue_agent.contracts.tools import (
    ExecutePythonRequest,
    ExecuteQueryRequest,
    InspectEvidenceRequest,
    InspectTableRequest,
    PreviewRowsRequest,
)


TABLE_ID = "6b085fd1-4c78-4b85-96c9-a201ce5e935c"
EVIDENCE_ID = "d816d53d-eac8-4d98-978e-97c1bd81f127"
EXISTING_ID = "123e4567-e89b-12d3-a456-426614174000"
DECIMAL = {
    "kind": "decimal",
    "value": "12345678901234567890.123456789012345678",
    "precision": 38,
    "scale": 18,
}


def evidence_output(name="derived"):
    return {
        "name": name,
        "kind": "evidence",
        "description": "Derived table",
        "shape": "table",
        "columns": [{"name": "value", "type": {"tag": "float64"}, "nullable": False}],
    }


def chart_output(name="trend", evidence_id=EXISTING_ID):
    return {
        "name": name,
        "kind": "chart",
        "title": "Trend",
        "description": "Derived trend",
        "series": [{
            "label": "Value",
            "evidence_id": evidence_id,
            "ordering": [],
            "scales": {"y": "linear"},
            "columns": {"x": "date", "y": "value"},
        }],
        "units": {"value": "USD"},
        "analysis_timezone": None,
        "limitations": [],
    }


@pytest.mark.parametrize(
    "model,payload",
    [
        (InspectTableRequest, {"table_id": TABLE_ID}),
        (PreviewRowsRequest, {"table_id": TABLE_ID, "columns": ['total "gross"', "顧客 名"], "limit": 25}),
        (PreviewRowsRequest, {"table_id": TABLE_ID, "columns": None, "limit": 1}),
        (InspectEvidenceRequest, {"evidence_id": EVIDENCE_ID}),
        (ExecuteQueryRequest, {"sql": "SELECT :amount", "parameters": {"amount": DECIMAL}}),
        (ExecutePythonRequest, {"code": "result = 1", "input_evidence_ids": [EXISTING_ID], "outputs": []}),
    ],
)
def test_tool_requests_round_trip_representative_protocol_shapes(model, payload):
    result = model.model_validate(payload)
    assert result.model_dump() == payload
    assert model.model_validate_json(json.dumps(payload)) == result


def test_explicit_preview_columns_are_nonempty_and_exactly_unique():
    for columns in ([], ["name", "name"]):
        with pytest.raises(ValidationError):
            PreviewRowsRequest.model_validate({"table_id": TABLE_ID, "columns": columns, "limit": 1})

    request = PreviewRowsRequest.model_validate(
        {"table_id": TABLE_ID, "columns": ["Name", "name"], "limit": 1}
    )
    assert request.columns == ["Name", "name"]


def test_parameter_names_are_casefold_unique_without_rewriting_values():
    with pytest.raises(ValidationError, match="case-insensitively"):
        ExecuteQueryRequest.model_validate({
            "sql": "SELECT :Name",
            "parameters": {
                "Name": {"kind": "int64", "value": "1"},
                "name": {"kind": "int64", "value": "2"},
            },
        })

    parameters = {"Straße": {"kind": "string", "value": "kept"}}
    request = ExecuteQueryRequest.model_validate({"sql": "SELECT :value", "parameters": parameters})
    assert request.model_dump()["parameters"] == parameters


def test_tool_models_reject_runtime_authority_and_invalid_nested_scalar():
    with pytest.raises(ValidationError, match="extra_forbidden"):
        ExecutePythonRequest.model_validate({
            "code": "pass",
            "input_evidence_ids": [EXISTING_ID],
            "outputs": [],
            "authority": "execute",
        })
    with pytest.raises(ValidationError):
        ExecuteQueryRequest.model_validate({
            "sql": "SELECT :value",
            "parameters": {"value": {"kind": "int64", "value": 1}},
        })


def test_python_outputs_bind_unique_names_and_chart_inputs():
    request = ExecutePythonRequest.model_validate({
        "code": "pass",
        "input_evidence_ids": [EXISTING_ID],
        "outputs": [evidence_output(), chart_output()],
    })
    assert [output.kind for output in request.outputs] == ["evidence", "chart"]

    with pytest.raises(ValidationError, match="output names"):
        ExecutePythonRequest.model_validate({
            "code": "pass",
            "input_evidence_ids": [EXISTING_ID],
            "outputs": [evidence_output("same"), chart_output("same")],
        })
    with pytest.raises(ValidationError, match="declared as an input"):
        ExecutePythonRequest.model_validate({
            "code": "pass",
            "input_evidence_ids": [EXISTING_ID],
            "outputs": [chart_output(evidence_id=TABLE_ID)],
        })
