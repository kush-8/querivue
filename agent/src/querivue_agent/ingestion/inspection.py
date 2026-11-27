"""File format inspection for import preview."""

from __future__ import annotations

import csv
import json
import sqlite3
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from querivue_agent.contracts.common import SafeCount, NonblankString
from querivue_agent.contracts.values import CanonicalUUID, UnicodeString
from querivue_agent.contracts.artifacts import Sha256
from querivue_agent.ingestion.settings import ImportFormat, SourceDescriptor


@dataclass(frozen=True)
class ColumnPreview:
    """Preview of a single column."""
    ordinal: int
    original_label: UnicodeString | None
    sample_values: list[str] = field(default_factory=list)
    inferred_type: Literal["int64", "uint64", "decimal", "string", "date", "time", "timestamp", "timestamptz", "boolean", "unknown"] = "unknown"
    null_count: int = 0
    total_count: int = 0
    has_quoted_empty: bool = False
    has_unquoted_empty: bool = False


@dataclass(frozen=True)
class TablePreview:
    """Preview of a single table."""
    source_descriptor: SourceDescriptor
    row_count: int
    columns: list[ColumnPreview] = field(default_factory=list)
    sample_rows: list[list[str]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class InspectionResult:
    """Result of file inspection."""
    format: ImportFormat
    tables: list[TablePreview] = field(default_factory=list)
    encoding: str = "utf-8"
    delimiter: str | None = None
    has_bom: bool = False
    total_byte_size: int = 0
    upload_sha256: Sha256 | None = None
    warnings: list[str] = field(default_factory=list)


def compute_sha256(path: Path) -> Sha256:
    """Compute SHA-256 of file."""
    import hashlib
    sha256 = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def inspect_csv(path: Path, encoding: str = "utf-8", delimiter: str | None = None) -> InspectionResult:
    """Inspect a CSV file."""
    result = InspectionResult(
        format="csv",
        total_byte_size=path.stat().st_size,
        upload_sha256=compute_sha256(path),
    )

    # Detect BOM
    with open(path, "rb") as f:
        first_bytes = f.read(4)
        if first_bytes.startswith(b'\xef\xbb\xbf'):
            result.has_bom = True
            encoding = "utf-8-sig"

    # Detect delimiter if not provided
    if delimiter is None:
        with open(path, "r", encoding=encoding, newline="") as f:
            sample = f.read(1024)
            sniffer = csv.Sniffer()
            try:
                dialect = sniffer.sniff(sample, delimiters=",\t;|")
                delimiter = dialect.delimiter
            except csv.Error:
                delimiter = ","

    result.delimiter = delimiter

    # Read preview
    with open(path, "r", encoding=encoding, newline="") as f:
        reader = csv.reader(f, delimiter=delimiter)
        rows = list(reader)

    if not rows:
        return result

    # Detect header
    header = rows[0] if rows else []
    data_rows = rows[1:] if len(rows) > 1 else []

    # Create column previews
    columns = []
    for i, label in enumerate(header):
        col_data = [row[i] if i < len(row) else "" for row in data_rows[:100]]
        null_count = sum(1 for v in col_data if v == "")
        has_quoted_empty = any(v == '""' for v in col_data)
        has_unquoted_empty = any(v == "" for v in col_data)

        # Infer type
        non_null = [v for v in col_data if v != ""]
        inferred = infer_type(non_null[:20]) if non_null else "unknown"

        columns.append(ColumnPreview(
            ordinal=i,
            original_label=label if label else None,
            sample_values=col_data[:5],
            inferred_type=inferred,
            null_count=null_count,
            total_count=len(data_rows),
            has_quoted_empty=has_quoted_empty,
            has_unquoted_empty=has_unquoted_empty,
        ))

    table_preview = TablePreview(
        source_descriptor=SourceDescriptor(
            source_id=CanonicalUUID(str(uuid4())),
            format="csv",
            descriptor="CSV file",
            sql_name=None,  # Not needed for preview
        ),
        row_count=len(data_rows),
        columns=columns,
        sample_rows=data_rows[:10],
    )

    result.tables.append(table_preview)
    return result


def inspect_tsv(path: Path, encoding: str = "utf-8") -> InspectionResult:
    """Inspect a TSV file."""
    return inspect_csv(path, encoding=encoding, delimiter="\t")


def infer_type(samples: list[str]) -> Literal["int64", "uint64", "decimal", "string", "date", "time", "timestamp", "timestamptz", "boolean", "unknown"]:
    """Infer column type from sample values."""
    if not samples:
        return "unknown"

    import re

    int_pattern = re.compile(r"^-?\d+$")
    uint_pattern = re.compile(r"^\d+$")
    decimal_pattern = re.compile(r"^-?\d+\.\d+$")
    date_pattern = re.compile(r"^\d{4}-\d{2}-\d{2}$")
    time_pattern = re.compile(r"^\d{2}:\d{2}:\d{2}$")
    timestamp_pattern = re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}")
    boolean_pattern = re.compile(r"^(true|false)$", re.IGNORECASE)

    if all(int_pattern.match(v) for v in samples):
        # Check if all non-negative
        if all(int(v) >= 0 for v in samples):
            return "uint64"
        return "int64"
    if all(decimal_pattern.match(v) or int_pattern.match(v) for v in samples):
        return "decimal"
    if all(date_pattern.match(v) for v in samples):
        return "date"
    if all(time_pattern.match(v) for v in samples):
        return "time"
    if all(timestamp_pattern.match(v) for v in samples):
        return "timestamp"
    if all(boolean_pattern.match(v) for v in samples):
        return "boolean"

    return "string"


