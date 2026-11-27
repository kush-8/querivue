"""Strict offline import settings and prepared catalog shapes."""

from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator, model_validator

from .artifacts import ArtifactRef, Sha256, SourceDependency
from .evidence import ColumnType
from .values import CanonicalUUID, RuntimeUUID, TypedScalar, UnicodeString


MAX_SAFE_INTEGER = 9007199254740991


def _nonblank(value: str) -> str:
    if not value.strip():
        raise ValueError("expected a nonblank string")
    return value


NonblankString = Annotated[UnicodeString, AfterValidator(_nonblank)]
SafeInteger = Annotated[int, Field(strict=True, ge=0, le=MAX_SAFE_INTEGER)]
PositiveSafeInteger = Annotated[int, Field(strict=True, ge=1, le=MAX_SAFE_INTEGER)]
OneCharacter = Annotated[UnicodeString, Field(min_length=1, max_length=1)]


class _StrictModel(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")


class FileSource(_StrictModel):
    kind: Literal["file"]
    format: Literal["csv", "tsv", "json", "jsonl", "parquet"]


class SQLiteSource(_StrictModel):
    kind: Literal["sqlite"]
    table_name: NonblankString


class WorksheetSource(_StrictModel):
    kind: Literal["worksheet"]
    worksheet_name: NonblankString
    selected_range: NonblankString


SourceDescriptor = Annotated[
    FileSource | SQLiteSource | WorksheetSource,
    Field(discriminator="kind"),
]


class ColumnImportSettings(_StrictModel):
    source_position: SafeInteger
    original_label: UnicodeString | None
    requested_type: ColumnType
    missing_markers: list[UnicodeString]
    decimal_separator: OneCharacter | None
    thousands_separator: OneCharacter | None
    datetime_format: NonblankString | None
    source_timezone: NonblankString | None
    conversion_choice: NonblankString | None

    @field_validator("missing_markers")
    @classmethod
    def unique_markers(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("missing markers must be unique")
        return value

    @model_validator(mode="after")
    def separators_differ(self) -> "ColumnImportSettings":
        if self.decimal_separator is not None and self.decimal_separator == self.thousands_separator:
            raise ValueError("decimal and thousands separators must differ")
        return self


class SourceSelection(_StrictModel):
    source: SourceDescriptor
    header_present: bool
    header_row: PositiveSafeInteger | None
    columns: list[ColumnImportSettings]
    warnings: list[NonblankString] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_selection(self) -> "SourceSelection":
        if self.header_present != (self.header_row is not None):
            raise ValueError("header presence and header row must agree")
        positions = [column.source_position for column in self.columns]
        if len(positions) != len(set(positions)):
            raise ValueError("column source positions must be unique")
        return self


class DelimitedDialect(_StrictModel):
    encoding: Literal["utf-8"]
    delimiter: OneCharacter
    quote: OneCharacter | None
    escape: OneCharacter | None
    strip_bom: bool


SourceFormat = Literal["csv", "tsv", "xlsx", "sqlite", "json", "jsonl", "parquet"]


def _selection_matches_format(selection: SourceSelection, source_format: str) -> bool:
    source = selection.source
    if source_format == "xlsx":
        return isinstance(source, WorksheetSource)
    if source_format == "sqlite":
        return isinstance(source, SQLiteSource)
    return isinstance(source, FileSource) and source.format == source_format


class ImportSettingsProposal(_StrictModel):
    settings_version: NonblankString
    source_format: SourceFormat
    selections: list[SourceSelection] = Field(min_length=1)
    dialect: DelimitedDialect | None

    @model_validator(mode="after")
    def validate_proposal(self) -> "ImportSettingsProposal":
        if self.source_format in {"csv", "tsv"}:
            if self.dialect is None:
                raise ValueError("delimited formats require a dialect")
            if self.source_format == "tsv" and self.dialect.delimiter != "\t":
                raise ValueError("TSV requires a tab delimiter")
        elif self.dialect is not None:
            raise ValueError("non-delimited formats do not accept a dialect")
        if any(not _selection_matches_format(item, self.source_format) for item in self.selections):
            raise ValueError("selection source does not match source format")
        payloads = [item.source.model_dump_json() for item in self.selections]
        if len(payloads) != len(set(payloads)):
            raise ValueError("selected source descriptors must be unique")
        return self


class ImportSettings(ImportSettingsProposal):
    confirmation_id: CanonicalUUID

    @model_validator(mode="after")
    def require_confirmed_columns(self) -> "ImportSettings":
        if any(not selection.columns for selection in self.selections):
            raise ValueError("confirmed selections require column schemas")
        return self

    def to_canonical_dict(self) -> dict:
        """Convert to canonical dict for hashing."""
        return self.model_dump(mode="json", exclude_none=True)

    def canonical_hash(self) -> str:
        """Compute canonical SHA-256 hash of settings."""
        import hashlib
        import json
        data = json.dumps(self.to_canonical_dict(), separators=(",", ":"), sort_keys=True)
        return hashlib.sha256(data.encode("utf-8")).hexdigest()


class ImportPreview(_StrictModel):
    dataset_id: CanonicalUUID
    upload_hash: Sha256
    proposed_settings: ImportSettingsProposal
    warnings: list[NonblankString]
    requires_confirmation: bool


TemporalKind = Literal["date", "time", "timestamp", "timestamptz"]


class TemporalBounds(_StrictModel):
    kind: TemporalKind
    lower: TypedScalar
    upper: TypedScalar

    @model_validator(mode="after")
    def matching_scalar_kinds(self) -> "TemporalBounds":
        if self.lower.kind != self.kind or self.upper.kind != self.kind:
            raise ValueError("temporal bound scalar kinds must match")
        return self


class CandidateKey(_StrictModel):
    column_ids: list[CanonicalUUID] = Field(min_length=1)
    basis: Literal["source_schema", "verified_unique_non_null"]
    verification_ref: CanonicalUUID | None

    @field_validator("column_ids")
    @classmethod
    def unique_columns(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("candidate key columns must be unique")
        return value

    @model_validator(mode="after")
    def require_verification(self) -> "CandidateKey":
        if self.basis == "verified_unique_non_null" and self.verification_ref is None:
            raise ValueError("verified keys require a verification reference")
        if self.basis == "source_schema" and self.verification_ref is not None:
            raise ValueError("source-schema hints cannot carry a verification reference")
        return self


class ColumnCatalog(_StrictModel):
    ordinal: SafeInteger
    source_position: SafeInteger
    column_id: CanonicalUUID
    original_label: UnicodeString | None
    sql_name: NonblankString
    type: ColumnType
    nullable: bool
    null_count: SafeInteger
    settings: ColumnImportSettings
    timezone_provenance_ref: CanonicalUUID | None
    temporal_bounds: TemporalBounds | None

    @model_validator(mode="after")
    def validate_column(self) -> "ColumnCatalog":
        if self.settings.source_position != self.source_position:
            raise ValueError("settings source position must match catalog source position")
        if self.settings.original_label != self.original_label:
            raise ValueError("settings original label must match catalog original label")
        if self.settings.requested_type != self.type:
            raise ValueError("requested type must match catalog column type")
        temporal_tags = {"date", "time", "timestamp", "timestamptz"}
        if self.temporal_bounds is not None:
            if self.type.tag not in temporal_tags or self.temporal_bounds.kind != self.type.tag:
                raise ValueError("temporal bounds must match the temporal column type")
        return self


class TableCatalog(_StrictModel):
    table_id: CanonicalUUID
    dataset_id: CanonicalUUID
    snapshot_id: CanonicalUUID
    ordinal: SafeInteger
    sql_name: NonblankString
    source: SourceDescriptor
    row_count: SafeInteger
    columns: list[ColumnCatalog] = Field(min_length=1)
    warnings: list[NonblankString]
    profile_evidence_ids: list[CanonicalUUID]
    candidate_keys: list[CandidateKey]

    @field_validator("profile_evidence_ids")
    @classmethod
    def unique_profile_ids(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("profile evidence IDs must be unique")
        return value

    @model_validator(mode="after")
    def validate_table(self) -> "TableCatalog":
        if [column.ordinal for column in self.columns] != list(range(len(self.columns))):
            raise ValueError("column ordinals must be contiguous from zero")
        for field_name, values in (
            ("column IDs", [column.column_id for column in self.columns]),
            ("column names", [column.sql_name for column in self.columns]),
            ("source positions", [column.source_position for column in self.columns]),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"{field_name} must be unique")
        if any(column.null_count > self.row_count for column in self.columns):
            raise ValueError("column null count exceeds table row count")
        if any(not column.nullable and column.null_count != 0 for column in self.columns):
            raise ValueError("nonnullable columns cannot report null values")
        column_ids = {column.column_id for column in self.columns}
        if any(not set(key.column_ids) <= column_ids for key in self.candidate_keys):
            raise ValueError("candidate key refers to an unknown column")
        return self


class PreparedSnapshotPayload(_StrictModel):
    dataset_id: CanonicalUUID
    attempt_id: CanonicalUUID
    snapshot_id: CanonicalUUID
    catalog_id: CanonicalUUID
    catalog_hash: Sha256
    table_ids: list[CanonicalUUID] = Field(min_length=1)
    artifact: ArtifactRef
    schema_fingerprint: Sha256
    environment_manifest_id: CanonicalUUID
    source_format: SourceFormat
    settings_hash: Sha256
    dependencies: list[SourceDependency] = Field(min_length=1)

    @field_validator("table_ids")
    @classmethod
    def unique_tables(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("table IDs must be unique")
        return value

    @field_validator("dependencies")
    @classmethod
    def unique_dependencies(cls, value: list[SourceDependency]) -> list[SourceDependency]:
        pairs = [(item.dataset_id, item.snapshot_id) for item in value]
        if len(pairs) != len(set(pairs)):
            raise ValueError("dependencies must be unique")
        return value

    @model_validator(mode="after")
    def validate_snapshot(self) -> "PreparedSnapshotPayload":
        if self.artifact.media_type != "application/x-duckdb":
            raise ValueError("prepared snapshots require DuckDB artifacts")
        if self.artifact.environment_manifest_id != self.environment_manifest_id:
            raise ValueError("artifact environment does not match snapshot environment")
        own_pair = (self.dataset_id, self.snapshot_id)
        if own_pair not in {(item.dataset_id, item.snapshot_id) for item in self.dependencies}:
            raise ValueError("dependencies must include the prepared snapshot")
        return self


class PreparedSnapshot(PreparedSnapshotPayload):
    ready_revision: PositiveSafeInteger


class PreparedCandidate(_StrictModel):
    candidate_id: RuntimeUUID
    snapshot: PreparedSnapshotPayload
    tables: list[TableCatalog] = Field(min_length=1)
    profile_evidence_ids: list[CanonicalUUID]
    validation_receipt_ids: list[CanonicalUUID] = Field(min_length=1)

    @field_validator("profile_evidence_ids", "validation_receipt_ids")
    @classmethod
    def unique_ids(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("references must be unique")
        return value

    @model_validator(mode="after")
    def validate_candidate(self) -> "PreparedCandidate":
        if [table.table_id for table in self.tables] != self.snapshot.table_ids:
            raise ValueError("ordered candidate tables must match snapshot table IDs")
        if [table.ordinal for table in self.tables] != list(range(len(self.tables))):
            raise ValueError("table ordinals must be contiguous from zero")
        if any(
            table.dataset_id != self.snapshot.dataset_id
            or table.snapshot_id != self.snapshot.snapshot_id
            for table in self.tables
        ):
            raise ValueError("candidate tables must belong to the prepared snapshot")
        expected_profiles = {
            evidence_id for table in self.tables for evidence_id in table.profile_evidence_ids
        }
        if set(self.profile_evidence_ids) != expected_profiles:
            raise ValueError("candidate profile evidence IDs must equal the table profile union")
        return self

