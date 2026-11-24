import json
from copy import deepcopy

import pytest
from pydantic import TypeAdapter, ValidationError

from querivue_agent.contracts.catalog import (
    CandidateKey,
    ColumnCatalog,
    ColumnImportSettings,
    DelimitedDialect,
    FileSource,
    ImportPreview,
    ImportSettings,
    ImportSettingsProposal,
    PreparedCandidate,
    PreparedSnapshot,
    PreparedSnapshotPayload,
    SQLiteSource,
    SourceDescriptor,
    SourceSelection,
    TableCatalog,
    TemporalBounds,
    WorksheetSource,
)


V4 = "6b085fd1-4c78-4b85-96c9-a201ce5e935c"
V4B = "79364864-0736-4e18-a3a0-6e2ff4c4ae21"
V1 = "123e4567-e89b-12d3-a456-426614174000"
V1B = "123e4567-e89b-12d3-a456-426614174001"
HASH = "a" * 64


def source(format="csv"):
    return {"kind": "file", "format": format}


def settings(position=0, label="  Amount 世界  ", tag="decimal"):
    column_type = {"tag": tag}
    if tag == "decimal":
        column_type |= {"precision": 10, "scale": 2}
    return {
        "source_position": position,
        "original_label": label,
        "requested_type": column_type,
        "missing_markers": ["", " NA "],
        "decimal_separator": ".",
        "thousands_separator": ",",
        "datetime_format": None,
        "source_timezone": None,
        "conversion_choice": " preserve source meaning ",
    }


def selection(columns=None, format="csv"):
    return {
        "source": source(format),
        "header_present": True,
        "header_row": 1,
        "columns": [settings()] if columns is None else columns,
    }


def proposal(format="csv", columns=None):
    dialect = {
        "encoding": "utf-8",
        "delimiter": "\t" if format == "tsv" else ",",
        "quote": '"',
        "escape": None,
        "strip_bom": True,
    } if format in {"csv", "tsv"} else None
    return {
        "settings_version": " v1 ",
        "source_format": format,
        "selections": [selection(columns=columns, format=format)],
        "dialect": dialect,
    }


def artifact():
    return {
        "artifact_id": V1,
        "storage_ref": V1B,
        "media_type": "application/x-duckdb",
        "size_bytes": 12,
        "sha256": HASH,
        "environment_manifest_id": V1B,
    }


def column_catalog(ordinal=0, column_id=V1, sql_name="amount", position=0):
    return {
        "ordinal": ordinal,
        "source_position": position,
        "column_id": column_id,
        "original_label": "  Amount 世界  ",
        "sql_name": sql_name,
        "type": {"tag": "decimal", "precision": 10, "scale": 2},
        "nullable": True,
        "null_count": 1,
        "settings": settings(position),
        "timezone_provenance_ref": None,
        "temporal_bounds": None,
    }


def table(table_id=V1B):
    return {
        "table_id": table_id,
        "dataset_id": V1,
        "snapshot_id": V4,
        "ordinal": 0,
        "sql_name": " sales ",
        "source": source(),
        "row_count": 2,
        "columns": [column_catalog()],
        "warnings": [" one null "],
        "profile_evidence_ids": [V1B],
        "candidate_keys": [{
            "column_ids": [V1],
            "basis": "verified_unique_non_null",
            "verification_ref": V4B,
        }],
    }


def snapshot_payload():
    return {
        "dataset_id": V1,
        "attempt_id": V4B,
        "snapshot_id": V4,
        "catalog_id": V1B,
        "catalog_hash": HASH,
        "table_ids": [V1B],
        "artifact": artifact(),
        "schema_fingerprint": "b" * 64,
        "environment_manifest_id": V1B,
        "source_format": "csv",
        "settings_hash": "c" * 64,
        "dependencies": [{"dataset_id": V1, "snapshot_id": V4}],
    }


def test_source_descriptors_are_discriminated_strict_metadata():
    adapter = TypeAdapter(SourceDescriptor)
    cases = [
        (source(), FileSource),
        ({"kind": "sqlite", "table_name": " t "}, SQLiteSource),
        ({"kind": "worksheet", "worksheet_name": " S ", "selected_range": " A1:B2 "}, WorksheetSource),
    ]
    for payload, model in cases:
        result = adapter.validate_python(payload)
        assert isinstance(result, model)
        assert adapter.validate_json(json.dumps(payload)) == result
    with pytest.raises(ValidationError):
        adapter.validate_python({**source(), "kind": "url"})
    with pytest.raises(ValidationError):
        adapter.validate_python({**source(), "credential": "secret"})


