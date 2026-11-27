"""Persistent SQL action runner with DuckDB connection and file mailbox protocol."""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import tempfile
import uuid
from dataclasses import dataclass, field
from datetime import datetime, UTC
from pathlib import Path
from typing import Any, Literal
from uuid import UUID, uuid4

import duckdb

from querivue_agent.contracts.tools import ExecuteQueryRequest, InspectTableRequest, PreviewRowsRequest, InspectEvidenceRequest
from querivue_agent.contracts.evidence import TabularEvidence, TabularPreview, SQLProducer, EvidenceColumn, ColumnType, CellLocator
from querivue_agent.contracts.artifacts import ArtifactRef, Sha256, SourceDependency
from querivue_agent.contracts.values import CanonicalUUID, TypedScalar
from querivue_agent.runtime.sql_policy import SQLPolicyValidator, SQLValidationError, create_sql_policy_validator


@dataclass(frozen=True)
class MailboxRequest:
    """Request file for SDK file mailbox protocol."""
    mailbox_id: UUID
    operation_id: UUID
    action_id: UUID
    attempt: int
    runner_nonce: str
    request_type: Literal["inspect_table", "preview_rows", "inspect_evidence", "execute_query"]
    payload: dict[str, Any]
    request_digest: str  # SHA-256 of canonical payload
    deadline: str  # ISO timestamp


@dataclass(frozen=True)
class MailboxResponse:
    """Response file for SDK file mailbox protocol."""
    mailbox_id: UUID
    operation_id: UUID
    action_id: UUID
    attempt: int
    runner_nonce: str
    status: Literal["succeeded", "failed", "timeout"]
    result: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
    response_digest: str = ""  # SHA-256 of canonical result


@dataclass(frozen=True)
class SQLRunnerConfig:
    """Configuration for SQL runner."""
    action_id: UUID
    run_id: UUID
    attempt: int
    runner_nonce: str
    sandbox_id: UUID
    pid: int
    authorized_tables: dict[CanonicalUUID, Path]  # table_id -> database path
    authorized_evidence: dict[CanonicalUUID, Path]  # evidence_id -> parquet path
    analysis_timezone: str | None
    policy_version: str
    mailbox_dir: Path
    artifact_dir: Path
    resource_limits: dict[str, Any]


