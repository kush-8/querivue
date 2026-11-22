import json
from copy import deepcopy

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
DECIMAL = {"kind": "decimal", "value": "12345678901234567890.123456789012345678", "precision": 38, "scale": 18}


@pytest.mark.parametrize(
    "model,payload",
    [
        (InspectTableRequest, {"table_id": TABLE_ID}),
        (
            PreviewRowsRequest,
            {"table_id": TABLE_ID, "columns": ['total "gross"', "顧客 名"], "limit": 25},
        ),
        (PreviewRowsRequest, {"table_id": TABLE_ID, "columns": None, "limit": 1}),
        (InspectEvidenceRequest, {"evidence_id": EVIDENCE_ID}),
        (ExecutePythonRequest, {"code": "result = 1", "input_evidence_ids": [EXISTING_ID], "outputs": []}),
        (
            ExecuteQueryRequest,
            {"sql": 'SELECT "総額" FROM "注文 表" WHERE id = :amount', "parameters": {"amount": DECIMAL}},
        ),
    ],
)
def test_requests_round_trip_python_and_json(model, payload):
    result = model.model_validate(payload)
    assert result.model_dump() == payload
    assert model.model_validate_json(result.model_dump_json()) == result
    assert model.model_validate_json(json.dumps(payload)) == result


@pytest.mark.parametrize(
    "model,payload,required_fields",
    [
        (InspectTableRequest, {"table_id": TABLE_ID}, ["table_id"]),
        (
            PreviewRowsRequest,
            {"table_id": TABLE_ID, "columns": None, "limit": 1},
            ["table_id", "columns", "limit"],
        ),
        (InspectEvidenceRequest, {"evidence_id": EVIDENCE_ID}, ["evidence_id"]),
        (ExecuteQueryRequest, {"sql": "SELECT 1", "parameters": {}}, ["sql", "parameters"]),
        (
            ExecutePythonRequest,
            {"code": "result = 1", "input_evidence_ids": [EXISTING_ID], "outputs": []},
            ["code", "input_evidence_ids", "outputs"],
        ),
    ],
)
def test_all_fields_are_required_and_extra_fields_are_forbidden(model, payload, required_fields):
    for field in required_fields:
        missing = deepcopy(payload)
        del missing[field]
        with pytest.raises(ValidationError, match="Field required"):
            model.model_validate(missing)
    with pytest.raises(ValidationError, match="extra_forbidden"):
        model.model_validate({**payload, "unexpected": True})


@pytest.mark.parametrize(
    "model,field,payload",
    [
        (InspectTableRequest, "table_id", {"table_id": TABLE_ID}),
        (
            PreviewRowsRequest,
            "table_id",
            {"table_id": TABLE_ID, "columns": None, "limit": 1},
        ),
        (InspectEvidenceRequest, "evidence_id", {"evidence_id": EVIDENCE_ID}),
    ],
)
@pytest.mark.parametrize("invalid", ["bad", TABLE_ID.upper(), 1, True, None])
def test_ids_reuse_strict_canonical_uuid(model, field, payload, invalid):
    with pytest.raises(ValidationError):
        model.model_validate({**payload, field: invalid})


@pytest.mark.parametrize(
    "model,field,payload",
    [
        (InspectTableRequest, "table_id", {"table_id": EXISTING_ID}),
        (PreviewRowsRequest, "table_id", {"table_id": EXISTING_ID, "columns": None, "limit": 1}),
        (InspectEvidenceRequest, "evidence_id", {"evidence_id": EXISTING_ID}),
    ],
)
def test_existing_reference_ids_accept_canonical_non_v4_uuid(model, field, payload):
    assert getattr(model.model_validate(payload), field) == EXISTING_ID


@pytest.mark.parametrize("invalid", [0, -1, True, 1.0, "1", None])
def test_preview_limit_is_a_strict_positive_integer(invalid):
    with pytest.raises(ValidationError):
        PreviewRowsRequest.model_validate(
            {"table_id": TABLE_ID, "columns": None, "limit": invalid}
        )


@pytest.mark.parametrize(
    "invalid",
    ["name", ("name",), {"name": True}, [1], [True], [None], [""], [" \t\n"]],
)
def test_preview_columns_are_a_strict_list_of_nonblank_names_or_null(invalid):
    with pytest.raises(ValidationError):
        PreviewRowsRequest.model_validate(
            {"table_id": TABLE_ID, "columns": invalid, "limit": 1}
        )


@pytest.mark.parametrize("invalid", ["", " \t\n\u2003", 1, True, None, b"SELECT 1"])
def test_sql_is_a_strict_nonblank_string(invalid):
    with pytest.raises(ValidationError):
        ExecuteQueryRequest.model_validate({"sql": invalid, "parameters": {}})


@pytest.mark.parametrize(
    "parameters",
    [None, [], (), "amount", {1: DECIMAL}, {"": DECIMAL}, {" \t": DECIMAL}],
)
def test_parameters_are_a_strict_map_with_nonblank_string_names(parameters):
    with pytest.raises(ValidationError):
        ExecuteQueryRequest.model_validate({"sql": "SELECT 1", "parameters": parameters})


@pytest.mark.parametrize(
    "scalar",
    [
        {"kind": "decimal", "value": "1.0", "precision": 3, "scale": 2},
        {"kind": "float64", "value": 1},
        {"kind": "string", "value": b"text"},
        {"kind": "unknown", "value": "x"},
        {"kind": "int64", "value": "1", "extra": True},
    ],
)
def test_parameters_reuse_nested_typed_scalar_validation(scalar):
    with pytest.raises(ValidationError):
        ExecuteQueryRequest.model_validate(
            {"sql": "SELECT :value", "parameters": {"value": scalar}}
        )
