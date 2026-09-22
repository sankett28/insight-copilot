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
from utils.data_loader import get_schema_description, validate_dataset

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

if "messages" not in st.session_state:
    st.session_state.messages = []
if "turn_artifacts" not in st.session_state:
    # Map message index -> list of chart dicts
    st.session_state.turn_artifacts = {}
if "current_plan" not in st.session_state:
    st.session_state.current_plan = None
if "current_tool_results" not in st.session_state:
    st.session_state.current_tool_results = []
if "current_errors" not in st.session_state:
    st.session_state.current_errors = []

# ---------------------------------------------------------------------------
# Sidebar: Dataset Explorer & Configuration
# ---------------------------------------------------------------------------

with st.sidebar:
    st.title("📊 Insight Copilot")
    st.caption("Deterministic Analytical Intelligence")

    st.divider()

    # Active Model Badge
    active_model = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
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
        "Compare North and South profit margin",
        "Show monthly profit trend with a bar chart",
        "Which product contributes most to total profit?",
        "Detect revenue anomalies using IQR",
        "What is the correlation between Units Sold and Revenue?",
    ]
    for sq in starter_queries:
        if st.button(sq, use_container_width=True, key=f"btn_{sq}"):
            st.session_state.pending_query = sq

    st.divider()

    # Clear Chat Button
    if st.button("🗑️ Clear Conversation", use_container_width=True):
        st.session_state.messages = []
        st.session_state.turn_artifacts = {}
        st.session_state.current_plan = None
        st.session_state.current_tool_results = []
        st.session_state.current_errors = []
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

        # 4. Standard rows table
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

    # Empty State Guide
    if not st.session_state.messages:
        st.info(
            "👋 **Welcome to Insight Copilot!**\n\n"
            "Ask questions about sales revenue, regional profitability, temporal trends, statistical anomalies, or correlations. "
            "Every calculation is executed deterministically in DuckDB with visible execution traces."
        )

    # Render Conversation History
    for idx, msg in enumerate(st.session_state.messages):
        role_label = "user" if msg.role == Role.USER else "assistant"
        with st.chat_message(role_label):
            st.markdown(msg.content)

            # Render inline charts attached to this assistant turn
            if role_label == "assistant" and idx in st.session_state.turn_artifacts:
                for chart_dict in st.session_state.turn_artifacts[idx]:
                    fig = go.Figure(chart_dict)
                    fig.update_layout(
                        template="plotly_dark",
                        margin=dict(l=20, r=20, t=40, b=20),
                    )
                    st.plotly_chart(fig, use_container_width=True)

    # Handle Input from chat_input or sidebar quick starters
    user_query = st.chat_input("Ask an analytical question about the 2024 sales dataset...")
    if "pending_query" in st.session_state and st.session_state.pending_query:
        user_query = st.session_state.pending_query
        st.session_state.pending_query = None

    if user_query:
        # Display user message immediately in chat
        with st.chat_message("user"):
            st.markdown(user_query)

        # Build initial turn state
        initial_state = create_initial_state(
            query=user_query,
            history=st.session_state.messages,
        )

        with st.spinner("Analyzing dataset & executing analytical plan..."):
            try:
                agent_graph = get_compiled_agent()
                final_state = agent_graph.invoke(initial_state)

                # Update session state with turn outputs
                st.session_state.messages = final_state.get("messages", [])
                st.session_state.current_plan = final_state.get("plan")
                st.session_state.current_tool_results = final_state.get("tool_results", [])
                st.session_state.current_errors = final_state.get("errors", [])

                # Store any generated charts linked to the latest assistant message index
                latest_assistant_idx = len(st.session_state.messages) - 1
                charts = final_state.get("chart_artifacts", [])
                if charts:
                    st.session_state.turn_artifacts[latest_assistant_idx] = charts

                st.rerun()

            except Exception as exc:  # noqa: BLE001
                st.error(f"Execution Error: {exc}")

# --- Right Column: Visible Execution Plan & Tool Trace ---
with col_trace:
    st.subheader("🗺️ Execution Plan & Trace")

    # Error Alert if turn encountered errors
    if st.session_state.current_errors:
        st.error(
            "**Encountered Warning / Error**:\n"
            + "\n".join([f"- {err}" for err in st.session_state.current_errors])
        )

    # Analytical Plan Card
    if st.session_state.current_plan:
        plan = st.session_state.current_plan
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
    if st.session_state.current_tool_results:
        st.write("---")
        st.markdown("**Deterministic Tool Outputs**:")
        for tr in st.session_state.current_tool_results:
            icon = "✅" if tr.success else "❌"
            header = f"{icon} Step {tr.step_number}: `{tr.tool.value}`"
            with st.expander(header, expanded=tr.success):
                _render_tool_result_ui(tr)


