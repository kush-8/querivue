import json
from copy import deepcopy

import pytest
from pydantic import TypeAdapter, ValidationError

from querivue_agent.contracts.evidence import (
    ChartDeclaration,
    EvidenceDeclaration,
    OutputDeclaration,
)


V4_ID = "6b085fd1-4c78-4b85-96c9-a201ce5e935c"
V1_ID = "123e4567-e89b-12d3-a456-426614174000"
ADAPTER = TypeAdapter(OutputDeclaration)

SIMPLE_TAGS = [
    "boolean", "int64", "uint64", "float64", "string", "date", "time",
    "timestamp", "timestamptz",
]


def column(name="value", column_type=None, nullable=False):
    return {
        "name": name,
        "type": column_type or {"tag": "string"},
        "nullable": nullable,
    }


EVIDENCE = {
    "name": "result_1",
    "kind": "evidence",
    "description": "  Résultat 世界  ",
    "shape": "table",
    "columns": [column()],
}
CHART = {
    "name": "chart_1",
    "kind": "chart",
    "title": "  Revenue 世界  ",
    "description": "Trend by month",
    "series": [{
        "label": "Gross revenue",
        "evidence_id": V1_ID,
        "ordering": [{"column": "month", "direction": "asc"}],
        "scales": {"y": "linear"},
        "columns": {"x": "month", "y_value": "gross revenue"},
    }],
    "units": {"gross revenue": "USD"},
    "analysis_timezone": "Not/A_Validated_Zone",
    "limitations": ["Partial month"],
}


@pytest.mark.parametrize(
    "payload,model", [(EVIDENCE, EvidenceDeclaration), (CHART, ChartDeclaration)]
)
def test_output_declarations_round_trip_native_and_json(payload, model):
    result = ADAPTER.validate_python(payload)
    assert isinstance(result, model)
    assert result.model_dump() == payload
    assert ADAPTER.validate_json(json.dumps(payload)) == result
    assert ADAPTER.validate_json(result.model_dump_json()) == result


@pytest.mark.parametrize("tag", SIMPLE_TAGS)
def test_every_simple_column_type_tag(tag):
    result = EvidenceDeclaration.model_validate(
        {**EVIDENCE, "columns": [column(column_type={"tag": tag})]}
    )
    assert result.columns[0].type.tag == tag


@pytest.mark.parametrize("precision,scale", [(1, 0), (1, 1), (38, 0), (38, 38)])
def test_decimal_precision_and_scale_boundaries(precision, scale):
    payload = {
        **EVIDENCE,
        "columns": [column(column_type={
            "tag": "decimal", "precision": precision, "scale": scale,
        })],
    }
    assert EvidenceDeclaration.model_validate(payload).columns[0].type.scale == scale


@pytest.mark.parametrize(
    "column_type",
    [
        {"tag": "decimal", "precision": 0, "scale": 0},
        {"tag": "decimal", "precision": 39, "scale": 0},
        {"tag": "decimal", "precision": 2, "scale": -1},
        {"tag": "decimal", "precision": 2, "scale": 3},
        {"tag": "decimal", "precision": True, "scale": 0},
        {"tag": "decimal", "precision": 2, "scale": 1.0},
        {"tag": "binary"},
        {"tag": "string", "precision": 1},
    ],
)
def test_invalid_or_unsupported_column_types_are_rejected(column_type):
    with pytest.raises(ValidationError):
        EvidenceDeclaration.model_validate(
            {**EVIDENCE, "columns": [column(column_type=column_type)]}
        )


@pytest.mark.parametrize("name", ["A", "a0", "Result_1", "z_"])
def test_output_names_are_ascii_identifiers(name):
    assert EvidenceDeclaration.model_validate({**EVIDENCE, "name": name}).name == name


@pytest.mark.parametrize(
    "name", ["", "_result", "1result", "has-dash", "two words", "évidence", 1, True]
)
def test_invalid_output_identifiers_are_rejected(name):
    with pytest.raises(ValidationError):
        EvidenceDeclaration.model_validate({**EVIDENCE, "name": name})