class SQLRunner:
    """Persistent SQL action runner with DuckDB connection."""

    def __init__(self, config: SQLRunnerConfig) -> None:
        self._config = config
        self._conn: duckdb.DuckDBPyConnection | None = None
        self._policy_validator = create_sql_policy_validator(config.policy_version)
        self._operation_counter = 0
        self._completed_operations: dict[str, MailboxResponse] = {}  # request_digest -> response

    async def start(self) -> None:
        """Start the runner and establish DuckDB connection."""
        # Connect to the first authorized table's database (they're all the same DuckDB file)
        if not self._config.authorized_tables:
            raise RuntimeError("No authorized tables provided")

        # Use the first database path
        db_path = next(iter(self._config.authorized_tables.values()))
        self._conn = duckdb.connect(str(db_path), read_only=False)

        # Configure session
        self._conn.execute("SET enable_progress_bar=false")

        # Set timezone
        tz = self._config.analysis_timezone or "UTC"
        self._conn.execute(f"SET TimeZone='{tz}'")

        # Set memory limit
        mem_limit = self._config.resource_limits.get("duckdb_memory_gib", 1.0)
        self._conn.execute(f"PRAGMA memory_limit='{int(mem_limit)}GiB'")

        # Register evidence relations
        for evidence_id, parquet_path in self._config.authorized_evidence.items():
            relation_name = f"evidence_{evidence_id}".replace("-", "_")
            self._conn.execute(
                f"CREATE VIEW {relation_name} AS SELECT * FROM read_parquet('{parquet_path}')"
            )

        # Lock configuration
        self._conn.execute("PRAGMA lock_configuration=true")

    def _get_next_operation_id(self) -> UUID:
        """Generate next operation ID."""
        self._operation_counter += 1
        return UUID(bytes=uuid4().bytes[:14] + self._operation_counter.to_bytes(2, "big"))

    def _compute_digest(self, data: dict[str, Any]) -> str:
        """Compute SHA-256 digest of canonical JSON."""
        import hashlib
        canonical = json.dumps(data, separators=(",", ":"), sort_keys=True)
        return hashlib.sha256(canonical.encode()).hexdigest()

    async def handle_request(self, request_file: Path) -> MailboxResponse:
        """Handle a mailbox request file."""
        # Read and validate request
        with open(request_file, "r") as f:
            request_data = json.load(f)

        mailbox_request = MailboxRequest(**request_data)
        return await self._handle_request_data(mailbox_request)

    async def handle_request_from_data(self, mailbox_request: MailboxRequest) -> MailboxResponse:
        """Handle a mailbox request from data object."""
        return await self._handle_request_data(mailbox_request)

    async def _handle_request_data(self, mailbox_request: MailboxRequest) -> MailboxResponse:
        """Handle a mailbox request from data object."""

        # Check for duplicate request digest
        if mailbox_request.request_digest in self._completed_operations:
            return self._completed_operations[mailbox_request.request_digest]

        # Create operation ID
        operation_id = self._get_next_operation_id()

        # Dispatch to appropriate handler
        try:
            if mailbox_request.request_type == "inspect_table":
                result = await self._handle_inspect_table(mailbox_request.payload, operation_id)
            elif mailbox_request.request_type == "preview_rows":
                result = await self._handle_preview_rows(mailbox_request.payload, operation_id)
            elif mailbox_request.request_type == "inspect_evidence":
                result = await self._handle_inspect_evidence(mailbox_request.payload, operation_id)
            elif mailbox_request.request_type == "execute_query":
                result = await self._handle_execute_query(mailbox_request.payload, operation_id)
            else:
                raise ValueError(f"Unknown request type: {mailbox_request.request_type}")

            response = MailboxResponse(
                mailbox_id=mailbox_request.mailbox_id,
                operation_id=operation_id,
                action_id=mailbox_request.action_id,
                attempt=mailbox_request.attempt,
                runner_nonce=self._config.runner_nonce,
                status="succeeded",
                result=result,
                response_digest=self._compute_digest(result) if result else "",
            )

        except SQLValidationError as e:
            response = MailboxResponse(
                mailbox_id=mailbox_request.mailbox_id,
                operation_id=operation_id,
                action_id=mailbox_request.action_id,
                attempt=mailbox_request.attempt,
                runner_nonce=self._config.runner_nonce,
                status="failed",
                error={
                    "code": e.code,
                    "message": e.message,
                    "stage": e.stage,
                    "operation_id": str(e.operation_id) if e.operation_id else None,
                    "disposition": e.disposition,
                },
                response_digest="",
            )
        except Exception as e:
            response = MailboxResponse(
                mailbox_id=mailbox_request.mailbox_id,
                operation_id=operation_id,
                action_id=mailbox_request.action_id,
                attempt=mailbox_request.attempt,
                runner_nonce=self._config.runner_nonce,
                status="failed",
                error={
                    "code": "internal_error",
                    "message": str(e),
                    "stage": "execution",
                    "operation_id": str(operation_id),
                    "disposition": "fail_action",
                },
                response_digest="",
            )

        # Cache completed operation
        self._completed_operations[mailbox_request.request_digest] = response
        return response

    async def _handle_inspect_table(self, payload: dict[str, Any], operation_id: UUID) -> dict[str, Any]:
        """Handle inspect_table request."""
        request = InspectTableRequest(**payload)
        table_id = request.table_id

        # Get table info from database
        # The table SQL name would be provided by runtime; we query the catalog
        table_name = f"t_{table_id}".replace("-", "_")

        # Get schema
        schema = self._conn.execute(f"DESCRIBE {table_name}").fetchall()
        columns = []
        for i, col in enumerate(schema):
            col_name, col_type, *_ = col
            columns.append({
                "ordinal": i,
                "name": col_name,
                "type": col_type,
                "nullable": True,  # Would come from detailed schema
            })

        # Get row count
        count_result = self._conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()
        row_count = count_result[0] if count_result else 0

        # Get profile stats if available
        # For now return basic info
        return {
            "table_id": str(table_id),
            "sql_name": table_name,
            "row_count": row_count,
            "columns": columns,
            "source_descriptor": f"Table {table_id}",
            "import_warnings": [],
        }

    async def _handle_preview_rows(self, payload: dict[str, Any], operation_id: UUID) -> dict[str, Any]:
        """Handle preview_rows request."""
        request = PreviewRowsRequest(**payload)
        table_id = request.table_id
        columns = request.columns
        limit = request.limit

        table_name = f"t_{table_id}".replace("-", "_")

        # Build column list
        if columns:
            col_list = ", ".join(f'"{c}"' for c in columns)
        else:
            # Get all columns
            schema = self._conn.execute(f"DESCRIBE {table_name}").fetchall()
            col_list = ", ".join(f'"{col[0]}"' for col in schema)

        # Execute preview query
        query = f"SELECT {col_list} FROM {table_name} LIMIT {limit}"
        result = self._conn.execute(query).fetchall()

        # Get column definitions
        desc = self._conn.execute(f"DESCRIBE {table_name}").fetchall()
        column_defs = []
        for i, col in enumerate(desc):
            if not columns or col[0] in columns:
                col_name, col_type, *_ = col
                column_defs.append({
                    "ordinal": i,
                    "name": col_name,
                    "original_label": col_name,
                    "original_ordinal": i,
                    "type": {"tag": self._duckdb_to_column_type(col_type)},
                    "nullable": True,
                })

        # Build rows with display encoding
        rows = []
        row_locators = []
        for i, row in enumerate(result):
            row_data = []
            for j, val in enumerate(row):
                if val is None:
                    row_data.append(None)
                else:
                    row_data.append(str(val))
            rows.append(row_data)
            row_locators.append(i)

        full_count_result = self._conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()
        full_row_count = full_count_result[0] if full_count_result else 0

        shortened_cells = []  # Would track cells truncated at 2048 bytes

        return {
            "columns": column_defs,
            "rows": rows,
            "row_locators": row_locators,
            "full_row_count": full_row_count,
            "returned_row_count": len(rows),
            "effective_limit": limit,
            "ordering": "unspecified",
            "truncated": len(rows) < full_row_count,
            "shortened_cells": shortened_cells,
        }

    async def _handle_inspect_evidence(self, payload: dict[str, Any], operation_id: UUID) -> dict[str, Any]:
        """Handle inspect_evidence request."""
        request = InspectEvidenceRequest(**payload)
        evidence_id = request.evidence_id

        if evidence_id not in self._config.authorized_evidence:
            raise SQLValidationError("unknown_relation", f"Evidence not authorized: {evidence_id}", "validation")

        parquet_path = self._config.authorized_evidence[evidence_id]
        relation_name = f"evidence_{evidence_id}".replace("-", "_")

        # Get schema from the view
        schema = self._conn.execute(f"DESCRIBE {relation_name}").fetchall()

        columns = []
        for i, col in enumerate(schema):
            col_name, col_type, *_ = col
            columns.append({
                "ordinal": i,
                "name": col_name,
                "original_label": col_name,
                "original_ordinal": i,
                "type": {"tag": self._duckdb_to_column_type(col_type)},
                "nullable": True,
            })

        # Get row count
        count_result = self._conn.execute(f"SELECT COUNT(*) FROM {relation_name}").fetchone()
        row_count = count_result[0] if count_result else 0

        # Get preview (first 10 rows)
        preview_result = self._conn.execute(f"SELECT * FROM {relation_name} LIMIT 10").fetchall()
        rows = []
        row_locators = []
        for i, row in enumerate(preview_result):
            row_data = []
            for val in row:
                row_data.append(str(val) if val is not None else None)
            rows.append(row_data)
            row_locators.append(i)

        return {
            "evidence_id": str(evidence_id),
            "sql_relation": relation_name,
            "columns": columns,
            "row_count": row_count,
            "preview": {
                "columns": columns,
                "rows": rows,
                "row_locators": row_locators,
                "full_row_count": row_count,
                "returned_row_count": len(rows),
                "effective_limit": 10,
                "ordering": "unspecified",
                "truncated": len(rows) < row_count,
                "shortened_cells": [],
            },
        }

    async def _handle_execute_query(self, payload: dict[str, Any], operation_id: UUID) -> dict[str, Any]:
        """Handle execute_query request."""
        request = ExecuteQueryRequest(**payload)

        # Validate against policy
        authorized_relations = self._policy_validator.validate(
            request,
            set(self._config.authorized_tables.keys()),
            set(self._config.authorized_evidence.keys())
        )

        conn = self._conn

        # Build parameterized query - replace named parameters with ?
        param_names = list(request.parameters.keys())
        param_values = [self._typed_scalar_to_python(request.parameters[name]) for name in param_names]

        # Replace :name with ? in the SQL
        query_sql = request.sql
        for name in param_names:
            query_sql = query_sql.replace(f":{name}", "?")

        # Execute query and write to Parquet
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as tmp:
            output_path = Path(tmp.name)

        try:
            query = f"COPY ({query_sql}) TO '{output_path}' (FORMAT PARQUET)"
            conn.execute(query, param_values)

            # Read back to get schema and count
            result = conn.execute(f"SELECT * FROM read_parquet('{output_path}')").fetchall()
            row_count = len(result)

            # Get schema
            schema = conn.execute(f"DESCRIBE SELECT * FROM read_parquet('{output_path}')").fetchall()

            columns = []
            for i, col in enumerate(schema):
                col_name, col_type, *_ = col
                columns.append({
                    "ordinal": i,
                    "name": col_name,
                    "original_label": col_name,
                    "original_ordinal": i,
                    "type": {"tag": self._duckdb_to_column_type(col_type)},
                    "nullable": True,
                })

            # Build preview (first 100 rows)
            preview_rows = result[:100]
            rows = []
            row_locators = []
            for i, row in enumerate(preview_rows):
                row_data = []
                for val in row:
                    row_data.append(str(val) if val is not None else None)
                rows.append(row_data)
                row_locators.append(i)

            # Compute artifact hash
            import hashlib
            sha256 = hashlib.sha256()
            with open(output_path, "rb") as f:
                for chunk in iter(lambda: f.read(8192), b""):
                    sha256.update(chunk)
            artifact_hash = sha256.hexdigest()
            artifact_size = output_path.stat().st_size

            # Move to artifact directory
            artifact_path = self._config.artifact_dir / f"evidence_{operation_id}.parquet"
            artifact_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(output_path), str(artifact_path))

            return {
                "evidence_id": str(operation_id),  # Using operation_id as evidence_id for now
                "artifact_path": str(artifact_path),
                "artifact_hash": artifact_hash,
                "artifact_size": artifact_size,
                "columns": columns,
                "row_count": row_count,
                "preview": {
                    "columns": columns,
                    "rows": rows,
                    "row_locators": row_locators,
                    "full_row_count": row_count,
                    "returned_row_count": len(rows),
                    "effective_limit": 100,
                    "ordering": "query_defined",
                    "truncated": len(rows) < row_count,
                    "shortened_cells": [],
                },
                "sql": request.sql,
                "parameters": {k: self._typed_scalar_to_json(v) for k, v in request.parameters.items()},
            }

        finally:
            if output_path.exists():
                output_path.unlink(missing_ok=True)

    def _duckdb_to_column_type(self, duckdb_type: str) -> str:
        """Convert DuckDB type to ColumnType tag."""
        duckdb_type = duckdb_type.upper()
        if "INT" in duckdb_type and "UNSIGNED" in duckdb_type:
            return "uint64"
        if "INT" in duckdb_type or "BIGINT" in duckdb_type or "SMALLINT" in duckdb_type or "TINYINT" in duckdb_type:
            return "int64"
        if "DECIMAL" in duckdb_type or "NUMERIC" in duckdb_type:
            return "decimal"
        if "FLOAT" in duckdb_type or "DOUBLE" in duckdb_type or "REAL" in duckdb_type:
            return "float64"
        if "VARCHAR" in duckdb_type or "TEXT" in duckdb_type or "CHAR" in duckdb_type or "STRING" in duckdb_type:
            return "string"
        if "DATE" == duckdb_type:
            return "date"
        if "TIME" == duckdb_type:
            return "time"
        if "TIMESTAMP" in duckdb_type and "TZ" in duckdb_type:
            return "timestamptz"
        if "TIMESTAMP" in duckdb_type:
            return "timestamp"
        if "BOOLEAN" in duckdb_type or "BOOL" == duckdb_type:
            return "boolean"
        return "string"

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

    def _typed_scalar_to_json(self, typed_scalar: TypedScalar) -> dict[str, Any]:
        """Convert TypedScalar to JSON-serializable dict."""
        if hasattr(typed_scalar, 'model_dump'):
            return typed_scalar.model_dump()
        if hasattr(typed_scalar, 'tag'):
            return {"tag": typed_scalar.tag, "value": typed_scalar.value}
        return {"value": str(typed_scalar)}

    async def shutdown(self) -> None:
        """Shutdown the runner and close connection."""
        if self._conn:
            self._conn.close()
            self._conn = None


async def create_sql_runner(config: SQLRunnerConfig) -> SQLRunner:
    """Create and start a SQL runner."""
    runner = SQLRunner(config)
    await runner.start()
    return runner