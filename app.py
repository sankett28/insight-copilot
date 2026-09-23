"""app.py
------
Modern Analytical Workspace for Insight Copilot (Antigravity & ChatGPT Style).

Layout:
  - Top Navigation Bar: Clean header with workspace title, engine badges, and model indicator.
  - Left Panel: Interactive Chat Workspace with pill-style input box & live response streaming.
  - Right Panel: Analysis Inspector & Monospace Terminal Trace with Plan, Tool Outputs, SQL, and Real-Time Logs.
  - Left Sidebar: Dataset health inspector, column metadata explorer, quick starters, and session resets.
"""

from __future__ import annotations

import os
import re
import time
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
# Custom CSS for Modern Antigravity / ChatGPT Style UI
# ---------------------------------------------------------------------------

st.markdown(
    """
    <style>
    /* 1. Hide default Streamlit top header & footer to prevent clipping */
    header[data-testid="stHeader"] {
        display: none !important;
    }
    #MainMenu, footer {
        visibility: hidden !important;
        display: none !important;
    }

    /* 2. Main Viewport & Theme */
    html, body {
        overflow: hidden !important;
        height: 100vh !important;
        margin: 0 !important;
        padding: 0 !important;
    }

    .stApp {
        background-color: #0d1117 !important;
        color: #e6edf3 !important;
    }

    .block-container {
        padding-top: 0.6rem !important;
        padding-bottom: 0.25rem !important;
        padding-left: 1.25rem !important;
        padding-right: 1.25rem !important;
        max-width: 100% !important;
        height: 100vh !important;
        box-sizing: border-box !important;
    }

    /* 3. Top Navigation Bar */
    .app-top-bar {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 0.35rem 0.5rem 0.55rem 0.5rem;
        margin-bottom: 0.5rem;
        border-bottom: 1px solid rgba(255, 255, 255, 0.08);
    }
    .top-bar-left {
        display: flex;
        align-items: center;
    }
    .app-title {
        font-size: 1.05rem;
        font-weight: 700;
        color: #f0f6fc;
        letter-spacing: -0.01em;
    }
    .app-tagline {
        font-size: 0.8rem;
        color: #8b949e;
        margin-left: 0.6rem;
        padding-left: 0.6rem;
        border-left: 1px solid rgba(255, 255, 255, 0.12);
    }
    .top-bar-right {
        display: flex;
        align-items: center;
        gap: 0.5rem;
    }
    .top-badge {
        font-size: 0.75rem;
        font-weight: 500;
        padding: 0.15rem 0.55rem;
        border-radius: 12px;
    }
    .db-badge {
        background: rgba(56, 189, 248, 0.12);
        color: #38bdf8;
        border: 1px solid rgba(56, 189, 248, 0.25);
    }
    .model-badge {
        background: rgba(168, 85, 247, 0.12);
        color: #c084fc;
        border: 1px solid rgba(168, 85, 247, 0.25);
    }

    /* 4. Sidebar Styling */
    [data-testid="stSidebar"] {
        background-color: #07090e !important;
        border-right: 1px solid rgba(255, 255, 255, 0.08) !important;
    }

    /* 5. Chat Message Container */
    [data-testid="stVerticalBlockBorderWrapper"] {
        border-color: rgba(255, 255, 255, 0.08) !important;
        background-color: rgba(22, 27, 34, 0.4) !important;
        border-radius: 12px !important;
    }

    /* 6. Modern Pill Chat Input Styling (ChatGPT / Antigravity Style) */
    [data-testid="stChatInput"] {
        padding-top: 0.3rem !important;
        padding-bottom: 0.15rem !important;
    }
    [data-testid="stChatInput"] > div {
        border-radius: 28px !important;
        background-color: #161b22 !important;
        border: 1px solid rgba(255, 255, 255, 0.15) !important;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.25) !important;
        padding: 2px 8px !important;
    }
    [data-testid="stChatInput"] textarea {
        background-color: transparent !important;
        color: #f0f6fc !important;
        border: none !important;
        font-size: 0.92rem !important;
        line-height: 1.4 !important;
        padding: 8px 14px !important;
    }
    [data-testid="stChatInput"] textarea::placeholder {
        color: #8b949e !important;
        font-size: 0.9rem !important;
    }
    [data-testid="stChatInput"] button {
        border-radius: 50% !important;
        background-color: #238636 !important;
        color: white !important;
        border: none !important;
    }

    /* 7. Inspector Header & Status */
    .inspector-top-bar {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding-bottom: 0.4rem;
        margin-bottom: 0.4rem;
        border-bottom: 1px solid rgba(255, 255, 255, 0.08);
    }

    .status-badge {
        display: inline-flex;
        align-items: center;
        gap: 0.35rem;
        font-size: 0.78rem;
        font-weight: 600;
        letter-spacing: 0.03em;
        padding: 0.15rem 0.55rem;
        border-radius: 4px;
    }
    .status-completed {
        background: rgba(35, 134, 54, 0.2);
        color: #3fb950;
        border: 1px solid rgba(35, 134, 54, 0.4);
    }
    .status-failed {
        background: rgba(218, 54, 51, 0.2);
        color: #f85149;
        border: 1px solid rgba(218, 54, 51, 0.4);
    }

    .section-title {
        font-size: 0.72rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        color: #8b949e;
        margin-top: 0.5rem;
        margin-bottom: 0.3rem;
    }

    .plan-step-row {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 0.35rem 0.55rem;
        margin-bottom: 0.25rem;
        background: rgba(22, 27, 34, 0.6);
        border: 1px solid rgba(255, 255, 255, 0.06);
        border-radius: 6px;
        font-size: 0.83rem;
    }
    .plan-step-num {
        font-weight: 600;
        color: #58a6ff;
        margin-right: 0.4rem;
    }
    .plan-step-desc {
        flex: 1;
        color: #c9d1d9;
    }

    /* Welcome Card */
    .welcome-card {
        background: rgba(22, 27, 34, 0.5);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 10px;
        padding: 1.1rem 1.3rem;
        margin-bottom: 0.8rem;
    }
    .welcome-title {
        font-size: 1.15rem;
        font-weight: 700;
        color: #f0f6fc;
        margin-bottom: 0.2rem;
    }
    .welcome-subtitle {
        font-size: 0.85rem;
        color: #8b949e;
        margin-bottom: 0.75rem;
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


def _extract_recent_logs(max_lines: int = 35) -> str:
    """Read recent log lines from app.log for live terminal inspection."""
    log_file = Path(__file__).resolve().parent / "logs" / "app.log"
    if not log_file.exists():
        return "No active log file found."
    try:
        lines = log_file.read_text(encoding="utf-8").splitlines()
        return "\n".join(lines[-max_lines:])
    except Exception as exc:
        return f"Error reading log file: {exc}"


# ---------------------------------------------------------------------------
# Helper: Streaming Generator
# ---------------------------------------------------------------------------

def _stream_text(text: str, delay: float = 0.012):
    """Yield word chunks for smooth assistant text streaming."""
    words = text.split(" ")
    for i, word in enumerate(words):
        yield word + (" " if i < len(words) - 1 else "")
        time.sleep(delay)


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
    st.markdown("### 📊 Insight Copilot")
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
# Top Navigation Bar (Antigravity Style)
# ---------------------------------------------------------------------------

active_model_name = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")

st.markdown(
    f"""
    <div class="app-top-bar">
        <div class="top-bar-left">
            <span class="app-title">📊 Insight Copilot</span>
            <span class="app-tagline">2024 Sales Intelligence Workspace</span>
        </div>
        <div class="top-bar-right">
            <span class="top-badge db-badge">⚡ DuckDB SQL Engine</span>
            <span class="top-badge model-badge">🤖 {active_model_name}</span>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------------
# Main Layout: Responsive Split Viewport (Height 490px)
# ---------------------------------------------------------------------------

col_chat, col_inspector = st.columns([1.45, 1.0], gap="medium")

# ===========================================================================
# 1. Chat Workspace (Left Column)
# ===========================================================================

with col_chat:
    messages = st.session_state.get("messages", [])
    turn_artifacts = st.session_state.get("turn_artifacts", {})

    # Responsive scrollable chat message container
    chat_container = st.container(height=490)

    with chat_container:
        # Compact Landing State (only displayed when conversation is empty)
        if not messages:
            st.markdown(
                """
                <div class="welcome-card">
                    <div class="welcome-title">Insight Copilot</div>
                    <div class="welcome-subtitle">Deterministic analytical workspace for your 2024 sales data.</div>
                    <div style="font-size: 0.85rem; color: #8b949e; line-height: 1.6;">
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
                            height=320,
                        )
                        st.plotly_chart(fig, width="stretch")

    # Pinned Chat Input at bottom of Chat Workspace (always visible)
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

        # Display user message immediately in chat
        with chat_container:
            with st.chat_message("user"):
                st.markdown(user_query)

        with st.spinner("Analyzing dataset..."):
            try:
                agent_graph = get_compiled_agent()
                final_state = agent_graph.invoke(initial_state)

                final_answer = final_state.get("final_answer") or "Analysis completed."
                charts = final_state.get("chart_artifacts", [])

                # Live Response Streaming in Chat
                with chat_container:
                    with st.chat_message("assistant"):
                        st.write_stream(_stream_text(final_answer))
                        if charts:
                            for chart_dict in charts:
                                fig = go.Figure(chart_dict)
                                fig.update_layout(
                                    template="plotly_dark",
                                    margin=dict(l=20, r=20, t=35, b=20),
                                    height=320,
                                )
                                st.plotly_chart(fig, width="stretch")

                # Update session state with completed turn
                st.session_state["messages"] = final_state.get("messages", [])
                st.session_state["current_plan"] = final_state.get("plan")
                st.session_state["current_tool_results"] = final_state.get("tool_results", [])
                st.session_state["current_errors"] = final_state.get("errors", [])
                st.session_state["current_telemetry"] = final_state.get("telemetry", {})
                st.session_state["last_query"] = user_query

                # Attach charts to assistant message
                latest_assistant_idx = len(st.session_state["messages"]) - 1
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
# 2. Analysis Inspector & Terminal Trace (Right Column - Antigravity Style)
# ===========================================================================

with col_inspector:
    turn_history = st.session_state.get("turn_history", [])
    active_turn = None

    if turn_history:
        if len(turn_history) > 1:
            turn_options = [
                f"Turn {t['turn_number']}: {t['query'][:30]}..."
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

    # Responsive scrollable inspector container
    inspector_container = st.container(height=490)

    with inspector_container:
        if i_query or i_plan or i_tool_results:
            # ---------------------------------------------------------------
            # A. Top Status Bar
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
                <div class="inspector-top-bar">
                    <div>
                        <span class="status-badge {status_class}">{status_label}</span>
                    </div>
                    <div style="font-size: 0.8rem; color: #8b949e;">
                        Intent: <b style="color: #f0f6fc;">{intent_name.upper()}</b>{duration_str}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            if i_errors:
                st.error("\n".join([f"• {e}" for e in i_errors]))

            # ---------------------------------------------------------------
            # Inspector Tabs: Plan, Outputs & SQL, Live Terminal
            # ---------------------------------------------------------------
            tab_plan, tab_tools, tab_term = st.tabs(
                ["🗺️ Plan", "📊 Tool Data & SQL", "💻 Terminal & Logs"]
            )

            with tab_plan:
                st.markdown('<div class="section-title">Execution Plan Steps</div>', unsafe_allow_html=True)
                if i_plan and hasattr(i_plan, "steps") and i_plan.steps:
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

                        is_done = step_success_map.get(s_num)
                        if is_done is True:
                            mark = "<span style='color: #3fb950;'>✓</span>"
                        elif is_done is False:
                            mark = "<span style='color: #f85149;'>✕</span>"
                        elif s.depends_on and any(step_success_map.get(d) is False for d in s.depends_on):
                            mark = "<span style='color: #d29922;'>⊘</span>"
                        else:
                            mark = "<span style='color: #3fb950;'>✓</span>"

                        st.markdown(
                            f"""
                            <div class="plan-step-row">
                                <span class="plan-step-num">{s_num}.</span>
                                <span class="plan-step-desc">{s_desc} <code style="font-size: 0.75rem; color: #58a6ff;">({s_tool})</code></span>
                                <span>{mark}</span>
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )
                else:
                    st.caption("Direct synthesis (no tool steps).")

            with tab_tools:
                st.markdown('<div class="section-title">Deterministic Outputs</div>', unsafe_allow_html=True)
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

                        with st.expander(exp_title, expanded=True):
                            _render_tool_result_ui(tr)

                # SQL queries expander
                st.markdown('<div class="section-title">Generated SQL</div>', unsafe_allow_html=True)
                sql_queries = _extract_recent_sql_queries()
                with st.expander("▶ View Deterministic SQL", expanded=False):
                    if sql_queries:
                        for q in sql_queries:
                            st.code(q, language="sql")
                    else:
                        st.caption("No SQL queries recorded for this turn.")

            with tab_term:
                st.markdown('<div class="section-title">Live Execution Logs (Antigravity Trace)</div>', unsafe_allow_html=True)
                logs_text = _extract_recent_logs(35)
                st.code(logs_text, language="text")

                if i_telemetry and "timings" in i_telemetry:
                    t_info = i_telemetry["timings"]
                    c1, c2 = st.columns(2)
                    c1.metric("Planner", f"{t_info.get('planner_ms', 0):.1f} ms")
                    c2.metric("Synthesizer", f"{t_info.get('synthesizer_ms', 0):.1f} ms")
                    st.caption(f"Run ID: `{i_telemetry.get('run_id', 'turn')}`")

        else:
            st.markdown(
                """
                <div style="padding: 2.5rem 1rem; text-align: center; color: #8b949e;">
                    <div style="font-size: 1.6rem; margin-bottom: 0.5rem;">🗺️</div>
                    <div style="font-weight: 600; font-size: 0.95rem; color: #f0f6fc;">Analysis Inspector</div>
                    <div style="font-size: 0.8rem; margin-top: 0.35rem; color: #8b949e;">
                        Submit a query to inspect live plan steps, deterministic tool outputs, and real-time logs.
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
