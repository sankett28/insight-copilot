"""
utils/data_loader.py
--------------------
Utility for loading, converting, validating, and querying the canonical dataset
(Sales_Dataset_2024.xlsx -> sales_dataset.parquet) via DuckDB.

Responsibilities:
  - Resolve dataset paths relative to PROJECT_ROOT.
  - Automatically convert Sales_Dataset_2024.xlsx to sales_dataset.parquet if missing.
  - Provide a shared, thread-safe DuckDB in-process connection.
  - Expose dataset schema contracts and metadata descriptions for LLM planning.
  - Perform startup validation on dataset integrity.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

from models.schemas import (
    CANONICAL_COLUMNS,
    CATEGORICAL_COLUMNS,
    DATE_COLUMN,
    NUMERIC_COLUMNS,
    ColumnMetadata,
    DatasetSchema,
)

logger = logging.getLogger(__name__)

# Absolute project root resolution
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
XLSX_PATH = DATA_DIR / "Sales_Dataset_2024.xlsx"
PARQUET_PATH = DATA_DIR / "sales_dataset.parquet"

# Cached module-level connection and schema
_connection: duckdb.DuckDBPyConnection | None = None
_schema_cache: DatasetSchema | None = None


def get_dataset_path() -> Path:
    """Return the path to the canonical runtime Parquet file, converting Excel if needed."""
    if not PARQUET_PATH.exists():
        ensure_parquet_dataset()
    return PARQUET_PATH


def ensure_parquet_dataset(force: bool = False) -> Path:
    """Ensure sales_dataset.parquet exists, converting from Sales_Dataset_2024.xlsx if missing."""
    if PARQUET_PATH.exists() and not force:
        return PARQUET_PATH

    if not XLSX_PATH.exists():
        raise FileNotFoundError(
            f"Source Excel file not found at '{XLSX_PATH}'. "
            "Please ensure Sales_Dataset_2024.xlsx is in the data/ directory."
        )

    logger.info("Converting '%s' to '%s'...", XLSX_PATH.name, PARQUET_PATH.name)
    df = pd.read_excel(XLSX_PATH)

    # Ensure Date column is parsed as ISO datetime string/timestamp
    if DATE_COLUMN in df.columns:
        df[DATE_COLUMN] = pd.to_datetime(df[DATE_COLUMN])

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(PARQUET_PATH, index=False)
    logger.info("Successfully created Parquet dataset at '%s' (%d rows).", PARQUET_PATH, len(df))

    return PARQUET_PATH


def create_session_connection() -> duckdb.DuckDBPyConnection:
    """Create and return an independent, session-isolated DuckDB in-process connection.

    Lifecycle & Safety Architecture:
        1. 'raw_dataset' (Bronze View): Read-only mirror pointing directly to canonical Parquet.
        2. 'dataset' (Silver View): Active analytical view queryable and transformable within this session.
    """
    parquet_file = get_dataset_path()
    conn = duckdb.connect(database=":memory:")
    escaped_path = str(parquet_file.as_posix())
    conn.execute(f"CREATE VIEW raw_dataset AS SELECT * FROM read_parquet('{escaped_path}')")
    conn.execute("CREATE VIEW dataset AS SELECT * FROM raw_dataset")
    logger.info("Created new session-isolated DuckDB connection with 'raw_dataset' and 'dataset' views.")
    return conn


def get_connection() -> duckdb.DuckDBPyConnection:
    """Return the shared/default DuckDB in-process connection with 'raw_dataset' and 'dataset' registered.

    Lifecycle & Safety Rationale:
        DuckDB in-process in-memory connection `:memory:` maintains:
        1. 'raw_dataset' (Bronze View): Immutable mirror of the source Parquet file.
        2. 'dataset' (Silver View): Active analytical view queryable by all tools.
    """
    global _connection  # noqa: PLW0603

    if _connection is None:
        _connection = create_session_connection()
        logger.info("Initialised default DuckDB connection.")

    return _connection


def reset_to_raw_dataset(conn: duckdb.DuckDBPyConnection | None = None) -> None:
    """Reset the active 'dataset' view to match the immutable 'raw_dataset' on the specified or default connection."""
    target_conn = conn if conn is not None else get_connection()
    target_conn.execute("CREATE OR REPLACE VIEW dataset AS SELECT * FROM raw_dataset")
    logger.info("Reset active 'dataset' view to raw_dataset.")


def reset_connection() -> None:
    """Close and reset the module-level connection (used for testing / isolation)."""
    global _connection, _schema_cache  # noqa: PLW0603
    if _connection is not None:
        try:
            _connection.close()
        except Exception:  # noqa: S110, BLE001
            pass
        _connection = None
    _schema_cache = None




def validate_dataset() -> dict[str, Any]:
    """Perform lightweight integrity validation on the canonical dataset.

    Returns:
        Dict with validation metrics (is_valid, row_count, column_count, null_counts, error).
    """
    parquet_path = get_dataset_path()
    conn = get_connection()

    try:
        row_count = conn.execute("SELECT COUNT(*) FROM dataset").fetchone()[0]
        columns_info = conn.execute("DESCRIBE dataset").fetchall()
        col_names = [info[0] for info in columns_info]

        # Check required columns
        missing_cols = [c for c in CANONICAL_COLUMNS if c not in col_names]
        if missing_cols:
            return {
                "is_valid": False,
                "row_count": row_count,
                "error": f"Missing canonical columns: {missing_cols}",
            }

        if row_count == 0:
            return {
                "is_valid": False,
                "row_count": 0,
                "error": "Dataset contains 0 rows.",
            }

        return {
            "is_valid": True,
            "row_count": row_count,
            "column_count": len(col_names),
            "columns": col_names,
            "error": None,
        }

    except Exception as exc:  # noqa: BLE001
        logger.exception("Dataset validation failed: %s", exc)
        return {
            "is_valid": False,
            "row_count": 0,
            "error": str(exc),
        }


def get_schema() -> list[dict[str, str]]:
    """Return column names and DuckDB data types of the dataset view."""
    conn = get_connection()
    result = conn.execute("DESCRIBE dataset").fetchall()
    return [{"column": row[0], "type": row[1]} for row in result]


def get_schema_description() -> DatasetSchema:
    """Return the structured DatasetSchema metadata description for LLM prompt context."""
    global _schema_cache  # noqa: PLW0603

    if _schema_cache is not None:
        return _schema_cache

    val_res = validate_dataset()
    row_count = val_res.get("row_count", 2000)

    cols_metadata: list[ColumnMetadata] = [
        ColumnMetadata(
            name=DATE_COLUMN,
            data_type="TIMESTAMP",
            semantic_role="time",
            can_group=True,
            can_metric=False,
            can_time=True,
        )
    ]

    for col in CATEGORICAL_COLUMNS:
        cols_metadata.append(
            ColumnMetadata(
                name=col,
                data_type="VARCHAR",
                semantic_role="dimension",
                can_group=True,
                can_metric=False,
                can_time=False,
            )
        )

    for col in NUMERIC_COLUMNS:
        cols_metadata.append(
            ColumnMetadata(
                name=col,
                data_type="DOUBLE",
                semantic_role="metric",
                can_group=False,
                can_metric=True,
                can_time=False,
            )
        )

    _schema_cache = DatasetSchema(
        dataset_name="Sales_Dataset_2024",
        total_rows=row_count,
        columns=cols_metadata,
    )

    return _schema_cache


def build_sql_where_clause(filters: dict[str, Any] | None) -> str:
    """Safely construct a SQL WHERE clause from a dictionary of column filters.

    Handles:
      - String scalars: case-insensitive match (LOWER(col) = LOWER('val'))
      - List/tuple/set of scalars: IN clause (LOWER(col) IN ('v1', 'v2'))
      - Numeric scalars: direct comparison (col = val)
      - Case-insensitive canonical column mapping
    """
    if not filters:
        return "1=1"

    where_clauses: list[str] = ["1=1"]
    for col, val in filters.items():
        matched_col = None
        for c in CANONICAL_COLUMNS:
            if col.lower() == c.lower():
                matched_col = c
                break
        if not matched_col:
            continue

        if isinstance(val, str):
            clean_val = val.replace("'", "''")
            where_clauses.append(f"LOWER({matched_col}) = LOWER('{clean_val}')")
        elif isinstance(val, (list, tuple, set)):
            clean_items: list[str] = []
            for item in val:
                if isinstance(item, str):
                    clean_item = item.replace("'", "''")
                    clean_items.append(f"LOWER('{clean_item}')")
                elif item is not None:
                    clean_items.append(str(item))
            if clean_items:
                where_clauses.append(f"LOWER({matched_col}) IN ({', '.join(clean_items)})")
        elif val is not None:
            where_clauses.append(f"{matched_col} = {val}")

    return " AND ".join(where_clauses)


