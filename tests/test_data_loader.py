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
    build_sql_where_clause,
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


def test_build_sql_where_clause_comprehensive():
    """Verify build_sql_where_clause handles scalars, lists, numeric values, empty lists, and quotes."""
    # 1. None or empty
    assert build_sql_where_clause(None) == "1=1"
    assert build_sql_where_clause({}) == "1=1"

    # 2. Scalar categorical filter
    res_scalar = build_sql_where_clause({"Region": "North"})
    assert "LOWER(Region) = LOWER('North')" in res_scalar

    # 3. Multi-value categorical filter
    res_list = build_sql_where_clause({"Region": ["West", "North", "South", "East"]})
    assert "LOWER(Region) IN (LOWER('West'), LOWER('North'), LOWER('South'), LOWER('East'))" in res_list

    # 4. Numeric scalar filter
    res_num = build_sql_where_clause({"Units_Sold": 10})
    assert "Units_Sold = 10" in res_num

    # 5. Numeric list filter
    res_num_list = build_sql_where_clause({"Units_Sold": [10, 20, 30]})
    assert "Units_Sold IN (10, 20, 30)" in res_num_list

    # 6. Empty list filter (matches zero rows)
    res_empty = build_sql_where_clause({"Region": []})
    assert "1=0" in res_empty

    # 7. Multiple filters together
    res_multi = build_sql_where_clause({"Region": ["North", "South"], "Category": "Electronics"})
    assert "LOWER(Region) IN (LOWER('North'), LOWER('South'))" in res_multi
    assert "LOWER(Category) = LOWER('Electronics')" in res_multi

    # 8. Single quotes escaping
    res_quote = build_sql_where_clause({"Salesperson": "O'Connor"})
    assert "LOWER(Salesperson) = LOWER('O''Connor')" in res_quote


def test_build_sql_where_clause_duckdb_execution():
    """Verify generated WHERE clauses execute correctly against DuckDB canonical dataset."""
    conn = get_connection()

    # Multi-value list filter
    where_list = build_sql_where_clause({"Region": ["West", "North", "South", "East"]})
    df_list = conn.execute(f"SELECT COUNT(*) FROM dataset WHERE {where_list}").fetchone()[0]
    assert df_list > 1900

    # Empty list filter returns 0 rows
    where_empty = build_sql_where_clause({"Region": []})
    df_empty = conn.execute(f"SELECT COUNT(*) FROM dataset WHERE {where_empty}").fetchone()[0]
    assert df_empty == 0

    # Multiple filters combined
    where_combined = build_sql_where_clause({"Region": ["North"], "Category": "Office"})
    df_combined = conn.execute(f"SELECT COUNT(*) FROM dataset WHERE {where_combined}").fetchone()[0]
    assert df_combined > 0



