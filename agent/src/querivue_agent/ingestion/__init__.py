"""Data ingestion pipeline for prepared datasets."""

from .settings import ImportSettings, ImportFormat, SourceDescriptor, ColumnImportSettings, TableImportSettings
from .catalog import (
    TableCatalog,
    ColumnCatalog,
    generate_sql_name,
    generate_column_sql_names,
)
from .inspection import (
    inspect_csv,
    inspect_tsv,
    inspect_json,
    inspect_jsonl,
    inspect_parquet,
    inspect_excel,
    inspect_sqlite,
    InspectionResult,
)
from .preparation import (
    prepare_dataset,
    PreparationAttempt,
    PreparedSnapshot,
    PreparationError,
)
from .controller import (
    inspect_upload_controller,
    prepare_dataset_controller,
)

__all__ = [
    "ImportSettings",
    "ImportFormat",
    "SourceDescriptor",
    "ColumnImportSettings",
    "TableImportSettings",
    "TableCatalog",
    "ColumnCatalog",
    "generate_sql_name",
    "generate_column_sql_names",
    "inspect_csv",
    "inspect_tsv",
    "inspect_json",
    "inspect_jsonl",
    "inspect_parquet",
    "inspect_excel",
    "inspect_sqlite",
    "InspectionResult",
    "prepare_dataset",
    "PreparationAttempt",
    "PreparedSnapshot",
    "PreparationError",
    "inspect_upload_controller",
    "prepare_dataset_controller",
]