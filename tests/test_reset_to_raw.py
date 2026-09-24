"""
tests/test_reset_to_raw.py
--------------------------
Deterministic regression tests for ISSUE 2: Dataset reset to raw source correctness.

Verifies:
  - Test A: Raw table immutability, active view cleaning, and reset restoration.
  - Test B: Tool node SQL queries (metrics) return raw categories (e.g. MOBLIE) after reset.
  - Test C: Region cleaning followed by reset restores dirty Region variants.
  - Test D: Multi-connection session isolation and independent reset correctness.
  - Test E: Charts generated after reset reflect restored raw dataset categories.
"""

import pytest

from models.schemas import (
    AnalysisPlan,
    ChartRequest,
    DataCleanRequest,
    Intent,
    MetricsRequest,
    PlanStep,
    ToolName,
    ToolResult,
)
from tools.charts import charts_tool_node
from tools.data_clean import execute_data_clean
from tools.metrics import execute_metrics_request
from utils.data_cleaner import apply_cleaning_to_duckdb
from utils.data_loader import (
    create_session_connection,
    get_connection,
    reset_to_raw_dataset,
)


def test_A_raw_immutability_and_view_reset():
    """Test A: Confirm dataset cleaning alters dataset view, raw_dataset stays raw, and reset restores dataset view."""
    conn = create_session_connection()

    # 1. Confirm raw_dataset contains dirty category 'MOBLIE'
    raw_products = [r[0] for r in conn.execute("SELECT DISTINCT Product FROM raw_dataset WHERE Product IS NOT NULL").fetchall()]
    assert "MOBLIE" in raw_products, "raw_dataset must contain dirty category 'MOBLIE'"

    # 2. Apply cleaning to dataset view
    clean_req = DataCleanRequest(columns=["Product"], operations=["fuzzy_deduplicate", "standardize_casing"])
    apply_cleaning_to_duckdb(conn, clean_req)

    # 3. Confirm dataset view is cleaned
    cleaned_products = [r[0] for r in conn.execute("SELECT DISTINCT Product FROM dataset WHERE Product IS NOT NULL").fetchall()]
    assert "MOBLIE" not in cleaned_products, "dataset view must be cleaned"
    assert "Mobile" in cleaned_products

    # 4. Confirm raw_dataset remains unchanged (immutable)
    raw_products_after = [r[0] for r in conn.execute("SELECT DISTINCT Product FROM raw_dataset WHERE Product IS NOT NULL").fetchall()]
    assert "MOBLIE" in raw_products_after, "raw_dataset must remain immutable"

    # 5. Call reset_to_raw_dataset(conn)
    reset_to_raw_dataset(conn)

    # 6. Confirm dataset view matches raw state again
    restored_products = [r[0] for r in conn.execute("SELECT DISTINCT Product FROM dataset WHERE Product IS NOT NULL").fetchall()]
    assert "MOBLIE" in restored_products, "dataset view must be restored to raw state after reset"


def test_B_metrics_returns_raw_categories_after_reset():
    """Test B: Execute revenue-by-product after reset; confirm MOBLIE exists and Mobile returns to raw total."""
    conn = get_connection()

    # Get raw Mobile total
    raw_mobile_rev = conn.execute("SELECT SUM(Revenue) FROM raw_dataset WHERE Product = 'Mobile'").fetchone()[0]

    # Clean Product
    clean_req = DataCleanRequest(columns=["Product"], operations=["fuzzy_deduplicate", "standardize_casing"])
    execute_data_clean(clean_req, conn=conn)

    # Reset
    reset_to_raw_dataset(conn)

    # Query metrics
    metrics_res = execute_metrics_request(
        MetricsRequest(metric="Revenue", group_by="Product", limit=20)
    )
    product_names = [row["Product"] for row in metrics_res]
    assert "MOBLIE" in product_names, "MOBLIE must exist in metrics results after reset"

    mobile_row = next(r for r in metrics_res if r["Product"] == "Mobile")
    assert abs(mobile_row["sum_revenue"] - raw_mobile_rev) < 0.01, (
        f"Mobile revenue {mobile_row['sum_revenue']} should match raw total {raw_mobile_rev}"
    )


