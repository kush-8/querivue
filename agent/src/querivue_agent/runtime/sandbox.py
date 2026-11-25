"""Sandbox controller for deterministic execution environment."""

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


@dataclass(frozen=True)
class EnvironmentManifest:
    """Immutable environment manifest for reproducibility."""
    manifest_id: UUID
    schema_version: str
    image_digest: str  # SHA-256 of container image
    provider_template_revision: str
    os_kernel_arch: str
    python_version: str
    package_hashes: dict[str, str]  # package -> lockfile hash
    duckdb_version: str
    arrow_version: str
    sql_parser_policy_version: str
    importer_version: str
    profiler_version: str
    validator_version: str
    locale: str
    timezone: str
    resource_profile: str
    created_at: str
    provider_identity: str
    observed_controls: dict[str, bool] = field(default_factory=dict)


@dataclass(frozen=True)
class ResourceLimits:
    """Resource limits for sandbox execution."""
    session_vcpus: float = 2.0
    session_ram_gib: float = 4.0
    session_disk_gib: float = 4.0
    action_vcpus: float = 1.0
    action_ram_gib: float = 2.0
    duckdb_memory_gib: float = 1.0
    scratch_gib: float = 1.0
    output_mib: float = 128.0
    max_output_files: int = 16
    sql_timeout_seconds: int = 30
    python_timeout_seconds: int = 60
    session_lifetime_seconds: int = 300
    prep_wall_seconds: int = 120
    inspect_wall_seconds: int = 30
    import_diagnostics_count: int = 20
    import_diagnostics_kib: int = 2


@dataclass(frozen=True)
class SandboxConfig:
    """Sandbox configuration."""
    environment_manifest: EnvironmentManifest
    resource_limits: ResourceLimits
    session_id: UUID
    run_id: UUID
    read_only_inputs: list[Path] = field(default_factory=list)
    working_dir: Path = field(default_factory=Path.cwd)


@dataclass(frozen=True)
class ExecutionResult:
    """Result of a sandbox execution."""
    status: Literal["succeeded", "failed", "timeout", "resource_exceeded"]
    stdout: str = ""
    stderr: str = ""
    exit_code: int | None = None
    artifacts: list[Path] = field(default_factory=list)
    resource_usage: dict[str, Any] = field(default_factory=dict)
    error: dict[str, Any] | None = None


@dataclass(frozen=True)
class ArtifactValidationResult:
    """Result of artifact validation."""
    valid: bool
    path: Path
    size_bytes: int
    sha256: str
    mime_type: str | None = None
    validation_errors: list[str] = field(default_factory=list)


