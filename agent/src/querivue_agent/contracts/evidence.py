"""Strict declarations for Python-produced evidence and charts."""

import re
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator, model_validator

from .actions import AnalysisConstraints
from .artifacts import ArtifactRef, Sha256, SourceDependency
from .values import CanonicalUUID, RuntimeUUID, TypedScalar, UnicodeString


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


MAX_SAFE_INTEGER = 9007199254740991
SafeInteger = Annotated[int, Field(strict=True, ge=0, le=MAX_SAFE_INTEGER)]
PositiveSafeInteger = Annotated[int, Field(strict=True, ge=1, le=MAX_SAFE_INTEGER)]


def _unique_strings(value: list[str], subject: str) -> list[str]:
    if len(value) != len(set(value)):
        raise ValueError(f"{subject} must be unique")
    return value


class EvidenceColumn(_StrictModel):
    ordinal: SafeInteger
    name: NonblankString
    original_label: UnicodeString | None
    original_ordinal: SafeInteger
    type: ColumnType
    nullable: bool


class CellLocator(_StrictModel):
    row_locator: SafeInteger
    column_ordinal: SafeInteger


class TabularPreview(_StrictModel):
    columns: list[EvidenceColumn] = Field(min_length=1)
    rows: list[list[UnicodeString | None]]
    row_locators: list[SafeInteger]
    full_row_count: SafeInteger
    returned_row_count: SafeInteger
    effective_limit: PositiveSafeInteger
    ordering: Literal["unspecified", "query_defined"]
    truncated: bool
    shortened_cells: list[CellLocator]

    @model_validator(mode="after")
    def validate_preview(self) -> "TabularPreview":
        column_ordinals = [column.ordinal for column in self.columns]
        if len(column_ordinals) != len(set(column_ordinals)):
            raise ValueError("column ordinals must be unique")
        _unique_strings([column.name for column in self.columns], "column names")
        if any(len(row) != len(self.columns) for row in self.rows):
            raise ValueError("preview row width must match columns")
        if any(
            cell is not None and len(cell.encode("utf-8")) > 2048
            for row in self.rows
            for cell in row
        ):
            raise ValueError("preview display cells must not exceed 2048 UTF-8 bytes")
        if any(
            cell is None and not self.columns[index].nullable
            for row in self.rows
            for index, cell in enumerate(row)
        ):
            raise ValueError("nonnullable preview columns cannot contain null cells")
        if self.returned_row_count != len(self.rows) or len(self.row_locators) != len(self.rows):
            raise ValueError("returned row counts must match rows and locators")
        if self.returned_row_count > self.effective_limit or self.returned_row_count > self.full_row_count:
            raise ValueError("returned row count exceeds its bounds")
        _unique_strings(self.row_locators, "row locators")
        if any(locator >= self.full_row_count for locator in self.row_locators):
            raise ValueError("row locator exceeds the full row count")
        shortened = [(item.row_locator, item.column_ordinal) for item in self.shortened_cells]
        if len(shortened) != len(set(shortened)):
            raise ValueError("shortened cell locators must be unique")
        visible_rows = set(self.row_locators)
        visible_columns = set(column_ordinals)
        if any(row not in visible_rows or column not in visible_columns for row, column in shortened):
            raise ValueError("shortened cells must target visible in-bounds cells")
        row_indexes = {locator: index for index, locator in enumerate(self.row_locators)}
        column_indexes = {column.ordinal: index for index, column in enumerate(self.columns)}
        if any(
            self.rows[row_indexes[row]][column_indexes[column]] is None
            for row, column in shortened
        ):
            raise ValueError("null cells cannot be marked as shortened")
        expected_truncated = self.returned_row_count != self.full_row_count or bool(shortened)
        if self.truncated != expected_truncated:
            raise ValueError("truncation flag does not match visible truncation")
        return self


class SQLProducer(_StrictModel):
    kind: Literal["sql"]
    run_id: CanonicalUUID
    action_id: CanonicalUUID
    operation_id: CanonicalUUID
    attempt: PositiveSafeInteger
    sql: NonblankString
    parameters: dict[NonblankString, TypedScalar]
    table_ids: list[CanonicalUUID]
    input_evidence_ids: list[CanonicalUUID]
    constraints: AnalysisConstraints
    environment_manifest_id: CanonicalUUID
    policy_version: NonblankString

    @field_validator("table_ids", "input_evidence_ids")
    @classmethod
    def unique_inputs(cls, value: list[str]) -> list[str]:
        return _unique_strings(value, "producer inputs")


class PythonProducer(_StrictModel):
    kind: Literal["python"]
    run_id: CanonicalUUID
    action_id: CanonicalUUID
    operation_id: CanonicalUUID
    attempt: PositiveSafeInteger
    script_ref: CanonicalUUID
    script_hash: Sha256
    input_evidence_ids: list[CanonicalUUID] = Field(min_length=1)
    action_input_evidence_ids: list[CanonicalUUID] = Field(min_length=1)
    constraints: AnalysisConstraints
    random_seed: Annotated[int, Field(strict=True)] | None
    method_parameters: dict[NonblankString, TypedScalar]
    environment_manifest_id: CanonicalUUID
    policy_version: NonblankString

    @field_validator("input_evidence_ids", "action_input_evidence_ids")
    @classmethod
    def unique_inputs(cls, value: list[str]) -> list[str]:
        return _unique_strings(value, "producer inputs")

    @model_validator(mode="after")
    def call_inputs_are_authorized(self) -> "PythonProducer":
        if not set(self.input_evidence_ids) <= set(self.action_input_evidence_ids):
            raise ValueError("call inputs must be a subset of action inputs")
        return self


