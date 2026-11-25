"""Import settings and format definitions."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, UTC
from pathlib import Path
from typing import Any, Literal
from uuid import UUID, uuid4

from querivue_agent.contracts.common import SafeCount, TimestampText, NonblankString
from querivue_agent.contracts.values import CanonicalUUID, UnicodeString
from querivue_agent.contracts.artifacts import Sha256


ImportFormat = Literal["csv", "tsv", "json", "jsonl", "parquet", "excel", "sqlite"]


@dataclass(frozen=True)
class SourceDescriptor:
    """Describes a source table/worksheet to import."""
    source_id: CanonicalUUID
    format: ImportFormat
    descriptor: str  # Worksheet name, range, SQLite table name, etc.
    header_row: SafeCount | None = None
    has_header: bool = True
    selected_range: str | None = None  # e.g., "A1:D100" for Excel


@dataclass(frozen=True)
class ColumnImportSettings:
    """Per-column import settings."""
    source_ordinal: SafeCount
    original_label: UnicodeString | None
    sql_name: NonblankString
    requested_type: Literal["auto", "int64", "uint64", "decimal", "string", "date", "time", "timestamp", "timestamptz", "boolean"]
    missing_markers: list[str] = field(default_factory=list)
    decimal_separator: str | None = None
    thousands_separator: str | None = None
    date_format: str | None = None
    time_format: str | None = None
    datetime_format: str | None = None
    source_timezone: str | None = None
    conversion_choice: str | None = None  # For currency/percentage/ambiguous numeric


@dataclass(frozen=True)
class TableImportSettings:
    """Per-table import settings."""
    source_descriptor: SourceDescriptor
    column_settings: list[ColumnImportSettings] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ImportSettings:
    """Complete import settings for an upload."""
    settings_version: int = 1
    source_format: ImportFormat = "csv"
    table_settings: list[TableImportSettings] = field(default_factory=list)

    # CSV/TSV specific
    delimiter: str | None = None
    encoding: str = "utf-8"
    quote_char: str = '"'
    escape_char: str | None = None
    allow_quoted_nulls: bool = False

    # JSON/JSONL specific
    json_array_of_objects: bool = True  # True for JSON array, False for JSONL

    # Excel specific
    excel_keep_links: bool = False

    # SQLite specific
    sqlite_selected_tables: list[str] = field(default_factory=list)

    def canonical_hash(self) -> Sha256:
        """Compute canonical SHA-256 hash of settings."""
        import hashlib
        import json
        data = json.dumps(self.to_canonical_dict(), separators=(",", ":"), sort_keys=True)
        return hashlib.sha256(data.encode("utf-8")).hexdigest()

    def to_canonical_dict(self) -> dict[str, Any]:
        """Convert to canonical dict for hashing."""
        return {
            "settings_version": self.settings_version,
            "source_format": self.source_format,
            "table_settings": [self._table_to_dict(t) for t in self.table_settings],
            "delimiter": self.delimiter,
            "encoding": self.encoding,
            "quote_char": self.quote_char,
            "escape_char": self.escape_char,
            "allow_quoted_nulls": self.allow_quoted_nulls,
            "json_array_of_objects": self.json_array_of_objects,
            "excel_keep_links": self.excel_keep_links,
            "sqlite_selected_tables": self.sqlite_selected_tables,
        }

    def _table_to_dict(self, table: TableImportSettings) -> dict[str, Any]:
        return {
            "source_descriptor": {
                "source_id": str(table.source_descriptor.source_id),
                "format": table.source_descriptor.format,
                "descriptor": table.source_descriptor.descriptor,
                "header_row": table.source_descriptor.header_row,
                "has_header": table.source_descriptor.has_header,
                "selected_range": table.source_descriptor.selected_range,
            },
            "column_settings": [self._column_to_dict(c) for c in table.column_settings],
            "warnings": table.warnings,
        }

    def _column_to_dict(self, col: ColumnImportSettings) -> dict[str, Any]:
        return {
            "source_ordinal": col.source_ordinal,
            "original_label": col.original_label,
            "sql_name": col.sql_name,
            "requested_type": col.requested_type,
            "missing_markers": col.missing_markers,
            "decimal_separator": col.decimal_separator,
            "thousands_separator": col.thousands_separator,
            "date_format": col.date_format,
            "time_format": col.time_format,
            "datetime_format": col.datetime_format,
            "source_timezone": col.source_timezone,
            "conversion_choice": col.conversion_choice,
        }


@dataclass(frozen=True)
class PreparationAttempt:
    """A preparation attempt for a dataset."""
    dataset_id: CanonicalUUID
    attempt_id: CanonicalUUID
    attempt_number: int
    settings_hash: Sha256
    upload_hash: Sha256
    expected_owner_generation: int
    phase: Literal["staged", "inspecting", "awaiting_confirmation", "preparing", "validated", "transferred", "ready", "failed"]
    environment_manifest_id: CanonicalUUID | None
    physical_incarnation: str | None = None
    limits: dict[str, Any] = field(default_factory=dict)
    deadline: TimestampText | None = None
    diagnostic_ref: CanonicalUUID | None = None
    candidate_ref: CanonicalUUID | None = None
    publication_ref: CanonicalUUID | None = None
    created_at: TimestampText = field(default_factory=lambda: datetime.now(UTC).isoformat().replace("+00:00", "Z"))
    updated_at: TimestampText = field(default_factory=lambda: datetime.now(UTC).isoformat().replace("+00:00", "Z"))


@dataclass(frozen=True)
class PreparedSnapshot:
    """A prepared dataset snapshot."""
    dataset_id: CanonicalUUID
    attempt_id: CanonicalUUID
    snapshot_id: CanonicalUUID
    catalog_hash: Sha256
    table_ids: list[CanonicalUUID]
    artifact_ref: str  # Reference to DuckDB file artifact
    artifact_size: int
    artifact_sha256: Sha256
    schema_fingerprint: str
    environment_manifest_id: CanonicalUUID
    dependencies: list[CanonicalUUID] = field(default_factory=list)
    ready_revision: int = 0
    created_at: TimestampText = field(default_factory=lambda: datetime.now(UTC).isoformat().replace("+00:00", "Z"))


class PreparationError(Exception):
    """Error during preparation."""
    def __init__(self, message: str, phase: str, recoverable: bool = False):
        super().__init__(message)
        self.phase = phase
        self.recoverable = recoverable