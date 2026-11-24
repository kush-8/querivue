import json
from copy import deepcopy

import pytest
from pydantic import TypeAdapter, ValidationError

from querivue_agent.contracts.evidence import (
    CellLocator,
    ChartArtifact,
    EvidenceCandidate,
    EvidenceColumn,
    EvidenceRef,
    Producer,
    ProfileProducer,
    PythonProducer,
    SQLInspectedEvidence,
    SQLProducer,
    TabularEvidence,
    TabularPreview,
)


V4 = "6b085fd1-4c78-4b85-96c9-a201ce5e935c"
V4B = "79364864-0736-4e18-a3a0-6e2ff4c4ae21"
V1 = "123e4567-e89b-12d3-a456-426614174000"
V1B = "123e4567-e89b-12d3-a456-426614174001"
HASH = "a" * 64


CONSTRAINTS = {
    "metric_definitions": {},
    "filters": [],
    "date_windows": [],
    "analysis_timezone": None,
    "grain": None,
    "units": {},
}


def column(ordinal=0, name="amount", nullable=True):
    return {
        "ordinal": ordinal,
        "name": name,
        "original_label": "  Amount 世界  ",
        "original_ordinal": 2,
        "type": {"tag": "decimal", "precision": 10, "scale": 2},
        "nullable": nullable,
    }


def preview(rows=None, locators=None, shortened=None, full=1, truncated=False):
    rows = [[" 1.20 "]] if rows is None else rows
    locators = [0] if locators is None else locators
    shortened = [] if shortened is None else shortened
    return {
        "columns": [column()],
        "rows": rows,
        "row_locators": locators,
        "full_row_count": full,
        "returned_row_count": len(rows),
        "effective_limit": 10,
        "ordering": "query_defined",
        "truncated": truncated,
        "shortened_cells": shortened,
    }


def artifact(media="application/vnd.apache.parquet"):
    return {
        "artifact_id": V1B,
        "storage_ref": V1,
        "media_type": media,
        "size_bytes": 12,
        "sha256": HASH,
        "environment_manifest_id": V1,
    }


def sql_producer():
    return {
        "kind": "sql",
        "run_id": V1,
        "action_id": V4,
        "operation_id": V1B,
        "attempt": 1,
        "sql": " SELECT 1 ",
        "parameters": {"label": {"kind": "string", "value": " 世界 "}},
        "table_ids": [V1],
        "input_evidence_ids": [],
        "constraints": CONSTRAINTS,
        "environment_manifest_id": V1,
        "policy_version": " p1 ",
    }


def python_producer():
    return {
        "kind": "python",
        "run_id": V1,
        "action_id": V4,
        "operation_id": V1B,
        "attempt": 1,
        "script_ref": V1,
        "script_hash": HASH,
        "input_evidence_ids": [V1B],
        "action_input_evidence_ids": [V1B, V1],
        "constraints": CONSTRAINTS,
        "random_seed": 0,
        "method_parameters": {"alpha": {"kind": "float64", "value": 0.5}},
        "environment_manifest_id": V1,
        "policy_version": "p1",
    }


def profile_producer():
    return {
        "kind": "ingestion_profile",
        "dataset_id": V1,
        "snapshot_id": V4,
        "table_id": V1B,
        "settings_hash": HASH,
        "profile_schema_version": "v1",
        "environment_manifest_id": V1,
    }


def tabular(producer=None):
    producer = sql_producer() if producer is None else producer
    dependency = {"dataset_id": V1, "snapshot_id": V4}
    return {
        "evidence_id": V1B,
        "content_hash": HASH,
        "artifact": artifact(),
        "columns": [column()],
        "row_count": 1,
        "preview": preview(),
        "producer": producer,
        "dependencies": [dependency],
    }


def chart_declaration():
    return {
        "name": "chart_1",
        "kind": "chart",
        "title": "Revenue",
        "description": "Trend",
        "series": [{
            "label": "Series",
            "evidence_id": V1B,
            "ordering": [],
            "scales": {"y": "linear"},
            "columns": {"x": "amount"},
        }],
        "units": {},
        "analysis_timezone": None,
        "limitations": [],
    }


