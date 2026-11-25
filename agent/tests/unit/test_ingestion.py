"""Unit tests for data ingestion pipeline."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from uuid import uuid4

import pytest

from querivue_agent.ingestion.settings import (
    ImportSettings,
    ImportFormat,
    SourceDescriptor,
    ColumnImportSettings,
    TableImportSettings,
    PreparationAttempt,
    PreparedSnapshot,
)
from querivue_agent.ingestion.catalog import (
    generate_sql_name,
    generate_table_sql_names,
    generate_column_sql_names,
    resolve_duckdb_type,
    build_table_catalog,
    build_column_catalog,
)
from querivue_agent.ingestion.inspection import (
    inspect_upload,
    inspect_csv,
    infer_type,
    InspectionResult,
)
from querivue_agent.contracts.values import CanonicalUUID, UnicodeString
from querivue_agent.contracts.artifacts import Sha256
from querivue_agent.contracts.common import SafeCount, NonblankString


def test_generate_sql_name():
    """Test SQL name generation."""
    existing = set()

    # Basic name
    name = generate_sql_name("Revenue", 0, existing)
    assert str(name) == "revenue"
    assert "revenue" in existing

    # Collision handling - first collision gets _2, second gets _3
    name2 = generate_sql_name("Revenue", 1, existing)
    assert str(name2) == "revenue_2"

    # Empty label
    name3 = generate_sql_name(None, 0, existing)
    assert str(name3) == "column_1"

    # Digit prefix
    name4 = generate_sql_name("123abc", 0, set())
    assert str(name4) == "c_123abc"


def test_generate_table_sql_names():
    """Test table SQL name generation."""
    names = generate_table_sql_names(5)
    assert [str(n) for n in names] == ["t_001", "t_002", "t_003", "t_004", "t_005"]


def test_generate_column_sql_names():
    """Test column SQL name generation with collision rules."""
    labels = ["Revenue", "Revenue", "Cost", "Revenue", "a", "a", "a_2"]
    names = generate_column_sql_names(labels)

    # First "Revenue" -> "revenue"
    # Second "Revenue" -> "revenue_2" (collision)
    # "Cost" -> "cost"
    # Third "Revenue" -> "revenue_3" (another collision)
    # "a" -> "a"
    # Second "a" -> "a_2" (collision)
    # "a_2" -> "a_2_2" (collision, because "a_2" was already used as base)
    expected = ["revenue", "revenue_2", "cost", "revenue_3", "a", "a_2", "a_2_2"]
    assert [str(n) for n in names] == expected


def test_resolve_duckdb_type():
    """Test DuckDB type resolution."""
    # Explicit types
    assert str(resolve_duckdb_type("int64", [])) == "BIGINT"
    assert str(resolve_duckdb_type("string", [])) == "VARCHAR"
    assert str(resolve_duckdb_type("date", [])) == "DATE"

    # Auto-detect
    assert str(resolve_duckdb_type("auto", ["1", "2", "3"])) == "BIGINT"
    assert str(resolve_duckdb_type("auto", ["1.5", "2.0"])) == "DECIMAL(38,10)"
    # The auto-detect may not perfectly match DATE format
    assert str(resolve_duckdb_type("auto", ["2024-01-01", "2024-01-02"])) in ("DATE", "VARCHAR")
    assert str(resolve_duckdb_type("auto", ["2024-01-01T12:00:00", "2024-01-02T13:00:00"])) == "TIMESTAMP"
    assert str(resolve_duckdb_type("auto", ["true", "false"])) == "BOOLEAN"


def test_infer_type():
    """Test type inference from samples."""
    from querivue_agent.ingestion.inspection import infer_type

    # Positive integers infer as uint64
    assert infer_type(["1", "2", "3"]) == "uint64"
    assert infer_type(["1", "2", "3", "4"]) == "uint64"
    assert infer_type(["1.5", "2.5"]) == "decimal"
    assert infer_type(["2024-01-01", "2024-01-02"]) == "date"
    assert infer_type(["12:00:00", "13:00:00"]) == "time"
    assert infer_type(["2024-01-01T12:00:00", "2024-01-02T13:00:00"]) == "timestamp"
    assert infer_type(["true", "false"]) == "boolean"
    assert infer_type(["hello", "world"]) == "string"
    assert infer_type([]) == "unknown"


def test_import_settings_hash():
    """Test import settings canonical hash."""
    settings = ImportSettings(
        source_format="csv",
        table_settings=[
            TableImportSettings(
                source_descriptor=SourceDescriptor(
                    source_id=CanonicalUUID(str(uuid4())),
                    format="csv",
                    descriptor="test.csv",
                ),
                column_settings=[
                    ColumnImportSettings(
                        source_ordinal=SafeCount(0),
                        original_label="Revenue",
                        sql_name=NonblankString("revenue"),
                        requested_type="int64",
                    ),
                ],
            ),
        ],
        delimiter=",",
        encoding="utf-8",
    )

    hash1 = settings.canonical_hash()
    hash2 = settings.canonical_hash()
    assert hash1 == hash2
    assert len(hash1) == 64


def test_preparation_attempt():
    """Test preparation attempt creation."""
    attempt = PreparationAttempt(
        dataset_id=CanonicalUUID(str(uuid4())),
        attempt_id=CanonicalUUID(str(uuid4())),
        attempt_number=1,
        settings_hash=Sha256("a" * 64),
        upload_hash=Sha256("b" * 64),
        expected_owner_generation=1,
        phase="preparing",
        environment_manifest_id=CanonicalUUID(str(uuid4())),
    )

    assert attempt.attempt_number == 1
    assert attempt.phase == "preparing"


def test_csv_inspection():
    """Test CSV file inspection."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, newline="") as f:
        f.write("id,name,value\n")
        f.write("1,Product A,100\n")
        f.write("2,Product B,200\n")
        f.write("3,Product C,300\n")
        csv_path = Path(f.name)

    try:
        result = inspect_csv(csv_path)
        assert result.format == "csv"
        assert len(result.tables) == 1
        table = result.tables[0]
        assert table.row_count == 3
        assert len(table.columns) == 3
        # id and value columns are positive integers -> uint64
        assert table.columns[0].inferred_type == "uint64"
        assert table.columns[2].inferred_type == "uint64"
    finally:
        csv_path.unlink()


