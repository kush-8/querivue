"""Unit tests for ArtifactStore implementation."""

import hashlib
import io
import tempfile
from pathlib import Path
from uuid import uuid4

import pytest

from querivue_agent.storage.artifacts import ArtifactStore, initialize_artifact_store
from querivue_agent.contracts.common import Scope
from querivue_agent.contracts.values import CanonicalUUID


V1 = "00000000-0000-1000-8000-000000000001"
V1B = "00000000-0000-1000-8000-000000000002"


def _make_scope() -> Scope:
    return Scope(project_id=V1, chat_id=V1B, run_id=None, eligible_dataset_ids=[V1, V1B])


@pytest.fixture
def artifact_store() -> ArtifactStore:
    with tempfile.TemporaryDirectory() as tmp:
        state_root = Path(tmp) / "state"
        yield initialize_artifact_store(state_root)


def test_stage_and_verify(artifact_store: ArtifactStore) -> None:
    """Test staging and verifying an artifact."""
    data = b"test artifact content"
    source = io.BytesIO(data)
    scope = _make_scope()

    staged = artifact_store.stage(source, scope, byte_limit=1024 * 1024)
    assert staged.artifact.size_bytes == len(data)
    assert staged.artifact.sha256 == hashlib.sha256(data).hexdigest()
    assert staged.validation_receipt_id is None

    receipt = artifact_store.verify(staged, staged.artifact.sha256)
    assert receipt.artifact_id == staged.artifact.artifact_id
    assert receipt.sha256 == staged.artifact.sha256
    assert receipt.size_bytes == len(data)
    assert "sha256" in receipt.checks
    assert "size" in receipt.checks


def test_stage_exceeds_byte_limit(artifact_store: ArtifactStore) -> None:
    """Test staging artifact that exceeds byte limit."""
    data = b"x" * 100
    source = io.BytesIO(data)
    scope = _make_scope()

    with pytest.raises(ValueError, match="exceeds byte limit"):
        artifact_store.stage(source, scope, byte_limit=50)


def test_verify_hash_mismatch(artifact_store: ArtifactStore) -> None:
    """Test verification fails on hash mismatch."""
    data = b"test content"
    source = io.BytesIO(data)
    scope = _make_scope()

    staged = artifact_store.stage(source, scope, byte_limit=1024 * 1024)
    wrong_hash = "a" * 64

    with pytest.raises(ValueError, match="hash mismatch"):
        artifact_store.verify(staged, wrong_hash)


def test_read_artifact(artifact_store: ArtifactStore) -> None:
    """Test reading a verified artifact."""
    data = b"read test content"
    source = io.BytesIO(data)
    scope = _make_scope()

    staged = artifact_store.stage(source, scope, byte_limit=1024 * 1024)
    artifact_store.verify(staged, staged.artifact.sha256)

    # Read back
    with artifact_store.read(staged.artifact, scope) as f:
        read_data = f.read()
    assert read_data == data


def test_read_nonexistent_artifact(artifact_store: ArtifactStore) -> None:
    """Test reading non-existent artifact fails."""
    from querivue_agent.contracts.artifacts import ArtifactRef
    from querivue_agent.contracts.values import CanonicalUUID

    ref = ArtifactRef(
        artifact_id=str(uuid4()),
        storage_ref=str(uuid4()),
        media_type="application/octet-stream",
        size_bytes=100,
        sha256="a" * 64,
        environment_manifest_id=None,
    )
    scope = _make_scope()

    with pytest.raises(ValueError, match="not found"):
        artifact_store.read(ref, scope)


