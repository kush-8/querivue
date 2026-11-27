from django.db import models
from django.db.models import Q

from .base import UUIDModel
from .content import ContentRecord
from .datasets import DatasetSnapshot
from .projects import Project


class CatalogTable(UUIDModel):
    project = models.ForeignKey(Project, on_delete=models.PROTECT, related_name="catalog_tables")
    snapshot = models.ForeignKey(DatasetSnapshot, on_delete=models.PROTECT, related_name="catalog_tables")
    ordinal = models.BigIntegerField()
    sql_name = models.TextField()
    metadata_record = models.ForeignKey(ContentRecord, on_delete=models.PROTECT, related_name="catalog_tables")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("snapshot", "ordinal"), name="catalog_table_snapshot_ordinal_unique"),
            models.UniqueConstraint(fields=("snapshot", "sql_name"), name="catalog_table_snapshot_sql_name_unique"),
            models.UniqueConstraint(fields=("project", "id"), name="catalog_table_project_identity"),
            models.CheckConstraint(condition=Q(ordinal__range=(0, 9_007_199_254_740_991)), name="catalog_table_ordinal_safe"),
        ]


class CatalogColumn(UUIDModel):
    project = models.ForeignKey(Project, on_delete=models.PROTECT, related_name="catalog_columns")
    table = models.ForeignKey(CatalogTable, on_delete=models.PROTECT, related_name="columns")
    ordinal = models.BigIntegerField()
    sql_name = models.TextField()
    metadata_record = models.ForeignKey(ContentRecord, on_delete=models.PROTECT, related_name="catalog_columns")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("table", "ordinal"), name="catalog_column_table_ordinal_unique"),
            models.UniqueConstraint(fields=("table", "sql_name"), name="catalog_column_table_sql_name_unique"),
            models.CheckConstraint(condition=Q(ordinal__range=(0, 9_007_199_254_740_991)), name="catalog_column_ordinal_safe"),
        ]
