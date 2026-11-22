"""Strict declarations for Python-produced evidence and charts."""

import re
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator, model_validator

from .values import CanonicalUUID, UnicodeString


def _nonblank(value: str) -> str:
    if not value.strip():
        raise ValueError("expected a nonblank string")
    return value


def _identifier(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", value):
        raise ValueError("expected an ASCII identifier")
    return value


NonblankString = Annotated[UnicodeString, AfterValidator(_nonblank)]
Identifier = Annotated[str, Field(strict=True), AfterValidator(_identifier)]


class _StrictModel(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")


class _SimpleColumnType(_StrictModel):
    pass


class BooleanColumn(_SimpleColumnType):
    tag: Literal["boolean"]


class Int64Column(_SimpleColumnType):
    tag: Literal["int64"]


class Uint64Column(_SimpleColumnType):
    tag: Literal["uint64"]


class Float64Column(_SimpleColumnType):
    tag: Literal["float64"]


class StringColumn(_SimpleColumnType):
    tag: Literal["string"]


class DateColumn(_SimpleColumnType):
    tag: Literal["date"]


class TimeColumn(_SimpleColumnType):
    tag: Literal["time"]


class TimestampColumn(_SimpleColumnType):
    tag: Literal["timestamp"]


class TimestamptzColumn(_SimpleColumnType):
    tag: Literal["timestamptz"]


class DecimalColumn(_StrictModel):
    tag: Literal["decimal"]
    precision: Annotated[int, Field(strict=True, ge=1, le=38)]
    scale: Annotated[int, Field(strict=True, ge=0)]

    @model_validator(mode="after")
    def validate_scale(self) -> "DecimalColumn":
        if self.scale > self.precision:
            raise ValueError("scale exceeds precision")
        return self


ColumnType = Annotated[
    BooleanColumn | Int64Column | Uint64Column | Float64Column | StringColumn
    | DateColumn | TimeColumn | TimestampColumn | TimestamptzColumn | DecimalColumn,
    Field(discriminator="tag"),
]


class OutputColumn(_StrictModel):
    name: NonblankString
    type: ColumnType
    nullable: bool


class EvidenceDeclaration(_StrictModel):
    name: Identifier
    kind: Literal["evidence"]
    description: NonblankString
    shape: Literal["scalar", "table"]
    columns: list[OutputColumn] = Field(min_length=1)

    @field_validator("columns")
    @classmethod
    def unique_columns(cls, value: list[OutputColumn]) -> list[OutputColumn]:
        if len({column.name for column in value}) != len(value):
            raise ValueError("column names must be unique")
        return value


class ColumnOrdering(_StrictModel):
    column: NonblankString
    direction: Literal["asc", "desc"]


class ChartSeries(_StrictModel):
    label: NonblankString
    evidence_id: CanonicalUUID
    ordering: list[ColumnOrdering]
    scales: dict[NonblankString, Literal["linear", "log"]]
    columns: dict[Identifier, NonblankString] = Field(min_length=1)


class ChartDeclaration(_StrictModel):
    name: Identifier
    kind: Literal["chart"]
    title: NonblankString
    description: NonblankString
    series: list[ChartSeries] = Field(min_length=1)
    units: dict[NonblankString, NonblankString]
    analysis_timezone: NonblankString | None
    limitations: list[NonblankString]


OutputDeclaration = Annotated[
    EvidenceDeclaration | ChartDeclaration,
    Field(discriminator="kind"),
]