def test_read_hash_verification_fails(artifact_store: ArtifactStore) -> None:
    """Test read fails if artifact was corrupted."""
    data = b"original content"
    source = io.BytesIO(data)
    scope = _make_scope()

    staged = artifact_store.stage(source, scope, byte_limit=1024 * 1024)
    artifact_store.verify(staged, staged.artifact.sha256)

    # Corrupt the file
    file_path = artifact_store._artifacts_dir / staged.artifact.storage_ref
    with open(file_path, "wb") as f:
        f.write(b"corrupted")

    # Read should fail hash verification
    with pytest.raises(ValueError, match="hash verification failed"):
        with artifact_store.read(staged.artifact, scope):
            pass


def test_cleanup_artifact(artifact_store: ArtifactStore) -> None:
    """Test cleaning up an artifact."""
    data = b"cleanup test"
    source = io.BytesIO(data)
    scope = _make_scope()

    staged = artifact_store.stage(source, scope, byte_limit=1024 * 1024)
    artifact_store.verify(staged, staged.artifact.sha256)

    # Verify file exists
    file_path = artifact_store._artifacts_dir / staged.artifact.storage_ref
    assert file_path.exists()

    # Cleanup
    artifact_store.cleanup(staged.artifact, None)

    # File should be gone
    assert not file_path.exists()


def test_stage_uses_same_filesystem_atomic_move(artifact_store: ArtifactStore) -> None:
    """Test staging uses atomic move on same filesystem."""
    data = b"atomic move test"
    source = io.BytesIO(data)
    scope = _make_scope()

    staged = artifact_store.stage(source, scope, byte_limit=1024 * 1024)

    # File should be in artifacts dir, not quarantine
    file_path = artifact_store._artifacts_dir / staged.artifact.storage_ref
    assert file_path.exists()

    quarantine_file = artifact_store._quarantine_dir / f"{staged.artifact.storage_ref}.tmp"
    assert not quarantine_file.exists()


def test_stage_preserves_hash(artifact_store: ArtifactStore) -> None:
    """Test that staged artifact hash matches source."""
    import os

    data = b"hash preservation test"
    expected_hash = hashlib.sha256(data).hexdigest()
    source = io.BytesIO(data)
    scope = _make_scope()

    staged = artifact_store.stage(source, scope, byte_limit=1024 * 1024)

    assert staged.artifact.sha256 == expected_hash

    # Verify file on disk has same hash
    file_path = artifact_store._artifacts_dir / staged.artifact.storage_ref
    with open(file_path, "rb") as f:
        disk_hash = hashlib.sha256(f.read()).hexdigest()
    assert disk_hash == expected_hash


def test_multiple_artifacts_isolated(artifact_store: ArtifactStore) -> None:
    """Test multiple artifacts are isolated."""
    data1 = b"artifact one"
    data2 = b"artifact two"
    scope = _make_scope()

    staged1 = artifact_store.stage(io.BytesIO(data1), scope, byte_limit=1024 * 1024)
    staged2 = artifact_store.stage(io.BytesIO(data2), scope, byte_limit=1024 * 1024)

    assert staged1.artifact.storage_ref != staged2.artifact.storage_ref
    assert staged1.artifact.sha256 != staged2.artifact.sha256

    # Both should be readable
    with artifact_store.read(staged1.artifact, scope) as f:
        assert f.read() == data1
    with artifact_store.read(staged2.artifact, scope) as f:
        assert f.read() == data2


def test_verify_returns_receipt_with_metadata(artifact_store: ArtifactStore) -> None:
    """Test verification returns receipt with all required metadata."""
    data = b"metadata test"
    source = io.BytesIO(data)
    scope = _make_scope()

    staged = artifact_store.stage(source, scope, byte_limit=1024 * 1024)
    receipt = artifact_store.verify(staged, staged.artifact.sha256)

    assert receipt.receipt_id is not None
    assert receipt.artifact_id == staged.artifact.artifact_id
    assert receipt.sha256 == staged.artifact.sha256
    assert receipt.size_bytes == len(data)
    assert receipt.validator_version == "sha256-v1"
    assert receipt.environment_manifest_id is not None
    assert set(receipt.checks) == {"sha256", "size"}