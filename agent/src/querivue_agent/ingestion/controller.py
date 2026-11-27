"""Ingestion controller: bridges CLI/storage with inspection and preparation logic."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from uuid import UUID, uuid4

from querivue_agent.contracts.catalog import ImportPreview, ImportSettingsProposal, SourceSelection, DelimitedDialect, ColumnImportSettings as CatalogColumnImportSettings, FileSource, SourceFormat
from querivue_agent.contracts.evidence import ColumnType, StringColumn, Int64Column, BooleanColumn, DateColumn, TimeColumn, TimestampColumn, TimestamptzColumn, Uint64Column, DecimalColumn
from querivue_agent.contracts.common import Scope, NonblankString, SafeCount
from querivue_agent.contracts.artifacts import StagedArtifact, ArtifactRef
from querivue_agent.contracts.values import CanonicalUUID
from querivue_agent.storage.artifacts import ArtifactStore
from querivue_agent.ingestion.inspection import (
    inspect_upload,
    InspectionResult,
    TablePreview,
    ColumnPreview,
)
from querivue_agent.ingestion.catalog import (
    generate_table_sql_names,
    generate_column_sql_names,
    resolve_duckdb_type,
)
from querivue_agent.ingestion.settings import (
    ImportSettings,
    SourceDescriptor,
    ColumnImportSettings as SettingsColumnImportSettings,
    TableImportSettings,
    ImportFormat,
)


def _inspection_to_import_preview(
    inspection: InspectionResult,
    dataset_id: CanonicalUUID,
    upload_hash: str,
) -> ImportPreview:
    """Convert InspectionResult to strict ImportPreview with proposed settings."""

    if not inspection.tables:
        raise ValueError("No tables found in inspection")

    selections = []
    for table_idx, table in enumerate(inspection.tables):
        # Generate column SQL names preserving collision rules
        original_labels = [col.original_label for col in table.columns]
        sql_names = generate_column_sql_names(original_labels)

        column_settings = []
        for col_idx, (col, sql_name) in enumerate(zip(table.columns, sql_names)):
            # Map inferred type to requested type (ColumnType discriminated union)
            type_map = {
                "int64": Int64Column(tag="int64"),
                "uint64": Uint64Column(tag="uint64"),
                "decimal": DecimalColumn(tag="decimal", precision=38, scale=10),  # Default precision/scale
                "string": StringColumn(tag="string"),
                "date": DateColumn(tag="date"),
                "time": TimeColumn(tag="time"),
                "timestamp": TimestampColumn(tag="timestamp"),
                "timestamptz": TimestamptzColumn(tag="timestamptz"),
                "boolean": BooleanColumn(tag="boolean"),
                "unknown": StringColumn(tag="string"),
            }
            requested_type = type_map.get(col.inferred_type, StringColumn(tag="string"))

            column_settings.append(CatalogColumnImportSettings(
                source_position=col.ordinal,
                original_label=col.original_label,
                requested_type=requested_type,
                missing_markers=[],
                decimal_separator=None,
                thousands_separator=None,
                datetime_format=None,
                source_timezone=None,
                conversion_choice=None,
            ))

        # Determine source descriptor (using Pydantic FileSource)
        file_source = FileSource(
            kind="file",
            format=inspection.format,  # type: ignore[arg-type]
        )

        selections.append(SourceSelection(
            source=file_source,
            header_present=table.source_descriptor.has_header,
            header_row=table.source_descriptor.header_row if table.source_descriptor.has_header else None,
            columns=column_settings,
            warnings=table.warnings,
        ))

    # Build dialect for delimited formats
    dialect = None
    if inspection.format in ("csv", "tsv"):
        from querivue_agent.contracts.catalog import DelimitedDialect
        dialect = DelimitedDialect(
            encoding=inspection.encoding,
            delimiter=inspection.delimiter or ("," if inspection.format == "csv" else "\t"),
            quote='"',
            escape=None,
            strip_bom=inspection.has_bom,
        )

    proposed_settings = ImportSettingsProposal(
        settings_version="1",
        source_format=inspection.format,
        selections=selections,
        dialect=dialect,
    )

    return ImportPreview(
        dataset_id=dataset_id,
        upload_hash=upload_hash,
        proposed_settings=proposed_settings,
        warnings=inspection.warnings,
        requires_confirmation=True,
    )


async def inspect_upload_controller(
    upload_id: UUID,
    scope: Scope,
    state_root: Path,
) -> ImportPreview:
    """
    Inspect a staged upload and return ImportPreview.

    This is the controller function that bridges the CLI/storage layer
    with the inspection logic.
    """
    # Initialize artifact store
    artifact_store = ArtifactStore(state_root)

    # Get the staged artifact from the artifact store
    # For now, we'll create a temporary file path from the upload_id
    # In a real implementation, this would look up the staged artifact by ID
    artifacts_dir = state_root / "artifacts"

    # Find the staged artifact file
    # The upload_id maps to a storage_ref in the artifacts directory
    artifact_file = artifacts_dir / str(upload_id)
    if not artifact_file.exists():
        # Try quarantine directory
        quarantine_file = state_root / "quarantine" / f"{upload_id}.tmp"
        if quarantine_file.exists():
            artifact_file = quarantine_file
        else:
            raise ValueError(f"Staged artifact not found for upload_id: {upload_id}")

    # Create a temporary copy for inspection (inspection reads the file)
    with tempfile.NamedTemporaryFile(suffix=f".{inspection_format_from_upload(upload_id)}", delete=False) as tmp:
        tmp_path = Path(tmp.name)
        # Copy the artifact to temp location
        import shutil
        shutil.copy2(artifact_file, tmp_path)

    try:
        # Detect format from extension or content
        format_hint = _detect_format_from_path(artifact_file)

        # Run inspection
        inspection = inspect_upload(tmp_path, format_hint)

        # Convert to ImportPreview
        dataset_id = CanonicalUUID(str(uuid4()))
        preview = _inspection_to_import_preview(inspection, dataset_id, inspection.upload_sha256 or "")

        return preview
    finally:
        tmp_path.unlink(missing_ok=True)


def inspection_format_from_upload(upload_id: UUID) -> str:
    """Get format hint from upload ID metadata (placeholder)."""
    return "csv"


def _detect_format_from_path(path: Path) -> ImportFormat | None:
    """Detect import format from file extension."""
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return "csv"
    elif suffix == ".tsv":
        return "tsv"
    elif suffix == ".json":
        return "json"
    elif suffix == ".jsonl":
        return "jsonl"
    elif suffix == ".parquet":
        return "parquet"
    elif suffix in (".xlsx", ".xls"):
        return "excel"
    elif suffix in (".sqlite", ".db"):
        return "sqlite"
    return None


async def prepare_dataset_controller(
    dataset_id: UUID,
    settings: ImportSettings,
    scope: Scope,
    state_root: Path,
) -> dict:
    """
    Prepare a dataset from confirmed settings.

    This is the controller function that bridges the CLI/storage layer
    with the preparation logic.
    """
    from querivue_agent.ingestion.preparation import prepare_dataset, PreparationAttempt, PreparationResult
    from querivue_agent.contracts.catalog import PreparedCandidate
    from querivue_agent.storage.ledger import Ledger, LedgerOps
    from querivue_agent.ingestion.settings import (
        ImportSettings as SettingsImportSettings,
        SourceDescriptor,
        ColumnImportSettings as SettingsColumnImportSettings,
        TableImportSettings,
        ImportFormat,
    )

    # Open ledger
    ledger_path = state_root / "ledger.sqlite"
    ledger = Ledger.open(ledger_path)
    ops = LedgerOps(ledger)

    try:
        # Get dataset from ledger
        dataset = ops.get_dataset(str(dataset_id))
        if not dataset:
            raise ValueError(f"Dataset {dataset_id} not found")

        # Get upload reference
        upload_ref = dataset["upload_ref"]
        upload_hash = dataset["upload_hash"]

        # Convert Pydantic ImportSettings to dataclass ImportSettings for preparation
        selections = settings.selections
        dialect = settings.dialect

        # Build table settings from selections
        table_settings = []
        for selection in selections:
            # Map Pydantic SourceDescriptor to dataclass SourceDescriptor
            source = selection.source
            if hasattr(source, 'format'):
                # FileSource
                source_format = source.format
                descriptor = "data.csv"  # Default descriptor
            else:
                source_format = "csv"
                descriptor = "data.csv"

            source_descriptor = SourceDescriptor(
                source_id=CanonicalUUID("00000000-0000-0000-0000-000000000000"),
                format=source_format,  # type: ignore
                descriptor=descriptor,
                has_header=selection.header_present,
                header_row=selection.header_row,
            )

            column_settings = []
            for col in selection.columns:
                column_settings.append(SettingsColumnImportSettings(
                    source_ordinal=col.source_position,
                    original_label=col.original_label,
                    sql_name=NonblankString(col.sql_name) if hasattr(col, 'sql_name') and col.sql_name else NonblankString(f"col_{col.source_position}"),
                    requested_type=col.requested_type.tag,
                    missing_markers=col.missing_markers,
                    decimal_separator=col.decimal_separator,
                    thousands_separator=col.thousands_separator,
                    date_format=None,
                    time_format=None,
                    datetime_format=col.datetime_format,
                    source_timezone=col.source_timezone,
                    conversion_choice=col.conversion_choice,
                ))

            table_settings.append(TableImportSettings(
                source_descriptor=source_descriptor,
                column_settings=column_settings,
                warnings=selection.warnings,
            ))

        # Create dataclass ImportSettings
        settings_for_prep = SettingsImportSettings(
            settings_version=int(settings.settings_version),
            source_format=settings.source_format,  # type: ignore
            table_settings=table_settings,
            delimiter=dialect.delimiter if dialect else ",",
            encoding=dialect.encoding if dialect else "utf-8",
            quote_char=dialect.quote if dialect else '"',
            escape_char=dialect.escape if dialect else None,
            allow_quoted_nulls=False,
            json_array_of_objects=True,
            excel_keep_links=False,
            sqlite_selected_tables=[],
        )

        # Create preparation attempt
        attempt_id = CanonicalUUID(str(uuid4()))
        attempt = PreparationAttempt(
            dataset_id=CanonicalUUID(str(dataset_id)),
            attempt_id=attempt_id,
            attempt_number=dataset.get("attempt_number", 1),
            settings_hash=settings_for_prep.canonical_hash(),
            upload_hash=upload_hash,
            expected_owner_generation=1,
            phase="preparing",
            environment_manifest_id=CanonicalUUID("00000000-0000-0000-0000-000000000000"),
            deadline="2099-12-31T23:59:59.999999Z",
        )

        # Record preparation attempt
        ops.create_preparation_attempt(
            attempt_id=str(attempt_id),
            dataset_id=str(dataset_id),
            attempt_number=attempt.attempt_number,
            settings_json=json.dumps(settings.to_canonical_dict()),
            settings_hash=attempt.settings_hash,
            upload_ref=upload_ref,
            upload_hash=upload_hash,
            owner_generation=1,
            deadline=attempt.deadline,
        )

        # Find the upload artifact
        artifacts_dir = state_root / "artifacts"
        upload_file = artifacts_dir / upload_ref
        if not upload_file.exists():
            raise ValueError(f"Upload artifact not found: {upload_ref}")

        # Run preparation
        # Use a work directory that persists for artifact registration
        work_path = state_root / "work_prep"
        work_path.mkdir(exist_ok=True)

        try:
            result = prepare_dataset(upload_file, settings_for_prep, attempt, work_path)

            if result.errors:
                ops.update_preparation_attempt(str(attempt_id), phase="failed")
                raise ValueError(f"Preparation failed: {result.errors}")

            # Register the prepared database as an immutable artifact
            db_path = work_path / "prepared.duckdb"
            if not db_path.exists():
                raise ValueError("Prepared database not found")

            # Stage the artifact
            artifact_store = ArtifactStore(state_root)
            with open(db_path, "rb") as f:
                staged = artifact_store.stage(
                    f,
                    scope,
                    byte_limit=100 * 1024 * 1024,  # 100MB limit
                )

            # Verify the artifact
            artifact_store.verify(staged, result.snapshot.artifact_sha256)

            # Update attempt with publication reference
            ops.update_preparation_attempt(
                str(attempt_id),
                phase="validated",
                candidate_ref=str(result.snapshot.snapshot_id) if result.snapshot else None,
                publication_ref=staged.artifact.storage_ref,
            )

            # Return prepared candidate info
            return {
                "status": "prepared",
                "dataset_id": str(dataset_id),
                "attempt_id": str(attempt_id),
                "snapshot_id": str(result.snapshot.snapshot_id) if result.snapshot else None,
                "tables": len(result.catalog),
                "artifact_ref": staged.artifact.storage_ref,
                "artifact_sha256": staged.artifact.sha256,
            }
        finally:
            # Clean up work directory
            import shutil
            if work_path.exists():
                shutil.rmtree(work_path)
    finally:
        ledger.close()