@pytest.mark.parametrize("field", ["name", "kind", "description", "shape", "columns"])
def test_evidence_fields_are_required(field):
    payload = deepcopy(EVIDENCE)
    del payload[field]
    with pytest.raises(ValidationError, match="Field required"):
        EvidenceDeclaration.model_validate(payload)


@pytest.mark.parametrize(
    "change",
    [
        {"kind": "artifact"}, {"shape": "vector"}, {"description": " \t"},
        {"columns": []}, {"columns": "value"},
        {"columns": [column(nullable=1)]},
        {"columns": [column(name="")]},
    ],
)
def test_evidence_shape_and_strict_types(change):
    with pytest.raises(ValidationError):
        EvidenceDeclaration.model_validate({**EVIDENCE, **change})


def test_duplicate_evidence_column_names_are_rejected():
    with pytest.raises(ValidationError, match="column names must be unique"):
        EvidenceDeclaration.model_validate(
            {**EVIDENCE, "columns": [column("same"), column("same", nullable=True)]}
        )


def test_declarations_forbid_unknown_fields_at_every_level():
    with pytest.raises(ValidationError, match="extra_forbidden"):
        EvidenceDeclaration.model_validate({**EVIDENCE, "extra": True})
    nested = deepcopy(EVIDENCE)
    nested["columns"][0]["extra"] = True
    with pytest.raises(ValidationError, match="extra_forbidden"):
        EvidenceDeclaration.model_validate(nested)
    chart = deepcopy(CHART)
    chart["series"][0]["ordering"][0]["extra"] = True
    with pytest.raises(ValidationError, match="extra_forbidden"):
        ChartDeclaration.model_validate(chart)


@pytest.mark.parametrize(
    "field", [
        "name", "kind", "title", "description", "series", "units",
        "analysis_timezone", "limitations",
    ]
)
def test_chart_fields_are_required(field):
    payload = deepcopy(CHART)
    del payload[field]
    with pytest.raises(ValidationError, match="Field required"):
        ChartDeclaration.model_validate(payload)


@pytest.mark.parametrize(
    "change",
    [
        {"kind": "evidence"}, {"title": "\n"}, {"description": ""},
        {"series": []}, {"units": {"y": " "}},
        {"analysis_timezone": 1}, {"limitations": [""]},
    ],
)
def test_chart_top_level_validation(change):
    with pytest.raises(ValidationError):
        ChartDeclaration.model_validate({**CHART, **change})


@pytest.mark.parametrize(
    "field,value",
    [
        ("label", " "), ("evidence_id", V1_ID.upper()), ("evidence_id", 1),
        ("ordering", [{"column": "", "direction": "asc"}]),
        ("ordering", [{"column": "month", "direction": "ascending"}]),
        ("scales", {"y": "symlog"}), ("scales", {"": "linear"}),
        ("columns", {}), ("columns", {"x-axis": "month"}),
        ("columns", {"x": ""}),
    ],
)
def test_chart_series_validation(field, value):
    payload = deepcopy(CHART)
    payload["series"][0][field] = value
    with pytest.raises(ValidationError):
        ChartDeclaration.model_validate(payload)


def test_chart_accepts_v1_reference_unicode_and_unchecked_bindings():
    payload = deepcopy(CHART)
    payload["series"][0]["label"] = "売上 📈"
    payload["series"][0]["evidence_id"] = V1_ID
    payload["series"][0]["columns"] = {"x": "not verified here"}
    payload["analysis_timezone"] = "Definitely/Not-IANA"
    result = ChartDeclaration.model_validate(payload)
    assert result.series[0].evidence_id == V1_ID
    assert result.analysis_timezone == "Definitely/Not-IANA"


@pytest.mark.parametrize("payload", [{**EVIDENCE, "kind": "chart"}, {**CHART, "kind": "evidence"}])
def test_discriminator_does_not_accept_the_wrong_shape(payload):
    with pytest.raises(ValidationError):
        ADAPTER.validate_python(payload)
