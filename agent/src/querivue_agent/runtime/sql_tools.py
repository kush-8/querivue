"""SQL tool implementations for the SQL Specialist."""

from __future__ import annotations

import asyncio
import hashlib
import json
import tempfile
from dataclasses import dataclass
from datetime import datetime, UTC
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import duckdb
import pyarrow.parquet as pq

from querivue_agent.contracts.tools import (
    InspectTableRequest,
    PreviewRowsRequest,
    InspectEvidenceRequest,
    ExecuteQueryRequest,
    NonblankString,
)
from querivue_agent.contracts.evidence import (
    TabularEvidence,
    TabularPreview,
    EvidenceColumn,
    ColumnType,
    CellLocator,
    SQLProducer,
    SQLInspectedEvidence,
    Int64Column,
    Uint64Column,
    Float64Column,
    StringColumn,
    DateColumn,
    TimeColumn,
    TimestampColumn,
    TimestamptzColumn,
    DecimalColumn,
    BooleanColumn,
)
from querivue_agent.contracts.actions import AnalysisConstraints
from querivue_agent.contracts.artifacts import ArtifactRef, Sha256, SourceDependency
from querivue_agent.contracts.values import CanonicalUUID, TypedScalar
from querivue_agent.contracts.evidence import SafeInteger, PositiveSafeInteger
from querivue_agent.runtime.sql_policy import SQLPolicyValidator, SQLValidationError, create_sql_policy_validator


@dataclass(frozen=True)
class SQLToolContext:
    """Context for SQL tool execution."""
    run_id: CanonicalUUID
    action_id: CanonicalUUID
    attempt: int
    authorized_tables: dict[CanonicalUUID, Path]  # table_id -> database path
    authorized_evidence: dict[CanonicalUUID, Path]  # evidence_id -> parquet path
    analysis_timezone: str | None
    policy_version: str
    artifact_dir: Path
    environment_manifest_id: CanonicalUUID
    operation_id: CanonicalUUID
    runner_nonce: str
    deadline: datetime