def test_import_settings_proposal_and_confirmation_are_distinct():
    proposed = ImportSettingsProposal.model_validate(proposal())
    assert proposed.selections[0].columns[0].missing_markers == ["", " NA "]
    confirmed = ImportSettings.model_validate({**proposal(), "confirmation_id": V1})
    assert confirmed.confirmation_id == V1
    with pytest.raises(ValidationError):
        ImportSettingsProposal.model_validate({**proposal(), "confirmation_id": V1})
    with pytest.raises(ValidationError):
        ImportSettings.model_validate({**proposal(columns=[]), "confirmation_id": V1})


@pytest.mark.parametrize(
    "change",
    [
        {"source_position": -1},
        {"source_position": True},
        {"missing_markers": ["", ""]},
        {"decimal_separator": ".."},
        {"decimal_separator": ",", "thousands_separator": ","},
        {"datetime_format": " "},
        {"source_timezone": ""},
        {"conversion_choice": "\t"},
    ],
)
def test_column_import_settings_reject_invalid_boundaries(change):
    with pytest.raises(ValidationError):
        ColumnImportSettings.model_validate({**settings(), **change})


def test_source_selection_header_and_positions_are_consistent():
    assert SourceSelection.model_validate(selection()).header_row == 1
    for change in [
        {"header_present": False},
        {"header_present": True, "header_row": None},
        {"columns": [settings(0), settings(0, "Other")]},
    ]:
        with pytest.raises(ValidationError):
            SourceSelection.model_validate({**selection(), **change})
    assert SourceSelection.model_validate({**selection(columns=[]), "header_present": False, "header_row": None}).columns == []


@pytest.mark.parametrize(
    "payload",
    [
        {**proposal(), "dialect": None},
        {**proposal("tsv"), "dialect": {**proposal("tsv")["dialect"], "delimiter": ","}},
        {**proposal("json"), "dialect": {"encoding": "utf-8", "delimiter": ",", "quote": None, "escape": None, "strip_bom": False}},
        {**proposal(), "selections": [selection(), selection()]},
        {**proposal(), "selections": [selection(format="parquet")]},
    ],
)
def test_proposal_format_dialect_and_descriptor_must_agree(payload):
    with pytest.raises(ValidationError):
        ImportSettingsProposal.model_validate(payload)


def test_dialect_requires_single_characters_and_utf8():
    valid = {"encoding": "utf-8", "delimiter": ",", "quote": None, "escape": None, "strip_bom": False}
    assert DelimitedDialect.model_validate(valid).quote is None
    for change in [{"encoding": "latin-1"}, {"delimiter": "||"}, {"quote": ""}, {"strip_bom": 1}]:
        with pytest.raises(ValidationError):
            DelimitedDialect.model_validate({**valid, **change})


def test_import_preview_preserves_warning_text_and_requires_hash():
    payload = {
        "dataset_id": V1,
        "upload_hash": HASH,
        "proposed_settings": proposal(columns=[]),
        "warnings": [" warning 世界 "],
        "requires_confirmation": True,
    }
    result = ImportPreview.model_validate(payload)
    assert result.warnings == [" warning 世界 "]
    with pytest.raises(ValidationError):
        ImportPreview.model_validate({**payload, "upload_hash": "A" * 64})


def test_temporal_bounds_kind_must_match_both_scalars():
    payload = {
        "kind": "date",
        "lower": {"kind": "date", "value": "2026-01-01"},
        "upper": {"kind": "date", "value": "2025-01-01"},
    }
    assert TemporalBounds.model_validate(payload).upper.value == "2025-01-01"
    with pytest.raises(ValidationError):
        TemporalBounds.model_validate({**payload, "upper": {"kind": "timestamp", "value": "2026-01-01T00:00:00"}})


