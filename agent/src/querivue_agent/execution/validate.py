"""Artifact validation gates for sandbox execution environment."""

from __future__ import annotations

import hashlib
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal
from uuid import UUID, uuid4

from querivue_agent.contracts.artifacts import ArtifactRef, Sha256
from querivue_agent.runtime.sandbox import (
    EnvironmentManifest,
    ResourceLimits,
    ResourceAdmissionController,
    ArtifactValidator,
    ArtifactValidationResult,
)


@dataclass(frozen=True)
class GateResult:
    """Result of a validator gate check."""
    gate_id: UUID
    gate_name: str
    passed: bool
    details: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


@dataclass(frozen=True)
class EnvironmentAdmissionResult:
    """Result of environment admission checks."""
    admitted: bool
    manifest: EnvironmentManifest | None = None
    gate_results: list[GateResult] = ()
    resource_admission: Any = None


class EnvironmentAdmissionGate:
    """Validates environment for execution."""

    def __init__(self) -> None:
        self._supported_duckdb_versions = {"1.0.0", "1.1.0"}
        self._supported_arrow_versions = {"16.0.0", "17.0.0"}
        self._supported_python_versions = {"3.12", "3.13"}
        self._supported_os = {"linux/x86_64"}

    def check_manifest(self, manifest: EnvironmentManifest) -> list[GateResult]:
        """Check environment manifest compatibility."""
        results = []

        # Check DuckDB version
        duckdb_ok = manifest.duckdb_version in self._supported_duckdb_versions
        results.append(GateResult(
            gate_id=uuid4(),
            gate_name="duckdb_version",
            passed=duckdb_ok,
            details={"expected": list(self._supported_duckdb_versions), "actual": manifest.duckdb_version},
            error=None if duckdb_ok else f"Unsupported DuckDB version: {manifest.duckdb_version}",
        ))

        # Check Arrow version
        arrow_ok = manifest.arrow_version in self._supported_arrow_versions
        results.append(GateResult(
            gate_id=uuid4(),
            gate_name="arrow_version",
            passed=arrow_ok,
            details={"expected": list(self._supported_arrow_versions), "actual": manifest.arrow_version},
            error=None if arrow_ok else f"Unsupported Arrow version: {manifest.arrow_version}",
        ))

        # Check Python version
        python_ok = manifest.python_version in self._supported_python_versions
        results.append(GateResult(
            gate_id=uuid4(),
            gate_name="python_version",
            passed=python_ok,
            details={"expected": list(self._supported_python_versions), "actual": manifest.python_version},
            error=None if python_ok else f"Unsupported Python version: {manifest.python_version}",
        ))

        # Check OS/architecture
        os_ok = manifest.os_kernel_arch in self._supported_os
        results.append(GateResult(
            gate_id=uuid4(),
            gate_name="os_architecture",
            passed=os_ok,
            details={"expected": list(self._supported_os), "actual": manifest.os_kernel_arch},
            error=None if os_ok else f"Unsupported OS/arch: {manifest.os_kernel_arch}",
        ))

        # Check observed controls
        required_controls = [
            "read_only_inputs",
            "network_blocked",
            "process_tree_termination",
            "cgroup_v2",
            "bubblewrap",
        ]
        missing_controls = [
            c for c in required_controls
            if not manifest.observed_controls.get(c, False)
        ]
        controls_ok = len(missing_controls) == 0
        results.append(GateResult(
            gate_id=uuid4(),
            gate_name="execution_controls",
            passed=controls_ok,
            details={"required": required_controls, "missing": missing_controls, "observed": manifest.observed_controls},
            error=None if controls_ok else f"Missing required controls: {missing_controls}",
        ))

        return results

    def admit_environment(self, manifest: EnvironmentManifest) -> EnvironmentAdmissionResult:
        """Run full environment admission checks."""
        gate_results = self.check_manifest(manifest)
        all_passed = all(g.passed for g in gate_results)

        return EnvironmentAdmissionResult(
            admitted=all_passed,
            manifest=manifest if all_passed else None,
            gate_results=gate_results,
        )


