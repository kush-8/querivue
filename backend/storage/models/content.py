from django.db import models
from django.db.models import Q

from .base import UUIDModel
from .datasets import Dataset, DatasetSnapshot
from .projects import Chat, Project


class ContentRecord(UUIDModel):
    class Lifecycle(models.TextChoices):
        LIVE = "live"
        ERASED = "erased"

    project = models.ForeignKey(Project, on_delete=models.PROTECT, related_name="content_records")
    chat = models.ForeignKey(Chat, on_delete=models.PROTECT, related_name="content_records", null=True, blank=True)
    dataset = models.ForeignKey(Dataset, on_delete=models.PROTECT, related_name="content_records", null=True, blank=True)
    snapshot = models.ForeignKey(
        DatasetSnapshot, on_delete=models.PROTECT, related_name="content_records", null=True, blank=True
    )
    kind = models.CharField(max_length=64)
    schema_version = models.PositiveIntegerField()
    canonical_bytes = models.BinaryField(null=True, blank=True)
    digest = models.BinaryField(max_length=32, db_index=True)
    lifecycle = models.CharField(max_length=6, choices=Lifecycle, default=Lifecycle.LIVE)
    revision = models.BigIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("project", "id"), name="content_project_identity"),
            models.UniqueConstraint(fields=("project", "dataset", "id"), name="content_project_dataset_identity"),
            models.UniqueConstraint(fields=("project", "dataset", "snapshot", "id"), name="content_owner_identity"),
            models.CheckConstraint(condition=Q(lifecycle__in=("live", "erased")), name="content_lifecycle_valid"),
            models.CheckConstraint(condition=Q(schema_version__gte=1), name="content_schema_version_positive"),
            models.CheckConstraint(condition=Q(revision__range=(0, 9_007_199_254_740_991)), name="content_revision_safe"),
            models.CheckConstraint(
                condition=(Q(lifecycle="live", canonical_bytes__isnull=False)
                           | Q(lifecycle="erased", canonical_bytes__isnull=True)),
                name="content_bytes_match_lifecycle",
            ),
            models.CheckConstraint(
                condition=Q(snapshot__isnull=True) | Q(dataset__isnull=False),
                name="content_snapshot_requires_dataset",
            ),
            models.CheckConstraint(
                condition=Q(chat__isnull=True) | Q(dataset__isnull=True, snapshot__isnull=True),
                name="content_chat_owner_exclusive",
            ),
        ]


class SourceDependency(UUIDModel):
    project = models.ForeignKey(Project, on_delete=models.PROTECT, related_name="source_dependencies")
    record = models.ForeignKey(ContentRecord, on_delete=models.PROTECT, related_name="source_dependencies")
    dataset = models.ForeignKey(Dataset, on_delete=models.PROTECT, related_name="source_dependencies")
    snapshot = models.ForeignKey(DatasetSnapshot, on_delete=models.PROTECT, related_name="source_dependencies")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("record", "dataset", "snapshot"), name="source_dependency_unique"),
        ]
        indexes = [
            models.Index(fields=("dataset", "snapshot", "record"), name="source_dependency_reverse_idx"),
        ]


class RecordDependency(UUIDModel):
    project = models.ForeignKey(Project, on_delete=models.PROTECT, related_name="record_dependencies")
    derived = models.ForeignKey(ContentRecord, on_delete=models.PROTECT, related_name="derived_dependencies")
    input = models.ForeignKey(ContentRecord, on_delete=models.PROTECT, related_name="input_dependencies")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("derived", "input"), name="record_dependency_unique"),
            models.CheckConstraint(condition=~Q(derived=models.F("input")), name="record_dependency_not_self"),
        ]
