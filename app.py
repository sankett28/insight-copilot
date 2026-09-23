"""app.py
------
Production Streamlit application for Insight Copilot.

Features:
  - Interactive multi-turn conversational chat with session history persistence.
  - Modern Split-Screen Layout: Independent scrolling conversation on the left, sticky live execution trace on the right.
  - Active Prompt & Step Timeline Tracker: Real-time visibility into current query, intent, step progression, and tool status.
  - Multi-Turn Historical Trace Inspector: Browse and audit execution plans and SQL queries from any past turn.
  - Native Plotly Dark-Themed Visualizations embedded directly in assistant messages.
  - Dataset metadata & health inspector in the sidebar.
  - Comprehensive telemetry, error alerts, and persistent log inspection.

Run with:
    streamlit run app.py
"""

from __future__ import annotations

import os
from pathlib import Path
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
from utils.logging_config import log_run_start, setup_logging

load_dotenv()
setup_logging()

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
# Custom CSS for Modern, Sticky Layout & High-Polish UI
# ---------------------------------------------------------------------------

st.markdown(
    """
    <style>
    /* Main container padding */
    .block-container {
        padding-top: 1.5rem;
        padding-bottom: 2rem;
    }
    
    /* Sticky right column for Execution Plan & Trace */
    [data-testid="column"]:nth-child(2) {
        position: sticky;
        top: 1.5rem;
        align-self: flex-start;
        max-height: calc(100vh - 4rem);
        overflow-y: auto;
        padding-left: 0.5rem;
    }

    /* Active Query Banner */
    .active-query-card {
        background: linear-gradient(135deg, rgba(99, 102, 241, 0.12) 0%, rgba(56, 189, 248, 0.12) 100%);
        border: 1px solid rgba(99, 102, 241, 0.35);
        border-radius: 12px;
        padding: 0.9rem 1.1rem;
        margin-bottom: 0.8rem;
    }
    .query-text {
        font-weight: 600;
        font-size: 0.95rem;
        color: #e2e8f0;
        margin-top: 0.25rem;
    }
    .query-meta {
        font-size: 0.8rem;
        color: #94a3b8;
        display: flex;
        align-items: center;
        gap: 0.5rem;
        flex-wrap: wrap;
    }

    /* Step Timeline Pills */
    .step-pill-container {
        display: flex;
        gap: 0.4rem;
        flex-wrap: wrap;
        margin-top: 0.5rem;
    }
    .step-pill {
        background: rgba(30, 41, 59, 0.8);
        border: 1px solid rgba(148, 163, 184, 0.3);
        border-radius: 16px;
        padding: 0.2rem 0.65rem;
        font-size: 0.78rem;
        font-weight: 500;
        color: #cbd5e1;
        display: inline-flex;
        align-items: center;
        gap: 0.3rem;
    }
    .step-pill.success {
        border-color: rgba(74, 222, 128, 0.5);
        color: #86efac;
        background: rgba(22, 101, 52, 0.2);
    }
    .step-pill.failed {
        border-color: rgba(248, 113, 113, 0.5);
        color: #fca5a5;
        background: rgba(153, 27, 27, 0.2);
    }

    /* Streamlit tabs styling */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
    }
    .stTabs [data-baseweb="tab"] {
        border-radius: 6px;
        padding: 6px 14px;
        font-size: 0.85rem;
        font-weight: 500;
    }
    </style>
    """,
    unsafe_allow_html=True,
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
st.session_state.setdefault("turn_history", [])  # List of full turn audit records
st.session_state.setdefault("current_plan", None)
st.session_state.setdefault("current_tool_results", [])
st.session_state.setdefault("current_errors", [])
st.session_state.setdefault("current_telemetry", {})
st.session_state.setdefault("last_query", None)
st.session_state.setdefault("pending_query", None)
if "db_conn" not in st.session_state:
    st.session_state["db_conn"] = create_session_connection()

# ---------------------------------------------------------------------------
# Sidebar: Dataset Explorer & Configuration
# ---------------------------------------------------------------------------

with st.sidebar:
    st.title("📊 Insight Copilot")
    st.caption("Deterministic Analytical Intelligence & Auditing")

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
            st.markdown(
                f"- **`{col.name}`** (`{col.data_type}`)  \n  *Role: {col.semantic_role}*"
            )

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
        if st.button(sq, width="stretch", key=f"btn_{sq}"):
            st.session_state["pending_query"] = sq

    st.divider()

    # Reset Cleaned Data View Button
    if st.button("🔄 Reset Active Dataset to Raw", width="stretch"):
        reset_to_raw_dataset(st.session_state.get("db_conn"))
        st.toast("Active dataset view reset to raw data.", icon="🔄")
        st.rerun()

    # Clear Chat Button
    if st.button("🗑️ Clear Conversation", width="stretch"):
        st.session_state["messages"] = []
        st.session_state["turn_artifacts"] = {}
        st.session_state["turn_history"] = []
        st.session_state["current_plan"] = None
        st.session_state["current_tool_results"] = []
        st.session_state["current_errors"] = []
        st.session_state["current_telemetry"] = {}
        st.session_state["last_query"] = None
        st.session_state["pending_query"] = None
        st.rerun()


# ---------------------------------------------------------------------------
# UI Helper Functions for Tool Trace
# ---------------------------------------------------------------------------

def _render_tool_result_ui(tr: Any) -> None:
    """Render structured, readable presentation of tool execution results."""
    # Check if tr has an error
    error_msg = getattr(tr, "error", None)
    if error_msg:
        st.error(f"**Error**: {error_msg}")
        return

    data = getattr(tr, "result", None) or getattr(tr, "data", None)
    if data is None:
        st.caption("No data returned.")
        return

    # List of records (Standard tabular output)
    if isinstance(data, list):
        if len(data) > 0:
            st.dataframe(data, width="stretch")
        else:
            st.caption("Query returned 0 matching records.")
        return

    # Structured Dict Output
    if isinstance(data, dict):
        # 1. Data Profile rendering
        if "numeric_summary" in data and "row_count" in data:
            c1, c2, c3 = st.columns(3)
            c1.metric("Total Rows", f"{data.get('row_count', 0):,}")
            c2.metric("Total Columns", data.get("column_count", 0))
            dr = data.get("date_range", {})
            c3.metric(
                "Date Span", f"{dr.get('min', 'N/A')} → {dr.get('max', 'N/A')}"
            )

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
                    summary_rows.append(
                        {
                            "Metric": col_name,
                            "Min": stats.get("min"),
                            "Max": stats.get("max"),
                            "Mean": stats.get("mean"),
                            "Std Dev": stats.get("stddev"),
                        }
                    )
                st.dataframe(summary_rows, width="stretch")

            tab1, tab2 = st.tabs(["Null Counts", "Categorical Cardinality"])
            with tab1:
                null_counts = data.get("null_counts", {})
                null_rows = [
                    {"Column": k, "Nulls": v} for k, v in null_counts.items()
                ]
                st.dataframe(null_rows, width="stretch")
            with tab2:
                cardinality = data.get("categorical_cardinality", {})
                card_rows = [
                    {"Dimension": k, "Distinct Values": v}
                    for k, v in cardinality.items()
                ]
                st.dataframe(card_rows, width="stretch")
            return

        # 2. Correlation rendering
        if "correlation_coefficient" in data and "field_a" in data:
            c1, c2 = st.columns(2)
            c1.metric("Field Pair", f"{data['field_a']} vs {data['field_b']}")
            c2.metric(
                "Correlation (r)", f"{data['correlation_coefficient']:+.4f}"
            )
            st.info(
                f"**Interpretation**: {data.get('interpretation', '').capitalize()}"
            )
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
                st.dataframe(data["rows"], width="stretch")
            else:
                st.success("No anomalies detected outside threshold boundaries.")
            return

        # 4. Data Clean rendering
        if "cluster_mappings" in data and "distinct_before" in data:
            st.success(
                data.get("message", "Data cleaning completed successfully.")
            )
            c1, c2 = st.columns(2)
            for col in data.get("columns_cleaned", []):
                b_cnt = data.get("distinct_before", {}).get(col, 0)
                a_cnt = data.get("distinct_after", {}).get(col, 0)
                nulls_cnt = data.get("nulls_replaced", {}).get(col, 0)
                diff = b_cnt - a_cnt
                c1.metric(
                    f"'{col}' Distinct Values",
                    f"{b_cnt} → {a_cnt}",
                    delta=f"-{diff} merged" if diff > 0 else None,
                )
                c2.metric(f"'{col}' Nulls Filled", f"{nulls_cnt} rows")

            mappings = data.get("cluster_mappings", {})
            for col, cmap in mappings.items():
                if cmap:
                    st.markdown(
                        f"🔄 **Transformation Mappings applied to `{col}`:**"
                    )
                    map_rows = [
                        {"Raw Value": k, "Normalized To": v}
                        for k, v in cmap.items()
                    ]
                    st.dataframe(map_rows, width="stretch")
            return

        # 5. Standard rows table inside dict
        if "rows" in data and isinstance(data["rows"], list):
            st.dataframe(data["rows"], width="stretch")
            with st.expander("Summary Statistics", expanded=False):
                summary_dict = {k: v for k, v in data.items() if k != "rows"}
                st.json(summary_dict)
            return

        # Fallback to json
        st.json(data)
        return

    st.write(data)


# ---------------------------------------------------------------------------
# Main Layout: Modern Split Screen (Chat 58% | Trace & Plan 42%)
# ---------------------------------------------------------------------------

col_chat, col_trace = st.columns([1.4, 1.0], gap="large")

# --- Left Column: Interactive Chat & Visualizations ---
with col_chat:
    st.subheader("💬 Conversation & Visualizations")

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
                    st.plotly_chart(fig, width="stretch")

    # Handle Input from chat_input or sidebar quick starters
    user_query = st.chat_input(
        "Ask an analytical question about the 2024 sales dataset..."
    )
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

        run_id = initial_state["run_id"]
        log_run_start(run_id, user_query)

        with st.spinner("Analyzing dataset & executing analytical plan..."):
            try:
                agent_graph = get_compiled_agent()
                final_state = agent_graph.invoke(initial_state)

                # Update session state with turn outputs
                st.session_state["messages"] = final_state.get("messages", [])
                st.session_state["current_plan"] = final_state.get("plan")
                st.session_state["current_tool_results"] = final_state.get(
                    "tool_results", []
                )
                st.session_state["current_errors"] = final_state.get(
                    "errors", []
                )
                st.session_state["current_telemetry"] = final_state.get(
                    "telemetry", {}
                )
                st.session_state["last_query"] = user_query

                # Store any generated charts linked to the latest assistant message index
                latest_assistant_idx = len(st.session_state["messages"]) - 1
                charts = final_state.get("chart_artifacts", [])
                if charts:
                    st.session_state["turn_artifacts"][latest_assistant_idx] = (
                        charts
                    )

                # Record full historical turn snapshot
                turn_snapshot = {
                    "turn_number": len(st.session_state["turn_history"]) + 1,
                    "query": user_query,
                    "plan": final_state.get("plan"),
                    "tool_results": final_state.get("tool_results", []),
                    "errors": final_state.get("errors", []),
                    "telemetry": final_state.get("telemetry", {}),
                    "charts": charts,
                }
                st.session_state["turn_history"].append(turn_snapshot)

                st.rerun()

            except Exception as exc:  # noqa: BLE001
                st.error(f"Execution Error: {exc}")


# --- Right Column: Visible Execution Plan & Tool Trace ---
with col_trace:
    st.subheader("🗺️ Execution Plan & Trace")

    turn_history = st.session_state.get("turn_history", [])

    # Turn Selector if multi-turn conversation
    active_turn_data = None
    if turn_history:
        if len(turn_history) > 1:
            turn_options = [
                f"Turn {t['turn_number']}: {t['query'][:40]}..."
                for t in turn_history
            ]
            selected_turn_str = st.selectbox(
                "🔍 Inspect Turn History:",
                options=turn_options,
                index=len(turn_options) - 1,
                label_visibility="collapsed",
            )
            selected_idx = turn_options.index(selected_turn_str)
            active_turn_data = turn_history[selected_idx]
        else:
            active_turn_data = turn_history[-1]

    # Extract display variables
    if active_turn_data:
        disp_query = active_turn_data["query"]
        disp_plan = active_turn_data["plan"]
        disp_tool_results = active_turn_data["tool_results"]
        disp_errors = active_turn_data["errors"]
        disp_telemetry = active_turn_data["telemetry"]
    else:
        disp_query = st.session_state.get("last_query")
        disp_plan = st.session_state.get("current_plan")
        disp_tool_results = st.session_state.get("current_tool_results", [])
        disp_errors = st.session_state.get("current_errors", [])
        disp_telemetry = st.session_state.get("current_telemetry", {})

    # 1. Active Query & Step Progression Banner
    if disp_query:
        total_time_str = ""
        if disp_telemetry and "timings" in disp_telemetry:
            t_ms = disp_telemetry["timings"].get("total_turn_ms", 0)
            total_time_str = f" • ⏱️ {t_ms:.0f}ms"

        intent_name = (
            getattr(disp_plan, "intent", "UNKNOWN") if disp_plan else "DIRECT"
        )
        if hasattr(intent_name, "value"):
            intent_name = intent_name.value

        status_badge = "✅ COMPLETED" if not disp_errors else "⚠️ ISSUES"

        # Build step timeline pills HTML
        step_pills_html = []
        if disp_plan and hasattr(disp_plan, "steps") and disp_plan.steps:
            for s in disp_plan.steps:
                tool_val = getattr(s, "tool", "")
                if hasattr(tool_val, "value"):
                    tool_val = tool_val.value
                step_pills_html.append(
                    f"<span class='step-pill success'>Step {s.step_number}: <b>{tool_val}</b></span>"
                )
        pills_str = "".join(step_pills_html)

        st.markdown(
            f"""
            <div class="active-query-card">
                <div class="query-meta">
                    <span>🎯 Intent: <b>{intent_name.upper()}</b></span>
                    <span>• {status_badge}</span>
                    <span>{total_time_str}</span>
                </div>
                <div class="query-text">"{disp_query}"</div>
                <div class="step-pill-container">{pills_str}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.info(
            "💡 **No Active Execution Yet**\n\n"
            "Ask a question or select a Quick Starter to inspect the live planner graph, DuckDB execution, and tool results."
        )

    # 2. Error Display if any
    if disp_errors:
        st.error(
            "**Encountered Warning / Error**:\n"
            + "\n".join([f"- {err}" for err in disp_errors])
        )

    # 3. Main Trace Tabs
    tab_plan, tab_tools, tab_telemetry = st.tabs(
        ["🗺️ Analytical Plan", "📊 Tool Outputs & SQL", "⏱️ Telemetry & Logs"]
    )

    # --- TAB 1: Analytical Plan ---
    with tab_plan:
        if disp_plan:
            plan = disp_plan
            intent_val = getattr(plan, "intent", "")
            if hasattr(intent_val, "value"):
                intent_val = intent_val.value

            st.markdown(f"**Intent Classification**: `{intent_val.upper()}`")
            if hasattr(plan, "rationale") and plan.rationale:
                st.markdown(f"**Planner Rationale**: *{plan.rationale}*")

            st.divider()
            st.markdown("#### Planned Execution Steps:")
            for step in plan.steps:
                tool_val = getattr(step, "tool", "")
                if hasattr(tool_val, "value"):
                    tool_val = tool_val.value
                dep_text = (
                    f" *(depends on Step {step.depends_on})*"
                    if step.depends_on
                    else ""
                )

                with st.expander(
                    f"Step {step.step_number}: `{tool_val}`{dep_text}",
                    expanded=True,
                ):
                    st.markdown(f"**Description**: {step.description}")
                    if step.parameters:
                        st.markdown("**Parameters**:")
                        st.json(step.parameters)
        else:
            st.caption("No plan recorded for this turn.")

    # --- TAB 2: Tool Outputs & SQL Execution ---
    with tab_tools:
        if disp_tool_results:
            st.markdown("#### Deterministic Tool Results:")
            for tr in disp_tool_results:
                tool_val = getattr(tr, "tool", "")
                if hasattr(tool_val, "value"):
                    tool_val = tool_val.value
                step_num = getattr(tr, "step_number", "?")
                is_success = getattr(tr, "success", True)
                exec_time = getattr(tr, "execution_time_ms", None)

                icon = "✅" if is_success else "❌"
                timing_str = f" ({exec_time:.1f}ms)" if exec_time else ""
                header = f"{icon} Step {step_num}: `{tool_val}`{timing_str}"

                with st.expander(header, expanded=True):
                    _render_tool_result_ui(tr)
        else:
            st.caption(
                "No tools were invoked for this turn (direct conversational response)."
            )

    # --- TAB 3: Telemetry & Logs ---
    with tab_telemetry:
        if disp_telemetry and "timings" in disp_telemetry:
            timings = disp_telemetry["timings"]
            run_id_val = str(disp_telemetry.get("run_id", "turn"))

            st.markdown(f"**Run Identifier**: `{run_id_val}`")
            c1, c2, c3 = st.columns(3)
            c1.metric("Planner Latency", f"{timings.get('planner_ms', 0):.1f} ms")
            c2.metric(
                "Synthesizer Latency",
                f"{timings.get('synthesizer_ms', 0):.1f} ms",
            )
            c3.metric(
                "Total Graph Turn", f"{timings.get('total_turn_ms', 0):.1f} ms"
            )

        st.divider()
        st.markdown("#### Recent Application Logs (`logs/app.log`):")
        log_file_path = Path(__file__).resolve().parent / "logs" / "app.log"
        if log_file_path.exists():
            try:
                lines = log_file_path.read_text(encoding="utf-8").splitlines()
                recent_logs = "\n".join(lines[-25:])
                st.code(recent_logs, language="text")
            except Exception as exc:  # noqa: BLE001
                st.caption(f"Unable to read logs: {exc}")
        else:
            st.caption("No log file found.")
