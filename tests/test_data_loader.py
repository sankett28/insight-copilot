"""
tests/test_data_loader.py
--------------------------
Unit tests for data loader: path resolution, Parquet conversion, dataset validation,
and schema metadata generation.
"""

import pytest
from pathlib import Path
from utils.data_loader import (
    get_dataset_path,
    ensure_parquet_dataset,
    get_connection,
    create_session_connection,
    reset_to_raw_dataset,
    validate_dataset,
    get_schema,
    get_schema_description,
    CANONICAL_COLUMNS,
    NUMERIC_COLUMNS,
    CATEGORICAL_COLUMNS,
    DATE_COLUMN,
)


def test_dataset_path_resolution():
    """Verify that get_dataset_path returns an existing Parquet file."""
    path = get_dataset_path()
    assert isinstance(path, Path)
    assert path.exists()
    assert path.suffix == ".parquet"


def test_validate_canonical_dataset():
    """Validate that the canonical Sales_Dataset_2024 has 2000 rows and 10 columns."""
    res = validate_dataset()
    assert res["is_valid"] is True
    assert res["row_count"] == 2000
    assert res["column_count"] == 10
    assert set(res["columns"]) == set(CANONICAL_COLUMNS)
    assert res["error"] is None


def test_duckdb_schema_types():
    """Verify DuckDB table schema types for canonical columns."""
    schema = get_schema()
    col_dict = {col["column"]: col["type"] for col in schema}
    assert DATE_COLUMN in col_dict
    for cat in CATEGORICAL_COLUMNS:
        assert cat in col_dict
    for num in NUMERIC_COLUMNS:
        assert num in col_dict


def test_schema_description_summary():
    """Verify get_schema_description generates a structured prompt summary."""
    schema_desc = get_schema_description()
    assert schema_desc.dataset_name == "Sales_Dataset_2024"
    assert schema_desc.total_rows == 2000
    assert len(schema_desc.columns) == 10

    summary = schema_desc.to_prompt_summary()
    assert "Sales_Dataset_2024 (2000 rows)" in summary
    assert "Date (TIMESTAMP, role: time)" in summary
    assert "Revenue (DOUBLE, role: metric)" in summary


def test_missing_excel_file_raises(tmp_path, monkeypatch):
    """Verify FileNotFoundError if source Excel does not exist."""
    fake_xlsx = tmp_path / "NonExistent.xlsx"
    fake_parquet = tmp_path / "NonExistent.parquet"

    monkeypatch.setattr("utils.data_loader.XLSX_PATH", fake_xlsx)
    monkeypatch.setattr("utils.data_loader.PARQUET_PATH", fake_parquet)

    with pytest.raises(FileNotFoundError, match="Source Excel file not found"):
        ensure_parquet_dataset()


def test_session_isolated_connections():
    """Verify that independent DuckDB connections maintain isolated dataset views."""
    conn_a = create_session_connection()
    conn_b = create_session_connection()

    # Mutate dataset view in conn_a (e.g. filter to North only)
    conn_a.execute("CREATE OR REPLACE VIEW dataset AS SELECT * FROM raw_dataset WHERE Region = 'North'")

    count_a = conn_a.execute("SELECT COUNT(*) FROM dataset").fetchone()[0]
    count_b = conn_b.execute("SELECT COUNT(*) FROM dataset").fetchone()[0]

    # conn_a has filtered subset
    assert count_a < 2000
    # conn_b retains full 2000 rows
    assert count_b == 2000

    # Reset conn_a
    reset_to_raw_dataset(conn_a)
    assert conn_a.execute("SELECT COUNT(*) FROM dataset").fetchone()[0] == 2000

    conn_a.close()
    conn_b.close()


def test_raw_dataset_immutability():
    """Verify that raw_dataset view remains read-only / immutable."""
    conn = create_session_connection()
    raw_count = conn.execute("SELECT COUNT(*) FROM raw_dataset").fetchone()[0]
    assert raw_count == 2000

    # Mutating the active dataset view does not affect raw_dataset
    conn.execute("CREATE OR REPLACE VIEW dataset AS SELECT * FROM raw_dataset WHERE Profit > 0")
    filtered_dataset_count = conn.execute("SELECT COUNT(*) FROM dataset").fetchone()[0]
    assert filtered_dataset_count < 2000

    raw_count_after = conn.execute("SELECT COUNT(*) FROM raw_dataset").fetchone()[0]
    assert raw_count_after == 2000
    conn.close()