def inspect_json(path: Path) -> InspectionResult:
    """Inspect a JSON file (array of objects)."""
    result = InspectionResult(
        format="json",
        total_byte_size=path.stat().st_size,
        upload_sha256=compute_sha256(path),
    )

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list):
        result.warnings.append("JSON root is not an array")
        return result

    if not data:
        return result

    # Analyze first object to get columns
    first_obj = data[0] if data else {}
    if not isinstance(first_obj, dict):
        result.warnings.append("Array elements are not objects")
        return result

    columns = []
    for i, (key, value) in enumerate(first_obj.items()):
        samples = [str(obj.get(key, "")) for obj in data[:20] if isinstance(obj, dict)]
        inferred = infer_type(samples)
        columns.append(ColumnPreview(
            ordinal=i,
            original_label=key,
            sample_values=samples[:5],
            inferred_type=inferred,
            null_count=samples.count(""),
            total_count=len(data),
        ))

    table_preview = TablePreview(
        source_descriptor=SourceDescriptor(
            source_id=CanonicalUUID(str(uuid4())),
            format="json",
            descriptor="JSON array",
        ),
        row_count=len(data),
        columns=columns,
        sample_rows=[[str(obj.get(k, "")) for k in first_obj.keys()] for obj in data[:10]],
    )

    result.tables.append(table_preview)
    return result


def inspect_jsonl(path: Path) -> InspectionResult:
    """Inspect a JSONL file."""
    result = InspectionResult(
        format="jsonl",
        total_byte_size=path.stat().st_size,
        upload_sha256=compute_sha256(path),
    )

    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    if not lines:
        return result

    data = []
    for line in lines:
        line = line.strip()
        if line:
            try:
                data.append(json.loads(line))
            except json.JSONDecodeError as e:
                result.warnings.append(f"Invalid JSON on line: {e}")

    if not data:
        return result

    # Use union of all keys
    all_keys = set()
    for obj in data:
        if isinstance(obj, dict):
            all_keys.update(obj.keys())

    columns = []
    for i, key in enumerate(sorted(all_keys)):
        samples = [str(obj.get(key, "")) for obj in data[:20] if isinstance(obj, dict)]
        inferred = infer_type(samples)
        columns.append(ColumnPreview(
            ordinal=i,
            original_label=key,
            sample_values=samples[:5],
            inferred_type=inferred,
            null_count=samples.count(""),
            total_count=len(data),
        ))

    table_preview = TablePreview(
        source_descriptor=SourceDescriptor(
            source_id=CanonicalUUID(str(uuid4())),
            format="jsonl",
            descriptor="JSONL file",
        ),
        row_count=len(data),
        columns=columns,
        sample_rows=[[str(obj.get(k, "")) for k in sorted(all_keys)] for obj in data[:10]],
    )

    result.tables.append(table_preview)
    return result


def inspect_parquet(path: Path) -> InspectionResult:
    """Inspect a Parquet file."""
    result = InspectionResult(
        format="parquet",
        total_byte_size=path.stat().st_size,
        upload_sha256=compute_sha256(path),
    )

    try:
        import pyarrow.parquet as pq
        table = pq.read_table(path)
        schema = table.schema

        columns = []
        for i, field in enumerate(schema):
            # Get sample values
            samples = []
            col = table.column(i)
            for j in range(min(20, len(col))):
                val = col[j].as_py()
                samples.append(str(val) if val is not None else "")

            inferred = infer_type([v for v in samples if v])
            columns.append(ColumnPreview(
                ordinal=i,
                original_label=field.name,
                sample_values=samples[:5],
                inferred_type=inferred,
                null_count=col.null_count,
                total_count=len(col),
            ))

        table_preview = TablePreview(
            source_descriptor=SourceDescriptor(
                source_id=CanonicalUUID(str(uuid4())),
                format="parquet",
                descriptor="Parquet file",
            ),
            row_count=table.num_rows,
            columns=columns,
            sample_rows=[[str(table.column(c)[r].as_py()) for c in range(table.num_columns)] for r in range(min(10, table.num_rows))],
        )

        result.tables.append(table_preview)

    except Exception as e:
        result.warnings.append(f"Parquet inspection failed: {e}")

    return result