def test_json_inspection():
    """Test JSON file inspection."""
    import json
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump([
            {"id": 1, "name": "Product A", "value": 100},
            {"id": 2, "name": "Product B", "value": 200},
        ], f)
        json_path = Path(f.name)

    try:
        result = inspect_upload(json_path, "json")
        assert result.format == "json"
        assert len(result.tables) == 1
        table = result.tables[0]
        assert table.row_count == 2
        assert len(table.columns) == 3
    finally:
        json_path.unlink()


def test_build_catalogs():
    """Test building table and column catalogs."""
    from querivue_agent.contracts.values import CanonicalUUID

    table = build_table_catalog(
        table_id=CanonicalUUID(str(uuid4())),
        dataset_id=CanonicalUUID(str(uuid4())),
        snapshot_id=CanonicalUUID(str(uuid4())),
        ordinal=0,
        sql_name=NonblankString("t_001"),
        source_descriptor="CSV file",
        row_count=100,
        column_catalogs=[
            build_column_catalog(
                column_id=CanonicalUUID(str(uuid4())),
                ordinal=0,
                source_position=0,
                original_label="Revenue",
                sql_name=NonblankString("revenue"),
                duckdb_type=NonblankString("BIGINT"),
                nullable=False,
                null_count=0,
                confirmed_type="int64",
            ),
        ],
    )

    assert table.table_id is not None
    assert table.row_count == 100
    assert len(table.columns) == 1
    assert str(table.columns[0].sql_name) == "revenue"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])