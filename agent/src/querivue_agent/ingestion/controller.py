"""Ingestion controller: bridges CLI/storage with inspection and preparation logic."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from uuid import UUID, uuid4

from querivue_agent.contracts.catalog import ImportPreview, ImportSettingsProposal
from querivue_agent.contracts.common import Scope
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
    ColumnImportSettings,
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
            # Map inferred type to requested type
            type_map = {
                "int64": "int64",
                "uint64": "uint64",
                "decimal": "decimal",
                "string": "string",
                "date": "date",
                "time": "time",
                "timestamp": "timestamp",
                "timestamptz": "timestamptz",
                "boolean": "boolean",
                "unknown": "string",
            }
            requested_type = type_map.get(col.inferred_type, "string")

            column_settings.append(ColumnImportSettings(
                source_ordinal=col.ordinal,
                original_label=col.original_label,
                sql_name=sql_name,
                requested_type=requested_type,
                missing_markers=[],
                decimal_separator=None,
                thousands_separator=None,
                datetime_format=None,
                source_timezone=None,
                conversion_choice=None,
            ))

        # Determine source descriptor
        source_desc = SourceDescriptor(
            source_id=table.source_descriptor.source_id,
            format=inspection.format,
            descriptor=table.source_descriptor.descriptor,
            sql_name=table.source_descriptor.sql_name,
            header_row=0 if table.source_descriptor.format in ("csv", "tsv") else None,
            has_header=True,
        )

        selections.append(TableImportSettings(
            source_descriptor=source_desc,
            column_settings=column_settings,
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

        # Create preparation attempt
        attempt_id = CanonicalUUID(str(uuid4()))
        attempt = PreparationAttempt(
            dataset_id=CanonicalUUID(str(dataset_id)),
            attempt_id=attempt_id,
            attempt_number=dataset.get("attempt_number", 1),
            settings_hash=settings.canonical_hash(),
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
        with tempfile.TemporaryDirectory(dir=state_root) as tmp:
            work_path = Path(tmp)
            result = prepare_dataset(upload_file, settings, attempt, work_path)

        if result.errors:
            ops.update_preparation_attempt(str(attempt_id), phase="failed")
            raise ValueError(f"Preparation failed: {result.errors}")

        # Update attempt status
        ops.update_preparation_attempt(
            str(attempt_id),
            phase="validated",
            candidate_ref=str(result.snapshot.snapshot_id) if result.snapshot else None,
        )

        # Return prepared candidate info
        return {
            "status": "prepared",
            "dataset_id": str(dataset_id),
            "attempt_id": str(attempt_id),
            "snapshot_id": str(result.snapshot.snapshot_id) if result.snapshot else None,
            "tables": len(result.catalog),
        }
    finally:
        ledger.close()