class SQLToolExecutor:
    """Executes SQL tools within a validated context."""

    def __init__(self, context: SQLToolContext) -> None:
        self._context = context
        self._conn: duckdb.DuckDBPyConnection | None = None
        self._policy_validator = create_sql_policy_validator(context.policy_version)

    async def start(self) -> None:
        """Initialize DuckDB connection."""
        if not self._context.authorized_tables:
            raise RuntimeError("No authorized tables")

        db_path = next(iter(self._context.authorized_tables.values()))
        self._conn = duckdb.connect(str(db_path), read_only=False)

        self._conn.execute("SET enable_progress_bar=false")

        tz = self._context.analysis_timezone or "UTC"
        self._conn.execute(f"SET TimeZone='{tz}'")

        mem_limit = 1  # 1 GiB
        self._conn.execute(f"PRAGMA memory_limit='{mem_limit}GiB'")

        # Register evidence relations
        for evidence_id, parquet_path in self._context.authorized_evidence.items():
            relation_name = f"evidence_{evidence_id}".replace("-", "_")
            self._conn.execute(
                f"CREATE VIEW {relation_name} AS SELECT * FROM read_parquet('{parquet_path}')"
            )

        self._conn.execute("PRAGMA lock_configuration=true")

    def _get_table_sql_name(self, table_id: CanonicalUUID) -> str:
        """Get the SQL name for a table."""
        # Runtime would provide this mapping; for now use a convention
        return f"main.t_{table_id}".replace("-", "_")

    def _get_evidence_relation_name(self, evidence_id: CanonicalUUID) -> str:
        """Get the SQL relation name for evidence."""
        return f"evidence_{evidence_id}".replace("-", "_")

    async def inspect_table(self, request: InspectTableRequest) -> SQLInspectedEvidence:
        """Execute inspect_table tool."""
        table_id = request.table_id

        if table_id not in self._context.authorized_tables:
            raise SQLValidationError("unknown_relation", f"Table not authorized: {table_id}", "validation")

        table_name = self._get_table_sql_name(table_id)

        # Get schema
        schema = self._conn.execute(f"DESCRIBE {table_name}").fetchall()

        columns = []
        for i, col in enumerate(schema):
            col_name, col_type, *_ = col
            columns.append(EvidenceColumn(
                ordinal=SafeInteger(i),
                name=NonblankString(col_name),
                original_label=col_name,
                original_ordinal=SafeInteger(i),
                type=self._duckdb_to_column_type(col_type),
                nullable=True,
            ))

        # Get row count
        count_result = self._conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()
        row_count = SafeInteger(count_result[0] if count_result else 0)

        # Build preview (first 10 rows)
        preview_result = self._conn.execute(f"SELECT * FROM {table_name} LIMIT 10").fetchall()
        rows = []
        row_locators = []
        for i, row in enumerate(preview_result):
            row_data = []
            for val in row:
                row_data.append(str(val) if val is not None else None)
            rows.append(row_data)
            row_locators.append(SafeInteger(i))

        preview = TabularPreview(
            columns=columns,
            rows=rows,
            row_locators=row_locators,
            full_row_count=row_count,
            returned_row_count=SafeInteger(len(rows)),
            effective_limit=PositiveSafeInteger(10),
            ordering="unspecified",
            truncated=len(rows) < int(row_count),
            shortened_cells=[],
        )

        # Create artifact reference for the table
        artifact = ArtifactRef(
            artifact_id=CanonicalUUID(str(uuid4())),
            storage_ref=CanonicalUUID(str(uuid4())),
            environment_manifest_id=self._context.environment_manifest_id,
            media_type="application/vnd.apache.parquet",
            size_bytes=0,  # Not materialized
            sha256=Sha256("0" * 64),
        )

        # Dependencies - this table's dataset/snapshot
        dependencies = [SourceDependency(
            dataset_id=CanonicalUUID(str(uuid4())),
            snapshot_id=CanonicalUUID(str(uuid4())),
        )]

        producer = SQLProducer(
            kind="sql",
            run_id=self._context.run_id,
            action_id=self._context.action_id,
            operation_id=self._context.operation_id,
            attempt=self._context.attempt,
            sql=f"SELECT * FROM {table_name}",
            parameters={},
            table_ids=[table_id],
            input_evidence_ids=[],
            constraints=AnalysisConstraints(
                metric_definitions={},
                filters=[],
                date_windows=[],
                analysis_timezone=None,
                grain=None,
                units={},
            ),
            environment_manifest_id=self._context.environment_manifest_id,
            policy_version=NonblankString(self._context.policy_version),
        )

        return SQLInspectedEvidence(
            evidence_id=CanonicalUUID(str(uuid4())),
            content_hash=Sha256("0" * 64),
            artifact=artifact,
            columns=columns,
            row_count=row_count,
            preview=preview,
            producer=producer,
            dependencies=dependencies,
            sql_relation=NonblankString(table_name),
        )

    async def preview_rows(self, request: PreviewRowsRequest) -> TabularPreview:
        """Execute preview_rows tool."""
        table_id = request.table_id
        columns = request.columns
        limit = request.limit

        if table_id not in self._context.authorized_tables:
            raise SQLValidationError("unknown_relation", f"Table not authorized: {table_id}", "validation")

        table_name = self._get_table_sql_name(table_id)

        # Get full schema first
        full_schema = self._conn.execute(f"DESCRIBE {table_name}").fetchall()

        # Filter columns if specified
        if columns:
            col_names = [str(c) for c in columns]
            # Validate all columns exist
            available = {col[0] for col in full_schema}
            for c in col_names:
                if c not in available:
                    raise SQLValidationError("unknown_column", f"Column not found: {c}", "validation")
            col_list = ", ".join(f'"{c}"' for c in col_names)
            selected_indices = [i for i, col in enumerate(full_schema) if col[0] in col_names]
        else:
            col_list = ", ".join(f'"{col[0]}"' for col in full_schema)
            selected_indices = list(range(len(full_schema)))

        # Get row count
        count_result = self._conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()
        full_row_count = SafeInteger(count_result[0] if count_result else 0)

        # Execute preview query
        query = f"SELECT {col_list} FROM {table_name} LIMIT {limit}"
        result = self._conn.execute(query).fetchall()

        # Build column definitions for selected columns
        preview_columns = []
        for idx in selected_indices:
            col = full_schema[idx]
            col_name, col_type, *_ = col
            preview_columns.append(EvidenceColumn(
                ordinal=SafeInteger(len(preview_columns)),
                name=NonblankString(col_name),
                original_label=col_name,
                original_ordinal=SafeInteger(idx),
                type=self._duckdb_to_column_type(col_type),
                nullable=True,
            ))

        # Build rows with display encoding
        rows = []
        row_locators = []
        for i, row in enumerate(result):
            row_data = []
            for val in row:
                row_data.append(str(val) if val is not None else None)
            rows.append(row_data)
            row_locators.append(SafeInteger(i))

        returned_count = SafeInteger(len(rows))

        shortened_cells = []
        # Check for cells exceeding 2048 bytes
        for row_idx, row in enumerate(rows):
            for col_idx, cell in enumerate(row):
                if cell is not None and len(cell.encode("utf-8")) > 2048:
                    shortened_cells.append(CellLocator(
                        row_locator=row_locators[row_idx],
                        column_ordinal=preview_columns[col_idx].ordinal,
                    ))

        return TabularPreview(
            columns=preview_columns,
            rows=rows,
            row_locators=row_locators,
            full_row_count=full_row_count,
            returned_row_count=returned_count,
            effective_limit=PositiveSafeInteger(limit),
            ordering="unspecified",
            truncated=returned_count < full_row_count or len(shortened_cells) > 0,
            shortened_cells=shortened_cells,
        )

    async def inspect_evidence(self, request: InspectEvidenceRequest) -> SQLInspectedEvidence:
        """Execute inspect_evidence tool."""
        evidence_id = request.evidence_id

        if evidence_id not in self._context.authorized_evidence:
            raise SQLValidationError("unknown_relation", f"Evidence not authorized: {evidence_id}", "validation")

        parquet_path = self._context.authorized_evidence[evidence_id]
        relation_name = self._get_evidence_relation_name(evidence_id)

        # Get schema from the view
        schema = self._conn.execute(f"DESCRIBE {relation_name}").fetchall()

        columns = []
        for i, col in enumerate(schema):
            col_name, col_type, *_ = col
            columns.append(EvidenceColumn(
                ordinal=SafeInteger(i),
                name=NonblankString(col_name),
                original_label=col_name,
                original_ordinal=SafeInteger(i),
                type=self._duckdb_to_column_type(col_type),
                nullable=True,
            ))

        # Get row count
        count_result = self._conn.execute(f"SELECT COUNT(*) FROM {relation_name}").fetchone()
        row_count = SafeInteger(count_result[0] if count_result else 0)

        # Build preview (first 10 rows)
        preview_result = self._conn.execute(f"SELECT * FROM {relation_name} LIMIT 10").fetchall()
        rows = []
        row_locators = []
        for i, row in enumerate(preview_result):
            row_data = []
            for val in row:
                row_data.append(str(val) if val is not None else None)
            rows.append(row_data)
            row_locators.append(SafeInteger(i))

        preview = TabularPreview(
            columns=columns,
            rows=rows,
            row_locators=row_locators,
            full_row_count=row_count,
            returned_row_count=SafeInteger(len(rows)),
            effective_limit=PositiveSafeInteger(10),
            ordering="unspecified",
            truncated=len(rows) < int(row_count),
            shortened_cells=[],
        )

        # Read artifact metadata
        artifact_size = parquet_path.stat().st_size
        sha256 = hashlib.sha256()
        with open(parquet_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        artifact_hash = Sha256(sha256.hexdigest())

        artifact = ArtifactRef(
            artifact_id=CanonicalUUID(str(uuid4())),
            storage_ref=CanonicalUUID(str(uuid4())),
            environment_manifest_id=self._context.environment_manifest_id,
            media_type="application/vnd.apache.parquet",
            size_bytes=artifact_size,
            sha256=artifact_hash,
        )

        dependencies = [SourceDependency(
            dataset_id=CanonicalUUID(str(uuid4())),
            snapshot_id=CanonicalUUID(str(uuid4())),
        )]

        producer = SQLProducer(
            kind="sql",
            run_id=self._context.run_id,
            action_id=self._context.action_id,
            operation_id=self._context.operation_id,
            attempt=self._context.attempt,
            sql=f"SELECT * FROM {relation_name}",
            parameters={},
            table_ids=[],
            input_evidence_ids=[evidence_id],
            constraints=AnalysisConstraints(
                metric_definitions={},
                filters=[],
                date_windows=[],
                analysis_timezone=None,
                grain=None,
                units={},
            ),
            environment_manifest_id=self._context.environment_manifest_id,
            policy_version=NonblankString(self._context.policy_version),
        )

        return SQLInspectedEvidence(
            evidence_id=evidence_id,
            content_hash=artifact_hash,
            artifact=artifact,
            columns=columns,
            row_count=row_count,
            preview=preview,
            producer=producer,
            dependencies=dependencies,
            sql_relation=NonblankString(relation_name),
        )

    async def execute_query(self, request: ExecuteQueryRequest) -> TabularEvidence:
        """Execute execute_query tool."""
        # Validate against policy
        self._policy_validator.validate(
            request,
            set(self._context.authorized_tables.keys()),
            set(self._context.authorized_evidence.keys())
        )

        # Build parameterized query - replace named parameters with ?
        param_names = list(request.parameters.keys())
        param_values = [self._typed_scalar_to_python(request.parameters[name]) for name in param_names]

        # Replace :name with ? in the SQL
        query_sql = request.sql
        for name in param_names:
            query_sql = query_sql.replace(f":{name}", "?")

        # Execute and write to Parquet
        with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as tmp:
            output_path = Path(tmp.name)

        try:
            query = f"COPY ({query_sql}) TO '{output_path}' (FORMAT PARQUET)"
            self._conn.execute(query, param_values)

            # Read back result
            result_table = self._conn.execute(f"SELECT * FROM read_parquet('{output_path}')").fetchall()
            row_count = SafeInteger(len(result_table))

            # Get schema
            schema = self._conn.execute(f"DESCRIBE SELECT * FROM read_parquet('{output_path}')").fetchall()

            columns = []
            for i, col in enumerate(schema):
                col_name, col_type, *_ = col
                columns.append(EvidenceColumn(
                    ordinal=SafeInteger(i),
                    name=NonblankString(col_name),
                    original_label=col_name,
                    original_ordinal=SafeInteger(i),
                    type=self._duckdb_to_column_type(col_type),
                    nullable=True,
                ))

            # Build preview (first 100 rows)
            preview_rows = result_table[:100]
            rows = []
            row_locators = []
            for i, row in enumerate(preview_rows):
                row_data = []
                for val in row:
                    row_data.append(str(val) if val is not None else None)
                rows.append(row_data)
                row_locators.append(SafeInteger(i))

            returned_count = SafeInteger(len(rows))

            shortened_cells = []
            for row_idx, row in enumerate(rows):
                for col_idx, cell in enumerate(row):
                    if cell is not None and len(cell.encode("utf-8")) > 2048:
                        shortened_cells.append(CellLocator(
                            row_locator=row_locators[row_idx],
                            column_ordinal=columns[col_idx].ordinal,
                        ))

            preview = TabularPreview(
                columns=columns,
                rows=rows,
                row_locators=row_locators,
                full_row_count=row_count,
                returned_row_count=returned_count,
                effective_limit=PositiveSafeInteger(100),
                ordering="query_defined",
                truncated=returned_count < row_count or len(shortened_cells) > 0,
                shortened_cells=shortened_cells,
            )

            # Compute artifact hash
            sha256 = hashlib.sha256()
            with open(output_path, "rb") as f:
                for chunk in iter(lambda: f.read(8192), b""):
                    sha256.update(chunk)
            artifact_hash = Sha256(sha256.hexdigest())
            artifact_size = output_path.stat().st_size

            # Move to artifact directory
            final_path = self._context.artifact_dir / f"evidence_{self._context.operation_id}.parquet"
            final_path.parent.mkdir(parents=True, exist_ok=True)
            import shutil
            shutil.move(str(output_path), str(final_path))

            artifact = ArtifactRef(
                artifact_id=self._context.operation_id,
                storage_ref=CanonicalUUID(str(uuid4())),
                environment_manifest_id=self._context.environment_manifest_id,
                media_type="application/vnd.apache.parquet",
                size_bytes=artifact_size,
                sha256=artifact_hash,
            )

            # Build producer provenance
            producer = SQLProducer(
                kind="sql",
                run_id=self._context.run_id,
                action_id=self._context.action_id,
                operation_id=self._context.operation_id,
                attempt=self._context.attempt,
                sql=request.sql,
                parameters={k: v for k, v in request.parameters.items()},
                table_ids=list(self._context.authorized_tables.keys()),
                input_evidence_ids=list(self._context.authorized_evidence.keys()),
                constraints=AnalysisConstraints(
                    metric_definitions={},
                    filters=[],
                    date_windows=[],
                    analysis_timezone=None,
                    grain=None,
                    units={},
                ),
                environment_manifest_id=self._context.environment_manifest_id,
                policy_version=NonblankString(self._context.policy_version),
            )

            dependencies = [
                SourceDependency(dataset_id=CanonicalUUID(str(uuid4())), snapshot_id=CanonicalUUID(str(uuid4())))
                for _ in self._context.authorized_tables
            ] + [
                SourceDependency(dataset_id=CanonicalUUID(str(uuid4())), snapshot_id=CanonicalUUID(str(uuid4())))
                for _ in self._context.authorized_evidence
            ]

            evidence_id = CanonicalUUID(str(uuid4()))
            return TabularEvidence(
                evidence_id=evidence_id,
                content_hash=artifact_hash,
                artifact=artifact,
                columns=columns,
                row_count=row_count,
                preview=preview,
                producer=producer,
                dependencies=dependencies,
            )

        finally:
            if output_path.exists():
                output_path.unlink(missing_ok=True)

    def _duckdb_to_column_type(self, duckdb_type: str) -> ColumnType:
        """Convert DuckDB type to ColumnType."""
        duckdb_type = duckdb_type.upper()
        if "INT" in duckdb_type and "UNSIGNED" in duckdb_type:
            return Uint64Column(tag="uint64")
        if "INT" in duckdb_type or "BIGINT" in duckdb_type or "SMALLINT" in duckdb_type or "TINYINT" in duckdb_type:
            return Int64Column(tag="int64")
        if "DECIMAL" in duckdb_type or "NUMERIC" in duckdb_type:
            # Extract precision/scale if possible
            return DecimalColumn(tag="decimal", precision=38, scale=10)
        if "FLOAT" in duckdb_type or "DOUBLE" in duckdb_type or "REAL" in duckdb_type:
            return Float64Column(tag="float64")
        if "VARCHAR" in duckdb_type or "TEXT" in duckdb_type or "CHAR" in duckdb_type or "STRING" in duckdb_type:
            return StringColumn(tag="string")
        if "DATE" == duckdb_type:
            return DateColumn(tag="date")
        if "TIME" == duckdb_type:
            return TimeColumn(tag="time")
        if "TIMESTAMP" in duckdb_type and "TZ" in duckdb_type:
            return TimestamptzColumn(tag="timestamptz")
        if "TIMESTAMP" in duckdb_type:
            return TimestampColumn(tag="timestamp")
        if "BOOLEAN" in duckdb_type or "BOOL" == duckdb_type:
            return BooleanColumn(tag="boolean")
        return StringColumn(tag="string")

    def _typed_scalar_to_python(self, typed_scalar: TypedScalar) -> Any:
        """Convert TypedScalar to Python value for DuckDB binding."""
        # TypedScalar uses 'kind' as discriminator
        kind = getattr(typed_scalar, 'kind', None)
        if kind == "null":
            return None
        if kind == "boolean":
            return typed_scalar.value
        if kind in ("int64", "uint64"):
            return int(typed_scalar.value)
        if kind == "decimal":
            from decimal import Decimal
            return Decimal(str(typed_scalar.value))
        if kind == "float64":
            return float(typed_scalar.value)
        if kind in ("string", "date", "time", "timestamp", "timestamptz"):
            return str(typed_scalar.value)
        return str(typed_scalar)

    async def shutdown(self) -> None:
        """Close connection."""
        if self._conn:
            self._conn.close()
            self._conn = None


async def create_sql_tool_executor(context: SQLToolContext) -> SQLToolExecutor:
    """Create and initialize a SQL tool executor."""
    executor = SQLToolExecutor(context)
    await executor.start()
    return executor