def test_C_region_cleaning_and_reset_restoration():
    """Test C: Clean Region column, reset, and confirm dirty Region variants return."""
    conn = get_connection()

    # 1. Clean Region
    clean_req = DataCleanRequest(columns=["Region"], operations=["fuzzy_deduplicate", "standardize_casing"])
    execute_data_clean(clean_req, conn=conn)

    cleaned_regions = [r[0] for r in conn.execute("SELECT DISTINCT Region FROM dataset WHERE Region IS NOT NULL").fetchall()]
    assert "westt" not in cleaned_regions
    assert "Easst" not in cleaned_regions

    # 2. Reset
    reset_to_raw_dataset(conn)

    # 3. Confirm dirty region variants return
    restored_regions = [r[0] for r in conn.execute("SELECT DISTINCT Region FROM dataset WHERE Region IS NOT NULL").fetchall()]
    assert any("westt" in r or "Easst" in r or "north" in r for r in restored_regions), (
        "Dirty region variants must return after dataset reset"
    )


def test_D_multi_session_connection_isolation():
    """Test D: Clean connection A, leave B untouched, reset A, prove A and B are independently correct."""
    conn_a = create_session_connection()
    conn_b = create_session_connection()

    # Clean A
    clean_req = DataCleanRequest(columns=["Product"], operations=["fuzzy_deduplicate", "standardize_casing"])
    apply_cleaning_to_duckdb(conn_a, clean_req)

    # B untouched -> should still have MOBLIE
    b_prods_before = [r[0] for r in conn_b.execute("SELECT DISTINCT Product FROM dataset WHERE Product IS NOT NULL").fetchall()]
    assert "MOBLIE" in b_prods_before

    # Reset A
    reset_to_raw_dataset(conn_a)

    # Both A and B are now in raw state
    a_prods_after = [r[0] for r in conn_a.execute("SELECT DISTINCT Product FROM dataset WHERE Product IS NOT NULL").fetchall()]
    b_prods_after = [r[0] for r in conn_b.execute("SELECT DISTINCT Product FROM dataset WHERE Product IS NOT NULL").fetchall()]

    assert "MOBLIE" in a_prods_after
    assert "MOBLIE" in b_prods_after


def test_E_charts_after_reset_reflect_restored_raw_categories():
    """Test E: Confirm charts generated after reset use restored dataset and include raw categories."""
    conn = get_connection()

    # Clean and then reset
    clean_req = DataCleanRequest(columns=["Product"], operations=["fuzzy_deduplicate", "standardize_casing"])
    execute_data_clean(clean_req, conn=conn)
    reset_to_raw_dataset(conn)

    # Run metrics on restored dataset
    metrics_data = execute_metrics_request(
        MetricsRequest(metric="Revenue", group_by="Product", limit=20)
    )

    # Input metrics result to charts tool node
    prior_result = ToolResult(
        step_number=1,
        tool=ToolName.METRICS,
        success=True,
        data=metrics_data,
        source_view="dataset",
        row_count=len(metrics_data),
        execution_time_ms=5.0,
    )

    plan = AnalysisPlan(
        intent=Intent.METRICS,
        rationale="Metrics and chart",
        steps=[
            PlanStep(step_number=1, tool=ToolName.METRICS, description="Metrics", parameters={"metric": "Revenue", "group_by": "Product"}),
            PlanStep(step_number=2, tool=ToolName.CHARTS, description="Chart", parameters={"chart_type": "bar", "x": "Product", "y": "sum_revenue"}, depends_on=[1]),
        ],
        selected_tools=[ToolName.METRICS, ToolName.CHARTS],
    )

    state = {
        "plan": plan,
        "selected_tools": [ToolName.METRICS, ToolName.CHARTS],
        "current_step": 1,
        "tool_results": [prior_result],
        "chart_artifacts": [],
        "errors": [],
    }

    result = charts_tool_node(state)

    tool_results = result["tool_results"]

    assert len(tool_results) == 2
    chart_res = tool_results[1]
    assert chart_res.success is True
    assert chart_res.data is not None

    chart_dict = chart_res.data
    x_vals = chart_dict["data"][0]["x"]
    assert "MOBLIE" in x_vals, "Chart x-axis categories after reset must include raw category 'MOBLIE'"
