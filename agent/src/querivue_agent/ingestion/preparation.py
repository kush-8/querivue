"""Dataset preparation pipeline."""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, UTC
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import duckdb

from querivue_agent.contracts.common import SafeCount, NonblankString, TimestampText
from querivue_agent.contracts.values import CanonicalUUID
from querivue_agent.contracts.artifacts import Sha256
from querivue_agent.ingestion.settings import (
    ImportSettings,
    ImportFormat,
    PreparationAttempt,
    PreparedSnapshot,
    PreparationError,
    ColumnImportSettings,
    TableImportSettings,
)
from querivue_agent.ingestion.catalog import (
    TableCatalog,
    ColumnCatalog,
    build_table_catalog,
    build_column_catalog,
    resolve_duckdb_type,
)
from querivue_agent.ingestion.inspection import InspectionResult


@dataclass(frozen=True)
class PreparationResult:
    """Result of dataset preparation."""
    attempt: PreparationAttempt
    snapshot: PreparedSnapshot | None = None
    catalog: list[TableCatalog] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def prepare_dataset(
    upload_path: Path,
    settings: ImportSettings,
    attempt: PreparationAttempt,
    work_dir: Path | None = None,
) -> PreparationResult:
    """Prepare a dataset from upload using confirmed settings."""
    errors = []

    try:
        with tempfile.TemporaryDirectory(dir=work_dir) as tmp:
            work_path = Path(tmp)

            # 1. Create DuckDB database
            db_path = work_path / "prepared.duckdb"
            conn = duckdb.connect(str(db_path))

            try:
                catalog = []

                # 2. Process each table based on format
                for table_settings in settings.table_settings:
                    table_catalog = _process_table(
                        conn,
                        upload_path,
                        table_settings,
                        settings,
                        work_path,
                    )
                    catalog.append(table_catalog)

                # 3. Validate and finalize
                _validate_catalog(conn, catalog)

                # 4. Close connection (checkpoints the database)
                conn.close()

                # 5. Hash the database file
                artifact_sha256 = _compute_file_hash(db_path)
                artifact_size = db_path.stat().st_size

                # 6. Build prepared snapshot
                snapshot = PreparedSnapshot(
                    dataset_id=attempt.dataset_id,
                    attempt_id=attempt.attempt_id,
                    snapshot_id=CanonicalUUID(str(uuid4())),
                    catalog_hash=_compute_catalog_hash(catalog),
                    table_ids=[CanonicalUUID(str(uuid4())) for _ in catalog],  # Would be actual table IDs
                    artifact_ref=f"artifact_{attempt.attempt_id}",
                    artifact_size=artifact_size,
                    artifact_sha256=artifact_sha256,
                    schema_fingerprint=_compute_schema_fingerprint(conn),
                    environment_manifest_id=attempt.environment_manifest_id or CanonicalUUID(str(uuid4())),
                    ready_revision=1,
                )

                return PreparationResult(
                    attempt=attempt,
                    snapshot=snapshot,
                    catalog=catalog,
                )

            finally:
                if 'conn' in locals():
                    conn.close()

    except Exception as e:
        errors.append(f"Preparation failed: {e}")
        return PreparationResult(
            attempt=attempt,
            errors=errors,
        )


def _process_table(
    conn: duckdb.DuckDBPyConnection,
    upload_path: Path,
    table_settings: TableImportSettings,
    settings: ImportSettings,
    work_path: Path,
) -> TableCatalog:
    """Process a single table based on format."""
    source_desc = table_settings.source_descriptor
    format = settings.source_format

    if format in ("csv", "tsv"):
        return _process_csv_table(conn, upload_path, table_settings, settings)
    elif format == "json":
        return _process_json_table(conn, upload_path, table_settings)
    elif format == "jsonl":
        return _process_jsonl_table(conn, upload_path, table_settings)
    elif format == "parquet":
        return _process_parquet_table(conn, upload_path, table_settings)
    elif format == "excel":
        return _process_excel_table(conn, upload_path, table_settings)
    elif format == "sqlite":
        return _process_sqlite_table(conn, upload_path, table_settings)
    else:
        raise ValueError(f"Unsupported format: {format}")