def test_evidence_column_and_preview_round_trip_preserving_display_text():
    parsed = TabularPreview.model_validate(preview())
    assert parsed.rows == [[" 1.20 "]]
    assert parsed.columns[0].original_label == "  Amount 世界  "
    assert TabularPreview.model_validate_json(json.dumps(preview())) == parsed
    assert isinstance(EvidenceColumn.model_validate(column()), EvidenceColumn)
    assert CellLocator.model_validate({"row_locator": 0, "column_ordinal": 0}).row_locator == 0


@pytest.mark.parametrize(
    "change",
    [
        {"columns": [column(), column(0, "other")], "rows": [["1", "2"]]},
        {"columns": [column(), column(1, "amount")]},
        {"rows": [["1", "2"]]},
        {"row_locators": []},
        {"row_locators": [1], "full_row_count": 1},
        {"returned_row_count": 0},
        {"effective_limit": 0},
        {"truncated": True},
        {"shortened_cells": [{"row_locator": 0, "column_ordinal": 1}], "truncated": True},
        {"shortened_cells": [{"row_locator": 1, "column_ordinal": 0}], "truncated": True},
    ],
)
def test_preview_rejects_broken_schema_counts_and_locator_coverage(change):
    with pytest.raises(ValidationError):
        TabularPreview.model_validate({**preview(), **change})


def test_preview_rejects_nulls_in_nonnullable_columns_and_shortened_null_cells():
    with pytest.raises(ValidationError):
        TabularPreview.model_validate({
            **preview(rows=[[None]]),
            "columns": [column(nullable=False)],
        })
    with pytest.raises(ValidationError):
        TabularPreview.model_validate(preview(
            rows=[[None]],
            shortened=[{"row_locator": 0, "column_ordinal": 0}],
            truncated=True,
        ))


def test_preview_accepts_selected_stable_column_ordinals_and_addresses_shortening_by_ordinal():
    selected = {
        **preview(
            rows=[["first", "shortened"]],
            shortened=[{"row_locator": 0, "column_ordinal": 5}],
            truncated=True,
        ),
        "columns": [column(0, "c0"), column(5, "c5")],
    }
    result = TabularPreview.model_validate(selected)
    assert [item.ordinal for item in result.columns] == [0, 5]

    with pytest.raises(ValidationError):
        TabularPreview.model_validate({
            **selected,
            "shortened_cells": [{"row_locator": 0, "column_ordinal": 1}],
        })
    with pytest.raises(ValidationError):
        TabularPreview.model_validate({**selected, "rows": [["first", None]]})


def test_preview_display_cells_are_bounded_by_utf8_bytes_without_mutation():
    exactly_limit = "é" * 1024
    payload = preview(
        rows=[[exactly_limit]],
        shortened=[{"row_locator": 0, "column_ordinal": 0}],
        truncated=True,
    )
    assert TabularPreview.model_validate(payload).rows == [[exactly_limit]]

    with pytest.raises(ValidationError):
        TabularPreview.model_validate({**payload, "rows": [[exactly_limit + "a"]]})


def test_empty_preview_is_distinct_and_valid():
    empty = preview(rows=[], locators=[], full=0)
    assert TabularPreview.model_validate(empty).rows == []
    with pytest.raises(ValidationError):
        TabularPreview.model_validate({**empty, "full_row_count": 1, "truncated": False})


def test_producer_discriminator_and_strict_provenance():
    adapter = TypeAdapter(Producer)
    cases = [(sql_producer(), SQLProducer), (python_producer(), PythonProducer), (profile_producer(), ProfileProducer)]
    for payload, model in cases:
        result = adapter.validate_python(payload)
        assert isinstance(result, model)
        assert adapter.validate_json(json.dumps(payload)) == result
    with pytest.raises(ValidationError):
        SQLProducer.model_validate({**sql_producer(), "attempt": 0})
    with pytest.raises(ValidationError):
        SQLProducer.model_validate({**sql_producer(), "parameters": {"": {"kind": "null", "value": None}}})
    with pytest.raises(ValidationError):
        PythonProducer.model_validate({**python_producer(), "input_evidence_ids": [V4B]})
    with pytest.raises(ValidationError):
        ProfileProducer.model_validate({**profile_producer(), "settings_hash": "A" * 64})