class ProfileProducer(_StrictModel):
    kind: Literal["ingestion_profile"]
    dataset_id: CanonicalUUID
    snapshot_id: CanonicalUUID
    table_id: CanonicalUUID
    settings_hash: Sha256
    profile_schema_version: NonblankString
    environment_manifest_id: CanonicalUUID


Producer = Annotated[
    SQLProducer | PythonProducer | ProfileProducer,
    Field(discriminator="kind"),
]


class EvidenceRef(_StrictModel):
    evidence_id: CanonicalUUID
    artifact_id: CanonicalUUID
    content_hash: Sha256
    dependencies: list[SourceDependency] = Field(min_length=1)

    @field_validator("dependencies")
    @classmethod
    def unique_dependencies(cls, value: list[SourceDependency]) -> list[SourceDependency]:
        pairs = [(item.dataset_id, item.snapshot_id) for item in value]
        if len(pairs) != len(set(pairs)):
            raise ValueError("dependencies must be unique")
        return value


class TabularEvidence(_StrictModel):
    evidence_id: CanonicalUUID
    content_hash: Sha256
    artifact: ArtifactRef
    columns: list[EvidenceColumn] = Field(min_length=1)
    row_count: SafeInteger
    preview: TabularPreview
    producer: Producer
    dependencies: list[SourceDependency] = Field(min_length=1)

    @field_validator("dependencies")
    @classmethod
    def unique_dependencies(cls, value: list[SourceDependency]) -> list[SourceDependency]:
        return EvidenceRef.unique_dependencies(value)

    @model_validator(mode="after")
    def validate_evidence(self) -> "TabularEvidence":
        if self.artifact.media_type != "application/vnd.apache.parquet":
            raise ValueError("tabular evidence requires a Parquet artifact")
        if [column.ordinal for column in self.columns] != list(range(len(self.columns))):
            raise ValueError("evidence column ordinals must be contiguous from zero")
        _unique_strings([column.name for column in self.columns], "evidence column names")
        if any(
            preview_column.ordinal >= len(self.columns)
            or preview_column != self.columns[preview_column.ordinal]
            for preview_column in self.preview.columns
        ):
            raise ValueError("preview columns must match full evidence schema entries")
        if self.preview.full_row_count != self.row_count:
            raise ValueError("preview full row count must match evidence row count")
        if self.producer.environment_manifest_id != self.artifact.environment_manifest_id:
            raise ValueError("producer and artifact environments must match")
        if isinstance(self.producer, ProfileProducer):
            own_pair = (self.producer.dataset_id, self.producer.snapshot_id)
            pairs = {(item.dataset_id, item.snapshot_id) for item in self.dependencies}
            if own_pair not in pairs:
                raise ValueError("profile evidence must depend on its own snapshot")
        return self


class SQLInspectedEvidence(TabularEvidence):
    sql_relation: NonblankString


class EvidenceCandidate(_StrictModel):
    candidate_id: RuntimeUUID
    evidence: TabularEvidence
    validation_receipt_id: CanonicalUUID


class ChartArtifact(_StrictModel):
    chart_artifact_id: CanonicalUUID
    artifact: ArtifactRef
    declaration: ChartDeclaration
    producer: PythonProducer
    pixel_width: PositiveSafeInteger
    pixel_height: PositiveSafeInteger
    encoder_version: NonblankString
    normalization_version: NonblankString
    backing_evidence_ids: list[CanonicalUUID] = Field(min_length=1)
    dependencies: list[SourceDependency] = Field(min_length=1)

    @field_validator("backing_evidence_ids")
    @classmethod
    def unique_backing_ids(cls, value: list[str]) -> list[str]:
        return _unique_strings(value, "backing evidence IDs")

    @field_validator("dependencies")
    @classmethod
    def unique_dependencies(cls, value: list[SourceDependency]) -> list[SourceDependency]:
        return EvidenceRef.unique_dependencies(value)

    @model_validator(mode="after")
    def validate_chart(self) -> "ChartArtifact":
        if self.artifact.media_type != "image/png":
            raise ValueError("chart artifacts require PNG artifacts")
        if self.artifact.artifact_id != self.chart_artifact_id:
            raise ValueError("chart artifact identity must match its artifact reference")
        if self.artifact.environment_manifest_id != self.producer.environment_manifest_id:
            raise ValueError("producer and artifact environments must match")
        series_ids = {series.evidence_id for series in self.declaration.series}
        if set(self.backing_evidence_ids) != series_ids:
            raise ValueError("backing evidence IDs must equal chart series evidence IDs")
        if not set(self.backing_evidence_ids) <= set(self.producer.input_evidence_ids):
            raise ValueError("backing evidence must be included in producer call inputs")
        return self
