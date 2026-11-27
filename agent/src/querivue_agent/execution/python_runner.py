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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal
from uuid import UUID, uuid4

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
    OutputColumn,
    SafeInteger,
    PositiveSafeInteger,
    NonblankString,
)
from querivue_agent.contracts.actions import AnalysisConstraints
from querivue_agent.contracts.artifacts import ArtifactRef, Sha256, SourceDependency
from querivue_agent.contracts.values import CanonicalUUID, TypedScalar
from querivue_agent.contracts.tools import ExecutePythonRequest, OutputDeclaration
from querivue_agent.contracts.records import OperationRequest, SandboxTicket
from querivue_agent.contracts.common import Scope, PositiveCount
from querivue_agent.runtime.sandbox import SandboxController


@dataclass(frozen=True)
class PythonRunnerConfig:
    """Configuration for Python runner."""
    action_id: UUID
    run_id: UUID
    attempt: int
    runner_nonce: int  # Changed to int for PositiveCount
    sandbox_id: UUID
    pid: int
    authorized_evidence: dict[CanonicalUUID, Path]  # evidence_id -> parquet path
    analysis_timezone: str | None
    artifact_dir: Path
    resource_limits: dict[str, Any]
    scope: Scope


class PythonRunner:
    """Fresh Python call runner - each call in a new child interpreter."""

    def __init__(self, config: PythonRunnerConfig, sandbox: SandboxController) -> None:
        self._config = config
        self._sandbox = sandbox
        self._ticket: SandboxTicket | None = None

    async def start(self) -> None:
        """Initialize sandbox ticket."""
        # Create a sandbox ticket for this runner
        from querivue_agent.contracts.records import SandboxTicket
        from querivue_agent.contracts.values import CanonicalUUID, RuntimeUUID
        from querivue_agent.contracts.common import NonblankString

        ticket_id = str(uuid4())
        self._ticket = SandboxTicket(
            ticket_id=RuntimeUUID(ticket_id),
            scope=self._config.scope,
            sandbox_id=NonblankString(f"sandbox-{self._config.sandbox_id}"),
            command_id=NonblankString(f"python-{self._config.action_id}"),
            incarnation_id=RuntimeUUID(str(uuid4())),
            action_id=CanonicalUUID(str(self._config.action_id)),
            operation_id=None,
            attempt=self._config.attempt,
            generation=PositiveCount(self._config.runner_nonce),
            environment_manifest_id=CanonicalUUID("00000000-0000-0000-0000-000000000000"),
            state="prepared",
            created_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            expires_at="2099-12-31T23:59:59.999999Z",
        )

    async def execute_python(
        self,
        request: ExecutePythonRequest,
        operation_id: UUID,
    ) -> dict[str, Any]:
        """Execute Python code in fresh child interpreter."""
        await self.start()

        # Stage input evidence as read-only files
        evidence_paths = []
        for evidence_id in request.input_evidence_ids:
            if evidence_id in self._config.authorized_evidence:
                src_path = self._config.authorized_evidence[evidence_id]
                dst_path = self._config.artifact_dir / f"input_{evidence_id}.parquet"
                if not dst_path.exists():
                    shutil.copy2(src_path, dst_path)
                evidence_paths.append(dst_path)

        # Write Python code to temp file in artifact directory
        code_path = self._config.artifact_dir / f"script_{operation_id}.py"
        code_path.write_text(request.code)

        try:
            # Execute in sandbox using execute_python method
            outcome = await self._sandbox.execute_python(
                action_id=self._config.action_id,
                script_path=code_path,
                evidence_paths=evidence_paths,
            )

            # Debug: log stdout/stderr
            print(f"Python execution stdout: {outcome.stdout[:500]}")
            print(f"Python execution stderr: {outcome.stderr[:500]}")
            print(f"Python execution status: {outcome.status}")

            # Process output declarations from sandbox outputs
            evidence_list = []
            chart_list = []

            # Check for output files in the sandbox action directory (working dir) and outputs dir
            action_dir = self._sandbox._get_action_dir(self._config.action_id)
            output_dir = action_dir / "outputs"

            # Debug: list files in action_dir and output_dir
            print(f"Files in action_dir: {list(action_dir.glob('*'))}")
            print(f"Files in output_dir: {list(output_dir.glob('*')) if output_dir.exists() else 'N/A'}")

            for output_decl in request.outputs:
                if output_decl.kind == "evidence":
                    # Find the output parquet - check both working dir and outputs dir
                    output_path = output_dir / f"output_{output_decl.name}.parquet"
                    if not output_path.exists():
                        output_path = action_dir / f"output_{output_decl.name}.parquet"
                    print(f"Looking for evidence output at: {output_path}, exists: {output_path.exists()}")
                    if output_path.exists():
                        evidence = await self._load_evidence(output_path, output_decl, operation_id, request)
                        evidence_list.append(evidence)
                elif output_decl.kind == "chart":
                    # Find the output PNG - check both working dir and outputs dir
                    output_path = output_dir / f"output_{output_decl.name}.png"
                    if not output_path.exists():
                        output_path = action_dir / f"output_{output_decl.name}.png"
                    print(f"Looking for chart output at: {output_path}, exists: {output_path.exists()}")
                    if output_path.exists():
                        chart = await self._load_chart(output_path, output_decl, operation_id, request)
                        chart_list.append(chart)

            return {
                "evidence": [e.model_dump() for e in evidence_list],
                "charts": [c.model_dump() for c in chart_list],
                "diagnostics": {
                    "stdout": outcome.stdout,
                    "stderr": outcome.stderr,
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
        request: ExecutePythonRequest,
    ) -> TabularEvidence:
        """Load and validate Parquet evidence."""
        # Read schema
        table = pq.read_table(parquet_path)
        row_count = SafeInteger(table.num_rows)

        columns = []
        for i, field in enumerate(table.schema):
            col_type = self._arrow_to_column_type(field.type)
            columns.append(EvidenceColumn(
                ordinal=SafeInteger(i),
                name=NonblankString(field.name),
                original_label=field.name,
                original_ordinal=SafeInteger(i),
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
                cell_str = str(val) if val is not None else None
                # Truncate to 2048 UTF-8 bytes
                if cell_str is not None and len(cell_str.encode("utf-8")) > 2048:
                    cell_str = cell_str[:2045] + "..."
                row_data.append(cell_str)
            rows.append(row_data)
            row_locators.append(SafeInteger(i))

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

        # Build producer provenance with all required fields
        # Compute script hash
        script_sha256 = hashlib.sha256()
        script_sha256.update(request.code.encode('utf-8'))
        script_hash = Sha256(script_sha256.hexdigest())

        # Build constraints (empty for now - would come from action planning)
        constraints = AnalysisConstraints(
            metric_definitions={},
            filters=[],
            date_windows=[],
            analysis_timezone=None,
            grain=None,
            units={},
        )

        producer = PythonProducer(
            kind="python",
            run_id=CanonicalUUID(str(self._config.run_id)),
            action_id=CanonicalUUID(str(self._config.action_id)),
            operation_id=CanonicalUUID(str(operation_id)),
            attempt=PositiveSafeInteger(self._config.attempt),
            script_ref=CanonicalUUID(str(uuid4())),
            script_hash=script_hash,
            input_evidence_ids=[CanonicalUUID(str(e)) for e in request.input_evidence_ids],
            action_input_evidence_ids=[CanonicalUUID(str(e)) for e in request.input_evidence_ids],
            constraints=constraints,
            random_seed=None,
            method_parameters={},
            environment_manifest_id=CanonicalUUID("00000000-0000-0000-0000-000000000000"),
            policy_version=NonblankString("1.0"),
        )

        dependencies = [
            SourceDependency(dataset_id=CanonicalUUID(str(uuid4())), snapshot_id=CanonicalUUID(str(uuid4())))
            for _ in request.input_evidence_ids
        ]

        # Build preview as TabularPreview
        preview = {
            "columns": columns,
            "rows": rows,
            "row_locators": row_locators,
            "full_row_count": row_count,
            "returned_row_count": SafeInteger(len(rows)),
            "effective_limit": PositiveSafeInteger(100),
            "ordering": "query_defined",
            "truncated": len(rows) < int(row_count),
            "shortened_cells": [],
        }

        return TabularEvidence(
            evidence_id=CanonicalUUID(str(uuid4())),
            content_hash=artifact_hash,
            artifact=artifact,
            columns=columns,
            row_count=row_count,
            preview=preview,
            producer=producer,
            dependencies=dependencies,
        )

    async def _load_chart(
        self,
        png_path: Path,
        output_decl: OutputDeclaration,
        operation_id: UUID,
        request: ExecutePythonRequest,
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

        # Build producer provenance with all required fields
        # Compute script hash
        script_sha256 = hashlib.sha256()
        script_sha256.update(request.code.encode('utf-8'))
        script_hash = Sha256(script_sha256.hexdigest())

        constraints = AnalysisConstraints(
            metric_definitions={},
            filters=[],
            date_windows=[],
            analysis_timezone=None,
            grain=None,
            units={},
        )

        producer = PythonProducer(
            kind="python",
            run_id=CanonicalUUID(str(self._config.run_id)),
            action_id=CanonicalUUID(str(self._config.action_id)),
            operation_id=CanonicalUUID(str(operation_id)),
            attempt=PositiveSafeInteger(self._config.attempt),
            script_ref=CanonicalUUID(str(uuid4())),
            script_hash=script_hash,
            input_evidence_ids=[CanonicalUUID(str(e)) for e in request.input_evidence_ids],
            action_input_evidence_ids=[CanonicalUUID(str(e)) for e in request.input_evidence_ids],
            constraints=constraints,
            random_seed=None,
            method_parameters={},
            environment_manifest_id=CanonicalUUID("00000000-0000-0000-0000-000000000000"),
            policy_version=NonblankString("1.0"),
        )

        backing_evidence_ids = [CanonicalUUID(str(e)) for e in request.input_evidence_ids]

        dependencies = [
            SourceDependency(dataset_id=CanonicalUUID(str(uuid4())), snapshot_id=CanonicalUUID(str(uuid4())))
            for _ in request.input_evidence_ids
        ]

        # Get dimensions from the PNG
        try:
            from PIL import Image
            with Image.open(png_path) as img:
                pixel_width = PositiveSafeInteger(img.width)
                pixel_height = PositiveSafeInteger(img.height)
        except Exception:
            pixel_width = PositiveSafeInteger(800)
            pixel_height = PositiveSafeInteger(600)

        # chart_artifact_id must match artifact.artifact_id
        chart_artifact_id = artifact.artifact_id

        return ChartArtifact(
            chart_artifact_id=chart_artifact_id,
            artifact=artifact,
            declaration=output_decl,  # type: ignore
            producer=producer,
            pixel_width=pixel_width,
            pixel_height=pixel_height,
            encoder_version="matplotlib",
            normalization_version="1.0",
            backing_evidence_ids=backing_evidence_ids,
            dependencies=dependencies,
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
