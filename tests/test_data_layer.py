"""
tests/test_data_layer.py
-------------------------
Unit & integration tests for the deterministic data layer (utils/data_loader.py).
Tests MUST NOT require Streamlit or Gemini API keys.
"""

from pathlib import Path
import pytest
import pandas as pd

from utils.data_loader import (
    CANONICAL_COLUMNS,
    CATEGORICAL_COLUMNS,
    DATE_COLUMN,
    NUMERIC_COLUMNS,
    XLSX_PATH,
    PARQUET_PATH,
    ensure_parquet_dataset,
    get_connection,
    get_dataset_path,
    get_schema,
    get_schema_description,
    reset_connection,
    validate_dataset,
)


def test_1_canonical_dataset_located():
    """Verify canonical Sales_Dataset_2024.xlsx file exists in data/."""
    assert XLSX_PATH.exists()
    assert XLSX_PATH.name == "Sales_Dataset_2024.xlsx"


def test_2_excel_to_parquet_conversion(tmp_path, monkeypatch):
    """Verify Excel -> Parquet conversion creating sales_dataset.parquet."""
    fake_parquet = tmp_path / "sales_dataset.parquet"
    monkeypatch.setattr("utils.data_loader.PARQUET_PATH", fake_parquet)

    path = ensure_parquet_dataset(force=True)
    assert path.exists()
    assert path == fake_parquet


def test_3_parquet_exists():
    """Verify get_dataset_path returns an existing Parquet file."""
    path = get_dataset_path()
    assert path.exists()
    assert path.suffix == ".parquet"


def test_4_duckdb_connection_initializes():
    """Verify DuckDB connection initializes cleanly and can execute queries."""
    reset_connection()
    conn = get_connection()
    assert conn is not None
    res = conn.execute("SELECT 1").fetchone()
    assert res == (1,)



def test_5_dataset_view_exists():
    """Verify DuckDB view 'dataset' exists and is readable."""
    conn = get_connection()
    res = conn.execute("SELECT COUNT(*) FROM dataset").fetchone()
    assert res is not None
    assert res[0] == 2000


def test_6_schema_returned():
    """Verify get_schema() returns list of dicts with column and type."""
    schema = get_schema()
    assert isinstance(schema, list)
    assert len(schema) == 10
    col_names = [col["column"] for col in schema]
    assert set(col_names) == set(CANONICAL_COLUMNS)


def test_7_canonical_columns_present():
    """Verify all 10 canonical columns are recognized."""
    schema_desc = get_schema_description()
    cols = [c.name for c in schema_desc.columns]
    assert len(cols) == 10
    assert DATE_COLUMN in cols
    for cat in CATEGORICAL_COLUMNS:
        assert cat in cols
    for num in NUMERIC_COLUMNS:
        assert num in cols


def test_8_validation_succeeds():
    """Verify validate_dataset() returns is_valid=True with 0 errors."""
    val = validate_dataset()
    assert val["is_valid"] is True
    assert val["error"] is None
    assert val["row_count"] == 2000
    assert val["column_count"] == 10


def test_9_row_count_correct():
    """Verify row count matches exact 2,000 rows of the canonical dataset."""
    conn = get_connection()
    count = conn.execute("SELECT COUNT(*) FROM dataset").fetchone()[0]
    assert count == 2000


def test_10_date_usable_temporal_type():
    """Verify Date column has a usable TIMESTAMP / date type."""
    conn = get_connection()
    res = conn.execute("SELECT MIN(Date), MAX(Date) FROM dataset").fetchone()
    min_date, max_date = str(res[0]), str(res[1])
    assert "2024-01-01" in min_date
    assert "2024-12-31" in max_date