def _process_csv_table(
    conn: duckdb.DuckDBPyConnection,
    upload_path: Path,
    table_settings: TableImportSettings,
    settings: ImportSettings,
) -> TableCatalog:
    """Process CSV/TSV table using DuckDB's native reader."""
    delimiter = settings.delimiter or ("," if settings.source_format == "csv" else "\t")

    # Build COPY statement
    column_defs = []
    for col_setting in table_settings.column_settings:
        sql_name = col_setting.sql_name
        duckdb_type = _map_type(col_setting.requested_type)
        column_defs.append(f'"{sql_name}" {duckdb_type}')

    create_sql = f'CREATE TABLE "{table_settings.source_descriptor.sql_name}" ({", ".join(column_defs)})'
    conn.execute(create_sql)

    # Use DuckDB's CSV reader
    null_markers = []
    for col_setting in table_settings.column_settings:
        null_markers.extend(col_setting.missing_markers)
    null_str = ",".join(f"'{m}'" for m in null_markers) if null_markers else "''"

    copy_sql = f"""
    COPY "{table_settings.source_descriptor.sql_name}"
    FROM '{upload_path}'
    WITH (
        FORMAT csv,
        DELIMITER '{delimiter}',
        HEADER {str(settings.table_settings[0].source_descriptor.has_header).lower()},
        QUOTE '{settings.quote_char}',
        ESCAPE '{settings.escape_char or "\\\\"}',
        NULL {null_str},
        ENCODING '{settings.encoding}',
        ALLOW_QUOTED_NULLS {str(settings.allow_quoted_nulls).lower()}
    )
    """
    conn.execute(copy_sql)

    # Get row count and column info
    count_result = conn.execute(f'SELECT COUNT(*) FROM "{table_settings.source_descriptor.sql_name}"').fetchone()
    row_count = count_result[0] if count_result else 0

    # Build column catalogs
    column_catalogs = []
    for i, col_setting in enumerate(table_settings.column_settings):
        # Get actual null count
        null_count_result = conn.execute(
            f'SELECT COUNT(*) FROM "{table_settings.source_descriptor.sql_name}" WHERE "{col_setting.sql_name}" IS NULL'
        ).fetchone()
        null_count = null_count_result[0] if null_count_result else 0

        column_catalogs.append(build_column_catalog(
            column_id=CanonicalUUID(str(uuid4())),
            ordinal=i,
            source_position=i,
            original_label=col_setting.original_label,
            sql_name=col_setting.sql_name,
            duckdb_type=NonblankString(_map_type(col_setting.requested_type)),
            nullable=True,  # Would be determined from schema
            null_count=null_count,
            confirmed_type=col_setting.requested_type,
            missing_markers=col_setting.missing_markers,
            decimal_separator=col_setting.decimal_separator,
            thousands_separator=col_setting.thousands_separator,
            date_format=col_setting.date_format,
            time_format=col_setting.time_format,
            datetime_format=col_setting.datetime_format,
            source_timezone=col_setting.source_timezone,
            conversion_choice=col_setting.conversion_choice,
        ))

    return build_table_catalog(
        table_id=CanonicalUUID(str(uuid4())),
        dataset_id=CanonicalUUID(str(uuid4())),  # Would be actual dataset ID
        snapshot_id=CanonicalUUID(str(uuid4())),
        ordinal=0,
        sql_name=table_settings.source_descriptor.sql_name,
        source_descriptor=table_settings.source_descriptor.descriptor,
        row_count=row_count,
        column_catalogs=column_catalogs,
        warnings=table_settings.warnings,
    )


def _process_json_table(
    conn: duckdb.DuckDBPyConnection,
    upload_path: Path,
    table_settings: TableImportSettings,
) -> TableCatalog:
    """Process JSON table using DuckDB's native reader."""
    # DuckDB can read JSON directly
    conn.execute(f"""
    CREATE TABLE "{table_settings.source_descriptor.sql_name}"
    AS SELECT * FROM read_json_auto('{upload_path}')
    """)

    return _finalize_table(conn, table_settings)


