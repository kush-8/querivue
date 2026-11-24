import json
from copy import deepcopy

import pytest
from pydantic import ValidationError

from querivue_agent.contracts.artifacts import (
    ArtifactRef,
    SourceDependency,
    StagedArtifact,
    ValidationReceipt,
)


V4 = "6b085fd1-4c78-4b85-96c9-a201ce5e935c"
V4B = "79364864-0736-4e18-a3a0-6e2ff4c4ae21"
V1 = "123e4567-e89b-12d3-a456-426614174000"
HASH = "a" * 64


ARTIFACT = {
    "artifact_id": V1,
    "storage_ref": V4B,
    "media_type": "  application/octet-stream  ",
    "size_bytes": 0,
    "sha256": HASH,
    "environment_manifest_id": V1,
}


def test_artifact_models_round_trip_native_and_json():
    dependency = SourceDependency(dataset_id=V1, snapshot_id=V4)
    assert dependency.model_dump() == {"dataset_id": V1, "snapshot_id": V4}
    artifact = ArtifactRef.model_validate(ARTIFACT)
    assert artifact.model_dump() == ARTIFACT
    assert ArtifactRef.model_validate_json(json.dumps(ARTIFACT)) == artifact

    staged = StagedArtifact.model_validate({
        "staging_id": V4,
        "artifact": ARTIFACT,
        "owner_generation": 1,
        "validation_receipt_id": None,
    })
    assert staged.artifact.artifact_id == V1

    receipt = ValidationReceipt.model_validate({
        "receipt_id": V4,
        "artifact_id": V1,
        "sha256": HASH,
        "size_bytes": 0,
        "validator_version": " v1 ",
        "environment_manifest_id": V1,
        "checks": ["hash", " size "],
    })
    assert receipt.checks == ["hash", " size "]


def test_raw_and_staged_artifacts_require_explicit_but_nullable_environment():
    raw = {**ARTIFACT, "environment_manifest_id": None}
    assert ArtifactRef.model_validate(raw).environment_manifest_id is None
    staged = StagedArtifact.model_validate({
        "staging_id": V4,
        "artifact": raw,
        "owner_generation": 1,
        "validation_receipt_id": None,
    })
    assert staged.artifact.environment_manifest_id is None

    missing = deepcopy(raw)
    del missing["environment_manifest_id"]
    with pytest.raises(ValidationError, match="Field required"):
        ArtifactRef.model_validate(missing)


@pytest.mark.parametrize(
    "change",
    [
        {"media_type": " \t"},
        {"size_bytes": -1},
        {"size_bytes": True},
        {"size_bytes": 9007199254740992},
        {"sha256": "A" * 64},
        {"sha256": "a" * 63},
        {"artifact_id": V1.upper()},
        {"path": "/tmp/result"},
    ],
)
def test_artifact_rejects_invalid_boundaries_and_capability_fields(change):
    with pytest.raises(ValidationError):
        ArtifactRef.model_validate({**ARTIFACT, **change})


@pytest.mark.parametrize("field", ARTIFACT)
def test_artifact_fields_are_required(field):
    payload = deepcopy(ARTIFACT)
    del payload[field]
    with pytest.raises(ValidationError, match="Field required"):
        ArtifactRef.model_validate(payload)


@pytest.mark.parametrize(
    "change",
    [
        {"staging_id": V1},
        {"owner_generation": 0},
        {"owner_generation": 1.0},
        {"validation_receipt_id": V1.upper()},
        {"published": True},
    ],
)
def test_staging_is_strict_and_does_not_imply_publication(change):
    payload = {
        "staging_id": V4,
        "artifact": ARTIFACT,
        "owner_generation": 1,
        "validation_receipt_id": V1,
    }
    with pytest.raises(ValidationError):
        StagedArtifact.model_validate({**payload, **change})


@pytest.mark.parametrize(
    "change",
    [
        {"receipt_id": V1},
        {"sha256": "b" * 65},
        {"size_bytes": -1},
        {"validator_version": ""},
        {"checks": []},
        {"checks": ["hash", "hash"]},
        {"checks": [" "]},
        {"executed": True},
    ],
)
def test_validation_receipt_rejects_untrusted_or_invalid_shapes(change):
    payload = {
        "receipt_id": V4,
        "artifact_id": V1,
        "sha256": HASH,
        "size_bytes": 0,
        "validator_version": "v1",
        "environment_manifest_id": V1,
        "checks": ["hash"],
    }
    with pytest.raises(ValidationError):
        ValidationReceipt.model_validate({**payload, **change})

