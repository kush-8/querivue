"""Strict offline artifact references and validation receipts."""

import re
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator

from .values import CanonicalUUID, RuntimeUUID, UnicodeString


MAX_SAFE_INTEGER = 9007199254740991


def _nonblank(value: str) -> str:
    if not value.strip():
        raise ValueError("expected a nonblank string")
    return value


def _sha256(value: str) -> str:
    if not re.fullmatch(r"[0-9a-f]{64}", value):
        raise ValueError("expected a lowercase SHA-256 hex digest")
    return value


NonblankString = Annotated[UnicodeString, AfterValidator(_nonblank)]
Sha256 = Annotated[str, Field(strict=True), AfterValidator(_sha256)]
SafeInteger = Annotated[int, Field(strict=True, ge=0, le=MAX_SAFE_INTEGER)]
PositiveSafeInteger = Annotated[int, Field(strict=True, ge=1, le=MAX_SAFE_INTEGER)]


class _StrictModel(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")


class SourceDependency(_StrictModel):
    dataset_id: CanonicalUUID
    snapshot_id: CanonicalUUID


class ArtifactRef(_StrictModel):
    artifact_id: CanonicalUUID
    storage_ref: CanonicalUUID
    media_type: NonblankString
    size_bytes: SafeInteger
    sha256: Sha256
    environment_manifest_id: CanonicalUUID | None


class StagedArtifact(_StrictModel):
    staging_id: RuntimeUUID
    artifact: ArtifactRef
    owner_generation: PositiveSafeInteger
    validation_receipt_id: CanonicalUUID | None


class ValidationReceipt(_StrictModel):
    receipt_id: RuntimeUUID
    artifact_id: CanonicalUUID
    sha256: Sha256
    size_bytes: SafeInteger
    validator_version: NonblankString
    environment_manifest_id: CanonicalUUID
    checks: list[NonblankString] = Field(min_length=1)

    @field_validator("checks")
    @classmethod
    def unique_checks(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("checks must be unique")
        return value

