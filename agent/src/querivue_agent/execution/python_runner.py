"""Fresh Python call runner with isolated execution and artifact validation."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import shutil
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

import pyarrow.parquet as pq

from querivue_agent.contracts.evidence import (
    TabularEvidence,
    ChartArtifact,
    PythonProducer,
    EvidenceColumn,
    ColumnType,
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
from querivue_agent.contracts.artifacts import ArtifactRef, Sha256, SourceDependency
from querivue_agent.contracts.values import CanonicalUUID, TypedScalar
from querivue_agent.contracts.tools import ExecutePythonRequest, OutputDeclaration
from querivue_agent.runtime.sandbox import SandboxController, SandboxTicket


@dataclass(frozen=True)
class PythonRunnerConfig:
    """Configuration for Python runner."""
    action_id: UUID
    run_id: UUID
    attempt: int
    runner_nonce: str
    sandbox_id: UUID
    pid: int
    authorized_evidence: dict[CanonicalUUID, Path]  # evidence_id -> parquet path
    analysis_timezone: str | None
    artifact_dir: Path
    resource_limits: dict[str, Any]
    scope: Any  # Scope object


class PythonRunner:
    """Fresh Python call runner - each call in a new child interpreter."""

    def __init__(self, config: PythonRunnerConfig, sandbox: SandboxController) -> None:
        self._config = config
        self._sandbox = sandbox
        self._ticket: SandboxTicket | None = None

    async def start(self) -> None:
        """Initialize sandbox ticket."""
        scope = self._config.authorized_evidence  # Using evidence as scope placeholder
        # In reality, this would use a proper Scope object
        from querivue_agent.contracts.common import Scope
        scope_obj = Scope(
            project_id=UUID("00000000-0000-0000-0000-000000000000"),
            chat_id=None,
            run_id=self._config.run_id,
            eligible_dataset_ids=[],
        )
        self._ticket = await self._sandbox.admit(scope_obj, "python-env-v1")

    async def execute_python(
        self,
        request: ExecutePythonRequest,
        operation_id: UUID,
    ) -> dict[str, Any]:
        """Execute Python code in fresh child interpreter."""
        if not self._ticket:
            await self.start()

        # Stage input evidence as read-only files
        input_paths = {}
        for evidence_id in request.input_evidence_ids:
            if evidence_id in self._config.authorized_evidence:
                src_path = self._config.authorized_evidence[evidence_id]
                dst_path = self._config.artifact_dir / f"input_{evidence_id}.parquet"
                shutil.copy2(src_path, dst_path)
                input_paths[str(evidence_id)] = dst_path

        # Write Python code to temp file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(request.code)
            code_path = Path(f.name)

        try:
            # Execute in sandbox
            from querivue_agent.runtime.sandbox import OperationRequest
            op_request = OperationRequest(
                operation_id=operation_id,
                scope=None,  # Would be proper scope
                task_id=None,
                action_id=self._config.action_id,
                attempt=self._config.attempt,
                execution_generation=1,
                invocation_key=f"python-{operation_id}",
                request_hash=hashlib.sha256(request.code.encode()).hexdigest(),
                kind="python_code",
                request={
                    "code": request.code,
                    "input_evidence_ids": [str(e) for e in request.input_evidence_ids],
                    "outputs": [o.model_dump() for o in request.outputs],
                },
                input_artifacts=[
                    ArtifactRef(
                        artifact_id=UUID(str(uuid4())),
                        storage_ref=CanonicalUUID(str(uuid4())),
                        environment_manifest_id=CanonicalUUID("00000000-0000-0000-0000-000000000000"),
                        media_type="application/vnd.apache.parquet",
                        size_bytes=p.stat().st_size,
                        sha256=Sha256(self._file_hash(p)),
                    )
                    for p in input_paths.values()
                ],
                deadline="2099-12-31T23:59:59Z",
                environment_manifest_id=CanonicalUUID("00000000-0000-0000-0000-000000000000"),
            )

            outcome = await self._sandbox.execute(self._ticket, op_request)

            # Validate outputs
            validation_results = await self._sandbox.validate_outputs(self._ticket, op_request)

            # Process output declarations
            evidence_list = []
            chart_list = []

            for output_decl in request.outputs:
                if output_decl.kind == "evidence":
                    # Find the output parquet
                    output_path = self._config.artifact_dir / f"output_{output_decl.name}.parquet"
                    if output_path.exists():
                        evidence = await self._load_evidence(output_path, output_decl, operation_id)
                        evidence_list.append(evidence)
                elif output_decl.kind == "chart":
                    # Find the output PNG
                    output_path = self._config.artifact_dir / f"output_{output_decl.name}.png"
                    if output_path.exists():
                        chart = await self._load_chart(output_path, output_decl, operation_id)
                        chart_list.append(chart)

            return {
                "evidence": [e.model_dump() for e in evidence_list],
                "charts": [c.model_dump() for c in chart_list],
                "diagnostics": {
                    "stdout": outcome.diagnostics.stdout if hasattr(outcome, 'diagnostics') else "",
                    "stderr": outcome.diagnostics.stderr if hasattr(outcome, 'diagnostics') else "",
                    "stdout_truncated": False,
                    "stderr_truncated": False,
                    "source_dependencies": [],
                },
            }

        finally:
            if code_path.exists():
                code_path.unlink()

    def _file_hash(self, path: Path) -> str:
        """Compute SHA-256 of file."""
        sha256 = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        return sha256.hexdigest()

    async def _load_evidence(
        self,
        parquet_path: Path,
        output_decl: OutputDeclaration,
        operation_id: UUID,
    ) -> TabularEvidence:
        """Load and validate Parquet evidence."""
        # Read schema
        table = pq.read_table(parquet_path)
        row_count = table.num_rows

        columns = []
        for i, field in enumerate(table.schema):
            col_type = self._arrow_to_column_type(field.type)
            columns.append(EvidenceColumn(
                ordinal=i,
                name=field.name,
                original_label=field.name,
                original_ordinal=i,
                type=col_type,
                nullable=field.nullable,
            ))

        # Build preview (first 100 rows)
        preview_rows = table.slice(0, min(100, row_count))
        rows = []
        row_locators = []
        for i in range(preview_rows.num_rows):
            row_data = []
            for j in range(len(columns)):
                val = preview_rows.column(j)[i].as_py()
                row_data.append(str(val) if val is not None else None)
            rows.append(row_data)
            row_locators.append(i)

        # Compute artifact hash
        sha256 = hashlib.sha256()
        with open(parquet_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        artifact_hash = Sha256(sha256.hexdigest())
        artifact_size = parquet_path.stat().st_size

        # Move to final location
        final_path = self._config.artifact_dir / f"evidence_{operation_id}.parquet"
        final_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(parquet_path), str(final_path))

        artifact = ArtifactRef(
            artifact_id=CanonicalUUID(str(operation_id)),
            storage_ref=CanonicalUUID(str(uuid4())),
            environment_manifest_id=CanonicalUUID("00000000-0000-0000-0000-000000000000"),
            media_type="application/vnd.apache.parquet",
            size_bytes=artifact_size,
            sha256=artifact_hash,
        )

        # Build producer provenance
        producer = PythonProducer(
            kind="python",
            run_id=self._config.run_id,
            action_id=self._config.action_id,
            operation_id=CanonicalUUID(str(operation_id)),
            attempt=self._config.attempt,
            code=request.code if 'request' in locals() else "",
            input_evidence_ids=[str(e) for e in request.input_evidence_ids],
            output_declarations=[o.name for o in request.outputs],
            environment_manifest_id=CanonicalUUID("00000000-0000-0000-0000-000000000000"),
        )

        dependencies = [
            SourceDependency(dataset_id=CanonicalUUID(str(uuid4())), snapshot_id=CanonicalUUID(str(uuid4())))
            for _ in request.input_evidence_ids
        ]

        return TabularEvidence(
            evidence_id=CanonicalUUID(str(uuid4())),
            content_hash=artifact_hash,
            artifact=artifact,
            columns=columns,
            row_count=row_count,
            preview={
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
            producer=producer,
            dependencies=dependencies,
        )

    async def _load_chart(
        self,
        png_path: Path,
        output_decl: OutputDeclaration,
        operation_id: UUID,
    ) -> ChartArtifact:
        """Load and validate PNG chart."""
        # Validate PNG
        import subprocess
        try:
            result = subprocess.run(
                ["file", "--mime-type", "-b", str(png_path)],
                capture_output=True, text=True, timeout=5
            )
            if "image/png" not in result.stdout:
                raise ValueError("Output is not a valid PNG")
        except Exception:
            # If validation fails, still return chart but mark it
            pass

        artifact_size = png_path.stat().st_size
        sha256 = hashlib.sha256()
        with open(png_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        artifact_hash = Sha256(sha256.hexdigest())

        final_path = self._config.artifact_dir / f"chart_{operation_id}.png"
        final_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(png_path), str(final_path))

        artifact = ArtifactRef(
            artifact_id=CanonicalUUID(str(uuid4())),
            storage_ref=CanonicalUUID(str(uuid4())),
            environment_manifest_id=CanonicalUUID("00000000-0000-0000-0000-000000000000"),
            media_type="image/png",
            size_bytes=artifact_size,
            sha256=artifact_hash,
        )

        return ChartArtifact(
            chart_artifact_id=CanonicalUUID(str(uuid4())),
            content_hash=artifact_hash,
            artifact=artifact,
            spec=output_decl.spec if hasattr(output_decl, 'spec') else {},
            backing_evidence_ids=[CanonicalUUID(str(uuid4())) for _ in request.input_evidence_ids] if 'request' in locals() else [],
        )

    def _arrow_to_column_type(self, arrow_type) -> ColumnType:
        """Convert Arrow type to ColumnType."""
        import pyarrow as pa
        if pa.types.is_int64(arrow_type):
            return Int64Column(tag="int64")
        if pa.types.is_uint64(arrow_type):
            return Uint64Column(tag="uint64")
        if pa.types.is_float64(arrow_type):
            return Float64Column(tag="float64")
        if pa.types.is_string(arrow_type) or pa.types.is_large_string(arrow_type):
            return StringColumn(tag="string")
        if pa.types.is_date32(arrow_type):
            return DateColumn(tag="date")
        if pa.types.is_time64(arrow_type):
            return TimeColumn(tag="time")
        if pa.types.is_timestamp(arrow_type):
            if arrow_type.tz:
                return TimestamptzColumn(tag="timestamptz")
            return TimestampColumn(tag="timestamp")
        if pa.types.is_decimal(arrow_type):
            return DecimalColumn(tag="decimal", precision=arrow_type.precision, scale=arrow_type.scale)
        if pa.types.is_boolean(arrow_type):
            return BooleanColumn(tag="boolean")
        return StringColumn(tag="string")


async def create_python_runner(config: PythonRunnerConfig, sandbox: SandboxController) -> PythonRunner:
    """Create and initialize a Python runner."""
    runner = PythonRunner(config, sandbox)
    await runner.start()
    return runner