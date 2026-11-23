"""Shared strict identity, ownership, and scalar contracts."""

import re
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator, model_validator

from .values import CanonicalUUID, RuntimeUUID, TimestamptzScalar, UnicodeString


class StrictRecord(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")


def _nonblank(value: str) -> str:
    if not value.strip():
        raise ValueError("expected a nonblank string")
    return value


def _timestamp(value: str) -> str:
    return TimestamptzScalar.validate_timestamp(value)


def _money(value: str) -> str:
    if len(value) > 128 or not re.fullmatch(r"(?:0|[1-9][0-9]*)(?:\.[0-9]+)?", value):
        raise ValueError("expected a nonnegative plain decimal string of at most 128 characters")
    return value


NonblankString = Annotated[UnicodeString, Field(strict=True), AfterValidator(_nonblank)]
SafeCount = Annotated[int, Field(strict=True, ge=0, le=9007199254740991)]
PositiveCount = Annotated[int, Field(strict=True, ge=1, le=9007199254740991)]
Hash64 = Annotated[str, Field(strict=True, pattern=r"^[0-9a-f]{64}$")]
TimestampText = Annotated[str, Field(strict=True), AfterValidator(_timestamp)]
MoneyText = Annotated[str, Field(strict=True), AfterValidator(_money)]
Role = Literal["entry", "supervisor", "sql", "python", "answer", "reviewer", "clarification"]


class Scope(StrictRecord):
    project_id: CanonicalUUID
    chat_id: CanonicalUUID | None
    run_id: CanonicalUUID | None
    eligible_dataset_ids: list[CanonicalUUID]

    @field_validator("eligible_dataset_ids")
    @classmethod
    def unique_datasets(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("eligible_dataset_ids must be unique")
        return value

    @model_validator(mode="after")
    def validate_scope(self) -> "Scope":
        if self.run_id is not None and self.chat_id is None:
            raise ValueError("run_id requires chat_id")
        return self


class OwnerFence(StrictRecord):
    scope: Scope
    subject_kind: Literal["intake", "run", "preparation", "action", "operation"]
    subject_id: CanonicalUUID
    owner_id: RuntimeUUID
    generation: PositiveCount
    attempt: PositiveCount
    expected_revision: SafeCount
    lease_expires_at: TimestampText

    @model_validator(mode="after")
    def validate_run_subject(self) -> "OwnerFence":
        if self.subject_kind == "run" and self.scope.run_id != self.subject_id:
            raise ValueError("run subject_id must equal scope.run_id")
        return self
