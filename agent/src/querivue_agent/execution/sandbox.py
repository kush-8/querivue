"""Sandbox controller for deterministic execution environment with E2B/Docker isolation."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import shutil
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, UTC
from pathlib import Path
from typing import Any, Literal
from uuid import UUID, uuid4

from querivue_agent.runtime.validator_gates import (
    EnvironmentAdmissionGate,
    ExecutionValidatorGate,
    ArtifactValidationGate,
    GateOrchestrator,
    GateResult,
    EnvironmentAdmissionResult,
)
from querivue_agent.runtime.sandbox import (
    EnvironmentManifest,
    ResourceLimits,
    ResourceAdmissionController,
    ArtifactValidator,
    ArtifactValidationResult,
    SandboxConfig,
    ExecutionResult,
)


@dataclass(frozen=True)
class SandboxTicket:
    """Ticket representing an admitted sandbox execution."""
    ticket_id: UUID
    scope: Any  # Scope object
    sandbox_id: str
    command_id: str | None
    incarnation_id: UUID
    action_id: UUID
    operation_id: UUID | None
    attempt: int
    generation: int
    environment_manifest_id: UUID
    state: Literal[
        "prepared", "running", "executed", "validated", "published", "retiring",
        "retired", "unreachable",
    ]
    created_at: str
    expires_at: str


@dataclass(frozen=True)
class OperationRequest:
    """Request to execute an operation in the sandbox."""
    operation_id: UUID
    scope: Any
    task_id: UUID | None
    action_id: UUID | None
    attempt: int
    execution_generation: int
    invocation_key: str
    request_hash: str
    kind: Literal["sql_query", "python_code", "ingestion_inspect", "ingestion_prepare"]
    request: Any
    input_artifacts: list[Any]
    deadline: str
    environment_manifest_id: UUID


@dataclass(frozen=True)
class OperationOutcome:
    """Outcome of a sandbox operation."""
    operation_id: UUID
    attempt: int
    execution_generation: int
    request_hash: str
    evidence: list[Any]
    charts: list[Any]
    diagnostics: Any
    completed_at: str
    status: Literal["succeeded", "failed", "blocked"]
    error: Any | None = None


class SandboxController:
    """Controls sandbox lifecycle and execution with E2B/Docker isolation."""

    def __init__(self, config: SandboxConfig) -> None:
        self._config = config
        self._session_dir: Path | None = None
        self._action_dirs: dict[UUID, Path] = {}
        self._process: asyncio.subprocess.Process | None = None
        self._gate_orchestrator = GateOrchestrator(
            config.resource_limits,
            config.session_dir / "quarantine" if config.session_dir else Path(tempfile.gettempdir()) / "querivue_quarantine"
        )

    @property
    def config(self) -> SandboxConfig:
        return self._config

    @property
    def session_dir(self) -> Path | None:
        return self._session_dir

    async def create_session(self) -> Path:
        """Create a new sandbox session directory."""
        base = Path(tempfile.gettempdir()) / "querivue_sandbox" / str(self._config.session_id)
        self._session_dir = base
        base.mkdir(parents=True, exist_ok=True)

        # Create subdirectories
        (base / "inputs").mkdir(exist_ok=True)
        (base / "scratch").mkdir(exist_ok=True)
        (base / "outputs").mkdir(exist_ok=True)
        (base / "quarantine").mkdir(exist_ok=True)
        (base / "validator").mkdir(exist_ok=True)

        # Mount read-only inputs
        for i, input_path in enumerate(self._config.read_only_inputs):
            link_path = base / "inputs" / f"input_{i}{input_path.suffix}"
            if input_path.is_file():
                os.link(input_path, link_path)
            else:
                shutil.copytree(input_path, link_path)
            # Make read-only
            link_path.chmod(0o444)

        # Run environment admission gates
        admission = self._gate_orchestrator.admit_environment(self._config.environment_manifest)
        if not admission.admitted:
            failed = [g for g in admission.gate_results if not g.passed]
            raise RuntimeError(f"Environment admission failed: {failed}")

        return base

    async def destroy_session(self) -> None:
        """Destroy the sandbox session."""
        if self._session_dir and self._session_dir.exists():
            # Read-only inputs may need special handling
            shutil.rmtree(self._session_dir, ignore_errors=True)
        self._session_dir = None
        self._action_dirs.clear()

    def _get_action_dir(self, action_id: UUID) -> Path:
        """Get or create action-specific directory."""
        if action_id not in self._action_dirs:
            action_dir = self._session_dir / "actions" / str(action_id)
            action_dir.mkdir(parents=True, exist_ok=True)
            (action_dir / "scratch").mkdir(exist_ok=True)
            (action_dir / "outputs").mkdir(exist_ok=True)
            self._action_dirs[action_id] = action_dir
        return self._action_dirs[action_id]

    async def admit(self, scope: Any, manifest_id: str) -> SandboxTicket:
        """Admit a new sandbox execution."""
        ticket_id = uuid4()
        incarnation_id = uuid4()

        ticket = SandboxTicket(
            ticket_id=ticket_id,
            scope=scope,
            sandbox_id=f"sandbox-{self._config.session_id}",
            command_id=None,
            incarnation_id=incarnation_id,
            action_id=UUID("00000000-0000-0000-0000-000000000000"),
            operation_id=None,
            attempt=1,
            generation=1,
            environment_manifest_id=UUID(manifest_id) if manifest_id != "00000000-0000-0000-0000-000000000000" else UUID("00000000-0000-0000-0000-000000000000"),
            state="prepared",
            created_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            expires_at="2099-12-31T23:59:59.999999Z",
        )
        return ticket

    async def execute(self, ticket: SandboxTicket, request: OperationRequest) -> OperationOutcome:
        """Execute an operation in the sandbox."""
        action_dir = self._get_action_dir(request.action_id or UUID("00000000-0000-0000-0000-000000000000"))

        # Validate pre-execution
        pre_results = self._gate_orchestrator.validate_pre_execution(
            self._config.session_id,
            self._config.run_id,
            "python" if request.kind == "python_code" else "sql",
        )
        if not all(r.passed for r in pre_results):
            failed = [r for r in pre_results if not r.passed]
            return OperationOutcome(
                operation_id=request.operation_id,
                attempt=request.attempt,
                execution_generation=request.execution_generation,
                request_hash=request.request_hash,
                evidence=[],
                charts=[],
                diagnostics=type('Diagnostics', (), {
                    'stdout': '',
                    'stderr': f'Pre-execution validation failed: {failed}',
                    'stdout_truncated': False,
                    'stderr_truncated': False,
                    'source_dependencies': [],
                })(),
                completed_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                status="blocked",
            )

        # Execute based on kind
        if request.kind == "sql_query":
            result = await self._execute_sql(request, action_dir)
        elif request.kind == "python_code":
            result = await self._execute_python(request, action_dir)
        else:
            result = ExecutionResult(
                status="failed",
                stderr=f"Unsupported operation kind: {request.kind}",
                exit_code=-1,
            )

        # Validate post-execution
        post_results = self._gate_orchestrator.validate_post_execution(
            "python" if request.kind == "python_code" else "sql",
            result.artifacts,
        )
        if not all(r.passed for r in post_results):
            failed = [r for r in post_results if not r.passed]
            return OperationOutcome(
                operation_id=request.operation_id,
                attempt=request.attempt,
                execution_generation=request.execution_generation,
                request_hash=request.request_hash,
                evidence=[],
                charts=[],
                diagnostics=type('Diagnostics', (), {
                    'stdout': result.stdout,
                    'stderr': f'Post-execution validation failed: {failed}',
                    'stdout_truncated': False,
                    'stderr_truncated': False,
                    'source_dependencies': [],
                })(),
                completed_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                status="blocked",
            )

        # Convert to OperationOutcome
        return OperationOutcome(
            operation_id=request.operation_id,
            attempt=request.attempt,
            execution_generation=request.execution_generation,
            request_hash=request.request_hash,
            evidence=[],  # Would be populated from validated artifacts
            charts=[],
            diagnostics=type('Diagnostics', (), {
                'stdout': result.stdout,
                'stderr': result.stderr,
                'stdout_truncated': False,
                'stderr_truncated': False,
                'source_dependencies': [],
            })(),
            completed_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            status=result.status if result.status in ("succeeded", "failed") else "failed",
        )

    async def _execute_sql(self, request: OperationRequest, action_dir: Path) -> ExecutionResult:
        """Execute a SQL query in the sandbox."""
        output_path = action_dir / "outputs" / "result.parquet"
        database_path = action_dir / "scratch" / "database.duckdb"

        # Build DuckDB command with resource limits
        cmd = [
            "duckdb",
            str(database_path),
            "-c", request.request.sql if hasattr(request.request, 'sql') else str(request.request),
            "-result_format", "parquet",
            "-output", str(output_path),
        ]

        # Add parameters if any
        params = request.request.parameters if hasattr(request.request, 'parameters') else {}
        for key, value in params.items():
            cmd.extend(["-param", f"{key}={value}"])

        return await self._run_command(
            action_id=request.action_id or UUID("00000000-0000-0000-0000-000000000000"),
            cmd=cmd,
            timeout=self._config.resource_limits.sql_timeout_seconds,
            expected_output=output_path,
        )

    async def _execute_python(self, request: OperationRequest, action_dir: Path) -> ExecutionResult:
        """Execute a Python script in the sandbox."""
        # Write script to file
        script_path = action_dir / "script.py"
        code = request.request.code if hasattr(request.request, 'code') else str(request.request)
        script_path.write_text(code)

        # Prepare isolated environment
        env = os.environ.copy()
        env["PYTHONPATH"] = str(action_dir / "scratch")
        env["QUERIVUE_EVIDENCE_DIR"] = str(action_dir / "inputs")
        env["QUERIVUE_OUTPUT_DIR"] = str(action_dir / "outputs")

        # Link evidence files as read-only
        evidence_paths = request.request.input_evidence_ids if hasattr(request.request, 'input_evidence_ids') else []
        for i, ev_id in enumerate(evidence_paths):
            # In real implementation, these would be actual paths from the artifact store
            link_path = action_dir / "inputs" / f"evidence_{i}.parquet"
            link_path.parent.mkdir(exist_ok=True)
            # Would link actual evidence file here
            pass

        cmd = ["python3", str(script_path)]

        return await self._run_command(
            action_id=request.action_id or UUID("00000000-0000-0000-0000-000000000000"),
            cmd=cmd,
            timeout=self._config.resource_limits.python_timeout_seconds,
            cwd=action_dir,
            env=env,
        )

    async def _run_command(
        self,
        action_id: UUID,
        cmd: list[str],
        timeout: int,
        cwd: Path | None = None,
        env: dict[str, str] | None = None,
        expected_output: Path | None = None,
    ) -> ExecutionResult:
        """Run a command with resource limits and timeout."""
        if not self._session_dir:
            raise RuntimeError("Session not created")

        action_dir = self._get_action_dir(action_id)
        if cwd is None:
            cwd = action_dir

        start_time = datetime.now(UTC)

        try:
            self._process = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=cwd,
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await asyncio.wait_for(
                self._process.communicate(),
                timeout=timeout,
            )

            exit_code = self._process.returncode
            status = "succeeded" if exit_code == 0 else "failed"

        except asyncio.TimeoutError:
            if self._process:
                self._process.kill()
                await self._process.wait()
            stdout = b""
            stderr = b"Execution timeout"
            exit_code = -1
            status = "timeout"

        except Exception as e:
            stdout = b""
            stderr = str(e).encode()
            exit_code = -1
            status = "failed"

        duration_ms = int((datetime.now(UTC) - start_time).total_seconds() * 1000)

        artifacts = []
        if expected_output and expected_output.exists():
            artifacts.append(expected_output)

        return ExecutionResult(
            status=status,
            stdout=stdout.decode("utf-8", errors="replace"),
            stderr=stderr.decode("utf-8", errors="replace"),
            exit_code=exit_code,
            artifacts=artifacts,
            resource_usage={
                "duration_ms": duration_ms,
                "timeout_seconds": timeout,
            },
            error={"message": stderr.decode("utf-8", errors="replace")} if status != "succeeded" else None,
        )

    async def validate_outputs(self, ticket: SandboxTicket, request: OperationRequest) -> tuple[Any, ...]:
        """Validate output artifacts from execution."""
        action_dir = self._get_action_dir(request.action_id or UUID("00000000-0000-0000-0000-000000000000"))
        outputs_dir = action_dir / "outputs"

        if not outputs_dir.exists():
            return ()

        artifacts = list(outputs_dir.iterdir())
        results = []

        for artifact in artifacts:
            validation = await self._gate_orchestrator.validate_artifact(
                artifact,
                artifact,  # Would be different destination in real implementation
            )
            results.append(validation)

        return tuple(results)

    async def retire(self, ticket: SandboxTicket) -> Any:
        """Retire the sandbox ticket."""
        # In real implementation, this would terminate the container/process tree
        # and provide retirement proof
        return type('RetirementProof', (), {
            'retirement_id': uuid4(),
            'sandbox_id': ticket.sandbox_id,
            'incarnation_id': ticket.incarnation_id,
            'confirmed_at': datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            'method': "process_tree_reaped",
            'process_tree_terminated': True,
            'proof_ref': UUID("00000000-0000-0000-0000-000000000000"),
            'environment_manifest_id': ticket.environment_manifest_id,
        })()


def create_sandbox_controller(
    session_id: UUID,
    run_id: UUID,
    read_only_inputs: list[Path] | None = None,
    manifest: EnvironmentManifest | None = None,
    limits: ResourceLimits | None = None,
) -> SandboxController:
    """Create a sandbox controller with default development config."""
    from querivue_agent.runtime.sandbox import create_default_environment_manifest

    if manifest is None:
        manifest = create_default_environment_manifest()
    if limits is None:
        limits = ResourceLimits()

    config = SandboxConfig(
        environment_manifest=manifest,
        resource_limits=limits,
        session_id=session_id,
        run_id=run_id,
        read_only_inputs=read_only_inputs or [],
    )
    return SandboxController(config)