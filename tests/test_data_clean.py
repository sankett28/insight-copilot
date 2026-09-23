"""
tests/test_data_clean.py
------------------------
Unit tests for utils/data_cleaner.py and tools/data_clean.py.
"""

import pytest

from agent.state import AgentState
from models.schemas import AnalysisPlan, DataCleanRequest, Intent, PlanStep, ToolName
from tools.data_clean import data_clean_tool_node, execute_data_clean
from utils.data_cleaner import (
    apply_cleaning_to_duckdb,
    build_fuzzy_cluster_mapping,
    damerau_levenshtein_distance,
    levenshtein_distance,
)
from utils.data_loader import (
    create_session_connection,
    get_connection,
    reset_to_raw_dataset,
)


@pytest.fixture(autouse=True)
def setup_and_teardown_data():
    """Ensure dataset view is reset to clean raw state before and after each test."""
    reset_to_raw_dataset()
    yield
    reset_to_raw_dataset()


def test_levenshtein_distance_algorithm():
    """Verify edit distance computation across various word pairs including transpositions."""
    assert levenshtein_distance("west", "west") == 0
    assert levenshtein_distance("west", "westt") == 1
    assert levenshtein_distance("East", "Easst") == 1
    assert levenshtein_distance("cat", "dog") == 3
    assert levenshtein_distance("kitten", "sitting") == 3
    assert levenshtein_distance("", "test") == 4
    # Transposition (Damerau-Levenshtein)
    assert damerau_levenshtein_distance("moblie", "mobile") == 1
    assert damerau_levenshtein_distance("MOBLIE".lower(), "Mobile".lower()) == 1


def test_build_fuzzy_cluster_mapping_product_moblie():
    """Verify fuzzy cluster mapping maps MOBLIE to dominant parent Mobile."""
    conn = get_connection()
    mapping = build_fuzzy_cluster_mapping(conn, "raw_dataset", "Product", threshold=1)

    assert isinstance(mapping, dict)
    # Check transposition typo resolution
    assert mapping.get("MOBLIE") == "Mobile"
    assert mapping.get("Mobile") == "Mobile"
    assert mapping.get("tabllet") == "Tablet"
    assert mapping.get("headPhones") == "Headphones"
    assert mapping.get("SMARTWATCH") == "Smartwatch"
    assert mapping.get("laptop") == "Laptop"


def test_build_fuzzy_cluster_mapping_region():
    """Verify fuzzy cluster mapping detects regional typos and casing anomalies."""
    conn = get_connection()
    mapping = build_fuzzy_cluster_mapping(conn, "raw_dataset", "Region", threshold=1)

    assert isinstance(mapping, dict)
    # Check casing normalizations
    assert mapping.get("north") == "North"
    assert mapping.get("NORTH") == "North"
    assert mapping.get("south") == "South"

    # Check fuzzy typo mappings
    assert mapping.get("westt") == "West"
    assert mapping.get("Easst") == "East"

    # Check canonical values remain stable
    assert mapping.get("West") == "West"
    assert mapping.get("North") == "North"
    assert mapping.get("East") == "East"
    assert mapping.get("South") == "South"



def test_apply_cleaning_to_duckdb_region():
    """Verify DuckDB view update aggregates 9 dirty regions into 4 canonical + Unassigned."""
    conn = get_connection()
    req = DataCleanRequest(
        columns=["Region"],
        operations=["standardize_casing", "fuzzy_deduplicate", "fill_nulls"],
        fill_null_value="Unassigned",
    )

    audit = apply_cleaning_to_duckdb(conn, req)

    assert audit["status"] == "success"
    assert audit["distinct_before"]["Region"] == 9
    assert audit["distinct_after"]["Region"] == 5  # West, North, East, South, Unassigned

    # Verify query against the newly updated active dataset view
    distinct_rows = conn.execute("SELECT DISTINCT Region FROM dataset ORDER BY Region").fetchall()
    distinct_regions = {r[0] for r in distinct_rows}
    assert distinct_regions == {"East", "North", "South", "West", "Unassigned"}


def test_data_clean_tool_node_success():
    """Verify LangGraph data_clean tool node executes and updates state."""
    plan = AnalysisPlan(
        intent=Intent.DATA_QUERY,
        rationale="Clean regional dimension typos",
        steps=[
            PlanStep(
                step_number=1,
                tool=ToolName.DATA_CLEAN,
                description="Clean Region typos and nulls",
                parameters={
                    "columns": ["Region"],
                    "operations": ["standardize_casing", "fuzzy_deduplicate", "fill_nulls"],
                    "fill_null_value": "Unassigned",
                },
                depends_on=[],
            )
        ],
        selected_tools=[ToolName.DATA_CLEAN],
    )

    state: AgentState = {
        "plan": plan,
        "selected_tools": [ToolName.DATA_CLEAN],
        "current_step": 0,
        "tool_results": [],
        "errors": [],
    }

    result = data_clean_tool_node(state)
    assert len(result["tool_results"]) == 1
    tr = result["tool_results"][0]
    assert tr.success is True
    assert tr.tool == ToolName.DATA_CLEAN
    assert tr.data["distinct_after"]["Region"] == 5


