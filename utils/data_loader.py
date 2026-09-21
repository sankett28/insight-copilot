"""
utils/data_loader.py
--------------------
Utility for loading datasets into DuckDB.

Responsibility:
  - Accept a file path (CSV, Parquet, or Excel) and register it as a DuckDB
    table/view so all tools can query it via the same in-process connection.
  - Validate that the file exists and has a supported format.
  - Provide a lightweight schema-inspection helper so the planner can
    (optionally) be told what columns are available.

Current status: INTERFACE DEFINED — not yet fully implemented.
Full implementation follows once the dataset is confirmed.
"""

from __future__ import annotations

import logging
from enum import Enum
from pathlib import Path

logger = logging.getLogger(__name__)


class DataFormat(str, Enum):
    """Supported dataset file formats."""

    CSV = "csv"
    PARQUET = "parquet"
    EXCEL = "xlsx"


_EXTENSION_MAP: dict[str, DataFormat] = {
    ".csv": DataFormat.CSV,
    ".parquet": DataFormat.PARQUET,
    ".xlsx": DataFormat.EXCEL,
    ".xls": DataFormat.EXCEL,
}

# Module-level DuckDB connection (lazily initialised).
_connection = None
_loaded_table: str | None = None


def load_dataset(file_path: str | Path, table_name: str = "dataset") -> str:
    """Load a dataset file into DuckDB and return the table name.

    Args:
        file_path:  Path to the dataset file.
        table_name: Name to register the table as in DuckDB.

    Returns:
        The registered table name (same as *table_name*).

    Raises:
        FileNotFoundError: If *file_path* does not exist.
        ValueError:        If the file format is not supported.
        NotImplementedError: Until the full implementation is added.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Dataset file not found: {path}")

    fmt = _EXTENSION_MAP.get(path.suffix.lower())
    if fmt is None:
        raise ValueError(
            f"Unsupported file format '{path.suffix}'. "
            f"Supported formats: {list(_EXTENSION_MAP.keys())}"
        )

    raise NotImplementedError(
        "data_loader.load_dataset not yet implemented. "
        "Will use DuckDB to register the file as a view."
    )


def get_schema(table_name: str = "dataset") -> list[dict[str, str]]:
    """Return the column names and types of a registered DuckDB table.

    Args:
        table_name: Name of the DuckDB table/view.

    Returns:
        List of ``{"column": str, "type": str}`` dicts.

    Raises:
        NotImplementedError: Until the data layer is ready.
    """
    raise NotImplementedError("data_loader.get_schema not yet implemented.")


def get_connection():
    """Return the module-level DuckDB connection, creating it if needed.

    Returns:
        A ``duckdb.DuckDBPyConnection`` instance.

    Raises:
        NotImplementedError: Until the data layer is ready.
    """
    raise NotImplementedError("data_loader.get_connection not yet implemented.")
