"""
app.py
------
Production Streamlit application for Insight Copilot.

Features:
  - Interactive multi-turn conversational chat with session history persistence.
  - Live split layout: Chat & visualizations on the left, Execution Plan & Tool Trace on the right.
  - Native dark-themed Plotly charts rendered directly inline within assistant responses.
  - Dataset metadata & health inspector in the sidebar.
  - Sample query starter buttons for quick testing.
  - Resilient error handling for API quotas and data edge cases.

Run with:
    streamlit run app.py
"""

from __future__ import annotations

import os
from typing import Any
import plotly.graph_objects as go
import streamlit as st
from dotenv import load_dotenv

from agent.graph import build_graph
from agent.state import create_initial_state
from llm.factory import create_llm
from models.schemas import Message, Role
from utils.data_loader import (
    create_session_connection,
    get_schema_description,
    reset_to_raw_dataset,
    validate_dataset,
)

load_dotenv()

# ---------------------------------------------------------------------------
# Page configuration — must be the first Streamlit call
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Insight Copilot — Analytical AI Assistant",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Cached Resources (Graph and Dataset initialization)
# ---------------------------------------------------------------------------

@st.cache_resource(show_spinner=False)
def init_data_layer():
    """Validate canonical dataset and fetch metadata description."""
    val = validate_dataset()
    schema = get_schema_description()
    return val, schema


@st.cache_resource(show_spinner=False)
def get_compiled_agent():
    """Instantiate and compile the LangGraph StateGraph."""
    llm = create_llm()
    return build_graph(llm)



dataset_status, dataset_schema = init_data_layer()

# ---------------------------------------------------------------------------
# Session State Initialization
# ---------------------------------------------------------------------------

st.session_state.setdefault("messages", [])
st.session_state.setdefault("turn_artifacts", {})
st.session_state.setdefault("current_plan", None)
st.session_state.setdefault("current_tool_results", [])
st.session_state.setdefault("current_errors", [])
st.session_state.setdefault("current_telemetry", {})
st.session_state.setdefault("pending_query", None)
if "db_conn" not in st.session_state:
    st.session_state["db_conn"] = create_session_connection()

# ---------------------------------------------------------------------------
# Sidebar: Dataset Explorer & Configuration
# ---------------------------------------------------------------------------

with st.sidebar:
    st.title("📊 Insight Copilot")
    st.caption("Deterministic Analytical Intelligence")

    st.divider()

    # Active Model Badge
    active_model = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")
    st.markdown(f"🤖 **Active Model**: `{active_model}`")



    st.divider()

    # Dataset Status Card
    if dataset_status.get("is_valid"):
        st.success(
            f"**Canonical Dataset Loaded**\n\n"
            f"- **Dataset**: `Sales_Dataset_2024.xlsx`\n"
            f"- **Rows**: `{dataset_status['row_count']:,}`\n"
            f"- **Columns**: `{dataset_status['column_count']}`"
        )
    else:
        st.error(f"Dataset error: {dataset_status.get('error')}")

    # Expandable Schema Metadata
    with st.expander("📋 View Column Metadata", expanded=False):
        for col in dataset_schema.columns:
            st.markdown(f"- **`{col.name}`** (`{col.data_type}`)  \n  *Role: {col.semantic_role}*")

    st.divider()

    # Quick Starter Queries
    st.subheader("💡 Quick Starters")
    starter_queries = [
        "What is the total revenue by region?",
        "Clean region typos and show total revenue by region",
        "Compare North and South profit margin",
        "Show monthly profit trend with a bar chart",
        "Which product contributes most to total profit?",
        "Detect revenue anomalies using IQR",
        "What is the correlation between Units Sold and Revenue?",
    ]
    for sq in starter_queries:
        if st.button(sq, use_container_width=True, key=f"btn_{sq}"):
            st.session_state["pending_query"] = sq

    st.divider()

    # Reset Cleaned Data View Button
    if st.button("🔄 Reset Active Dataset to Raw", use_container_width=True):
        reset_to_raw_dataset(st.session_state.get("db_conn"))
        st.toast("Active dataset view reset to raw data.", icon="🔄")
        st.rerun()

    # Clear Chat Button
    if st.button("🗑️ Clear Conversation", use_container_width=True):
        st.session_state["messages"] = []
        st.session_state["turn_artifacts"] = {}
        st.session_state["current_plan"] = None
        st.session_state["current_tool_results"] = []
        st.session_state["current_errors"] = []
        st.session_state["current_telemetry"] = {}
        st.session_state["pending_query"] = None
        st.rerun()



# ---------------------------------------------------------------------------
# UI Helper Functions
# ---------------------------------------------------------------------------

