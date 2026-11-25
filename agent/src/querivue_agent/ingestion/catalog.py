"""Table and column catalog for prepared datasets."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Literal
from uuid import UUID, uuid4

from querivue_agent.contracts.common import SafeCount, NonblankString, UnicodeString
from querivue_agent.contracts.values import CanonicalUUID


@dataclass(frozen=True)
class ColumnCatalog:
    """Catalog entry for a single column."""
    column_id: CanonicalUUID
    ordinal: SafeCount  # Zero-based position in table
    source_position: SafeCount  # Original column position in source
    original_label: UnicodeString | None
    sql_name: NonblankString
    duckdb_type: NonblankString  # Exact DuckDB type
    nullable: bool
    null_count: SafeCount
    confirmed_type: Literal["auto", "int64", "uint64", "decimal", "string", "date", "time", "timestamp", "timestamptz", "boolean"]
    missing_markers: list[str] = field(default_factory=list)
    decimal_separator: str | None = None
    thousands_separator: str | None = None
    date_format: str | None = None
    time_format: str | None = None
    datetime_format: str | None = None
    source_timezone: str | None = None
    conversion_choice: str | None = None
    temporal_bound_kind: Literal["none", "date", "time", "timestamp", "timestamptz"] = "none"
    temporal_lower: str | None = None  # Native typed value as string
    temporal_upper: str | None = None
    source_key_hint: bool = False
    key_check: Literal["not_checked", "verified_unique_non_null", "not_unique_or_null"] = "not_checked"


@dataclass(frozen=True)
class TableCatalog:
    """Catalog entry for a single table."""
    table_id: CanonicalUUID
    dataset_id: CanonicalUUID
    snapshot_id: CanonicalUUID
    ordinal: SafeCount  # Selection order within dataset
    sql_name: NonblankString  # e.g., "t_001"
    source_descriptor: str  # Untrusted metadata: worksheet name + range, SQLite table name, etc.
    row_count: SafeCount
    columns: list[ColumnCatalog] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ProfileSchema:
    """Immutable profile evidence schema."""
    table_id: CanonicalUUID
    snapshot_id: CanonicalUUID
    row_kind: Literal["table_summary", "column_profile"]
    profile_schema_version: int = 1
    column_id: CanonicalUUID | None = None
    column_ordinal: SafeCount | None = None
    row_count: SafeCount | None = None
    null_count: SafeCount | None = None
    bound_kind: Literal["none", "date", "time", "timestamp", "timestamptz"] = "none"
    date_lower: str | None = None
    date_upper: str | None = None
    time_lower: str | None = None
    time_upper: str | None = None
    timestamp_lower: str | None = None
    timestamp_upper: str | None = None
    timestamptz_lower: str | None = None
    timestamptz_upper: str | None = None
    source_key_hint: bool | None = None
    key_check: Literal["not_checked", "verified_unique_non_null", "not_unique_or_null"] | None = None


def _normalize_label(label: str) -> str:
    """Normalize a label for SQL name generation."""
    # NFKC normalize
    normalized = unicodedata.normalize("NFKC", label)
    # Lowercase
    normalized = normalized.lower()
    # Replace non-ASCII letters/digits/underscore with underscore
    normalized = re.sub(r"[^a-z0-9_]+", "_", normalized)
    # Trim underscores
    normalized = normalized.strip("_")
    return normalized


def generate_sql_name(base_label: str | None, position: int, existing_names: set[str], original_labels_seen: set[str] | None = None) -> NonblankString:
    """Generate a unique SQL name for a column or table."""
    if base_label:
        base = _normalize_label(base_label)
    else:
        base = f"column_{position + 1}"

    if base and base[0].isdigit():
        base = f"c_{base}"

    # Limit to 63 characters before collision suffix
    if len(base) > 63:
        base = base[:63]

    # Reserve natural base names first
    if base not in existing_names:
        existing_names.add(base)
        return NonblankString(base)

    # Find smallest unused suffix
    # Skip suffixes that correspond to original labels we've seen
    suffix = 2
    if original_labels_seen is None:
        original_labels_seen = set()

    while True:
        candidate = f"{base}_{suffix}"
        if len(candidate) <= 63 and candidate not in existing_names:
            existing_names.add(candidate)
            return NonblankString(candidate)
        suffix += 1


def generate_table_sql_names(count: int) -> list[NonblankString]:
    """Generate table SQL names in order: t_001, t_002, ..."""
    return [NonblankString(f"t_{i+1:03d}") for i in range(count)]


def generate_column_sql_names(
    original_labels: list[UnicodeString | None],
    existing_names: set[str] | None = None,
) -> list[NonblankString]:
    """Generate SQL names for columns preserving collision rules."""
    if existing_names is None:
        existing_names = set()

    # Track original labels we've seen to avoid suffix collisions
    original_labels_seen = set()

    names = []
    for i, label in enumerate(original_labels):
        name = generate_sql_name(label, i, existing_names, original_labels_seen)
        names.append(name)
        # Track normalized base names from original labels
        if label:
            original_labels_seen.add(label.lower().replace(" ", "_").replace("-", "_"))
    return names


def resolve_duckdb_type(
    requested: Literal["auto", "int64", "uint64", "decimal", "string", "date", "time", "timestamp", "timestamptz", "boolean"],
    sample_values: list[str],
) -> NonblankString:
    """Resolve the exact DuckDB type for a column."""
    type_map = {
        "int64": "BIGINT",
        "uint64": "UBIGINT",
        "decimal": "DECIMAL(38,10)",
        "string": "VARCHAR",
        "date": "DATE",
        "time": "TIME",
        "timestamp": "TIMESTAMP",
        "timestamptz": "TIMESTAMPTZ",
        "boolean": "BOOLEAN",
    }

    if requested != "auto":
        return NonblankString(type_map.get(requested, "VARCHAR"))

    # Auto-detect from sample values
    if not sample_values:
        return NonblankString("VARCHAR")

    # Check if all values look like booleans
    boolean_pattern = re.compile(r"^(true|false)$", re.IGNORECASE)
    if all(boolean_pattern.match(v) for v in sample_values):
        return NonblankString("BOOLEAN")

    # Check if all values look like integers
    int_pattern = re.compile(r"^-?\d+$")
    if all(int_pattern.match(v) for v in sample_values):
        return NonblankString("BIGINT")

    # Check if all values look like decimals
    decimal_pattern = re.compile(r"^-?\d+\.\d+$")
    if all(decimal_pattern.match(v) or int_pattern.match(v) for v in sample_values):
        return NonblankString("DECIMAL(38,10)")

    # Check if all values look like dates (YYYY-MM-DD)
    date_pattern = re.compile(r"^\d{4}-\d{2}-\d{2}$")
    if all(date_pattern.match(v) for v in sample_values):
        return NonblankString("DATE")

    # Check if all values look like timestamps
    timestamp_pattern = re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}")
    if all(timestamp_pattern.match(v) for v in sample_values):
        return NonblankString("TIMESTAMP")

    return NonblankString("VARCHAR")


def build_table_catalog(
    table_id: CanonicalUUID,
    dataset_id: CanonicalUUID,
    snapshot_id: CanonicalUUID,
    ordinal: int,
    sql_name: NonblankString,
    source_descriptor: str,
    row_count: int,
    column_catalogs: list[ColumnCatalog],
    warnings: list[str] | None = None,
) -> TableCatalog:
    """Build a table catalog entry."""
    return TableCatalog(
        table_id=table_id,
        dataset_id=dataset_id,
        snapshot_id=snapshot_id,
        ordinal=SafeCount(ordinal),
        sql_name=sql_name,
        source_descriptor=source_descriptor,
        row_count=SafeCount(row_count),
        columns=column_catalogs,
        warnings=warnings or [],
    )


def build_column_catalog(
    column_id: CanonicalUUID,
    ordinal: int,
    source_position: int,
    original_label: UnicodeString | None,
    sql_name: NonblankString,
    duckdb_type: NonblankString,
    nullable: bool,
    null_count: int,
    confirmed_type: Literal["auto", "int64", "uint64", "decimal", "string", "date", "time", "timestamp", "timestamptz", "boolean"],
    missing_markers: list[str] | None = None,
    decimal_separator: str | None = None,
    thousands_separator: str | None = None,
    date_format: str | None = None,
    time_format: str | None = None,
    datetime_format: str | None = None,
    source_timezone: str | None = None,
    conversion_choice: str | None = None,
    temporal_bound_kind: Literal["none", "date", "time", "timestamp", "timestamptz"] = "none",
    temporal_lower: str | None = None,
    temporal_upper: str | None = None,
    source_key_hint: bool = False,
    key_check: Literal["not_checked", "verified_unique_non_null", "not_unique_or_null"] = "not_checked",
) -> ColumnCatalog:
    """Build a column catalog entry."""
    return ColumnCatalog(
        column_id=column_id,
        ordinal=SafeCount(ordinal),
        source_position=SafeCount(source_position),
        original_label=original_label,
        sql_name=sql_name,
        duckdb_type=duckdb_type,
        nullable=nullable,
        null_count=SafeCount(null_count),
        confirmed_type=confirmed_type,
        missing_markers=missing_markers or [],
        decimal_separator=decimal_separator,
        thousands_separator=thousands_separator,
        date_format=date_format,
        time_format=time_format,
        datetime_format=datetime_format,
        source_timezone=source_timezone,
        conversion_choice=conversion_choice,
        temporal_bound_kind=temporal_bound_kind,
        temporal_lower=temporal_lower,
        temporal_upper=temporal_upper,
        source_key_hint=source_key_hint,
        key_check=key_check,
    )