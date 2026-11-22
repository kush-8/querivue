"""Strict shape validation for planned analysis actions."""

from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator, model_validator

from .values import CanonicalUUID, RuntimeUUID, TypedScalar, UnicodeString


def _nonblank(value: str) -> str:
    if not value.strip():
        raise ValueError("expected a nonblank string")
    return value


NonblankString = Annotated[UnicodeString, AfterValidator(_nonblank)]


class _StrictModel(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")


class DateWindow(_StrictModel):
    source_id: CanonicalUUID
    column: NonblankString
    lower: TypedScalar
    upper: TypedScalar
    lower_inclusive: bool
    upper_inclusive: bool


class AnalysisConstraints(_StrictModel):
    metric_definitions: dict[NonblankString, NonblankString]
    filters: list[NonblankString]
    date_windows: list[DateWindow]
    analysis_timezone: NonblankString | None
    grain: NonblankString | None
    units: dict[NonblankString, NonblankString]


class _Action(_StrictModel):
    action_id: RuntimeUUID
    objective: NonblankString
    constraints: AnalysisConstraints


class SQLAction(_Action):
    type: Literal["sql"]
    table_ids: list[CanonicalUUID]
    input_evidence_ids: list[CanonicalUUID]

    @field_validator("table_ids", "input_evidence_ids")
    @classmethod
    def unique_inputs(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("input references must be unique")
        return value

    @model_validator(mode="after")
    def require_input(self) -> "SQLAction":
        if not self.table_ids and not self.input_evidence_ids:
            raise ValueError("at least one table or evidence input is required")
        return self


class PythonAction(_Action):
    type: Literal["python"]
    input_evidence_ids: list[CanonicalUUID] = Field(min_length=1)
    required_outputs: list[Literal["evidence", "chart"]] = Field(min_length=1)

    @field_validator("input_evidence_ids", "required_outputs")
    @classmethod
    def unique_items(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("items must be unique")
        return value


class AnswerAction(_Action):
    type: Literal["answer"]
    evidence_ids: list[CanonicalUUID]
    chart_artifact_ids: list[CanonicalUUID]

    @field_validator("evidence_ids", "chart_artifact_ids")
    @classmethod
    def unique_references(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("references must be unique")
        return value


Action = Annotated[SQLAction | PythonAction | AnswerAction, Field(discriminator="type")]