def test_candidate_key_basis_controls_verification_reference():
    verified = {"column_ids": [V1], "basis": "verified_unique_non_null", "verification_ref": V4}
    assert CandidateKey.model_validate(verified).verification_ref == V4
    with pytest.raises(ValidationError):
        CandidateKey.model_validate({**verified, "verification_ref": None})
    assert CandidateKey.model_validate({"column_ids": [V1], "basis": "source_schema", "verification_ref": None}).basis == "source_schema"
    with pytest.raises(ValidationError):
        CandidateKey.model_validate({"column_ids": [V1], "basis": "source_schema", "verification_ref": V4})
    with pytest.raises(ValidationError):
        CandidateKey.model_validate({**verified, "column_ids": [V1, V1]})


def test_duplicate_source_descriptors_are_rejected_even_when_selection_settings_differ():
    duplicate_source = selection(columns=[settings(1, "Other")])
    payload = {**proposal(), "selections": [selection(), duplicate_source]}
    with pytest.raises(ValidationError):
        ImportSettingsProposal.model_validate(payload)


def test_column_and_table_catalog_enforce_schema_relationships():
    result = TableCatalog.model_validate(table())
    assert isinstance(ColumnCatalog.model_validate(column_catalog()), ColumnCatalog)
    assert result.columns[0].settings.source_position == result.columns[0].source_position
    invalid_tables = [
        {**table(), "row_count": 0},
        {**table(), "columns": [column_catalog(1)]},
        {**table(), "columns": [column_catalog(), column_catalog(1)]},
        {**table(), "candidate_keys": [{"column_ids": [V4B], "basis": "source_schema", "verification_ref": None}]},
    ]
    for payload in invalid_tables:
        with pytest.raises(ValidationError):
            TableCatalog.model_validate(payload)
    with pytest.raises(ValidationError):
        ColumnCatalog.model_validate({
            **column_catalog(),
            "original_label": "Other",
        })
    with pytest.raises(ValidationError):
        ColumnCatalog.model_validate({
            **column_catalog(),
            "type": {"tag": "string"},
        })
    nonnullable = {**column_catalog(), "nullable": False, "null_count": 1}
    with pytest.raises(ValidationError):
        TableCatalog.model_validate({**table(), "columns": [nonnullable]})
    temporal = {**column_catalog(), "type": {"tag": "string"}, "temporal_bounds": {"kind": "date", "lower": {"kind": "date", "value": "2026-01-01"}, "upper": {"kind": "date", "value": "2026-01-02"}}}
    with pytest.raises(ValidationError):
        ColumnCatalog.model_validate(temporal)


def test_prepared_snapshot_payload_integrity_and_ready_revision():
    payload = snapshot_payload()
    parsed = PreparedSnapshotPayload.model_validate(payload)
    assert PreparedSnapshotPayload.model_validate_json(json.dumps(payload)) == parsed
    assert PreparedSnapshot.model_validate({**payload, "ready_revision": 1}).ready_revision == 1
    for change in [
        {"artifact": {**artifact(), "media_type": "application/vnd.apache.parquet"}},
        {"artifact": {**artifact(), "environment_manifest_id": V4}},
        {"artifact": {**artifact(), "environment_manifest_id": None}},
        {"dependencies": [{"dataset_id": V1, "snapshot_id": V1B}]},
        {"table_ids": [V1B, V1B]},
    ]:
        with pytest.raises(ValidationError):
            PreparedSnapshotPayload.model_validate({**payload, **change})
    with pytest.raises(ValidationError):
        PreparedSnapshot.model_validate({**payload, "ready_revision": 0})


def test_prepared_candidate_binds_ordered_tables_and_profile_union():
    payload = {
        "candidate_id": V4,
        "snapshot": snapshot_payload(),
        "tables": [table()],
        "profile_evidence_ids": [V1B],
        "validation_receipt_ids": [V4B],
    }
    result = PreparedCandidate.model_validate(payload)
    assert result.candidate_id == V4
    assert not isinstance(result.snapshot, PreparedSnapshot)
    for change in [
        {"tables": [{**table(), "dataset_id": V4B}]},
        {"tables": [{**table(), "ordinal": 1}]},
        {"profile_evidence_ids": []},
        {"validation_receipt_ids": []},
    ]:
        with pytest.raises(ValidationError):
            PreparedCandidate.model_validate({**payload, **change})