def inspect_excel(path: Path) -> InspectionResult:
    """Inspect an Excel file."""
    result = InspectionResult(
        format="excel",
        total_byte_size=path.stat().st_size,
        upload_sha256=compute_sha256(path),
    )

    try:
        import openpyxl
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)

        for sheet_name in wb.sheetnames:
            if sheet_name.startswith("_"):
                continue  # Skip hidden sheets by default

            ws = wb[sheet_name]

            # Get dimensions
            rows = list(ws.iter_rows(values_only=True))
            if not rows:
                continue

            header = rows[0] if rows else []
            data_rows = rows[1:] if len(rows) > 1 else []

            columns = []
            for i, label in enumerate(header):
                col_data = [row[i] if i < len(row) else None for row in data_rows[:100]]
                samples = [str(v) if v is not None else "" for v in col_data]
                null_count = sum(1 for v in col_data if v is None)
                inferred = infer_type([v for v in samples if v != ""])

                columns.append(ColumnPreview(
                    ordinal=i,
                    original_label=str(label) if label else None,
                    sample_values=samples[:5],
                    inferred_type=inferred,
                    null_count=null_count,
                    total_count=len(data_rows),
                ))

            table_preview = TablePreview(
                source_descriptor=SourceDescriptor(
                    source_id=CanonicalUUID(str(uuid4())),
                    format="excel",
                    descriptor=f"Worksheet: {sheet_name}",
                ),
                row_count=len(data_rows),
                columns=columns,
                sample_rows=[[str(cell) if cell is not None else "" for cell in row] for row in data_rows[:10]],
                warnings=[f"Hidden worksheet: {sheet_name}"] if sheet_name.startswith("_") else [],
            )

            result.tables.append(table_preview)

    except Exception as e:
        result.warnings.append(f"Excel inspection failed: {e}")

    return result


def inspect_sqlite(path: Path) -> InspectionResult:
    """Inspect a SQLite database."""
    result = InspectionResult(
        format="sqlite",
        total_byte_size=path.stat().st_size,
        upload_sha256=compute_sha256(path),
    )

    try:
        conn = sqlite3.connect(path)
        conn.execute("PRAGMA query_only = ON")
        conn.execute("PRAGMA trusted_schema = OFF")

        # Get user tables
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
        tables = [row[0] for row in cursor.fetchall()]

        for table_name in tables:
            # Get column info
            cursor = conn.execute(f"PRAGMA table_info({table_name})")
            columns_info = cursor.fetchall()

            # Get row count
            cursor = conn.execute(f"SELECT COUNT(*) FROM {table_name}")
            row_count = cursor.fetchone()[0]

            # Get sample data
            cursor = conn.execute(f"SELECT * FROM {table_name} LIMIT 10")
            sample_rows = cursor.fetchall()

            columns = []
            for col_info in columns_info:
                _, name, col_type, _, _, _ = col_info
                # Get sample values
                samples = [str(row[columns_info.index(col_info)]) for row in sample_rows]
                inferred = infer_type(samples)
                columns.append(ColumnPreview(
                    ordinal=col_info[0],
                    original_label=name,
                    sample_values=samples[:5],
                    inferred_type=inferred,
                    null_count=0,  # Would need full scan
                    total_count=row_count,
                ))

            table_preview = TablePreview(
                source_descriptor=SourceDescriptor(
                    source_id=CanonicalUUID(str(uuid4())),
                    format="sqlite",
                    descriptor=f"Table: {table_name}",
                ),
                row_count=row_count,
                columns=columns,
                sample_rows=[[str(v) for v in row] for row in sample_rows],
                warnings=["Views and virtual tables excluded"],
            )

            result.tables.append(table_preview)

    except Exception as e:
        result.warnings.append(f"SQLite inspection failed: {e}")
    finally:
        if 'conn' in locals():
            conn.close()

    return result


def inspect_upload(path: Path, format_hint: ImportFormat | None = None) -> InspectionResult:
    """Inspect an uploaded file based on format hint or auto-detection."""
    if format_hint == "csv":
        return inspect_csv(path)
    elif format_hint == "tsv":
        return inspect_tsv(path)
    elif format_hint == "json":
        return inspect_json(path)
    elif format_hint == "jsonl":
        return inspect_jsonl(path)
    elif format_hint == "parquet":
        return inspect_parquet(path)
    elif format_hint == "excel":
        return inspect_excel(path)
    elif format_hint == "sqlite":
        return inspect_sqlite(path)
    else:
        # Auto-detect from extension
        suffix = path.suffix.lower()
        if suffix == ".csv":
            return inspect_csv(path)
        elif suffix == ".tsv":
            return inspect_tsv(path)
        elif suffix == ".json":
            return inspect_json(path)
        elif suffix == ".jsonl":
            return inspect_jsonl(path)
        elif suffix == ".parquet":
            return inspect_parquet(path)
        elif suffix in (".xlsx", ".xls"):
            return inspect_excel(path)
        elif suffix in (".sqlite", ".db"):
            return inspect_sqlite(path)
        else:
            result = InspectionResult(
                format="unknown",
                total_byte_size=path.stat().st_size,
            )
            result.warnings.append(f"Unsupported file format: {suffix}")
            return result