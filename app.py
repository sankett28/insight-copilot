"""app.py
------
Fixed-Height Analytical Workspace for Insight Copilot.

Architecture:
  - Fixed-height application viewport with independent scrolling regions.
  - Left Center: Chat Workspace with independently scrolling message history & pinned bottom input.
  - Right: Analysis Inspector with independent scrolling for Status, Plan, Tool Outputs, SQL, and Telemetry.
  - Left Sidebar: Compact dataset health, metadata inspector, and session controls.
"""

from __future__ import annotations

import os
import re
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
# Page Configuration
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Insight Copilot — Analytical Workspace",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Custom CSS for Fixed-Height Analytical Workspace Layout
# ---------------------------------------------------------------------------

st.markdown(
    """
    <style>
    /* Prevent full-window body scroll */
    html, body {
        overflow: hidden !important;
        height: 100vh !important;
    }

    .block-container {
        padding-top: 1.25rem !important;
        padding-bottom: 0.5rem !important;
        padding-left: 1.5rem !important;
        padding-right: 1.5rem !important;
        max-width: 100% !important;
        height: calc(100vh - 1.5rem) !important;
        overflow: hidden !important;
    }

    /* Modern restrained styling */
    .stApp {
        background-color: #0f172a;
        color: #f8fafc;
    }

    /* Sidebar restrained styling */
    [data-testid="stSidebar"] {
        background-color: #0b1120 !important;
        border-right: 1px solid rgba(255, 255, 255, 0.08) !important;
    }

    /* Inspector header & cards */
    .inspector-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding-bottom: 0.4rem;
        margin-bottom: 0.6rem;
        border-bottom: 1px solid rgba(255, 255, 255, 0.1);
    }

    .status-badge {
        display: inline-flex;
        align-items: center;
        gap: 0.4rem;
        font-size: 0.8rem;
        font-weight: 600;
        letter-spacing: 0.03em;
        padding: 0.2rem 0.6rem;
        border-radius: 4px;
    }
    .status-completed {
        background: rgba(34, 197, 94, 0.15);
        color: #4ade80;
        border: 1px solid rgba(34, 197, 94, 0.3);
    }
    .status-failed {
        background: rgba(239, 68, 68, 0.15);
        color: #f87171;
        border: 1px solid rgba(239, 68, 68, 0.3);
    }
    .status-idle {
        background: rgba(148, 163, 184, 0.1);
        color: #94a3b8;
        border: 1px solid rgba(148, 163, 184, 0.2);
    }

    .section-title {
        font-size: 0.75rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        color: #94a3b8;
        margin-top: 0.8rem;
        margin-bottom: 0.4rem;
    }

    .plan-step-row {
        display: flex;
        align-items: flex-start;
        justify-content: space-between;
        padding: 0.4rem 0.6rem;
        margin-bottom: 0.3rem;
        background: rgba(30, 41, 59, 0.5);
        border: 1px solid rgba(255, 255, 255, 0.05);
        border-radius: 6px;
        font-size: 0.85rem;
    }
    .plan-step-num {
        font-weight: 600;
        color: #38bdf8;
        margin-right: 0.5rem;
    }
    .plan-step-desc {
        flex: 1;
        color: #e2e8f0;
    }
    .plan-step-status {
        font-weight: 600;
        margin-left: 0.5rem;
    }

    /* Welcome Card */
    .welcome-card {
        background: rgba(30, 41, 59, 0.4);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 8px;
        padding: 1.25rem 1.5rem;
        margin-bottom: 1rem;
    }
    .welcome-title {
        font-size: 1.25rem;
        font-weight: 700;
        color: #f8fafc;
        margin-bottom: 0.3rem;
    }
    .welcome-subtitle {
        font-size: 0.9rem;
        color: #94a3b8;
        margin-bottom: 0.9rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------------
# Cached Resources
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
st.session_state.setdefault("turn_history", [])
st.session_state.setdefault("current_plan", None)
st.session_state.setdefault("current_tool_results", [])
st.session_state.setdefault("current_errors", [])
st.session_state.setdefault("current_telemetry", {})
st.session_state.setdefault("last_query", None)
st.session_state.setdefault("pending_query", None)
if "db_conn" not in st.session_state:
    st.session_state["db_conn"] = create_session_connection()


# ---------------------------------------------------------------------------
# Helper: Extract SQL for current run from logs
# ---------------------------------------------------------------------------

def _extract_recent_sql_queries(run_id: str | None = None) -> list[str]:
    """Read recent SQL queries executed by deterministic tools from app.log."""
    log_file = Path(__file__).resolve().parent / "logs" / "app.log"
    if not log_file.exists():
        return []
    try:
        lines = log_file.read_text(encoding="utf-8").splitlines()
        sql_queries = []
        for line in reversed(lines[-60:]):
            if "Executing " in line and " SQL: " in line:
                match = re.search(r"Executing \w+ SQL:\s*(SELECT .+)$", line)
                if match:
                    sql_queries.append(match.group(1))
        # Deduplicate preserving order
        seen = set()
        deduped = []
        for q in sql_queries:
            if q not in seen:
                seen.add(q)
                deduped.append(q)
        return deduped[:5]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Helper: Tool Result Formatter
# ---------------------------------------------------------------------------

def _render_tool_result_ui(tr: Any) -> None:
    """Render structured presentation of tool execution results."""
    error_msg = getattr(tr, "error", None)
    if error_msg:
        st.error(f"**Error**: {error_msg}")
        return

    data = getattr(tr, "result", None) or getattr(tr, "data", None)
    if data is None:
        st.caption("No tabular data returned.")
        return

    if isinstance(data, list):
        if len(data) > 0:
            st.dataframe(data, width="stretch")
        else:
            st.caption("Query returned 0 matching records.")
        return

    if isinstance(data, dict):
        # Data Profile
        if "numeric_summary" in data and "row_count" in data:
            c1, c2 = st.columns(2)
            c1.metric("Rows", f"{data.get('row_count', 0):,}")
            c2.metric("Columns", data.get("column_count", 0))

            warnings = data.get("data_quality_warnings", [])
            for w in warnings:
                st.warning(w)

            num_summary = data.get("numeric_summary", {})
            if num_summary:
                summary_rows = [
                    {
                        "Metric": col_name,
                        "Min": stats.get("min"),
                        "Max": stats.get("max"),
                        "Mean": stats.get("mean"),
                    }
                    for col_name, stats in num_summary.items()
                ]
                st.dataframe(summary_rows, width="stretch")
            return

        # Correlation
        if "correlation_coefficient" in data and "field_a" in data:
            st.metric(
                f"{data['field_a']} vs {data['field_b']}",
                f"r = {data['correlation_coefficient']:+.4f}",
            )
            st.caption(data.get("caveat", ""))
            return

        # Anomaly Detection
        if "total_anomalies" in data and "rows" in data:
            st.metric(
                f"Anomalies ({data.get('method', '').upper()})",
                data.get("total_anomalies", 0),
            )
            if data.get("rows"):
                st.dataframe(data["rows"], width="stretch")
            return

        # Data Clean
        if "cluster_mappings" in data and "distinct_before" in data:
            st.success(data.get("message", "Cleaning completed."))
            mappings = data.get("cluster_mappings", {})
            for col, cmap in mappings.items():
                if cmap:
                    st.caption(f"Mappings for **{col}**:")
                    map_rows = [{"Raw": k, "Cleaned": v} for k, v in cmap.items()]
                    st.dataframe(map_rows, width="stretch")
            return

        # Rows inside dict
        if "rows" in data and isinstance(data["rows"], list):
            st.dataframe(data["rows"], width="stretch")
            return

        st.json(data)
        return

    st.write(data)


# ---------------------------------------------------------------------------
# Sidebar: Dataset Information & Controls
# ---------------------------------------------------------------------------

with st.sidebar:
    st.markdown("### INSIGHT COPILOT")
    st.caption("Deterministic Analytical Assistant")

    st.divider()

    # Dataset Status
    if dataset_status.get("is_valid"):
        st.markdown("**Dataset**")
        st.text("Sales_Dataset_2024.xlsx")
        st.markdown(
            f"`{dataset_status['row_count']:,} rows` • `{dataset_status['column_count']} columns`"
        )
    else:
        st.error(f"Dataset error: {dataset_status.get('error')}")

    # Column Metadata Expander
    with st.expander("📋 View Column Metadata", expanded=False):
        for col in dataset_schema.columns:
            st.markdown(
                f"- **`{col.name}`** (`{col.data_type}`)  \n  *{col.semantic_role}*"
            )

    st.divider()

    # Starter Questions
    st.markdown("**Starter Queries**")
    starters = [
        "What is total revenue by region?",
        "Clean Region typos and show revenue",
        "Compare North and South profit margin",
        "Show monthly revenue trend",
        "Which 5 products generate most profit?",
        "What is the correlation between Units Sold and Revenue?",
    ]
    for sq in starters:
        if st.button(sq, width="stretch", key=f"btn_{sq}"):
            st.session_state["pending_query"] = sq

    st.divider()

    # Session Actions
    c_btn1, c_btn2 = st.columns(2)
    with c_btn1:
        if st.button("🔄 Reset Data", width="stretch"):
            reset_to_raw_dataset(st.session_state.get("db_conn"))
            st.toast("Reset to raw dataset.", icon="🔄")
            st.rerun()
    with c_btn2:
        if st.button("🗑️ Clear Chat", width="stretch"):
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
# Main Layout: Fixed-Height Split Viewport
# ---------------------------------------------------------------------------

col_chat, col_inspector = st.columns([1.5, 1.0], gap="medium")

# ===========================================================================
# 1. Chat Workspace (Left Column)
# ===========================================================================

with col_chat:
    messages = st.session_state.get("messages", [])
    turn_artifacts = st.session_state.get("turn_artifacts", {})

    # Fixed height scrollable chat message container
    chat_container = st.container(height=650)

    with chat_container:
        # Compact Landing State (only displayed when conversation is empty)
        if not messages:
            st.markdown(
                """
                <div class="welcome-card">
                    <div class="welcome-title">Insight Copilot</div>
                    <div class="welcome-subtitle">Deterministic analytical workspace for your 2024 sales data.</div>
                    <div style="font-size: 0.85rem; color: #cbd5e1; line-height: 1.6;">
                        Ask questions about sales revenue, margins, temporal trends, statistical anomalies, or data quality.<br>
                        Every computation runs deterministically in DuckDB with verified execution traces.
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            with st.expander("ℹ️ How Insight Copilot works", expanded=False):
                st.markdown(
                    """
                    1. **Intent & Planning**: Maps natural questions to structured analytical operations.
                    2. **Deterministic Execution**: Executes precise SQL in DuckDB with zero extrapolation.
                    3. **Grounded Synthesis**: Produces answers with explicit `[Step X]` evidence citations.
                    """
                )

        # Render Conversation Message Stream
        for idx, msg in enumerate(messages):
            role_label = "user" if msg.role == Role.USER else "assistant"
            with st.chat_message(role_label):
                st.markdown(msg.content)

                # Render attached Plotly figures
                if role_label == "assistant" and idx in turn_artifacts:
                    for chart_dict in turn_artifacts[idx]:
                        fig = go.Figure(chart_dict)
                        fig.update_layout(
                            template="plotly_dark",
                            margin=dict(l=20, r=20, t=35, b=20),
                            height=360,
                        )
                        st.plotly_chart(fig, width="stretch")

    # Pinned Chat Input at bottom of Chat Workspace
    user_query = st.chat_input("Ask about your dataset (e.g., total revenue by region)...")
    if st.session_state.get("pending_query"):
        user_query = st.session_state["pending_query"]
        st.session_state["pending_query"] = None

    if user_query:
        # Construct turn state
        initial_state = create_initial_state(
            query=user_query,
            history=st.session_state.get("messages", []),
        )
        run_id = initial_state["run_id"]
        log_run_start(run_id, user_query)

        with st.spinner("Analyzing dataset..."):
            try:
                agent_graph = get_compiled_agent()
                final_state = agent_graph.invoke(initial_state)

                # Update session state
                st.session_state["messages"] = final_state.get("messages", [])
                st.session_state["current_plan"] = final_state.get("plan")
                st.session_state["current_tool_results"] = final_state.get("tool_results", [])
                st.session_state["current_errors"] = final_state.get("errors", [])
                st.session_state["current_telemetry"] = final_state.get("telemetry", {})
                st.session_state["last_query"] = user_query

                # Attach charts to assistant message
                latest_assistant_idx = len(st.session_state["messages"]) - 1
                charts = final_state.get("chart_artifacts", [])
                if charts:
                    st.session_state["turn_artifacts"][latest_assistant_idx] = charts

                # Save turn history snapshot
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


# ===========================================================================
# 2. Analysis Inspector (Right Column)
# ===========================================================================

with col_inspector:
    st.markdown("### Analysis Inspector")

    turn_history = st.session_state.get("turn_history", [])
    active_turn = None

    if turn_history:
        if len(turn_history) > 1:
            turn_options = [
                f"Turn {t['turn_number']}: {t['query'][:32]}..."
                for t in turn_history
            ]
            selected_str = st.selectbox(
                "Turn History",
                options=turn_options,
                index=len(turn_options) - 1,
                label_visibility="collapsed",
            )
            idx = turn_options.index(selected_str)
            active_turn = turn_history[idx]
        else:
            active_turn = turn_history[-1]

    # Resolve active variables
    if active_turn:
        i_query = active_turn["query"]
        i_plan = active_turn["plan"]
        i_tool_results = active_turn["tool_results"]
        i_errors = active_turn["errors"]
        i_telemetry = active_turn["telemetry"]
    else:
        i_query = st.session_state.get("last_query")
        i_plan = st.session_state.get("current_plan")
        i_tool_results = st.session_state.get("current_tool_results", [])
        i_errors = st.session_state.get("current_errors", [])
        i_telemetry = st.session_state.get("current_telemetry", {})

    # Fixed height scrollable inspector container
    inspector_container = st.container(height=650)

    with inspector_container:
        if i_query or i_plan or i_tool_results:
            # ---------------------------------------------------------------
            # A. STATUS SECTION
            # ---------------------------------------------------------------
            intent_name = getattr(i_plan, "intent", "DIRECT") if i_plan else "DIRECT"
            if hasattr(intent_name, "value"):
                intent_name = intent_name.value

            duration_str = ""
            if i_telemetry and "timings" in i_telemetry:
                t_ms = i_telemetry["timings"].get("total_turn_ms", 0)
                duration_str = f" • {t_ms:.0f}ms"

            status_class = "status-completed" if not i_errors else "status-failed"
            status_label = "● COMPLETED" if not i_errors else "● FAILED"

            st.markdown(
                f"""
                <div class="inspector-header">
                    <div>
                        <span class="status-badge {status_class}">{status_label}</span>
                    </div>
                    <div style="font-size: 0.8rem; color: #94a3b8;">
                        Intent: <b style="color: #f1f5f9;">{intent_name.upper()}</b>{duration_str}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            if i_errors:
                st.error("\n".join([f"• {e}" for e in i_errors]))

            # ---------------------------------------------------------------
            # B. PLAN SECTION
            # ---------------------------------------------------------------
            st.markdown('<div class="section-title">Analysis Plan</div>', unsafe_allow_html=True)
            if i_plan and hasattr(i_plan, "steps") and i_plan.steps:
                # Map step status
                step_success_map = {
                    getattr(tr, "step_number", None): getattr(tr, "success", True)
                    for tr in i_tool_results
                }

                for s in i_plan.steps:
                    s_num = getattr(s, "step_number", 1)
                    s_desc = getattr(s, "description", "")
                    s_tool = getattr(s, "tool", "")
                    if hasattr(s_tool, "value"):
                        s_tool = s_tool.value

                    # Status indicator
                    is_done = step_success_map.get(s_num)
                    if is_done is True:
                        mark = "<span style='color: #4ade80;'>✓</span>"
                    elif is_done is False:
                        mark = "<span style='color: #f87171;'>✕</span>"
                    elif s.depends_on and any(step_success_map.get(d) is False for d in s.depends_on):
                        mark = "<span style='color: #fbbf24;'>⊘</span>"
                    else:
                        mark = "<span style='color: #4ade80;'>✓</span>"

                    st.markdown(
                        f"""
                        <div class="plan-step-row">
                            <span class="plan-step-num">{s_num}.</span>
                            <span class="plan-step-desc">{s_desc} <code style="font-size: 0.75rem;">({s_tool})</code></span>
                            <span class="plan-step-status">{mark}</span>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
            else:
                st.caption("Direct conversational synthesis (no tool steps required).")

            # ---------------------------------------------------------------
            # C. TOOL OUTPUTS SECTION
            # ---------------------------------------------------------------
            st.markdown('<div class="section-title">Tool Outputs</div>', unsafe_allow_html=True)
            if i_tool_results:
                for tr in i_tool_results:
                    tool_name = getattr(tr, "tool", "")
                    if hasattr(tool_name, "value"):
                        tool_name = tool_name.value
                    s_num = getattr(tr, "step_number", "?")
                    is_ok = getattr(tr, "success", True)
                    t_time = getattr(tr, "execution_time_ms", None)

                    icon = "✓" if is_ok else "✕"
                    t_str = f" ({t_time:.0f}ms)" if t_time else ""
                    exp_title = f"{icon} Step {s_num}: {tool_name}{t_str}"

                    with st.expander(exp_title, expanded=False):
                        _render_tool_result_ui(tr)
            else:
                st.caption("No tool executions recorded.")

            # ---------------------------------------------------------------
            # D. SQL SECTION (Collapsed by default)
            # ---------------------------------------------------------------
            st.markdown('<div class="section-title">Deterministic SQL</div>', unsafe_allow_html=True)
            sql_queries = _extract_recent_sql_queries()
            with st.expander("▶ SQL generated by deterministic tool", expanded=False):
                if sql_queries:
                    for q in sql_queries:
                        st.code(q, language="sql")
                else:
                    st.caption("No SQL queries recorded for this turn.")

            # ---------------------------------------------------------------
            # E. TELEMETRY SECTION (Collapsed by default)
            # ---------------------------------------------------------------
            st.markdown('<div class="section-title">Telemetry</div>', unsafe_allow_html=True)
            with st.expander("▶ Telemetry & Durations", expanded=False):
                if i_telemetry and "timings" in i_telemetry:
                    t_info = i_telemetry["timings"]
                    c1, c2 = st.columns(2)
                    c1.metric("Planner", f"{t_info.get('planner_ms', 0):.1f} ms")
                    c2.metric("Synthesizer", f"{t_info.get('synthesizer_ms', 0):.1f} ms")
                    st.caption(f"Run ID: `{i_telemetry.get('run_id', 'turn')}`")
                else:
                    st.caption("No telemetry data captured.")

        else:
            st.markdown(
                """
                <div style="padding: 2rem 1rem; text-align: center; color: #64748b;">
                    <div style="font-size: 1.5rem; margin-bottom: 0.5rem;">📊</div>
                    <div style="font-weight: 600; font-size: 0.9rem; color: #94a3b8;">Analysis Inspector</div>
                    <div style="font-size: 0.8rem; margin-top: 0.25rem;">
                        Submit a query to inspect live plan execution, deterministic tool outputs, and SQL queries.
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