def test_evidence_ref_requires_nonempty_unique_dependencies():
    payload = {
        "evidence_id": V1,
        "artifact_id": V1B,
        "content_hash": HASH,
        "dependencies": [{"dataset_id": V1, "snapshot_id": V4}],
    }
    assert EvidenceRef.model_validate(payload).artifact_id == V1B
    for dependencies in [[], payload["dependencies"] * 2]:
        with pytest.raises(ValidationError):
            EvidenceRef.model_validate({**payload, "dependencies": dependencies})


def test_tabular_evidence_binds_schema_counts_mime_environment_and_profile_dependency():
    payload = tabular()
    parsed = TabularEvidence.model_validate(payload)
    assert TabularEvidence.model_validate_json(json.dumps(payload)) == parsed
    invalid = [
        {"artifact": artifact("image/png")},
        {"artifact": {**artifact(), "environment_manifest_id": V4B}},
        {"artifact": {**artifact(), "environment_manifest_id": None}},
        {"preview": {**preview(), "columns": [column(name="other")] }},
        {"row_count": 2},
        {"dependencies": []},
    ]
    for change in invalid:
        with pytest.raises(ValidationError):
            TabularEvidence.model_validate({**payload, **change})
    profiled = tabular(profile_producer())
    assert isinstance(TabularEvidence.model_validate(profiled).producer, ProfileProducer)
    with pytest.raises(ValidationError):
        TabularEvidence.model_validate({**profiled, "dependencies": [{"dataset_id": V1, "snapshot_id": V1B}]})


def test_tabular_evidence_binds_selected_preview_columns_to_full_contiguous_schema():
    full_columns = [column(index, f"c{index}") for index in range(6)]
    selected_preview = {
        **preview(rows=[["first", "sixth"]]),
        "columns": [full_columns[0], full_columns[5]],
    }
    payload = {
        **tabular(),
        "columns": full_columns,
        "preview": selected_preview,
    }
    result = TabularEvidence.model_validate(payload)
    assert [item.ordinal for item in result.preview.columns] == [0, 5]

    forged = deepcopy(selected_preview)
    forged["columns"][1]["name"] = "forged"
    with pytest.raises(ValidationError):
        TabularEvidence.model_validate({**payload, "preview": forged})

    out_of_range = deepcopy(selected_preview)
    out_of_range["columns"][1] = column(6, "c6")
    with pytest.raises(ValidationError):
        TabularEvidence.model_validate({**payload, "preview": out_of_range})

    with pytest.raises(ValidationError):
        TabularEvidence.model_validate({
            **payload,
            "columns": [full_columns[0], full_columns[5]],
        })


def test_sql_relation_exists_only_on_authorized_inspected_shape():
    for producer in [sql_producer(), python_producer(), profile_producer()]:
        payload = {**tabular(producer), "sql_relation": " temp_result "}
        assert SQLInspectedEvidence.model_validate(payload).sql_relation == " temp_result "
        with pytest.raises(ValidationError):
            TabularEvidence.model_validate(payload)


def test_evidence_candidate_uses_composition_not_publication_inheritance():
    result = EvidenceCandidate.model_validate({
        "candidate_id": V4,
        "evidence": tabular(),
        "validation_receipt_id": V1,
    })
    assert result.evidence.evidence_id == V1B
    assert not isinstance(result, TabularEvidence)


def test_chart_artifact_binds_png_identity_inputs_and_dependencies():
    payload = {
        "chart_artifact_id": V1,
        "artifact": {**artifact("image/png"), "artifact_id": V1},
        "declaration": chart_declaration(),
        "producer": python_producer(),
        "pixel_width": 1,
        "pixel_height": 9007199254740991,
        "encoder_version": "e1",
        "normalization_version": "n1",
        "backing_evidence_ids": [V1B],
        "dependencies": [{"dataset_id": V1, "snapshot_id": V4}],
    }
    result = ChartArtifact.model_validate(payload)
    assert result.pixel_width == 1
    invalid = [
        {"artifact": {**payload["artifact"], "artifact_id": V1B}},
        {"artifact": {**payload["artifact"], "media_type": "application/vnd.apache.parquet"}},
        {"artifact": {**payload["artifact"], "environment_manifest_id": None}},
        {"pixel_width": 0},
        {"backing_evidence_ids": [V1]},
        {"producer": {**python_producer(), "input_evidence_ids": [V1]}},
        {"dependencies": []},
    ]
    for change in invalid:
        with pytest.raises(ValidationError):
            ChartArtifact.model_validate({**payload, **change})

