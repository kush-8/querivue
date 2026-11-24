import json
from uuid import UUID

import pytest
from pydantic import TypeAdapter, ValidationError

from querivue_agent.contracts.content import (
    CellTarget, ChartSpan, ContentSpan, Draft, MetadataTarget, SupportTarget, TextSpan,
    ValueSpan, ValueTarget,
)


ID = "123e4567-e89b-12d3-a456-426614174000"
OTHER_ID = "d816d53d-eac8-4d98-978e-97c1bd81f127"
CELL = {"kind": "cell", "evidence_id": ID, "row_locator": 0, "column_ordinal": 2}
METADATA = {"kind": "metadata", "evidence_id": ID, "field": "row_count"}
SUPPORTS = [
    CELL,
    METADATA,
    {"kind": "coverage", "evidence_id": ID},
    {"kind": "chart", "chart_artifact_id": OTHER_ID},
    {"kind": "context", "context_ref": OTHER_ID},
]
SPANS = [
    {"kind": "text", "text": " Résultat 世界 "},
    {"kind": "value", "target": CELL, "format": "fixed_2"},
    {"kind": "chart", "chart_artifact_id": OTHER_ID},
]
BLOCK = {"block_id": "claim-1", "kind": "data_claim", "spans": SPANS, "supports": SUPPORTS}
DRAFT = {
    "blocks": [BLOCK],
    "unmet_deliverables": [
        {"description": "Need breakdown", "reason": "Not supplied", "required_evidence": "Region table"}
    ],
}


@pytest.mark.parametrize("payload", SUPPORTS)
def test_support_targets_round_trip_and_are_discriminated(payload):
    adapter = TypeAdapter(SupportTarget)
    result = adapter.validate_python(payload)
    assert adapter.validate_json(json.dumps(payload)) == result
    assert result.model_dump() == payload


@pytest.mark.parametrize("payload,model", [(SPANS[0], TextSpan), (SPANS[1], ValueSpan), (SPANS[2], ChartSpan)])
def test_content_spans_round_trip(payload, model):
    adapter = TypeAdapter(ContentSpan)
    result = adapter.validate_python(payload)
    assert isinstance(result, model)
    assert adapter.validate_json(result.model_dump_json()) == result


def test_draft_round_trip_python_and_json():
    result = Draft.model_validate(DRAFT)
    assert result.model_dump() == DRAFT
    assert Draft.model_validate_json(result.model_dump_json()) == result


@pytest.mark.parametrize("target", [CELL, METADATA])
def test_value_target_accepts_only_cell_and_metadata(target):
    assert TypeAdapter(ValueTarget).validate_python(target).model_dump() == target


@pytest.mark.parametrize("target", SUPPORTS[2:])
def test_value_target_rejects_other_support_target_kinds(target):
    with pytest.raises(ValidationError):
        TypeAdapter(ValueTarget).validate_python(target)


@pytest.mark.parametrize("field", ["row_locator", "column_ordinal"])
@pytest.mark.parametrize("invalid", [-1, 1.0, "1", True, None])
def test_cell_indices_are_strict_nonnegative_integers(field, invalid):
    with pytest.raises(ValidationError):
        CellTarget.model_validate({**CELL, field: invalid})


def test_metadata_field_is_exact_literal():
    assert MetadataTarget.model_validate(METADATA).field == "row_count"
    with pytest.raises(ValidationError):
        MetadataTarget.model_validate({**METADATA, "field": "columns"})


@pytest.mark.parametrize("payload", SUPPORTS)
def test_targets_accept_supplied_canonical_v1_uuid(payload):
    assert TypeAdapter(SupportTarget).validate_python(payload)
    id_field = "evidence_id" if "evidence_id" in payload else next(k for k in payload if k.endswith("_id") or k == "context_ref")
    with pytest.raises(ValidationError):
        TypeAdapter(SupportTarget).validate_python({**payload, id_field: ID.upper()})


def test_text_span_is_nonempty_unicode_and_limited_by_utf8_bytes():
    assert TextSpan.model_validate({"kind": "text", "text": " "}).text == " "
    assert TextSpan.model_validate({"kind": "text", "text": "é" * 1024})
    for text in ["", "é" * 1024 + "a", "\ud800", 1]:
        with pytest.raises(ValidationError):
            TextSpan.model_validate({"kind": "text", "text": text})


def test_block_bounds_ids_and_supports_rules():
    assert Draft.model_validate({"blocks": [{**BLOCK, "supports": []}], "unmet_deliverables": []})
    assert Draft.model_validate({"blocks": [{**BLOCK, "spans": SPANS[:1] * 32}], "unmet_deliverables": []})
    for change in [
        {"block_id": ""}, {"block_id": "é" * 33}, {"spans": []}, {"spans": SPANS[:1] * 33},
        {"kind": "claim"}, {"supports": None},
    ]:
        with pytest.raises(ValidationError):
            Draft.model_validate({"blocks": [{**BLOCK, **change}], "unmet_deliverables": []})


def test_draft_count_and_uniqueness_boundaries():
    blocks = [{**BLOCK, "block_id": f"b{i}", "spans": SPANS[:1] * 8} for i in range(16)]
    assert Draft.model_validate({"blocks": blocks, "unmet_deliverables": []})
    with pytest.raises(ValidationError, match="128 spans"):
        Draft.model_validate({"blocks": [{**blocks[0], "spans": SPANS[:1] * 9}, *blocks[1:]], "unmet_deliverables": []})
    with pytest.raises(ValidationError):
        Draft.model_validate({"blocks": blocks + [{**BLOCK, "block_id": "b16"}], "unmet_deliverables": []})
    with pytest.raises(ValidationError, match="unique"):
        Draft.model_validate({"blocks": [BLOCK, BLOCK], "unmet_deliverables": []})


def test_distinct_target_limit_counts_support_and_automatic_union():
    supports = [
        {"kind": "context", "context_ref": str(UUID(int=i))}
        for i in range(1, 129)
    ]
    block = {**BLOCK, "spans": [{"kind": "chart", "chart_artifact_id": OTHER_ID}], "supports": supports}
    with pytest.raises(ValidationError, match="128 distinct targets"):
        Draft.model_validate({"blocks": [block], "unmet_deliverables": []})
    block["supports"][-1] = {"kind": "chart", "chart_artifact_id": OTHER_ID}
    assert Draft.model_validate({"blocks": [block], "unmet_deliverables": []})


def test_unmet_deliverables_bounds_and_utf8_limits():
    item = DRAFT["unmet_deliverables"][0]
    assert Draft.model_validate({"blocks": [BLOCK], "unmet_deliverables": [item] * 16})
    with pytest.raises(ValidationError):
        Draft.model_validate({"blocks": [BLOCK], "unmet_deliverables": [item] * 17})
    for field in item:
        for invalid in ["", " ", "é" * 513, 1]:
            with pytest.raises(ValidationError):
                Draft.model_validate({"blocks": [BLOCK], "unmet_deliverables": [{**item, field: invalid}]})
