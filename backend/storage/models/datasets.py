from django.db import models
from django.db.models import Q

from .base import TimestampedUUIDModel
from .projects import Blob, Project, Upload


class Dataset(TimestampedUUIDModel):
    class Status(models.TextChoices):
        PROCESSING = "processing"
        READY = "ready"
        FAILED = "failed"

    class Lifecycle(models.TextChoices):
        LIVE = "live"
        DELETING = "deleting"
        DELETED = "deleted"

    class PreparationPhase(models.TextChoices):
        PENDING = "pending"
        PREPARING = "preparing"
        PUBLISHED = "published"
        FAILED = "failed"

    project = models.ForeignKey(Project, on_delete=models.PROTECT, related_name="datasets")
    upload = models.ForeignKey(Upload, on_delete=models.PROTECT, related_name="datasets")
    status = models.CharField(max_length=10, choices=Status, default=Status.PROCESSING)
    lifecycle = models.CharField(max_length=8, choices=Lifecycle, default=Lifecycle.LIVE)
    preparation_phase = models.CharField(max_length=10, choices=PreparationPhase, default=PreparationPhase.PENDING)
    revision = models.BigIntegerField(default=0)
    current_attempt = models.ForeignKey(
        "DatasetAttempt", on_delete=models.PROTECT, related_name="current_for_datasets", null=True, blank=True
    )
    ready_snapshot = models.ForeignKey(
        "DatasetSnapshot", on_delete=models.PROTECT, related_name="ready_for_datasets", null=True, blank=True
    )
    replaces_dataset = models.ForeignKey(
        "self", on_delete=models.PROTECT, related_name="replacement_datasets", null=True, blank=True
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("project", "id"), name="dataset_project_identity"),
            models.CheckConstraint(condition=Q(status__in=("processing", "ready", "failed")), name="dataset_status_valid"),
            models.CheckConstraint(condition=Q(lifecycle__in=("live", "deleting", "deleted")), name="dataset_lifecycle_valid"),
            models.CheckConstraint(
                condition=Q(preparation_phase__in=("pending", "preparing", "published", "failed")),
                name="dataset_preparation_phase_valid",
            ),
            models.CheckConstraint(condition=Q(revision__range=(0, 9_007_199_254_740_991)), name="dataset_revision_safe"),
            models.CheckConstraint(
                condition=Q(ready_snapshot__isnull=True) | Q(current_attempt__isnull=False),
                name="dataset_ready_requires_current_attempt",
            ),
            models.CheckConstraint(
                condition=~Q(status="ready") | Q(ready_snapshot__isnull=False),
                name="dataset_ready_status_has_snapshot",
            ),
            models.CheckConstraint(
                condition=Q(replaces_dataset__isnull=True) | ~Q(replaces_dataset=models.F("id")),
                name="dataset_replacement_not_self",
            ),
        ]


class DatasetAttempt(TimestampedUUIDModel):
    class Lifecycle(models.TextChoices):
        ACTIVE = "active"
        SUCCEEDED = "succeeded"
        FAILED = "failed"
        ABANDONED = "abandoned"

    project = models.ForeignKey(Project, on_delete=models.PROTECT, related_name="dataset_attempts")
    dataset = models.ForeignKey(Dataset, on_delete=models.PROTECT, related_name="attempts")
    ordinal = models.BigIntegerField()
    settings_record = models.ForeignKey(
        "ContentRecord", on_delete=models.PROTECT, related_name="attempt_settings", null=True, blank=True
    )
    settings_digest = models.BinaryField(max_length=32, null=True, blank=True)
    manifest_record = models.ForeignKey(
        "ContentRecord", on_delete=models.PROTECT, related_name="attempt_manifests", null=True, blank=True
    )
    manifest_digest = models.BinaryField(max_length=32, null=True, blank=True)
    owner_generation = models.BigIntegerField()
    owner_deadline = models.DateTimeField()
    lifecycle = models.CharField(max_length=9, choices=Lifecycle, default=Lifecycle.ACTIVE)
    revision = models.BigIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("dataset", "ordinal"), name="attempt_dataset_ordinal_unique"),
            models.UniqueConstraint(fields=("project", "dataset", "id"), name="attempt_project_dataset_identity"),
            models.UniqueConstraint(fields=("dataset", "id"), name="attempt_dataset_identity"),
            models.CheckConstraint(condition=Q(ordinal__range=(1, 9_007_199_254_740_991)), name="attempt_ordinal_positive"),
            models.CheckConstraint(condition=Q(owner_generation__range=(1, 9_007_199_254_740_991)), name="attempt_owner_generation_positive"),
            models.CheckConstraint(condition=Q(lifecycle__in=("active", "succeeded", "failed", "abandoned")), name="attempt_lifecycle_valid"),
            models.CheckConstraint(condition=Q(revision__range=(0, 9_007_199_254_740_991)), name="attempt_revision_safe"),
            models.CheckConstraint(
                condition=(Q(settings_record__isnull=True, settings_digest__isnull=True)
                           | Q(settings_record__isnull=False, settings_digest__isnull=False)),
                name="attempt_settings_pin_complete",
            ),
            models.CheckConstraint(
                condition=(Q(manifest_record__isnull=True, manifest_digest__isnull=True)
                           | Q(manifest_record__isnull=False, manifest_digest__isnull=False)),
                name="attempt_manifest_pin_complete",
            ),
        ]


class DatasetSnapshot(TimestampedUUIDModel):
    project = models.ForeignKey(Project, on_delete=models.PROTECT, related_name="dataset_snapshots")
    dataset = models.OneToOneField(Dataset, on_delete=models.PROTECT, related_name="published_snapshot")
    attempt = models.ForeignKey(DatasetAttempt, on_delete=models.PROTECT, related_name="published_snapshots")
    prepared_blob = models.ForeignKey(Blob, on_delete=models.PROTECT, related_name="dataset_snapshots")
    catalog_record = models.ForeignKey("ContentRecord", on_delete=models.PROTECT, related_name="snapshot_catalogs")
    catalog_digest = models.BinaryField(max_length=32)
    settings_record = models.ForeignKey("ContentRecord", on_delete=models.PROTECT, related_name="snapshot_settings")
    settings_digest = models.BinaryField(max_length=32)
    profile_record = models.ForeignKey("ContentRecord", on_delete=models.PROTECT, related_name="snapshot_profiles")
    profile_digest = models.BinaryField(max_length=32)
    published_at = models.DateTimeField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("project", "dataset", "id"), name="snapshot_project_dataset_identity"),
            models.UniqueConstraint(fields=("dataset", "attempt", "id"), name="snapshot_dataset_attempt_identity"),
            models.UniqueConstraint(
                fields=("project", "dataset", "attempt", "id"),
                name="snapshot_project_dataset_attempt_identity",
            ),
            models.UniqueConstraint(fields=("project", "id"), name="snapshot_project_identity"),
        ]