def _render_tool_result_ui(tr: Any) -> None:
    """Render structured, readable presentation of tool execution results."""
    if tr.error:
        st.error(tr.error)
        return

    data = tr.data
    if data is None:
        st.caption("No data returned.")
        return

    if isinstance(data, list):
        if len(data) > 0:
            st.dataframe(data, use_container_width=True)
        else:
            st.caption("Query returned 0 matching records.")
        return

    if isinstance(data, dict):
        # 1. Data Profile rendering
        if "numeric_summary" in data and "row_count" in data:
            c1, c2, c3 = st.columns(3)
            c1.metric("Total Rows", f"{data.get('row_count', 0):,}")
            c2.metric("Total Columns", data.get("column_count", 0))
            dr = data.get("date_range", {})
            c3.metric("Date Span", f"{dr.get('min', 'N/A')} → {dr.get('max', 'N/A')}")

            warnings = data.get("data_quality_warnings", [])
            if warnings:
                st.markdown("⚠️ **Data Quality Warnings:**")
                for w in warnings:
                    st.warning(w)

            st.markdown("📈 **Numeric Metric Summary:**")
            num_summary = data.get("numeric_summary", {})
            if num_summary:
                summary_rows = []
                for col_name, stats in num_summary.items():
                    summary_rows.append({
                        "Metric": col_name,
                        "Min": stats.get("min"),
                        "Max": stats.get("max"),
                        "Mean": stats.get("mean"),
                        "Std Dev": stats.get("stddev"),
                    })
                st.dataframe(summary_rows, use_container_width=True)

            tab1, tab2 = st.tabs(["Null Counts", "Categorical Cardinality"])
            with tab1:
                null_counts = data.get("null_counts", {})
                null_rows = [{"Column": k, "Nulls": v} for k, v in null_counts.items()]
                st.dataframe(null_rows, use_container_width=True)
            with tab2:
                cardinality = data.get("categorical_cardinality", {})
                card_rows = [{"Dimension": k, "Distinct Values": v} for k, v in cardinality.items()]
                st.dataframe(card_rows, use_container_width=True)
            return

        # 2. Correlation rendering
        if "correlation_coefficient" in data and "field_a" in data:
            c1, c2 = st.columns(2)
            c1.metric("Field Pair", f"{data['field_a']} vs {data['field_b']}")
            c2.metric("Correlation (r)", f"{data['correlation_coefficient']:+.4f}")
            st.info(f"**Interpretation**: {data.get('interpretation', '').capitalize()}")
            st.caption(f"ℹ️ *{data.get('caveat', '')}*")
            return

        # 3. Anomaly Detection rendering
        if "total_anomalies" in data and "rows" in data:
            c1, c2, c3 = st.columns(3)
            c1.metric("Metric", data.get("metric", ""))
            c2.metric("Method", data.get("method", "").upper())
            c3.metric("Anomalies Found", data.get("total_anomalies", 0))
            if data.get("rows"):
                st.markdown("🔍 **Flagged Outlier Records:**")
                st.dataframe(data["rows"], use_container_width=True)
            else:
                st.success("No anomalies detected outside threshold boundaries.")
            return

        # 4. Data Clean rendering
        if "cluster_mappings" in data and "distinct_before" in data:
            st.success(data.get("message", "Data cleaning completed successfully."))
            c1, c2 = st.columns(2)
            for col in data.get("columns_cleaned", []):
                b_cnt = data.get("distinct_before", {}).get(col, 0)
                a_cnt = data.get("distinct_after", {}).get(col, 0)
                nulls_cnt = data.get("nulls_replaced", {}).get(col, 0)
                diff = b_cnt - a_cnt
                c1.metric(f"'{col}' Distinct Values", f"{b_cnt} → {a_cnt}", delta=f"-{diff} merged" if diff > 0 else None)
                c2.metric(f"'{col}' Nulls Filled", f"{nulls_cnt} rows")

            mappings = data.get("cluster_mappings", {})
            for col, cmap in mappings.items():
                if cmap:
                    st.markdown(f"🔄 **Transformation Mappings applied to `{col}`:**")
                    map_rows = [{"Raw Value": k, "Normalized To": v} for k, v in cmap.items()]
                    st.dataframe(map_rows, use_container_width=True)
            return

        # 5. Standard rows table
        if "rows" in data and isinstance(data["rows"], list):
            st.dataframe(data["rows"], use_container_width=True)
            with st.expander("Summary Statistics", expanded=False):
                summary_dict = {k: v for k, v in data.items() if k != "rows"}
                st.json(summary_dict)
            return

        # Fallback to json
        st.json(data)
        return

    st.write(data)



# ---------------------------------------------------------------------------
# Main Layout: Split Screen (Chat 60% | Trace 40%)
# ---------------------------------------------------------------------------

col_chat, col_trace = st.columns([1.5, 1.0], gap="large")

