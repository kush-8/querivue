"""Strict shape validation for SQL tool requests."""

from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator, model_validator

from .evidence import ChartDeclaration, OutputDeclaration
from .values import CanonicalUUID, TypedScalar, UnicodeString


def _nonblank(value: str) -> str:
    if not value.strip():
        raise ValueError("expected a nonblank string")
    return value


NonblankString = Annotated[UnicodeString, AfterValidator(_nonblank)]


class _StrictModel(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")


class InspectTableRequest(_StrictModel):
    table_id: CanonicalUUID


class PreviewRowsRequest(_StrictModel):
    table_id: CanonicalUUID
    columns: list[NonblankString] | None = Field(min_length=1)
    limit: Annotated[int, Field(strict=True, gt=0)]

    @field_validator("columns")
    @classmethod
    def unique_columns(cls, value: list[str] | None) -> list[str] | None:
        if value is not None and len(value) != len(set(value)):
            raise ValueError("column names must be unique")
        return value


class InspectEvidenceRequest(_StrictModel):
    evidence_id: CanonicalUUID


class ExecuteQueryRequest(_StrictModel):
    sql: NonblankString
    parameters: dict[NonblankString, TypedScalar]

    @field_validator("parameters")
    @classmethod
    def unique_parameter_names(cls, value: dict[str, TypedScalar]) -> dict[str, TypedScalar]:
        folded_names = [name.casefold() for name in value]
        if len(folded_names) != len(set(folded_names)):
            raise ValueError("parameter names must be unique case-insensitively")
        return value


class ExecutePythonRequest(_StrictModel):
    code: NonblankString
    input_evidence_ids: list[CanonicalUUID] = Field(min_length=1)
    outputs: list[OutputDeclaration] = Field(min_length=1)

    @field_validator("input_evidence_ids")
    @classmethod
    def unique_inputs(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("input_evidence_ids must be unique")
        return value

    @model_validator(mode="after")
    def validate_outputs(self) -> "ExecutePythonRequest":
        names = [output.name for output in self.outputs]
        if len(names) != len(set(names)):
            raise ValueError("output names must be unique")
        inputs = set(self.input_evidence_ids)
        for output in self.outputs:
            if isinstance(output, ChartDeclaration):
                if any(series.evidence_id not in inputs for series in output.series):
                    raise ValueError("chart evidence_id must be declared as an input")
        return self
