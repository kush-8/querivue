from django.db import migrations


FOREIGN_KEYS = (
    ("storage_upload", "upload_blob_same_project_fk", "project_id, blob_id", "storage_blob", "project_id, id"),
    ("storage_dataset", "dataset_upload_same_project_fk", "project_id, upload_id", "storage_upload", "project_id, id"),
    ("storage_dataset", "dataset_current_attempt_owner_fk", "project_id, id, current_attempt_id", "storage_datasetattempt", "project_id, dataset_id, id"),
    ("storage_dataset", "dataset_ready_snapshot_owner_fk", "project_id, id, current_attempt_id, ready_snapshot_id", "storage_datasetsnapshot", "project_id, dataset_id, attempt_id, id"),
    ("storage_dataset", "dataset_replacement_same_project_fk", "project_id, replaces_dataset_id", "storage_dataset", "project_id, id"),
    ("storage_datasetattempt", "attempt_dataset_same_project_fk", "project_id, dataset_id", "storage_dataset", "project_id, id"),
    ("storage_datasetattempt", "attempt_settings_same_project_fk", "project_id, settings_record_id", "storage_contentrecord", "project_id, id"),
    ("storage_datasetattempt", "attempt_manifest_dataset_owner_fk", "project_id, dataset_id, manifest_record_id", "storage_contentrecord", "project_id, dataset_id, id"),
    ("storage_datasetsnapshot", "snapshot_dataset_same_project_fk", "project_id, dataset_id", "storage_dataset", "project_id, id"),
    ("storage_datasetsnapshot", "snapshot_attempt_owner_fk", "project_id, dataset_id, attempt_id", "storage_datasetattempt", "project_id, dataset_id, id"),
    ("storage_datasetsnapshot", "snapshot_blob_same_project_fk", "project_id, prepared_blob_id", "storage_blob", "project_id, id"),
    ("storage_datasetsnapshot", "snapshot_catalog_dataset_owner_fk", "project_id, dataset_id, catalog_record_id", "storage_contentrecord", "project_id, dataset_id, id"),
    ("storage_datasetsnapshot", "snapshot_settings_same_project_fk", "project_id, settings_record_id", "storage_contentrecord", "project_id, id"),
    ("storage_datasetsnapshot", "snapshot_profile_dataset_owner_fk", "project_id, dataset_id, profile_record_id", "storage_contentrecord", "project_id, dataset_id, id"),
    ("storage_contentrecord", "content_chat_same_project_fk", "project_id, chat_id", "storage_chat", "project_id, id"),
    ("storage_contentrecord", "content_dataset_same_project_fk", "project_id, dataset_id", "storage_dataset", "project_id, id"),
    ("storage_contentrecord", "content_snapshot_owner_fk", "project_id, dataset_id, snapshot_id", "storage_datasetsnapshot", "project_id, dataset_id, id"),
    ("storage_catalogtable", "catalog_table_snapshot_same_project_fk", "project_id, snapshot_id", "storage_datasetsnapshot", "project_id, id"),
    ("storage_catalogtable", "catalog_table_metadata_same_project_fk", "project_id, metadata_record_id", "storage_contentrecord", "project_id, id"),
    ("storage_catalogcolumn", "catalog_column_table_same_project_fk", "project_id, table_id", "storage_catalogtable", "project_id, id"),
    ("storage_catalogcolumn", "catalog_column_metadata_same_project_fk", "project_id, metadata_record_id", "storage_contentrecord", "project_id, id"),
    ("storage_sourcedependency", "source_record_same_project_fk", "project_id, record_id", "storage_contentrecord", "project_id, id"),
    ("storage_sourcedependency", "source_snapshot_owner_fk", "project_id, dataset_id, snapshot_id", "storage_datasetsnapshot", "project_id, dataset_id, id"),
    ("storage_recorddependency", "record_derived_same_project_fk", "project_id, derived_id", "storage_contentrecord", "project_id, id"),
    ("storage_recorddependency", "record_input_same_project_fk", "project_id, input_id", "storage_contentrecord", "project_id, id"),
)

CHECKS = (
    ("storage_blob", "blob_sha256_lifecycle_valid", "(sha256 IS NULL AND state = 'staging') OR (sha256 IS NOT NULL AND octet_length(sha256) = 32)"),
    ("storage_upload", "upload_expected_sha256_32_bytes", "expected_sha256 IS NULL OR octet_length(expected_sha256) = 32"),
    ("storage_upload", "upload_actual_sha256_32_bytes", "actual_sha256 IS NULL OR octet_length(actual_sha256) = 32"),
    ("storage_datasetattempt", "attempt_settings_digest_32_bytes", "settings_digest IS NULL OR octet_length(settings_digest) = 32"),
    ("storage_datasetattempt", "attempt_manifest_digest_32_bytes", "manifest_digest IS NULL OR octet_length(manifest_digest) = 32"),
    ("storage_datasetsnapshot", "snapshot_catalog_digest_32_bytes", "octet_length(catalog_digest) = 32"),
    ("storage_datasetsnapshot", "snapshot_settings_digest_32_bytes", "octet_length(settings_digest) = 32"),
    ("storage_datasetsnapshot", "snapshot_profile_digest_32_bytes", "octet_length(profile_digest) = 32"),
    ("storage_contentrecord", "content_digest_32_bytes", "octet_length(digest) = 32"),
)


def _add_sql():
    statements = [
        f'ALTER TABLE "{table}" ADD CONSTRAINT "{name}" FOREIGN KEY ({columns}) '
        f'REFERENCES "{parent}" ({parent_columns}) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED'
        for table, name, columns, parent, parent_columns in FOREIGN_KEYS
    ]
    statements.extend(
        f'ALTER TABLE "{table}" ADD CONSTRAINT "{name}" CHECK ({expression})'
        for table, name, expression in CHECKS
    )
    return ";\n".join(statements) + ";"


def _drop_sql():
    constraints = [(table, name) for table, name, _ in CHECKS]
    constraints.extend((table, name) for table, name, *_ in FOREIGN_KEYS)
    return ";\n".join(
        f'ALTER TABLE "{table}" DROP CONSTRAINT "{name}"' for table, name in reversed(constraints)
    ) + ";"


class Migration(migrations.Migration):
    dependencies = [("storage", "0001_initial")]

    operations = [migrations.RunSQL(sql=_add_sql(), reverse_sql=_drop_sql())]
