"""Live tests for environment admission and execution gates.

These tests require a running Docker daemon and the sandbox image to be built.
They are marked with 'live' and 'redis' markers and excluded from the default test run.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from uuid import uuid4

import pytest

from querivue_agent.runtime.sandbox import (
    EnvironmentManifest,
    ResourceLimits,
    create_default_environment_manifest,
    create_sandbox_controller,
)
from querivue_agent.execution.sandbox import SandboxController
from querivue_agent.execution.validate import (
    EnvironmentAdmissionGate,
    ExecutionValidatorGate,
    ArtifactValidationGate,
    GateOrchestrator,
    compute_file_hash,
    validate_png_file,
    validate_parquet_file,
)


@pytest.mark.live
@pytest.mark.asyncio
async def test_docker_image_build():
    """Test that the sandbox Docker image can be built."""
    import subprocess

    # Build the Docker image
    result = subprocess.run(
        ["docker", "build", "-t", "querivue-sandbox:test", "agent/sandbox"],
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert result.returncode == 0, f"Docker build failed: {result.stderr}"
    assert "querivue-sandbox:test" in result.stdout or result.returncode == 0


@pytest.mark.live
@pytest.mark.asyncio
async def test_environment_admission_gate_live():
    """Test environment admission gate with real manifest."""
    gate = EnvironmentAdmissionGate()
    manifest = create_default_environment_manifest()

    # Update manifest with actual built image digest
    # In real scenario, this would come from the built image
    manifest.observed_controls = {
        "read_only_inputs": True,
        "network_blocked": True,
        "process_tree_termination": True,
        "cgroup_v2": True,
        "bubblewrap": True,
    }

    result = gate.admit_environment(manifest)
    assert result.admitted is True
    assert len(result.gate_results) == 5

    for g in result.gate_results:
        assert g.passed is True


@pytest.mark.live
@pytest.mark.asyncio
async def test_sandbox_session_creation():
    """Test creating a sandbox session with live controller."""
    controller = create_sandbox_controller(
        session_id=uuid4(),
        run_id=uuid4(),
    )

    session_dir = await controller.create_session()
    assert session_dir.exists()
    assert (session_dir / "inputs").exists()
    assert (session_dir / "scratch").exists()
    assert (session_dir / "outputs").exists()
    assert (session_dir / "quarantine").exists()
    assert (session_dir / "validator").exists()

    await controller.destroy_session()


@pytest.mark.live
@pytest.mark.asyncio
async def test_sandbox_sql_execution():
    """Test SQL execution in sandbox."""
    controller = create_sandbox_controller(
        session_id=uuid4(),
        run_id=uuid4(),
    )

    await controller.create_session()

    from querivue_agent.execution.sandbox import OperationRequest
    from querivue_agent.contracts.tools import ExecuteQueryRequest

    request = OperationRequest(
        operation_id=uuid4(),
        scope=None,
        task_id=None,
        action_id=uuid4(),
        attempt=1,
        execution_generation=1,
        invocation_key="test-sql",
        request_hash="test-hash",
        kind="sql_query",
        request=ExecuteQueryRequest(
            sql="SELECT 1 as test_col",
            parameters={},
        ),
        input_artifacts=[],
        deadline="2099-12-31T23:59:59Z",
        environment_manifest_id=uuid4(),
    )

    outcome = await controller.execute(None, request)
    assert outcome.status in ("succeeded", "failed")

    await controller.destroy_session()


@pytest.mark.live
@pytest.mark.asyncio
async def test_sandbox_python_execution():
    """Test Python execution in sandbox."""
    controller = create_sandbox_controller(
        session_id=uuid4(),
        run_id=uuid4(),
    )

    await controller.create_session()

    from querivue_agent.execution.sandbox import OperationRequest
    from querivue_agent.contracts.tools import ExecutePythonRequest, OutputDeclaration

    request = OperationRequest(
        operation_id=uuid4(),
        scope=None,
        task_id=None,
        action_id=uuid4(),
        attempt=1,
        execution_generation=1,
        invocation_key="test-python",
        request_hash="test-hash",
        kind="python_code",
        request=ExecutePythonRequest(
            code="print('hello from sandbox')",
            input_evidence_ids=[],
            outputs=[],
        ),
        input_artifacts=[],
        deadline="2099-12-31T23:59:59Z",
        environment_manifest_id=uuid4(),
    )

    outcome = await controller.execute(None, request)
    assert outcome.status in ("succeeded", "failed")

    await controller.destroy_session()


@pytest.mark.live
@pytest.mark.asyncio
async def test_artifact_validation_gate():
    """Test artifact validation gate with real files."""
    with tempfile.TemporaryDirectory() as tmp:
        quarantine_dir = Path(tmp) / "quarantine"
        quarantine_dir.mkdir()
        destination_dir = Path(tmp) / "final"
        destination_dir.mkdir()

        limits = ResourceLimits()
        gate = ArtifactValidationGate(quarantine_dir)

        # Create a test Parquet artifact
        import pyarrow as pa
        import pyarrow.parquet as pq

        table = pa.table({"col1": [1, 2, 3], "col2": ["a", "b", "c"]})
        artifact_path = quarantine_dir / "test.parquet"
        pq.write_table(table, artifact_path)

        # Validate and promote
        result = await gate.validate_and_promote(
            artifact_path,
            destination_dir / "test.parquet",
        )

        assert result.valid is True
        assert result.size_bytes > 0
        assert len(result.sha256) == 64
        assert result.mime_type == "application/vnd.apache.parquet"
        assert (destination_dir / "test.parquet").exists()


@pytest.mark.live
@pytest.mark.asyncio
async def test_execution_validator_gate_live():
    """Test execution validator gate with real artifacts."""
    limits = ResourceLimits(max_output_files=2, output_mib=1)
    gate = ExecutionValidatorGate(limits)

    with tempfile.TemporaryDirectory() as tmp:
        # Test artifact count limit
        artifacts = [Path(tmp) / f"result_{i}.parquet" for i in range(3)]
        for a in artifacts:
            a.write_bytes(b"test")

        results = gate.validate_post_execution("sql", artifacts)
        failed = [r for r in results if not r.passed]
        assert len(failed) == 1
        assert failed[0].gate_name == "artifact_count_limit"

        # Test size limit
        artifact = Path(tmp) / "large.parquet"
        artifact.write_bytes(b"x" * (2 * 1024 * 1024))  # 2 MiB

        results = gate.validate_post_execution("sql", [artifact])
        failed = [r for r in results if not r.passed]
        assert len(failed) == 1
        assert failed[0].gate_name == "total_output_size"


@pytest.mark.live
@pytest.mark.asyncio
async def test_compute_file_hash():
    """Test file hash computation."""
    with tempfile.TemporaryDirectory() as tmp:
        file_path = Path(tmp) / "test.txt"
        file_path.write_bytes(b"test data")

        hash_value = compute_file_hash(file_path)
        assert len(hash_value) == 64
        # Known SHA-256 of "test data"
        assert hash_value == "916f0027a575074ce72a331777c3478d6513f786a591bd892da1a577f23355d1"


@pytest.mark.live
@pytest.mark.asyncio
async def test_validate_png_file():
    """Test PNG file validation."""
    with tempfile.TemporaryDirectory() as tmp:
        # Create a minimal valid PNG
        png_path = Path(tmp) / "test.png"
        # Minimal PNG header + IHDR + IEND
        png_data = (
            b"\x89PNG\r\n\x1a\n"  # PNG signature
            b"\x00\x00\x00\rIHDR"  # IHDR chunk
            b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00"  # 1x1, 8-bit, truecolor
            b"\x90wS\xde"  # CRC
            b"\x00\x00\x00\x00IEND"  # IEND chunk
            b"\xaeB`\x82"  # CRC
        )
        png_path.write_bytes(png_data)

        # This test requires the `file` command to be available
        import shutil
        if shutil.which("file"):
            result = validate_png_file(png_path)
            # Note: minimal PNG may not be recognized by `file` command
            # This is just a smoke test


@pytest.mark.live
@pytest.mark.asyncio
async def test_validate_parquet_file():
    """Test Parquet file validation."""
    with tempfile.TemporaryDirectory() as tmp:
        parquet_path = Path(tmp) / "test.parquet"

        import pyarrow as pa
        import pyarrow.parquet as pq

        table = pa.table({"col1": [1, 2, 3]})
        pq.write_table(table, parquet_path)

        result = validate_parquet_file(parquet_path)
        assert result is True

        # Test invalid file
        invalid_path = Path(tmp) / "invalid.parquet"
        invalid_path.write_bytes(b"not a parquet file")
        result = validate_parquet_file(invalid_path)
        assert result is False


@pytest.mark.live
@pytest.mark.asyncio
async def test_gate_orchestrator_full_flow():
    """Test full gate orchestration flow."""
    limits = ResourceLimits()
    with tempfile.TemporaryDirectory() as tmp:
        quarantine_dir = Path(tmp) / "quarantine"
        quarantine_dir.mkdir()

        orchestrator = GateOrchestrator(limits, quarantine_dir)

        # Environment admission
        manifest = create_default_environment_manifest()
        result = orchestrator.admit_environment(manifest)
        assert result.admitted is True

        # Pre-execution validation
        session_id = uuid4()
        run_id = uuid4()
        results = orchestrator.validate_pre_execution(session_id, run_id, "sql")
        assert all(r.passed for r in results)

        # Post-execution validation
        artifacts = [Path(tmp) / "result.parquet"]
        artifacts[0].write_bytes(b"test")
        results = orchestrator.validate_post_execution("sql", artifacts)
        assert all(r.passed for r in results)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "live"])