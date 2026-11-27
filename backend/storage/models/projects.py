from django.db import models
from django.db.models import F, Q

from .base import TimestampedUUIDModel


class Project(TimestampedUUIDModel):
    class Lifecycle(models.TextChoices):
        LIVE = "live"
        DELETING = "deleting"
        DELETED = "deleted"

    name = models.BinaryField()
    lifecycle = models.CharField(max_length=8, choices=Lifecycle, default=Lifecycle.LIVE)
    revision = models.BigIntegerField(default=0)
    reserved_raw_bytes = models.BigIntegerField(default=0)
    retained_raw_bytes = models.BigIntegerField(default=0)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(lifecycle__in=("live", "deleting", "deleted")), name="project_lifecycle_valid"),
            models.CheckConstraint(condition=Q(revision__range=(0, 9_007_199_254_740_991)), name="project_revision_safe"),
            models.CheckConstraint(
                condition=Q(reserved_raw_bytes__gte=0) & Q(retained_raw_bytes__gte=0),
                name="project_quota_counters_nonnegative",
            ),
            models.CheckConstraint(
                condition=Q(reserved_raw_bytes__lte=52_428_800 - F("retained_raw_bytes")),
                name="project_raw_quota_bounded",
            ),
        ]


class Chat(TimestampedUUIDModel):
    class Lifecycle(models.TextChoices):
        LIVE = "live"
        DELETING = "deleting"
        DELETED = "deleted"

    project = models.ForeignKey(Project, on_delete=models.PROTECT, related_name="chats")
    title = models.BinaryField()
    lifecycle = models.CharField(max_length=8, choices=Lifecycle, default=Lifecycle.LIVE)
    revision = models.BigIntegerField(default=0)
    next_visibility_sequence = models.BigIntegerField(default=0)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(lifecycle__in=("live", "deleting", "deleted")), name="chat_lifecycle_valid"),
            models.CheckConstraint(
                condition=Q(revision__range=(0, 9_007_199_254_740_991))
                & Q(next_visibility_sequence__range=(0, 9_007_199_254_740_991)),
                name="chat_counters_safe",
            ),
            models.UniqueConstraint(fields=("project", "id"), name="chat_project_identity"),
        ]


class Blob(TimestampedUUIDModel):
    class StorageClass(models.TextChoices):
        PRIVATE = "private"

    class State(models.TextChoices):
        STAGING = "staging"
        COMMITTED = "committed"
        ERASED = "erased"

    project = models.ForeignKey(Project, on_delete=models.PROTECT, related_name="blobs")
    storage_key = models.TextField()
    storage_class = models.CharField(max_length=8, choices=StorageClass, default=StorageClass.PRIVATE)
    byte_size = models.BigIntegerField()
    sha256 = models.BinaryField(max_length=32, null=True, blank=True)
    media_type = models.TextField()
    state = models.CharField(max_length=9, choices=State, default=State.STAGING)
    revision = models.BigIntegerField(default=0)
    staging_owner = models.UUIDField(null=True, blank=True)
    staging_generation = models.BigIntegerField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("storage_key",), name="blob_storage_key_unique"),
            models.UniqueConstraint(fields=("project", "id"), name="blob_project_identity"),
            models.CheckConstraint(condition=Q(storage_class="private"), name="blob_storage_class_valid"),
            models.CheckConstraint(condition=Q(state__in=("staging", "committed", "erased")), name="blob_state_valid"),
            models.CheckConstraint(condition=Q(revision__range=(0, 9_007_199_254_740_991)), name="blob_revision_safe"),
            models.CheckConstraint(condition=Q(byte_size__range=(0, 9_007_199_254_740_991)), name="blob_byte_size_safe"),
            models.CheckConstraint(
                condition=(
                    Q(state="staging", staging_owner__isnull=False, staging_generation__isnull=False)
                    | ~Q(state="staging")
                    & Q(staging_owner__isnull=True, staging_generation__isnull=True)
                ),
                name="blob_staging_lease_appropriate",
            ),
            models.CheckConstraint(
                condition=Q(staging_generation__isnull=True)
                | Q(staging_generation__range=(1, 9_007_199_254_740_991)),
                name="blob_staging_generation_positive",
            ),
        ]


class Upload(TimestampedUUIDModel):
    class RetentionState(models.TextChoices):
        RETAINED = "retained"
        RELEASED = "released"

    class QuotaState(models.TextChoices):
        RESERVED = "reserved"
        RETAINED = "retained"
        RELEASED = "released"

    project = models.ForeignKey(Project, on_delete=models.PROTECT, related_name="uploads")
    blob = models.ForeignKey(Blob, on_delete=models.PROTECT, related_name="uploads")
    filename = models.BinaryField()
    declared_length = models.BigIntegerField()
    received_length = models.BigIntegerField(default=0)
    expected_sha256 = models.BinaryField(max_length=32, null=True, blank=True)
    actual_sha256 = models.BinaryField(max_length=32, null=True, blank=True)
    submission_key = models.BinaryField()
    retention_state = models.CharField(max_length=8, choices=RetentionState, default=RetentionState.RETAINED)
    quota_state = models.CharField(max_length=8, choices=QuotaState, default=QuotaState.RESERVED)
    revision = models.BigIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("project", "submission_key"), name="upload_project_submission_key_unique"),
            models.UniqueConstraint(fields=("project", "id"), name="upload_project_identity"),
            models.CheckConstraint(
                condition=Q(declared_length__range=(0, 9_007_199_254_740_991))
                & Q(received_length__range=(0, 9_007_199_254_740_991)),
                name="upload_lengths_safe",
            ),
            models.CheckConstraint(condition=Q(retention_state__in=("retained", "released")), name="upload_retention_state_valid"),
            models.CheckConstraint(condition=Q(quota_state__in=("reserved", "retained", "released")), name="upload_quota_state_valid"),
            models.CheckConstraint(condition=Q(revision__range=(0, 9_007_199_254_740_991)), name="upload_revision_safe"),
        ]
