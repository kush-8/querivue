from datetime import timedelta

from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.db.models.deletion import ProtectedError
from django.test import TransactionTestCase
from django.utils import timezone

from storage.models import (
    Blob,
    CatalogTable,
    Chat,
    ContentRecord,
    Dataset,
    DatasetAttempt,
    DatasetSnapshot,
    Project,
    RecordDependency,
    SourceDependency,
    Upload,
)


DIGEST = bytes(range(32))


class StorageSchemaTests(TransactionTestCase):
    def project(self, marker=b"project"):
        return Project.objects.create(name=marker)

    def blob(self, project, key):
        return Blob.objects.create(
            project=project,
            storage_key=key,
            byte_size=17,
            sha256=DIGEST,
            media_type="application/octet-stream",
            state=Blob.State.COMMITTED,
        )

    def upload(self, project, blob, key=b"submission"):
        return Upload.objects.create(
            project=project,
            blob=blob,
            filename=b"source.csv",
            declared_length=17,
            received_length=17,
            actual_sha256=DIGEST,
            submission_key=key,
        )

    def dataset(self, project, suffix="a"):
        blob = self.blob(project, f"objects/{project.id}/{suffix}")
        upload = self.upload(project, blob, f"submission-{suffix}".encode())
        return Dataset.objects.create(project=project, upload=upload)

    def record(self, project, *, dataset=None, payload=b"record", kind="test"):
        return ContentRecord.objects.create(
            project=project,
            dataset=dataset,
            kind=kind,
            schema_version=1,
            canonical_bytes=payload,
            digest=DIGEST,
        )

    def published_graph(self, project, suffix="a"):
        dataset = self.dataset(project, suffix)
        settings = self.record(project, kind="settings")
        manifest = self.record(project, dataset=dataset, kind="manifest")
        catalog = self.record(project, dataset=dataset, kind="catalog")
        profile = self.record(project, dataset=dataset, kind="profile")
        attempt = DatasetAttempt.objects.create(
            project=project,
            dataset=dataset,
            ordinal=1,
            settings_record=settings,
            settings_digest=DIGEST,
            manifest_record=manifest,
            manifest_digest=DIGEST,
            owner_generation=1,
            owner_deadline=timezone.now() + timedelta(minutes=5),
        )
        snapshot = DatasetSnapshot.objects.create(
            project=project,
            dataset=dataset,
            attempt=attempt,
            prepared_blob=dataset.upload.blob,
            catalog_record=catalog,
            catalog_digest=DIGEST,
            settings_record=settings,
            settings_digest=DIGEST,
            profile_record=profile,
            profile_digest=DIGEST,
            published_at=timezone.now(),
        )
        dataset.current_attempt = attempt
        dataset.ready_snapshot = snapshot
        dataset.status = Dataset.Status.READY
        dataset.preparation_phase = Dataset.PreparationPhase.PUBLISHED
        dataset.save(update_fields=("current_attempt", "ready_snapshot", "status", "preparation_phase", "updated_at"))
        return dataset, attempt, snapshot, catalog

    def assert_rejected(self, write):
        with self.assertRaises(IntegrityError), transaction.atomic():
            write()
            with connection.cursor() as cursor:
                cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")

    def test_named_scoped_constraints_are_installed(self):
        expected = {
            "upload_blob_same_project_fk",
            "dataset_current_attempt_owner_fk",
            "dataset_ready_snapshot_owner_fk",
            "snapshot_attempt_owner_fk",
            "content_snapshot_owner_fk",
            "record_input_same_project_fk",
            "blob_sha256_lifecycle_valid",
            "content_digest_32_bytes",
        }
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT conname FROM pg_constraint WHERE connamespace = current_schema()::regnamespace"
            )
            installed = {row[0] for row in cursor.fetchall()}
        self.assertTrue(expected <= installed, expected - installed)

    def test_scoped_integrity_migration_reverses_and_reapplies(self):
        executor = MigrationExecutor(connection)
        executor.migrate([("storage", "0001_initial")])
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT count(*) FROM pg_constraint WHERE conname = 'dataset_ready_snapshot_owner_fk'"
            )
            self.assertEqual(cursor.fetchone()[0], 0)

        executor = MigrationExecutor(connection)
        executor.migrate([("storage", "0002_scoped_integrity")])
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT count(*) FROM pg_constraint WHERE conname = 'dataset_ready_snapshot_owner_fk'"
            )
            self.assertEqual(cursor.fetchone()[0], 1)

    def test_cross_project_ownership_is_rejected_across_graph(self):
        first = self.project(b"first")
        second = self.project(b"second")
        blob = self.blob(first, "objects/first")
        self.assert_rejected(lambda: self.upload(second, blob, b"wrong-blob"))

        upload = self.upload(first, blob)
        self.assert_rejected(lambda: Dataset.objects.create(project=second, upload=upload))

        dataset = Dataset.objects.create(project=first, upload=upload)
        self.assert_rejected(
            lambda: DatasetAttempt.objects.create(
                project=second,
                dataset=dataset,
                ordinal=1,
                owner_generation=1,
                owner_deadline=timezone.now(),
            )
        )

        chat = Chat.objects.create(project=first, title=b"chat")
        self.assert_rejected(
            lambda: ContentRecord.objects.create(
                project=second,
                chat=chat,
                kind="chat",
                schema_version=1,
                canonical_bytes=b"x",
                digest=DIGEST,
            )
        )

        first_record = self.record(first)
        second_record = self.record(second)
        self.assert_rejected(
            lambda: RecordDependency.objects.create(
                project=first, derived=first_record, input=second_record
            )
        )

    def test_ready_pointer_requires_own_current_attempt_snapshot(self):
        project = self.project()
        first, _, first_snapshot, _ = self.published_graph(project, "first")
        second = self.dataset(project, "second")
        second_attempt = DatasetAttempt.objects.create(
            project=project,
            dataset=second,
            ordinal=1,
            owner_generation=1,
            owner_deadline=timezone.now(),
        )

        self.assert_rejected(
            lambda: Dataset.objects.filter(pk=second.pk).update(
                current_attempt=second_attempt,
                ready_snapshot=first_snapshot,
                status=Dataset.Status.READY,
            )
        )
        self.assert_rejected(
            lambda: Dataset.objects.filter(pk=second.pk).update(
                current_attempt=None,
                ready_snapshot=first_snapshot,
            )
        )
        self.assert_rejected(
            lambda: Dataset.objects.filter(pk=second.pk).update(status=Dataset.Status.READY)
        )
        conflicting_attempt = DatasetAttempt.objects.create(
            project=project,
            dataset=first,
            ordinal=2,
            owner_generation=1,
            owner_deadline=timezone.now(),
        )
        self.assert_rejected(
            lambda: Dataset.objects.filter(pk=first.pk).update(
                current_attempt=conflicting_attempt,
                ready_snapshot=first_snapshot,
            )
        )
        first.refresh_from_db()
        self.assertEqual(first.ready_snapshot_id, first_snapshot.id)

    def test_content_snapshot_requires_matching_dataset(self):
        project = self.project()
        dataset, _, snapshot, _ = self.published_graph(project)
        other = self.dataset(project, "other")

        self.assert_rejected(
            lambda: ContentRecord.objects.create(
                project=project,
                snapshot=snapshot,
                kind="invalid",
                schema_version=1,
                canonical_bytes=b"x",
                digest=DIGEST,
            )
        )
        self.assert_rejected(
            lambda: ContentRecord.objects.create(
                project=project,
                dataset=other,
                snapshot=snapshot,
                kind="invalid",
                schema_version=1,
                canonical_bytes=b"x",
                digest=DIGEST,
            )
        )
        self.assertEqual(snapshot.dataset_id, dataset.id)

    def test_source_dependency_snapshot_belongs_to_named_dataset(self):
        project = self.project()
        first, _, _, first_record = self.published_graph(project, "first")
        _, _, second_snapshot, _ = self.published_graph(project, "second")
        self.assert_rejected(
            lambda: SourceDependency.objects.create(
                project=project,
                record=first_record,
                dataset=first,
                snapshot=second_snapshot,
            )
        )

    def test_quota_bounds_keys_and_digest_scope(self):
        project = self.project(b"quota")
        self.assert_rejected(
            lambda: Project.objects.filter(pk=project.pk).update(reserved_raw_bytes=-1)
        )
        self.assert_rejected(
            lambda: Project.objects.filter(pk=project.pk).update(
                reserved_raw_bytes=52_428_800, retained_raw_bytes=1
            )
        )

        blob = self.blob(project, "objects/unique")
        self.upload(project, blob, b"same-key")
        self.assert_rejected(lambda: self.upload(project, blob, b"same-key"))
        other = self.project(b"other")
        self.assert_rejected(lambda: self.blob(other, "objects/unique"))

        first = self.record(project, payload=b"same")
        second = self.record(other, payload=b"same")
        self.assertEqual(first.digest, second.digest)

    def test_digest_lifecycle_and_safe_counter_ranges(self):
        project = self.project()
        self.assert_rejected(
            lambda: Blob.objects.create(
                project=project,
                storage_key="objects/missing-digest",
                byte_size=0,
                sha256=None,
                media_type="application/octet-stream",
                state=Blob.State.COMMITTED,
            )
        )
        self.assert_rejected(
            lambda: Blob.objects.create(
                project=project,
                storage_key="objects/zero-generation",
                byte_size=0,
                sha256=None,
                media_type="application/octet-stream",
                state=Blob.State.STAGING,
                staging_owner=project.id,
                staging_generation=0,
            )
        )
        self.assert_rejected(
            lambda: Project.objects.filter(pk=project.pk).update(
                revision=9_007_199_254_740_992
            )
        )

    def test_binary_payloads_round_trip_exactly(self):
        payload = "Unicode ₹ 😀\x00 1.2300 +05:30 -0".encode("utf-8")
        project = Project.objects.create(name=payload)
        chat = Chat.objects.create(project=project, title=payload)
        blob = self.blob(project, "objects/binary")
        upload = Upload.objects.create(
            project=project,
            blob=blob,
            filename=payload,
            declared_length=0,
            submission_key=payload,
        )
        record = self.record(project, payload=payload)

        project.refresh_from_db()
        chat.refresh_from_db()
        upload.refresh_from_db()
        record.refresh_from_db()
        self.assertEqual(bytes(project.name), payload)
        self.assertEqual(bytes(chat.title), payload)
        self.assertEqual(bytes(upload.filename), payload)
        self.assertEqual(bytes(record.canonical_bytes), payload)

    def test_restrictive_deletion_and_catalog_project_scope(self):
        project = self.project()
        _, _, snapshot, metadata = self.published_graph(project)
        table = CatalogTable.objects.create(
            project=project,
            snapshot=snapshot,
            ordinal=0,
            sql_name="source_table",
            metadata_record=metadata,
        )
        with self.assertRaises(ProtectedError):
            project.delete()

        other = self.project(b"other")
        other_metadata = self.record(other)
        self.assert_rejected(
            lambda: CatalogTable.objects.create(
                project=project,
                snapshot=snapshot,
                ordinal=1,
                sql_name="wrong_metadata",
                metadata_record=other_metadata,
            )
        )
        self.assertTrue(CatalogTable.objects.filter(pk=table.pk).exists())
