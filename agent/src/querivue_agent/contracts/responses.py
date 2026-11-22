"""Shape validation only: callers must supply runtime-sanitized, verified errors
and authorized, published evidence valid for the current scope and source.
"""

from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, ValidationInfo, field_validator

from .values import CanonicalUUID, RuntimeUUID, UnicodeString


def _nonblank(value: str) -> str:
    if not value.strip():
        raise ValueError("expected a nonblank string")
    return value


NonblankString = Annotated[UnicodeString, AfterValidator(_nonblank)]

ErrorCode = Literal[
    "invalid_arguments", "sql_parse_error", "unknown_relation", "unknown_column",
    "type_mismatch", "policy_violation", "sql_unsupported", "source_unavailable",
    "artifact_unavailable", "artifact_integrity_failure", "query_timeout",
    "result_limit_exceeded", "unsupported_result_type", "infrastructure_unavailable",
    "budget_exhausted", "no_progress", "invalid_specialist_output", "internal_error",
]
ErrorStage = Literal["validation", "execution", "persistence", "recovery"]
ErrorDisposition = Literal[
    "correct_query", "retry_operation", "clarify", "replan", "fail_action", "invalidate_run",
]


class _StrictModel(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")


class ToolError(_StrictModel):
    code: ErrorCode
    message: Annotated[NonblankString, Field(max_length=2048)]
    stage: ErrorStage
    operation_id: RuntimeUUID | None = None
    disposition: ErrorDisposition


class _SQLOutcome(_StrictModel):
    evidence_ids: list[CanonicalUUID]

    @field_validator("evidence_ids")
    @classmethod
    def unique_evidence(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("evidence_ids must be unique")
        return value


class SQLSucceeded(_SQLOutcome):
    status: Literal["succeeded"]
    observation: NonblankString
    evidence_ids: list[RuntimeUUID] = Field(min_length=1)
    limitations: list[NonblankString]


class SQLBlocked(_SQLOutcome):
    status: Literal["blocked"]
    explanation: NonblankString
    required_input: NonblankString


class SQLFailed(_SQLOutcome):
    status: Literal["failed"]
    error: ToolError


SQLOutcome = Annotated[SQLSucceeded | SQLBlocked | SQLFailed, Field(discriminator="status")]


class _PythonOutcome(_StrictModel):
    """Shape boundary only; runtime output and authorization checks happen elsewhere."""

    evidence_ids: list[CanonicalUUID]
    chart_artifact_ids: list[CanonicalUUID]

    @field_validator("evidence_ids", "chart_artifact_ids")
    @classmethod
    def unique_references(cls, value: list[str], info: ValidationInfo) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError(f"{info.field_name} must be unique")
        return value


class PythonSucceeded(_PythonOutcome):
    status: Literal["succeeded"]
    observation: NonblankString
    limitations: list[NonblankString]


class PythonBlocked(_PythonOutcome):
    status: Literal["blocked"]
    explanation: NonblankString
    required_input: NonblankString


class PythonFailed(_PythonOutcome):
    status: Literal["failed"]
    error: ToolError


PythonOutcome = Annotated[
    PythonSucceeded | PythonBlocked | PythonFailed,
    Field(discriminator="status"),
]