# --- Left Column: Interactive Chat & Visualizations ---
with col_chat:
    st.subheader("💬 Conversation")

    messages = st.session_state.get("messages", [])
    turn_artifacts = st.session_state.get("turn_artifacts", {})

    # Empty State Guide
    if not messages:
        st.info(
            "👋 **Welcome to Insight Copilot!**\n\n"
            "Ask questions about sales revenue, regional profitability, temporal trends, statistical anomalies, or correlations. "
            "Every calculation is executed deterministically in DuckDB with visible execution traces."
        )

    # Render Conversation History
    for idx, msg in enumerate(messages):
        role_label = "user" if msg.role == Role.USER else "assistant"
        with st.chat_message(role_label):
            st.markdown(msg.content)

            # Render inline charts attached to this assistant turn
            if role_label == "assistant" and idx in turn_artifacts:
                for chart_dict in turn_artifacts[idx]:
                    fig = go.Figure(chart_dict)
                    fig.update_layout(
                        template="plotly_dark",
                        margin=dict(l=20, r=20, t=40, b=20),
                    )
                    st.plotly_chart(fig, use_container_width=True)

    # Handle Input from chat_input or sidebar quick starters
    user_query = st.chat_input("Ask an analytical question about the 2024 sales dataset...")
    if st.session_state.get("pending_query"):
        user_query = st.session_state["pending_query"]
        st.session_state["pending_query"] = None

    if user_query:
        # Display user message immediately in chat
        with st.chat_message("user"):
            st.markdown(user_query)

        # Build initial turn state
        initial_state = create_initial_state(
            query=user_query,
            history=st.session_state.get("messages", []),
        )

        with st.spinner("Analyzing dataset & executing analytical plan..."):
            try:
                agent_graph = get_compiled_agent()
                final_state = agent_graph.invoke(initial_state)

                # Update session state with turn outputs
                st.session_state["messages"] = final_state.get("messages", [])
                st.session_state["current_plan"] = final_state.get("plan")
                st.session_state["current_tool_results"] = final_state.get("tool_results", [])
                st.session_state["current_errors"] = final_state.get("errors", [])
                st.session_state["current_telemetry"] = final_state.get("telemetry", {})

                # Store any generated charts linked to the latest assistant message index
                latest_assistant_idx = len(st.session_state["messages"]) - 1
                charts = final_state.get("chart_artifacts", [])
                if charts:
                    if "turn_artifacts" not in st.session_state:
                        st.session_state["turn_artifacts"] = {}
                    st.session_state["turn_artifacts"][latest_assistant_idx] = charts

                st.rerun()

            except Exception as exc:  # noqa: BLE001
                st.error(f"Execution Error: {exc}")

# --- Right Column: Visible Execution Plan & Tool Trace ---
with col_trace:
    st.subheader("🗺️ Execution Plan & Trace")

    current_errors = st.session_state.get("current_errors", [])
    current_plan = st.session_state.get("current_plan")
    current_tool_results = st.session_state.get("current_tool_results", [])
    current_telemetry = st.session_state.get("current_telemetry", {})

    # Telemetry card if available
    if current_telemetry and "timings" in current_telemetry:
        timings = current_telemetry["timings"]
        run_id_short = str(current_telemetry.get("run_id", "turn"))[:8]
        with st.expander(f"⏱️ Turn Telemetry (`{run_id_short}`)", expanded=False):
            c1, c2, c3 = st.columns(3)
            c1.metric("Planner", f"{timings.get('planner_ms', 0):.1f} ms")
            c2.metric("Synthesizer", f"{timings.get('synthesizer_ms', 0):.1f} ms")
            c3.metric("Total Turn", f"{timings.get('total_turn_ms', 0):.1f} ms")

    # Error Alert if turn encountered errors
    if current_errors:
        st.error(
            "**Encountered Warning / Error**:\n"
            + "\n".join([f"- {err}" for err in current_errors])
        )

    # Analytical Plan Card
    if current_plan:
        plan = current_plan
        with st.container():
            st.markdown(f"**Intent**: `{plan.intent.value.upper()}`")
            st.markdown(f"**Rationale**: *{plan.rationale}*")
            st.write("---")
            st.markdown("**Investigation Plan Steps**:")
            for step in plan.steps:
                dep_text = f" *(depends on Step {step.depends_on})*" if step.depends_on else ""
                st.markdown(f"**Step {step.step_number}**: `{step.tool.value}`{dep_text}")
                st.caption(step.description)
                if step.parameters:
                    with st.expander("🔍 View Step Parameters", expanded=False):
                        st.json(step.parameters)
    else:
        st.info("Submit a question to inspect the Planner's step-by-step analytical execution plan.")

    # Tool Execution Results Card
    if current_tool_results:
        st.write("---")
        st.markdown("**Deterministic Tool Outputs**:")
        for tr in current_tool_results:
            icon = "✅" if tr.success else "❌"
            provenance = f" | {tr.execution_time_ms}ms" if tr.execution_time_ms is not None else ""
            header = f"{icon} Step {tr.step_number}: `{tr.tool.value}`{provenance}"
            with st.expander(header, expanded=tr.success):
                _render_tool_result_ui(tr)




