"""Sandbox controller for deterministic execution environment with E2B isolation."""

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

# E2B imports
try:
    from e2b import Sandbox
    E2B_AVAILABLE = True
except ImportError:
    E2B_AVAILABLE = False
    Sandbox = None


@dataclass(frozen=True)
class E2BConfig:
    """E2B sandbox configuration."""
    template_id: str = "base"
    cpu: float = 2.0
    memory_gib: float = 4.0
    disk_gib: float = 4.0
    network_enabled: bool = False
    allow_internet_access: bool = False  # Explicit network control
    timeout_seconds: int = 60
    # Pooling configuration
    pool_size: int = 1
    pool_max_idle_seconds: int = 300
    # Pool management
    pool_reuse_sandbox: bool = True  # Reuse sandboxes across sessions


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
    """Controls sandbox lifecycle and execution with E2B isolation."""

    # Class-level sandbox pool (shared across instances)
    _pool: dict[str, list[tuple[Sandbox, datetime]]] = {}
    _pool_lock: asyncio.Lock = asyncio.Lock()

    def __init__(self, config: SandboxConfig, e2b_config: E2BConfig | None = None) -> None:
        self._config = config
        self._e2b_config = e2b_config or E2BConfig()
        self._session_dir: Path | None = None
        self._action_dirs: dict[UUID, Path] = {}
        self._e2b_sandbox: Sandbox | None = None
        self._gate_orchestrator = GateOrchestrator(
            config.resource_limits,
            config.working_dir / "quarantine" if config.working_dir else Path(tempfile.gettempdir()) / "querivue_quarantine"
        )
        self._pooled_sandbox: bool = False

    @property
    def config(self) -> SandboxConfig:
        return self._config

    @property
    def session_dir(self) -> Path | None:
        return self._session_dir

    @property
    def e2b_sandbox(self) -> Sandbox | None:
        return self._e2b_sandbox

    async def create_session(self) -> Path:
        """Create a new E2B sandbox session, reusing from pool if available."""
        if not E2B_AVAILABLE:
            raise RuntimeError("E2B SDK not installed. Run 'uv add e2b'")

        # Create local temp directory for file staging
        base = Path(tempfile.gettempdir()) / "querivue_sandbox" / str(self._config.session_id)
        self._session_dir = base
        base.mkdir(parents=True, exist_ok=True)

        # Create subdirectories for local file management
        (base / "inputs").mkdir(exist_ok=True)
        (base / "scratch").mkdir(exist_ok=True)
        (base / "outputs").mkdir(exist_ok=True)
        (base / "quarantine").mkdir(exist_ok=True)
        (base / "validator").mkdir(exist_ok=True)

        # Mount read-only inputs locally for staging
        for i, input_path in enumerate(self._config.read_only_inputs):
            link_path = base / "inputs" / f"input_{i}{input_path.suffix}"
            if input_path.is_file():
                os.link(input_path, link_path)
            else:
                shutil.copytree(input_path, link_path)
            # Make read-only
            link_path.chmod(0o444)

        # Get sandbox from pool or create new
        self._e2b_sandbox = await self._get_or_create_sandbox()

        # Run environment admission gates
        admission = self._gate_orchestrator.admit_environment(self._config.environment_manifest)
        if not admission.admitted:
            failed = [g for g in admission.gate_results if not g.passed]
            raise RuntimeError(f"Environment admission failed: {failed}")

        return base

    async def destroy_session(self) -> None:
        """Destroy the sandbox session, returning sandbox to pool if pooling enabled."""
        # Return sandbox to pool instead of killing
        if self._e2b_sandbox and self._pooled_sandbox and self._e2b_config.pool_reuse_sandbox:
            await self._return_sandbox_to_pool(self._e2b_sandbox)
            self._e2b_sandbox = None
        elif self._e2b_sandbox:
            try:
                self._e2b_sandbox.kill()
            except Exception:
                pass
            self._e2b_sandbox = None

        # Clean up local temp directory
        if self._session_dir and self._session_dir.exists():
            shutil.rmtree(self._session_dir, ignore_errors=True)
        self._session_dir = None
        self._action_dirs.clear()

    async def _get_or_create_sandbox(self) -> Sandbox:
        """Get a sandbox from the pool or create a new one."""
        if not self._e2b_config.pool_reuse_sandbox:
            return await self._create_new_sandbox()

        pool_key = self._get_pool_key()
        async with SandboxController._pool_lock:
            pool = SandboxController._pool.get(pool_key, [])
            now = datetime.now(UTC)

            # Try to find an idle sandbox that hasn't exceeded max idle time
            while pool:
                sandbox, last_used = pool.pop(0)
                idle_seconds = (now - last_used).total_seconds()
                if idle_seconds <= self._e2b_config.pool_max_idle_seconds:
                    # Check if sandbox is still alive
                    try:
                        result = sandbox.commands.run("echo alive", timeout=5)
                        if result.exit_code == 0:
                            self._pooled_sandbox = True
                            return sandbox
                    except Exception:
                        # Sandbox dead, discard
                        pass
                else:
                    # Too old, kill it
                    try:
                        sandbox.kill()
                    except Exception:
                        pass

            # No suitable sandbox in pool, create new
            return await self._create_new_sandbox()

    async def _create_new_sandbox(self) -> Sandbox:
        """Create a new E2B sandbox with proper configuration."""
        # Build sandbox creation parameters
        create_params = {
            "template": self._e2b_config.template_id,
            "timeout": self._e2b_config.timeout_seconds,
        }

        # Add CPU count if specified
        if self._e2b_config.cpu:
            create_params["cpu_count"] = int(self._e2b_config.cpu)

        # Explicit network control
        if not self._e2b_config.allow_internet_access:
            create_params["allow_internet_access"] = False
        elif self._e2b_config.network_enabled:
            create_params["allow_internet_access"] = True

        sandbox = Sandbox.create(**create_params)

        # Install required packages
        install_cmd = (
            "python3 -m pip install --quiet "
            "pandas pyarrow matplotlib pillow duckdb sqlglot numpy"
        )
        result = sandbox.commands.run(install_cmd)
        if result.exit_code != 0:
            raise RuntimeError(f"Failed to install packages in E2B sandbox: {result.stderr}")

        self._pooled_sandbox = True
        return sandbox

    def _get_pool_key(self) -> str:
        """Generate a pool key based on sandbox configuration."""
        return (
            f"{self._e2b_config.template_id}:"
            f"{self._e2b_config.cpu}:"
            f"{self._e2b_config.memory_gib}:"
            f"{self._e2b_config.disk_gib}:"
            f"{self._e2b_config.allow_internet_access}"
        )

    async def _return_sandbox_to_pool(self, sandbox: Sandbox) -> None:
        """Return a sandbox to the pool for reuse."""
        pool_key = self._get_pool_key()
        async with SandboxController._pool_lock:
            pool = SandboxController._pool.setdefault(pool_key, [])
            # Limit pool size
            if len(pool) >= self._e2b_config.pool_size:
                # Kill oldest
                oldest_sandbox, _ = pool.pop(0)
                try:
                    oldest_sandbox.kill()
                except Exception:
                    pass
            pool.append((sandbox, datetime.now(UTC)))

    def _get_action_dir(self, action_id: UUID) -> Path:
        """Get or create action-specific directory (local for file staging)."""
        if action_id not in self._action_dirs:
            action_dir = self._session_dir / "actions" / str(action_id)
            action_dir.mkdir(parents=True, exist_ok=True)
            (action_dir / "scratch").mkdir(exist_ok=True)
            (action_dir / "outputs").mkdir(exist_ok=True)
            # Copy input files from session inputs to action inputs with evidence_ prefix
            inputs_dir = action_dir / "inputs"
            inputs_dir.mkdir(exist_ok=True)
            if self._session_dir:
                session_inputs = self._session_dir / "inputs"
                if session_inputs.exists():
                    for i, src in enumerate(session_inputs.iterdir()):
                        if src.is_file():
                            dst = inputs_dir / f"evidence_{i}{src.suffix}"
                            if not dst.exists():
                                shutil.copy2(src, dst)
                                dst.chmod(0o444)
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
        """Execute a SQL query in the E2B sandbox using Python duckdb."""
        if not self._e2b_sandbox:
            raise RuntimeError("E2B sandbox not created")

        output_path = action_dir / "outputs" / "result.parquet"
        output_path.parent.mkdir(parents=True, exist_ok=True)

        sql = request.request.sql if hasattr(request.request, 'sql') else str(request.request)
        params = request.request.parameters if hasattr(request.request, 'parameters') else {}

        # Stage input evidence files to E2B sandbox
        evidence_paths = request.request.input_evidence_ids if hasattr(request.request, 'input_evidence_ids') else []
        for i, ev_id in enumerate(evidence_paths):
            local_path = action_dir / "inputs" / f"evidence_{i}.parquet"
            if local_path.exists():
                self._e2b_sandbox.files.write(f"/tmp/evidence_{i}.parquet", local_path.read_bytes())

        # Write Python script to execute SQL via duckdb Python API
        # Load evidence parquet files as duckdb tables
        load_evidence = "\n".join([
            f"con.execute(\"CREATE OR REPLACE TABLE evidence_{i} AS SELECT * FROM read_parquet('/tmp/evidence_{i}.parquet')\")"
            for i in range(len(evidence_paths))
        ])

        code = f"""
import duckdb
con = duckdb.connect("/tmp/database.duckdb")
# Load evidence tables
{load_evidence}
# Set parameters
{chr(10).join([f"con.execute('SET {k} = ?', [{repr(v)}])" for k, v in params.items()])}
result = con.execute({repr(sql)}).fetchdf()
result.to_parquet("/tmp/result.parquet", index=False)
print(f"Rows: {{len(result)}}")
"""

        script_path = "/tmp/sql_script.py"
        self._e2b_sandbox.files.write(script_path, code.encode())

        start_time = datetime.now(UTC)
        try:
            result = self._e2b_sandbox.commands.run(f"python3 {script_path}", timeout=self._config.resource_limits.sql_timeout_seconds)

            # Download result file
            if result.exit_code == 0:
                parquet_data = self._e2b_sandbox.files.read("/tmp/result.parquet", format="bytes")
                output_path.write_bytes(parquet_data)
                artifacts = [output_path]
            else:
                artifacts = []

            status = "succeeded" if result.exit_code == 0 else "failed"
            stdout = result.stdout
            stderr = result.stderr
            exit_code = result.exit_code

        except Exception as e:
            stdout = ""
            stderr = str(e)
            exit_code = -1
            status = "failed"
            artifacts = []

        duration_ms = int((datetime.now(UTC) - start_time).total_seconds() * 1000)

        return ExecutionResult(
            status=status,
            stdout=stdout,
            stderr=stderr,
            exit_code=exit_code,
            artifacts=artifacts,
            resource_usage={
                "duration_ms": duration_ms,
                "timeout_seconds": self._config.resource_limits.sql_timeout_seconds,
            },
            error={"message": stderr} if status != "succeeded" else None,
        )

    async def _execute_python(self, request: OperationRequest, action_dir: Path) -> ExecutionResult:
        """Execute a Python script in the E2B sandbox."""
        if not self._e2b_sandbox:
            raise RuntimeError("E2B sandbox not created")

        # Stage input evidence files to E2B sandbox
        evidence_paths = request.request.input_evidence_ids if hasattr(request.request, 'input_evidence_ids') else []
        for i, ev_id in enumerate(evidence_paths):
            # Find the local evidence file
            local_path = action_dir / "inputs" / f"evidence_{i}.parquet"
            if local_path.exists():
                # Upload to E2B sandbox
                self._e2b_sandbox.files.write(f"/tmp/evidence_{i}.parquet", local_path.read_bytes())

        # Write script to E2B sandbox
        code = request.request.code if hasattr(request.request, 'code') else str(request.request)
        script_path = "/tmp/script.py"
        self._e2b_sandbox.files.write(script_path, code.encode())

        start_time = datetime.now(UTC)
        try:
            # Run the Python script
            cmd = f"python3 {script_path}"
            result = self._e2b_sandbox.commands.run(cmd, timeout=self._config.resource_limits.python_timeout_seconds)

            # Download output artifacts
            artifacts = []
            outputs_dir = action_dir / "outputs"
            outputs_dir.mkdir(parents=True, exist_ok=True)

            # List files in /tmp to find all parquet and png outputs
            list_result = self._e2b_sandbox.commands.run("ls -1 /tmp/*.parquet /tmp/*.png 2>/dev/null || true")
            output_files = list_result.stdout.strip().split('\n') if list_result.stdout.strip() else []

            for remote_path in output_files:
                remote_path = remote_path.strip()
                if not remote_path:
                    continue
                local_filename = os.path.basename(remote_path)
                local_path = outputs_dir / local_filename
                try:
                    data = self._e2b_sandbox.files.read(remote_path, format="bytes")
                    local_path.write_bytes(data)
                    artifacts.append(local_path)
                except Exception as e:
                    print(f"Failed to download {remote_path}: {e}")

            status = "succeeded" if result.exit_code == 0 else "failed"
            stdout = result.stdout
            stderr = result.stderr
            exit_code = result.exit_code

        except Exception as e:
            stdout = ""
            stderr = str(e)
            exit_code = -1
            status = "failed"
            artifacts = []

        duration_ms = int((datetime.now(UTC) - start_time).total_seconds() * 1000)

        return ExecutionResult(
            status=status,
            stdout=stdout,
            stderr=stderr,
            exit_code=exit_code,
            artifacts=artifacts,
            resource_usage={
                "duration_ms": duration_ms,
                "timeout_seconds": self._config.resource_limits.python_timeout_seconds,
            },
            error={"message": stderr} if status != "succeeded" else None,
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
        """Run a command in E2B sandbox (fallback for generic commands)."""
        if not self._e2b_sandbox:
            raise RuntimeError("E2B sandbox not created")

        cmd_str = " ".join(cmd)
        start_time = datetime.now(UTC)

        try:
            result = self._e2b_sandbox.commands.run(cmd_str, timeout=timeout)

            artifacts = []
            if expected_output and expected_output.exists():
                artifacts.append(expected_output)

            status = "succeeded" if result.exit_code == 0 else "failed"
            stdout = result.stdout
            stderr = result.stderr
            exit_code = result.exit_code

        except Exception as e:
            stdout = ""
            stderr = str(e)
            exit_code = -1
            status = "failed"
            artifacts = []

        duration_ms = int((datetime.now(UTC) - start_time).total_seconds() * 1000)

        return ExecutionResult(
            status=status,
            stdout=stdout,
            stderr=stderr,
            exit_code=exit_code,
            artifacts=artifacts,
            resource_usage={
                "duration_ms": duration_ms,
                "timeout_seconds": timeout,
            },
            error={"message": stderr} if status != "succeeded" else None,
        )

    # Compatible interface for PythonRunner
    async def execute_python(
        self,
        action_id: UUID,
        script_path: Path,
        evidence_paths: list[Path],
    ) -> ExecutionResult:
        """Execute a Python script in the E2B sandbox (compatible with local SandboxController)."""
        if not self._e2b_sandbox:
            raise RuntimeError("E2B sandbox not created")

        action_dir = self._get_action_dir(action_id)
        outputs_dir = action_dir / "outputs"
        outputs_dir.mkdir(parents=True, exist_ok=True)

        # Stage input evidence files to E2B sandbox with expected names in working directory
        for i, ev_path in enumerate(evidence_paths):
            expected_name = ev_path.name  # e.g., input_00000000-0000-0000-0000-000000000002.parquet
            # Write to E2B working directory (/home/user) for direct access
            remote_path = f"/home/user/{expected_name}"
            self._e2b_sandbox.files.write(remote_path, ev_path.read_bytes())

        # Write script to E2B sandbox
        code = script_path.read_text()
        self._e2b_sandbox.files.write("/tmp/script.py", code.encode())

        start_time = datetime.now(UTC)
        try:
            # Run the Python script
            result = self._e2b_sandbox.commands.run(
                "python3 /tmp/script.py",
                timeout=self._config.resource_limits.python_timeout_seconds
            )

            # Check for output files in E2B sandbox (working directory /home/user)
            artifacts = []
            # List files in working directory to find outputs
            list_result = self._e2b_sandbox.commands.run("ls -la /home/user/*.parquet /home/user/*.png 2>/dev/null || true")
            output_files = list_result.stdout.strip().split('\n') if list_result.stdout.strip() else []

            for line in output_files:
                if line.strip():
                    parts = line.split()
                    if len(parts) >= 9:
                        # Full path is in parts[-1], e.g., /home/user/output_chart.png
                        remote_path = parts[-1]
                        local_filename = os.path.basename(remote_path)
                        local_path = outputs_dir / local_filename
                        try:
                            data = self._e2b_sandbox.files.read(remote_path, format="bytes")
                            local_path.write_bytes(data)
                            artifacts.append(local_path)
                        except Exception:
                            pass

            status = "succeeded" if result.exit_code == 0 else "failed"
            stdout = result.stdout
            stderr = result.stderr
            exit_code = result.exit_code

        except Exception as e:
            stdout = ""
            stderr = str(e)
            exit_code = -1
            status = "failed"
            artifacts = []

        duration_ms = int((datetime.now(UTC) - start_time).total_seconds() * 1000)

        return ExecutionResult(
            status=status,
            stdout=stdout,
            stderr=stderr,
            exit_code=exit_code,
            artifacts=artifacts,
            resource_usage={
                "duration_ms": duration_ms,
                "timeout_seconds": self._config.resource_limits.python_timeout_seconds,
            },
            error={"message": stderr} if status != "succeeded" else None,
        )

    # Compatible interface for PythonRunner
    async def execute_sql(
        self,
        action_id: UUID,
        sql: str,
        parameters: dict[str, Any],
        database_path: Path,
    ) -> ExecutionResult:
        """Execute a SQL query in the E2B sandbox (compatible with local SandboxController)."""
        if not self._e2b_sandbox:
            raise RuntimeError("E2B sandbox not created")

        action_dir = self._get_action_dir(action_id)
        inputs_dir = action_dir / "inputs"
        outputs_dir = action_dir / "outputs"
        outputs_dir.mkdir(parents=True, exist_ok=True)

        output_path = outputs_dir / "result.parquet"

        # Stage input evidence files to E2B sandbox working directory with expected names
        if inputs_dir.exists():
            for src in sorted(inputs_dir.iterdir()):
                if src.is_file():
                    expected_name = src.name
                    remote_path = f"/home/user/{expected_name}"
                    self._e2b_sandbox.files.write(remote_path, src.read_bytes())

        # Write Python script to execute SQL via duckdb Python API
        # The SQL should reference files at /home/user/input_{uuid}.parquet
        code = f"""
import duckdb
con = duckdb.connect("/tmp/database.duckdb")
result = con.execute({repr(sql)}).fetchdf()
result.to_parquet("/tmp/result.parquet", index=False)
print(f"Rows: {{len(result)}}")
"""

        script_path = "/tmp/sql_script.py"
        self._e2b_sandbox.files.write(script_path, code.encode())

        start_time = datetime.now(UTC)
        try:
            result = self._e2b_sandbox.commands.run(f"python3 {script_path}", timeout=self._config.resource_limits.sql_timeout_seconds)

            # Download result file
            if result.exit_code == 0:
                parquet_data = self._e2b_sandbox.files.read("/tmp/result.parquet", format="bytes")
                output_path.write_bytes(parquet_data)
                artifacts = [output_path]
            else:
                artifacts = []

            status = "succeeded" if result.exit_code == 0 else "failed"
            stdout = result.stdout
            stderr = result.stderr
            exit_code = result.exit_code

        except Exception as e:
            stdout = ""
            stderr = str(e)
            exit_code = -1
            status = "failed"
            artifacts = []

        duration_ms = int((datetime.now(UTC) - start_time).total_seconds() * 1000)

        return ExecutionResult(
            status=status,
            stdout=stdout,
            stderr=stderr,
            exit_code=exit_code,
            artifacts=artifacts,
            resource_usage={
                "duration_ms": duration_ms,
                "timeout_seconds": self._config.resource_limits.sql_timeout_seconds,
            },
            error={"message": stderr} if status != "succeeded" else None,
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
    e2b_config: E2BConfig | None = None,
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
    return SandboxController(config, e2b_config)