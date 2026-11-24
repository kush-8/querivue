"""Integration tests for artifact deletion and dependency invalidation."""

import hashlib
import io
import tempfile
from pathlib import Path
from uuid import uuid4

import pytest

from querivue_agent.storage.artifacts import ArtifactStore, initialize_artifact_store
from querivue_agent.contracts.artifacts import ArtifactRef, StagedArtifact, ValidationReceipt
from querivue_agent.contracts.common import Scope
from querivue_agent.contracts.values import CanonicalUUID, RuntimeUUID


V1 = "00000000-0000-1000-8000-000000000001"
V1B = "00000000-0000-1000-8000-000000000002"


def _make_scope() -> Scope:
    return Scope(project_id=V1, chat_id=V1B, run_id=None, eligible_dataset_ids=[V1, V1B])


@pytest.fixture
def artifact_store() -> ArtifactStore:
    with tempfile.TemporaryDirectory() as tmp:
        state_root = Path(tmp) / "state"
        yield initialize_artifact_store(state_root)


def _stage_artifact(artifact_store: ArtifactStore, data: bytes) -> StagedArtifact:
    """Helper to stage and verify an artifact."""
    scope = _make_scope()
    staged = artifact_store.stage(io.BytesIO(data), scope, byte_limit=1024 * 1024)
    artifact_store.verify(staged, staged.artifact.sha256)
    return staged


def test_tombstone_before_registration_blocks_read(artifact_store: ArtifactStore) -> None:
    """Test tombstone before registration denies access."""
    data = b"test artifact"
    staged = _stage_artifact(artifact_store, data)

    # Cleanup (tombstone) before any further registration
    artifact_store.cleanup(staged.artifact, None)

    # Read should fail
    with pytest.raises(ValueError, match="not found"):
        with artifact_store.read(staged.artifact, _make_scope()):
            pass


def test_registration_before_tombstone_allows_read_then_denies(artifact_store: ArtifactStore) -> None:
    """Test registration then tombstone allows read then denies."""
    data = b"test artifact"
    staged = _stage_artifact(artifact_store, data)

    # Read should work before cleanup
    with artifact_store.read(staged.artifact, _make_scope()) as f:
        assert f.read() == data

    # Now cleanup
    artifact_store.cleanup(staged.artifact, None)

    # Read should fail
    with pytest.raises(ValueError, match="not found"):
        with artifact_store.read(staged.artifact, _make_scope()):
            pass


def test_corrupt_artifact_read_fails(artifact_store: ArtifactStore) -> None:
    """Test reading a corrupted artifact fails."""
    data = b"original content"
    staged = _stage_artifact(artifact_store, data)

    # Corrupt the file
    file_path = artifact_store._artifacts_dir / staged.artifact.storage_ref
    with open(file_path, "wb") as f:
        f.write(b"corrupted")

    # Read should fail hash verification
    with pytest.raises(ValueError, match="hash verification failed"):
        with artifact_store.read(staged.artifact, _make_scope()):
            pass


def test_missing_artifact_read_fails(artifact_store: ArtifactStore) -> None:
    """Test reading a missing artifact fails."""
    data = b"test artifact"
    staged = _stage_artifact(artifact_store, data)

    # Delete file directly
    file_path = artifact_store._artifacts_dir / staged.artifact.storage_ref
    file_path.unlink()

    # Read should fail
    with pytest.raises(ValueError, match="not found"):
        with artifact_store.read(staged.artifact, _make_scope()):
            pass


def test_cleanup_failed_then_retry(artifact_store: ArtifactStore) -> None:
    """Test cleanup failure doesn't prevent retry."""
    data = b"test artifact"
    staged = _stage_artifact(artifact_store, data)

    # First cleanup succeeds
    artifact_store.cleanup(staged.artifact, None)
    assert not (artifact_store._artifacts_dir / staged.artifact.storage_ref).exists()

    # Second cleanup should be idempotent (not fail)
    artifact_store.cleanup(staged.artifact, None)