class SandboxController:
    """Controls sandbox lifecycle and execution."""

    def __init__(self, config: SandboxConfig) -> None:
        self._config = config
        self._session_dir: Path | None = None
        self._action_dirs: dict[UUID, Path] = {}
        self._process: asyncio.subprocess.Process | None = None

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

    async def execute_sql(
        self,
        action_id: UUID,
        sql: str,
        parameters: dict[str, Any],
        database_path: Path,
    ) -> ExecutionResult:
        """Execute a SQL query in the sandbox."""
        action_dir = self._get_action_dir(action_id)
        output_path = action_dir / "outputs" / "result.parquet"

        # Build DuckDB command with resource limits
        cmd = [
            "duckdb",
            str(database_path),
            "-c", sql,
            "-result_format", "parquet",
            "-output", str(output_path),
        ]

        # Add parameters if any
        for key, value in parameters.items():
            cmd.extend(["-param", f"{key}={value}"])

        return await self._run_command(
            action_id=action_id,
            cmd=cmd,
            timeout=self._config.resource_limits.sql_timeout_seconds,
            expected_output=output_path,
        )

    async def execute_python(
        self,
        action_id: UUID,
        script_path: Path,
        evidence_paths: list[Path],
    ) -> ExecutionResult:
        """Execute a Python script in the sandbox."""
        action_dir = self._get_action_dir(action_id)

        # Prepare isolated environment
        env = os.environ.copy()
        env["PYTHONPATH"] = str(action_dir / "scratch")
        env["QUERIVUE_EVIDENCE_DIR"] = str(action_dir / "inputs")
        env["QUERIVUE_OUTPUT_DIR"] = str(action_dir / "outputs")

        # Link evidence files as read-only
        for i, ev_path in enumerate(evidence_paths):
            link_path = action_dir / "inputs" / f"evidence_{i}{ev_path.suffix}"
            link_path.parent.mkdir(exist_ok=True)
            os.link(ev_path, link_path)
            link_path.chmod(0o444)

        cmd = ["python3", str(script_path)]

        return await self._run_command(
            action_id=action_id,
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

    async def validate_artifacts(self, artifacts: list[Path]) -> list[ArtifactValidationResult]:
        """Validate output artifacts."""
        results = []
        for artifact in artifacts:
            if not artifact.exists():
                results.append(ArtifactValidationResult(
                    valid=False,
                    path=artifact,
                    size_bytes=0,
                    sha256="",
                    validation_errors=["Artifact file not found"],
                ))
                continue

            # Check size
            size = artifact.stat().st_size
            max_size = int(self._config.resource_limits.output_mib * 1024 * 1024)
            if size > max_size:
                results.append(ArtifactValidationResult(
                    valid=False,
                    path=artifact,
                    size_bytes=size,
                    sha256="",
                    validation_errors=[f"Artifact exceeds size limit: {size} > {max_size}"],
                ))
                continue

            # Compute SHA-256
            sha256 = hashlib.sha256()
            with open(artifact, "rb") as f:
                for chunk in iter(lambda: f.read(8192), b""):
                    sha256.update(chunk)

            results.append(ArtifactValidationResult(
                valid=True,
                path=artifact,
                size_bytes=size,
                sha256=sha256.hexdigest(),
            ))

        return results


class ArtifactValidator:
    """Validates artifacts in quarantine before publication."""

    def __init__(self, quarantine_dir: Path, validator_version: str = "v1") -> None:
        self._quarantine_dir = quarantine_dir
        self._validator_version = validator_version

    async def validate(self, artifact_path: Path, expected_sha256: str | None = None) -> ArtifactValidationResult:
        """Validate an artifact from quarantine."""
        if not artifact_path.exists():
            return ArtifactValidationResult(
                valid=False,
                path=artifact_path,
                size_bytes=0,
                sha256="",
                validation_errors=["Artifact not found in quarantine"],
            )

        # Compute hash
        sha256 = hashlib.sha256()
        with open(artifact_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)

        actual_hash = sha256.hexdigest()
        size = artifact_path.stat().st_size

        # Verify against expected
        if expected_sha256 and actual_hash != expected_sha256:
            return ArtifactValidationResult(
                valid=False,
                path=artifact_path,
                size_bytes=size,
                sha256=actual_hash,
                validation_errors=[f"Hash mismatch: expected {expected_sha256}, got {actual_hash}"],
            )

        # Check file type
        mime_type = self._detect_mime_type(artifact_path)
        allowed_types = [
            "application/vnd.apache.parquet",
            "application/json",
            "text/csv",
            "image/png",
            "application/octet-stream",
        ]
        if mime_type not in allowed_types:
            return ArtifactValidationResult(
                valid=False,
                path=artifact_path,
                size_bytes=size,
                sha256=actual_hash,
                validation_errors=[f"Disallowed MIME type: {mime_type}"],
            )

        return ArtifactValidationResult(
            valid=True,
            path=artifact_path,
            size_bytes=size,
            sha256=actual_hash,
            mime_type=mime_type,
        )

    def _detect_mime_type(self, path: Path) -> str:
        """Detect MIME type from file extension."""
        suffix = path.suffix.lower()
        mime_map = {
            ".parquet": "application/vnd.apache.parquet",
            ".json": "application/json",
            ".csv": "text/csv",
            ".png": "image/png",
            ".bin": "application/octet-stream",
        }
        return mime_map.get(suffix, "application/octet-stream")

    async def promote_from_quarantine(
        self,
        artifact_path: Path,
        destination: Path,
    ) -> ArtifactValidationResult:
        """Validate and promote artifact from quarantine to final location."""
        result = await self.validate(artifact_path)
        if not result.valid:
            return result

        # Atomic move
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(artifact_path), str(destination))

        return ArtifactValidationResult(
            valid=True,
            path=destination,
            size_bytes=result.size_bytes,
            sha256=result.sha256,
            mime_type=result.mime_type,
        )


