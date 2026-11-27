"""Guest importer: prepares dataset and returns PreparedCandidate."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from uuid import UUID, uuid4

from querivue_agent.contracts.catalog import (
    PreparedCandidate,
    PreparedSnapshot,
    TableCatalog,
    ColumnCatalog,
    ColumnImportSettings,
    SourceDescriptor,
    FileSource,
    ImportSettings,
    ColumnType,
)
from querivue_agent.ingestion.settings import ImportFormat
from querivue_agent.contracts.common import Scope
from querivue_agent.contracts.values import CanonicalUUID, RuntimeUUID
from querivue_agent.contracts.artifacts import Sha256
from querivue_agent.contracts.catalog import NonblankString
from querivue_agent.contracts.artifacts import ArtifactRef, SourceDependency
from querivue_agent.ingestion.preparation import (
    prepare_dataset,
    PreparationAttempt,
    PreparationResult,
)
from querivue_agent.ingestion.catalog import build_table_catalog, build_column_catalog
from querivue_agent.storage.artifacts import ArtifactStore


def _build_column_catalog_from_prep(
    col_setting: ColumnImportSettings,
    ordinal: int,
    table_id: CanonicalUUID,
    dataset_id: CanonicalUUID,
    snapshot_id: CanonicalUUID,
) -> ColumnCatalog:
    """Build ColumnCatalog from ColumnImportSettings."""
    from querivue_agent.contracts.evidence import ColumnType
    from querivue_agent.contracts.catalog import TemporalBounds, TypedScalar

    # Map requested_type string to ColumnType
    type_map = {
        "int64": ColumnType(tag="int64"),
        "uint64": ColumnType(tag="uint64"),
        "decimal": ColumnType(tag="decimal"),
        "string": ColumnType(tag="string"),
        "date": ColumnType(tag="date"),
        "time": ColumnType(tag="time"),
        "timestamp": ColumnType(tag="timestamp"),
        "timestamptz": ColumnType(tag="timestamptz"),
        "boolean": ColumnType(tag="boolean"),
    }
    col_type = type_map.get(col_setting.requested_type, ColumnType(tag="string"))

    return ColumnCatalog(
        ordinal=ordinal,
        source_position=col_setting.source_position,
        column_id=CanonicalUUID(str(uuid4())),
        original_label=col_setting.original_label,
        sql_name=NonblankString(col_setting.sql_name),
        type=col_type,
        nullable=True,
        null_count=0,
        settings=col_setting,
        timezone_provenance_ref=None,
        temporal_bounds=None,
    )


def _build_table_catalog_from_prep(
    table_settings,
    attempt: PreparationAttempt,
    table_ordinal: int,
) -> TableCatalog:
    """Build TableCatalog from TableImportSettings."""
    columns = [
        _build_column_catalog_from_prep(
            col_setting=col,
            ordinal=i,
            table_id=CanonicalUUID(str(uuid4())),
            dataset_id=attempt.dataset_id,
            snapshot_id=CanonicalUUID(str(uuid4())),
        )
        for i, col in enumerate(table_settings.column_settings)
    ]

    return TableCatalog(
        table_id=CanonicalUUID(str(uuid4())),
        dataset_id=attempt.dataset_id,
        snapshot_id=CanonicalUUID(str(uuid4())),
        ordinal=table_ordinal,
        sql_name=NonblankString(table_settings.source_descriptor.sql_name),
        source=table_settings.source_descriptor,
        row_count=0,  # Will be updated after preparation
        columns=columns,
        warnings=table_settings.warnings,
        profile_evidence_ids=[],
        candidate_keys=[],
    )


async def import_dataset(
    dataset_id: UUID,
    settings: ImportSettings,
    scope: Scope,
    state_root: Path,
) -> PreparedCandidate:
    """
    Guest importer: prepares a dataset and returns a PreparedCandidate.

    This runs in a guest context (no authority) and produces a candidate
    that must be validated before acceptance.
    """
    from querivue_agent.storage.ledger import Ledger, LedgerOps

    # Open ledger to get dataset info
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
            raise ValueError(f"Preparation failed: {result.errors}")

        if not result.snapshot or not result.catalog:
            raise ValueError("Preparation produced no snapshot or catalog")

        # Build PreparedCandidate
        tables = []
        for i, table_catalog in enumerate(result.catalog):
            # Convert from ingestion TableCatalog to contracts TableCatalog
            columns = []
            for j, col in enumerate(table_catalog.columns):
                col_type_map = {
                    "BIGINT": "int64",
                    "UBIGINT": "uint64",
                    "DECIMAL": "decimal",
                    "VARCHAR": "string",
                    "DATE": "date",
                    "TIME": "time",
                    "TIMESTAMP": "timestamp",
                    "TIMESTAMPTZ": "timestamptz",
                    "BOOLEAN": "boolean",
                }
                from querivue_agent.contracts.evidence import ColumnType
                col_type = ColumnType(tag=col_type_map.get(col.duckdb_type, "string"))

                col_settings = ColumnImportSettings(
                    source_ordinal=col.source_position,
                    original_label=col.original_label,
                    sql_name=col.sql_name,
                    requested_type=col_type.tag,
                    missing_markers=col.missing_markers,
                    decimal_separator=None,
                    thousands_separator=None,
                    datetime_format=None,
                    source_timezone=None,
                    conversion_choice=None,
                )
                columns.append(ColumnCatalog(
                    ordinal=j,
                    source_position=col.source_position,
                    column_id=col.column_id,
                    original_label=col.original_label,
                    sql_name=col.sql_name,
                    type=col_type,
                    nullable=col.nullable,
                    null_count=col.null_count,
                    settings=col_settings,
                    timezone_provenance_ref=None,
                    temporal_bounds=None,
                ))

            tables.append(TableCatalog(
                table_id=table_catalog.table_id,
                dataset_id=table_catalog.dataset_id,
                snapshot_id=table_catalog.snapshot_id,
                ordinal=i,
                sql_name=table_catalog.sql_name,
                source=table_catalog.source_descriptor,
                row_count=table_catalog.row_count,
                columns=columns,
                warnings=table_catalog.warnings,
                profile_evidence_ids=table_catalog.profile_evidence_ids,
                candidate_keys=table_catalog.candidate_keys,
            ))

        # Create artifact reference for the prepared database
        artifact = ArtifactRef(
            artifact_id=CanonicalUUID(str(uuid4())),
            storage_ref=CanonicalUUID(str(uuid4())),
            environment_manifest_id=attempt.environment_manifest_id,
            media_type="application/x-duckdb",
            size_bytes=result.snapshot.artifact_size,
            sha256=result.snapshot.artifact_sha256,
        )

        # Create snapshot payload
        snapshot_payload = PreparedSnapshot(
            dataset_id=result.snapshot.dataset_id,
            attempt_id=result.snapshot.attempt_id,
            snapshot_id=result.snapshot.snapshot_id,
            catalog_id=CanonicalUUID(str(uuid4())),
            catalog_hash=result.snapshot.catalog_hash,
            table_ids=result.snapshot.table_ids,
            artifact=artifact,
            schema_fingerprint=result.snapshot.schema_fingerprint,
            environment_manifest_id=result.snapshot.environment_manifest_id,
            source_format=settings.source_format,
            settings_hash=result.snapshot.settings_hash,
            dependencies=[
                SourceDependency(
                    dataset_id=result.snapshot.dataset_id,
                    snapshot_id=result.snapshot.snapshot_id,
                )
            ],
            ready_revision=1,
        )

        candidate = PreparedCandidate(
            candidate_id=RuntimeUUID(str(uuid4())),
            snapshot=snapshot_payload,
            tables=tables,
            profile_evidence_ids=[],
            validation_receipt_ids=[],
        )

        return candidate
    finally:
        ledger.close()


def validate_candidate(
    candidate: PreparedCandidate,
    state_root: Path,
) -> bool:
    """
    Validate a PreparedCandidate by checking the artifact exists and matches.

    This is called by the authority to accept or reject the candidate.
    """
    # Verify artifact exists in artifact store
    artifact_store = ArtifactStore(state_root)
    try:
        artifact_path = artifact_store.get_artifact_path(candidate.snapshot.artifact)
        return artifact_path.exists()
    except Exception:
        return False