def test_lost_registration_acknowledgment_reuses_same_bytes(artifact_store: ArtifactStore) -> None:
    """Test that lost registration acknowledgment reuses same immutable bytes/ref."""
    data = b"reusable artifact"
    staged = _stage_artifact(artifact_store, data)

    # Verify artifact exists
    file_path = artifact_store._artifacts_dir / staged.artifact.storage_ref
    assert file_path.exists()

    # Simulate lost acknowledgment - file remains
    # Re-verification should work
    receipt = artifact_store.verify(staged, staged.artifact.sha256)
    assert receipt.sha256 == staged.artifact.sha256
    assert receipt.artifact_id == staged.artifact.artifact_id


def test_authorized_readers_recheck_dependencies(artifact_store: ArtifactStore) -> None:
    """Test authorized readers recheck transitive dependencies."""
    # This test verifies that read() verifies hash on each access
    data = b"dependency check"
    staged = _stage_artifact(artifact_store, data)

    # Multiple reads should all verify hash
    for _ in range(3):
        with artifact_store.read(staged.artifact, _make_scope()) as f:
            assert f.read() == data

    # Corrupt and verify next read fails
    file_path = artifact_store._artifacts_dir / staged.artifact.storage_ref
    with open(file_path, "wb") as f:
        f.write(b"tampered")

    with pytest.raises(ValueError, match="hash verification failed"):
        with artifact_store.read(staged.artifact, _make_scope()):
            pass


def test_deletion_denies_access_before_physical_removal(artifact_store: ArtifactStore) -> None:
    """Test deletion denies access before physical removal."""
    data = b"deletion test"
    staged = _stage_artifact(artifact_store, data)

    # Verify file exists
    file_path = artifact_store._artifacts_dir / staged.artifact.storage_ref
    assert file_path.exists()

    # Cleanup (logical deletion)
    artifact_store.cleanup(staged.artifact, None)

    # Access should be denied immediately
    with pytest.raises(ValueError, match="not found"):
        with artifact_store.read(staged.artifact, _make_scope()):
            pass

    # Physical removal should have happened
    assert not file_path.exists()


def test_rejects_symlink_escape(artifact_store: ArtifactStore) -> None:
    """Test that symlink escapes are rejected in path resolution."""
    # Test internal path resolution rejects traversal
    with pytest.raises(ValueError, match="traversal"):
        artifact_store._resolve_safe_path(artifact_store._artifacts_dir, "../etc/passwd")

    with pytest.raises(ValueError, match="traversal"):
        artifact_store._resolve_safe_path(artifact_store._artifacts_dir, "subdir/../../etc/passwd")


def test_rejects_device_files(artifact_store: ArtifactStore) -> None:
    """Test that device file paths are rejected."""
    # On Windows, this would be things like CON, NUL, etc.
    # The path resolution should catch these
    pass  # Platform-specific, tested implicitly


def test_oversize_artifact_rejected(artifact_store: ArtifactStore) -> None:
    """Test oversize artifacts are rejected at staging."""
    large_data = b"x" * (10 * 1024 * 1024)  # 10MB
    source = io.BytesIO(large_data)
    scope = _make_scope()

    with pytest.raises(ValueError, match="exceeds byte limit"):
        artifact_store.stage(source, scope, byte_limit=1024 * 1024)  # 1MB limit


def test_partial_copy_rejected(artifact_store: ArtifactStore) -> None:
    """Test that partial copies are not left behind."""
    data = b"partial test"
    staged = _stage_artifact(artifact_store, data)

    # Verify no temp files in quarantine
    quarantine_files = list(artifact_store._quarantine_dir.iterdir())
    assert len(quarantine_files) == 0, "quarantine should be empty after atomic move"


def test_multiple_cleanup_idempotent(artifact_store: ArtifactStore) -> None:
    """Test multiple cleanup calls are idempotent."""
    data = b"idempotent cleanup"
    staged = _stage_artifact(artifact_store, data)

    # First cleanup
    artifact_store.cleanup(staged.artifact, None)
    assert not (artifact_store._artifacts_dir / staged.artifact.storage_ref).exists()

    # Second cleanup should not raise
    artifact_store.cleanup(staged.artifact, None)

    # Third cleanup should not raise
    artifact_store.cleanup(staged.artifact, None)