class ExecutionValidatorGate:
    """Validates execution preconditions and postconditions."""

    def __init__(self, resource_limits: ResourceLimits) -> None:
        self._limits = resource_limits
        self._admission_controller = ResourceAdmissionController(resource_limits)

    def validate_pre_execution(
        self,
        session_id: UUID,
        run_id: UUID,
        action_type: Literal["sql", "python", "ingestion"],
        estimated_resources: dict[str, float] | None = None,
    ) -> list[GateResult]:
        """Validate preconditions before execution."""
        results = []

        # Resource admission check
        admission = self._admission_controller.check_admission(session_id, run_id, estimated_resources)
        results.append(GateResult(
            gate_id=uuid4(),
            gate_name="resource_admission",
            passed=admission.admitted,
            details=admission.resources,
            error=admission.reason,
        ))

        # Action-specific limits
        if action_type == "sql":
            results.append(GateResult(
                gate_id=uuid4(),
                gate_name="sql_execution_limits",
                passed=True,
                details={
                    "timeout_seconds": self._limits.sql_timeout_seconds,
                    "memory_gib": self._limits.duckdb_memory_gib,
                },
            ))
        elif action_type == "python":
            results.append(GateResult(
                gate_id=uuid4(),
                gate_name="python_execution_limits",
                passed=True,
                details={
                    "timeout_seconds": self._limits.python_timeout_seconds,
                    "memory_gib": self._limits.action_ram_gib,
                },
            ))

        return results

    def validate_post_execution(
        self,
        action_type: Literal["sql", "python"],
        artifacts: list[Path],
        expected_outputs: list[dict[str, Any]] | None = None,
    ) -> list[GateResult]:
        """Validate postconditions after execution."""
        results = []

        # Check artifact count
        if len(artifacts) > self._limits.max_output_files:
            results.append(GateResult(
                gate_id=uuid4(),
                gate_name="artifact_count_limit",
                passed=False,
                details={"max_files": self._limits.max_output_files, "actual": len(artifacts)},
                error=f"Too many output files: {len(artifacts)} > {self._limits.max_output_files}",
            ))
        else:
            results.append(GateResult(
                gate_id=uuid4(),
                gate_name="artifact_count_limit",
                passed=True,
                details={"max_files": self._limits.max_output_files, "actual": len(artifacts)},
            ))

        # Check total output size
        total_size = sum(a.stat().st_size for a in artifacts if a.exists())
        max_output = int(self._limits.output_mib * 1024 * 1024)
        if total_size > max_output:
            results.append(GateResult(
                gate_id=uuid4(),
                gate_name="total_output_size",
                passed=False,
                details={"max_bytes": max_output, "actual_bytes": total_size},
                error=f"Total output size exceeds limit: {total_size} > {max_output}",
            ))
        else:
            results.append(GateResult(
                gate_id=uuid4(),
                gate_name="total_output_size",
                passed=True,
                details={"max_bytes": max_output, "actual_bytes": total_size},
            ))

        return results


class ArtifactValidationGate:
    """Validates artifacts through quarantine."""

    def __init__(self, quarantine_dir: Path) -> None:
        self._validator = ArtifactValidator(quarantine_dir)

    async def validate_and_promote(
        self,
        artifact_path: Path,
        destination: Path,
        expected_sha256: str | None = None,
    ) -> ArtifactValidationResult:
        """Validate artifact and promote from quarantine."""
        return await self._validator.promote_from_quarantine(artifact_path, destination)


class GateOrchestrator:
    """Orchestrates all validator gates."""

    def __init__(self, resource_limits: ResourceLimits, quarantine_dir: Path) -> None:
        self._env_gate = EnvironmentAdmissionGate()
        self._exec_gate = ExecutionValidatorGate(resource_limits)
        self._artifact_gate = ArtifactValidationGate(quarantine_dir)

    def admit_environment(self, manifest: EnvironmentManifest) -> EnvironmentAdmissionResult:
        """Run environment admission gates."""
        return self._env_gate.admit_environment(manifest)

    def validate_pre_execution(
        self,
        session_id: UUID,
        run_id: UUID,
        action_type: Literal["sql", "python", "ingestion"],
        estimated_resources: dict[str, float] | None = None,
    ) -> list[GateResult]:
        """Run pre-execution gates."""
        return self._exec_gate.validate_pre_execution(session_id, run_id, action_type, estimated_resources)

    def validate_post_execution(
        self,
        action_type: Literal["sql", "python"],
        artifacts: list[Path],
        expected_outputs: list[dict[str, Any]] | None = None,
    ) -> list[GateResult]:
        """Run post-execution gates."""
        return self._exec_gate.validate_post_execution(action_type, artifacts, expected_outputs)

    async def validate_artifact(
        self,
        artifact_path: Path,
        destination: Path,
        expected_sha256: str | None = None,
    ) -> ArtifactValidationResult:
        """Validate and promote artifact."""
        return await self._artifact_gate.validate_and_promote(artifact_path, destination, expected_sha256)

    def all_passed(self, results: list[GateResult]) -> bool:
        """Check if all gate results passed."""
        return all(r.passed for r in results)


def compute_file_hash(path: Path) -> str:
    """Compute SHA-256 hash of a file."""
    sha256 = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def validate_png_file(path: Path) -> bool:
    """Validate that a file is a valid PNG using the `file` command."""
    try:
        result = subprocess.run(
            ["file", "--mime-type", "-b", str(path)],
            capture_output=True, text=True, timeout=5
        )
        return "image/png" in result.stdout
    except Exception:
        return False


def validate_parquet_file(path: Path) -> bool:
    """Validate that a file is a valid Parquet file."""
    try:
        import pyarrow.parquet as pq
        pq.read_table(path)
        return True
    except Exception:
        return False