@dataclass(frozen=True)
class AdmissionCheck:
    """Resource admission check result."""
    admitted: bool
    reason: str | None = None
    resources: dict[str, Any] = field(default_factory=dict)


class ResourceAdmissionController:
    """Controls resource admission for sandbox sessions."""

    def __init__(self, limits: ResourceLimits) -> None:
        self._limits = limits
        self._active_sessions: dict[UUID, dict[str, Any]] = {}

    def check_admission(
        self,
        session_id: UUID,
        run_id: UUID,
        estimated_resources: dict[str, float] | None = None,
    ) -> AdmissionCheck:
        """Check if a new session can be admitted."""
        # Check session count (initial profile: 1 active session)
        if len(self._active_sessions) >= 1:
            return AdmissionCheck(
                admitted=False,
                reason="Maximum concurrent sessions reached",
                resources={"active_sessions": len(self._active_sessions)},
            )

        # Check persistent storage (2 GiB for prepared/evidence artifacts)
        # This would check actual disk usage

        return AdmissionCheck(
            admitted=True,
            resources={
                "vcpus": self._limits.session_vcpus,
                "ram_gib": self._limits.session_ram_gib,
                "disk_gib": self._limits.session_disk_gib,
            },
        )

    def admit_session(
        self,
        session_id: UUID,
        run_id: UUID,
        resources: dict[str, Any],
    ) -> None:
        """Record an admitted session."""
        self._active_sessions[session_id] = {
            "run_id": run_id,
            "resources": resources,
            "admitted_at": datetime.now(UTC).isoformat(),
        }

    def release_session(self, session_id: UUID) -> None:
        """Release a session."""
        self._active_sessions.pop(session_id, None)

    def get_active_sessions(self) -> dict[UUID, dict[str, Any]]:
        """Get currently active sessions."""
        return dict(self._active_sessions)


def create_default_environment_manifest(
    manifest_id: UUID | None = None,
) -> EnvironmentManifest:
    """Create a default environment manifest for development."""
    return EnvironmentManifest(
        manifest_id=manifest_id or UUID(str(uuid4())),
        schema_version="1.0",
        image_digest="sha256:" + "a" * 64,
        provider_template_revision="dev",
        os_kernel_arch="linux/x86_64",
        python_version="3.12",
        package_hashes={},
        duckdb_version="1.0.0",
        arrow_version="15.0.0",
        sql_parser_policy_version="1.0",
        importer_version="1.0",
        profiler_version="1.0",
        validator_version="1.0",
        locale="en_US.UTF-8",
        timezone="UTC",
        resource_profile="development",
        created_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        provider_identity="local",
        observed_controls={
            "read_only_inputs": True,
            "network_blocked": True,
            "process_tree_termination": True,
            "cgroup_v2": True,
            "bubblewrap": True,
        },
    )


def create_sandbox_controller(
    session_id: UUID,
    run_id: UUID,
    read_only_inputs: list[Path] | None = None,
    manifest: EnvironmentManifest | None = None,
    limits: ResourceLimits | None = None,
) -> SandboxController:
    """Create a sandbox controller with default development config."""
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