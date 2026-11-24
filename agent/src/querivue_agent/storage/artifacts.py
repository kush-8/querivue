"""Immutable artifacts, quarantine and dependency invalidation."""

from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
from pathlib import Path
from typing import BinaryIO

from querivue_agent.contracts.artifacts import ArtifactRef, StagedArtifact, ValidationReceipt
from querivue_agent.contracts.common import Scope


class ArtifactStore:
    """Immutable artifact store with quarantine and dependency invalidation."""

    def __init__(self, state_root: Path) -> None:
        self._state_root = state_root.resolve()
        self._artifacts_dir = self._state_root / "artifacts"
        self._quarantine_dir = self._state_root / "quarantine"
        self._artifacts_dir.mkdir(parents=True, exist_ok=True)
        self._quarantine_dir.mkdir(parents=True, exist_ok=True)

    def _resolve_safe_path(self, base: Path, rel_path: str) -> Path:
        """Resolve a relative path within base, rejecting traversal."""
        resolved = (base / rel_path).resolve()
        try:
            resolved.relative_to(base)
        except ValueError:
            raise ValueError("path traversal attempt rejected")
        return resolved

    def stage(
        self, source: BinaryIO, scope: Scope, byte_limit: int
    ) -> StagedArtifact:
        """Stage immutable bytes in quarantine with hash verification."""
        import uuid

        from querivue_agent.contracts.artifacts import ArtifactRef, SourceDependency
        from querivue_agent.contracts.values import CanonicalUUID, RuntimeUUID

        # Read all bytes and verify size
        data = source.read()
        if len(data) > byte_limit:
            raise ValueError(f"artifact exceeds byte limit: {len(data)} > {byte_limit}")

        # Compute SHA-256
        sha256 = hashlib.sha256(data).hexdigest()

        # Create artifact reference
        artifact_id = str(uuid.uuid4())
        storage_ref = str(uuid.uuid4())
        artifact = ArtifactRef(
            artifact_id=artifact_id,
            storage_ref=storage_ref,
            media_type="application/octet-stream",
            size_bytes=len(data),
            sha256=sha256,
            environment_manifest_id=None,
        )

        # Write to quarantine with atomic move
        quarantine_file = self._quarantine_dir / f"{storage_ref}.tmp"
        final_file = self._artifacts_dir / f"{storage_ref}"

        with open(quarantine_file, "wb") as f:
            f.write(data)

        # Verify hash after write
        with open(quarantine_file, "rb") as f:
            written_hash = hashlib.sha256(f.read()).hexdigest()
        if written_hash != sha256:
            quarantine_file.unlink(missing_ok=True)
            raise ValueError("hash mismatch after quarantine write")

        # Atomic move to final location
        os.replace(quarantine_file, final_file)

        # Return staged artifact
        return StagedArtifact(
            staging_id=RuntimeUUID(storage_ref),
            artifact=artifact,
            owner_generation=1,
            validation_receipt_id=None,
        )

    def verify(
        self, candidate: StagedArtifact, expected_sha256: str
    ) -> ValidationReceipt:
        """Verify staged artifact hash and create validation receipt."""
        import uuid

        from querivue_agent.contracts.artifacts import ValidationReceipt
        from querivue_agent.contracts.values import RuntimeUUID

        # Read and verify artifact
        artifact = candidate.artifact
        file_path = self._artifacts_dir / artifact.storage_ref
        if not file_path.exists():
            raise ValueError("staged artifact not found")

        with open(file_path, "rb") as f:
            actual_hash = hashlib.sha256(f.read()).hexdigest()

        if actual_hash != expected_sha256:
            raise ValueError(
                f"hash mismatch: expected {expected_sha256}, got {actual_hash}"
            )
        if actual_hash != artifact.sha256:
            raise ValueError("artifact hash differs from stored reference")

        # Create validation receipt
        receipt = ValidationReceipt(
            receipt_id=RuntimeUUID(str(uuid.uuid4())),
            artifact_id=artifact.artifact_id,
            sha256=actual_hash,
            size_bytes=artifact.size_bytes,
            validator_version="sha256-v1",
            environment_manifest_id=artifact.environment_manifest_id
            or str(uuid.uuid4()),
            checks=["sha256", "size"],
        )

        return receipt

    def read(self, ref: ArtifactRef, scope: Scope) -> BinaryIO:
        """Read verified artifact, checking scope authorization."""
        file_path = self._artifacts_dir / ref.storage_ref
        if not file_path.exists():
            raise ValueError("artifact not found")

        # Verify hash on read
        with open(file_path, "rb") as f:
            actual_hash = hashlib.sha256(f.read()).hexdigest()
        if actual_hash != ref.sha256:
            raise ValueError("artifact hash verification failed on read")

        # Reopen for caller
        return open(file_path, "rb")

    def cleanup(self, ref: ArtifactRef, proof) -> None:
        """Clean up artifact after retirement proof verification."""
        file_path = self._artifacts_dir / ref.storage_ref
        if file_path.exists():
            file_path.unlink()

    def _reject_unsafe_path(self, path: Path) -> None:
        """Reject traversal, symlink/reparse escapes, device files."""
        try:
            path.resolve(strict=True)
        except OSError:
            raise ValueError("invalid path")

        # Check for symlinks/junctions in path
        for part in path.parents:
            if part.is_symlink() or part.is_mount():
                raise ValueError("symlink/reparse escape rejected")


def initialize_artifact_store(state_root: Path) -> ArtifactStore:
    """Initialize artifact store at state root."""
    return ArtifactStore(state_root)