def _process_jsonl_table(
    conn: duckdb.DuckDBPyConnection,
    upload_path: Path,
    table_settings: TableImportSettings,
) -> TableCatalog:
    """Process JSONL table using DuckDB's native reader."""
    conn.execute(f"""
    CREATE TABLE "{table_settings.source_descriptor.sql_name}"
    AS SELECT * FROM read_json_auto('{upload_path}', format='newline_delimited')
    """)

    return _finalize_table(conn, table_settings)


def _process_parquet_table(
    conn: duckdb.DuckDBPyConnection,
    upload_path: Path,
    table_settings: TableImportSettings,
) -> TableCatalog:
    """Process Parquet table using DuckDB's native reader."""
    conn.execute(f"""
    CREATE TABLE "{table_settings.source_descriptor.sql_name}"
    AS SELECT * FROM read_parquet('{upload_path}')
    """)

    return _finalize_table(conn, table_settings)


def _process_excel_table(
    conn: duckdb.DuckDBPyConnection,
    upload_path: Path,
    table_settings: TableImportSettings,
) -> TableCatalog:
    """Process Excel worksheet using openpyxl + DuckDB."""
    import openpyxl

    wb = openpyxl.load_workbook(upload_path, read_only=True, data_only=True)
    ws = wb[table_settings.source_descriptor.descriptor.replace("Worksheet: ", "")]

    # Read data
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        raise ValueError("Empty worksheet")

    header = rows[0]
    data_rows = rows[1:]

    # Create table with appropriate schema
    column_defs = []
    for i, col_setting in enumerate(table_settings.column_settings):
        duckdb_type = _map_type(col_setting.requested_type)
        column_defs.append(f'"{col_setting.sql_name}" {duckdb_type}')

    create_sql = f'CREATE TABLE "{table_settings.source_descriptor.sql_name}" ({", ".join(column_defs)})'
    conn.execute(create_sql)

    # Insert data
    for row in data_rows:
        values = []
        for i, val in enumerate(row):
            if val is None:
                values.append("NULL")
            elif isinstance(val, str):
                values.append(f"'{val.replace("'", "''")}'")
            else:
                values.append(str(val))
        insert_sql = f'INSERT INTO "{table_settings.source_descriptor.sql_name}" VALUES ({", ".join(values)})'
        conn.execute(insert_sql)

    return _finalize_table(conn, table_settings)


def _process_sqlite_table(
    conn: duckdb.DuckDBPyConnection,
    upload_path: Path,
    table_settings: TableImportSettings,
) -> TableCatalog:
    """Process SQLite table by copying to DuckDB."""
    import sqlite3

    sqlite_conn = sqlite3.connect(upload_path)
    sqlite_conn.execute("PRAGMA query_only = ON")

    # Get table name from descriptor
    table_name = table_settings.source_descriptor.descriptor.replace("Table: ", "")

    # Read schema
    cursor = sqlite_conn.execute(f"PRAGMA table_info({table_name})")
    columns_info = cursor.fetchall()

    # Create DuckDB table
    column_defs = []
    for col_info in columns_info:
        name = col_info[1]
        col_type = col_info[2]
        duckdb_type = _sqlite_to_duckdb_type(col_type)
        column_defs.append(f'"{name}" {duckdb_type}')

    create_sql = f'CREATE TABLE "{table_settings.source_descriptor.sql_name}" ({", ".join(column_defs)})'
    conn.execute(create_sql)

    # Copy data
    sqlite_cursor = sqlite_conn.execute(f"SELECT * FROM {table_name}")
    for row in sqlite_cursor:
        values = []
        for val in row:
            if val is None:
                values.append("NULL")
            elif isinstance(val, str):
                values.append(f"'{val.replace("'", "''")}'")
            else:
                values.append(str(val))
        insert_sql = f'INSERT INTO "{table_settings.source_descriptor.sql_name}" VALUES ({", ".join(values)})'
        conn.execute(insert_sql)

    sqlite_conn.close()
    return _finalize_table(conn, table_settings)


def _finalize_table(
    conn: duckdb.DuckDBPyConnection,
    table_settings: TableImportSettings,
) -> TableCatalog:
    """Finalize table and build catalog."""
    count_result = conn.execute(f'SELECT COUNT(*) FROM "{table_settings.source_descriptor.sql_name}"').fetchone()
    row_count = count_result[0] if count_result else 0

    column_catalogs = []
    for i, col_setting in enumerate(table_settings.column_settings):
        null_count_result = conn.execute(
            f'SELECT COUNT(*) FROM "{table_settings.source_descriptor.sql_name}" WHERE "{col_setting.sql_name}" IS NULL'
        ).fetchone()
        null_count = null_count_result[0] if null_count_result else 0

        column_catalogs.append(build_column_catalog(
            column_id=CanonicalUUID(str(uuid4())),
            ordinal=i,
            source_position=i,
            original_label=col_setting.original_label,
            sql_name=col_setting.sql_name,
            duckdb_type=NonblankString(_map_type(col_setting.requested_type)),
            nullable=True,
            null_count=null_count,
            confirmed_type=col_setting.requested_type,
            missing_markers=col_setting.missing_markers,
        ))

    return build_table_catalog(
        table_id=CanonicalUUID(str(uuid4())),
        dataset_id=CanonicalUUID(str(uuid4())),
        snapshot_id=CanonicalUUID(str(uuid4())),
        ordinal=0,
        sql_name=table_settings.source_descriptor.sql_name,
        source_descriptor=table_settings.source_descriptor.descriptor,
        row_count=row_count,
        column_catalogs=column_catalogs,
        warnings=table_settings.warnings,
    )


def _map_type(requested: str) -> str:
    """Map requested type to DuckDB type."""
    type_map = {
        "int64": "BIGINT",
        "uint64": "UBIGINT",
        "decimal": "DECIMAL(38,10)",
        "string": "VARCHAR",
        "date": "DATE",
        "time": "TIME",
        "timestamp": "TIMESTAMP",
        "timestamptz": "TIMESTAMPTZ",
        "boolean": "BOOLEAN",
    }
    return type_map.get(requested, "VARCHAR")


def _sqlite_to_duckdb_type(sqlite_type: str) -> str:
    """Convert SQLite type affinity to DuckDB type."""
    sqlite_type = sqlite_type.upper()
    if "INT" in sqlite_type:
        return "BIGINT"
    elif "REAL" in sqlite_type or "FLOA" in sqlite_type or "DOUB" in sqlite_type:
        return "DOUBLE"
    elif "TEXT" in sqlite_type or "CHAR" in sqlite_type or "CLOB" in sqlite_type:
        return "VARCHAR"
    elif "BLOB" in sqlite_type:
        return "BLOB"
    return "VARCHAR"


def _validate_catalog(conn: duckdb.DuckDBPyConnection, catalog: list[TableCatalog]) -> None:
    """Validate the prepared catalog."""
    for table in catalog:
        if table.row_count < 0:
            raise PreparationError("Negative row count", "validation")
        for col in table.columns:
            if col.null_count > table.row_count:
                raise PreparationError(f"Null count exceeds row count for {col.sql_name}", "validation")


def _compute_file_hash(path: Path) -> Sha256:
    """Compute SHA-256 of file."""
    sha256 = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def _compute_catalog_hash(catalog: list[TableCatalog]) -> Sha256:
    """Compute hash of catalog for integrity."""
    import json
    data = json.dumps([{
        "table_id": str(t.table_id),
        "sql_name": str(t.sql_name),
        "row_count": int(t.row_count),
        "columns": [{
            "column_id": str(c.column_id),
            "sql_name": str(c.sql_name),
            "duckdb_type": str(c.duckdb_type),
            "null_count": int(c.null_count),
        } for c in t.columns]
    } for t in catalog], separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def _compute_schema_fingerprint(conn: duckdb.DuckDBPyConnection) -> str:
    """Compute schema fingerprint of database."""
    tables = conn.execute("SHOW TABLES").fetchall()
    schema_parts = []
    for (table_name,) in tables:
        columns = conn.execute(f"DESCRIBE {table_name}").fetchall()
        for col in columns:
            schema_parts.append(f"{table_name}.{col[0]}:{col[1]}")
    return hashlib.sha256("|".join(sorted(schema_parts)).encode("utf-8")).hexdigest()[:64]