def test_data_clean_invalid_column_validation():
    """Verify invalid column parameter is rejected with validation error."""
    with pytest.raises(ValueError, match="Invalid column"):
        DataCleanRequest(columns=["NonExistentColumn"])


def test_downstream_metrics_aggregation_after_cleaning():
    """Verify that running metrics after cleaning returns exactly 4 canonical regions + Unassigned."""
    conn = get_connection()
    req = DataCleanRequest(
        columns=["Region"],
        operations=["standardize_casing", "fuzzy_deduplicate", "fill_nulls"],
    )
    execute_data_clean(req)

    # Run regional revenue metrics query on cleaned view
    rows = conn.execute(
        "SELECT Region, SUM(Revenue) AS total_rev FROM dataset GROUP BY Region ORDER BY total_rev DESC"
    ).fetchall()

    regional_dict = {r[0]: r[1] for r in rows}
    assert "West" in regional_dict
    assert "North" in regional_dict
    assert "East" in regional_dict
    assert "South" in regional_dict

    # Total West includes 5580782 + 18215 = 5598997
    assert regional_dict["West"] == 5598997.0
    # Total North includes 5069178 + 18818 + 17786 = 5105782
    assert regional_dict["North"] == 5105782.0


def test_concurrent_clean_isolation():
    """Verify data cleaning on connection A does not alter raw/uncleaned view on connection B."""
    conn_a = create_session_connection()
    conn_b = create_session_connection()

    req = DataCleanRequest(
        columns=["Region"],
        operations=["standardize_casing", "fuzzy_deduplicate", "fill_nulls"],
    )

    # Clean conn_a
    audit = execute_data_clean(req, conn=conn_a)
    assert audit["status"] == "success"

    # Distinct regions on conn_a should be 5
    distinct_a = conn_a.execute("SELECT COUNT(DISTINCT Region) FROM dataset").fetchone()[0]
    assert distinct_a == 5

    # Distinct regions on conn_b should remain 9 (uncleaned raw)
    distinct_b = conn_b.execute("SELECT COUNT(DISTINCT Region) FROM dataset").fetchone()[0]
    assert distinct_b == 9

    conn_a.close()
    conn_b.close()


def test_cleaning_audit_reconciliation():
    """Verify strict mathematical reconciliation: raw nulls -> nulls replaced -> target fill count."""
    conn = get_connection()
    reset_to_raw_dataset(conn)

    # 1. Raw null count before cleaning
    raw_region_nulls = conn.execute("SELECT COUNT(*) FROM raw_dataset WHERE Region IS NULL").fetchone()[0]
    assert raw_region_nulls == 39

    # 2. Clean with fill_nulls
    req_fill = DataCleanRequest(
        columns=["Region"],
        operations=["standardize_casing", "fuzzy_deduplicate", "fill_nulls"],
        fill_null_value="Unassigned",
    )
    audit_fill = execute_data_clean(req_fill, conn=conn)

    assert audit_fill["nulls_before"]["Region"] == 39
    assert audit_fill["nulls_replaced"]["Region"] == 39
    assert audit_fill["nulls_after"]["Region"] == 0
    assert audit_fill["target_fill_counts"]["Region"] == 39

    # Resulting Unassigned count in DuckDB dataset view
    unassigned_in_view = conn.execute("SELECT COUNT(*) FROM dataset WHERE Region = 'Unassigned'").fetchone()[0]
    assert unassigned_in_view == 39

    # Invariant: raw null count == number replaced == resulting target count
    assert raw_region_nulls == audit_fill["nulls_replaced"]["Region"] == unassigned_in_view

    # 3. Clean without fill_nulls -> nulls_replaced must be 0 and nulls remain
    reset_to_raw_dataset(conn)
    req_no_fill = DataCleanRequest(
        columns=["Region"],
        operations=["standardize_casing", "fuzzy_deduplicate"],
    )
    audit_no_fill = execute_data_clean(req_no_fill, conn=conn)

    assert audit_no_fill["nulls_before"]["Region"] == 39
    assert audit_no_fill["nulls_replaced"]["Region"] == 0
    assert audit_no_fill["nulls_after"]["Region"] == 39

