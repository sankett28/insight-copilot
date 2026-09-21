"""
app.py
------
Streamlit application entry-point for Insight Copilot.

Run with:
    streamlit run app.py
"""

from __future__ import annotations

import os
import streamlit as st
import plotly.graph_objects as go

from agent.graph import build_graph
from agent.state import create_initial_state
from llm.factory import get_llm
from models.schemas import Message, Role
from utils.data_loader import get_schema_description, validate_dataset

# ---------------------------------------------------------------------------
# Page configuration — must be the first Streamlit call.
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Insight Copilot",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Initialize dataset startup validation and caching
@st.cache_resource
def init_data_layer():
    val = validate_dataset()
    schema = get_schema_description()
    return val, schema

dataset_status, dataset_schema = init_data_layer()

# Initialize session state for conversation history and trace
if "messages" not in st.session_state:
    st.session_state.messages = []
if "current_plan" not in st.session_state:
    st.session_state.current_plan = None
if "current_tool_results" not in st.session_state:
    st.session_state.current_tool_results = []
if "current_charts" not in st.session_state:
    st.session_state.current_charts = []

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

with st.sidebar:
    st.title("📊 Dataset & System Info")
    if dataset_status.get("is_valid"):
        st.success(f"**Canonical Dataset Loaded**\n\n- Rows: {dataset_status['row_count']}\n- Columns: {dataset_status['column_count']}")
    else:
        st.error(f"Dataset error: {dataset_status.get('error')}")

    st.divider()
    st.subheader("📋 Schema Metadata")
    for col in dataset_schema.columns:
        st.caption(f"• **{col.name}** (`{col.data_type}`) — *{col.semantic_role}*")

    st.divider()
    st.caption("Insight Copilot v0.2.0 · Refactored Architecture")

# ---------------------------------------------------------------------------
# Main Content Layout
# ---------------------------------------------------------------------------

st.title("🔍 Insight Copilot")
st.caption("Deterministic analytical assistant powered by LangGraph & DuckDB")

st.divider()

col_chat, col_trace = st.columns([1.6, 1.0])

# Right column: Visible Execution Plan & Tool Trace
with col_trace:
    st.subheader("🗺️ Execution Plan & Trace")
    if st.session_state.current_plan:
        plan = st.session_state.current_plan
        st.markdown(f"**Intent**: `{plan.intent.value}`")
        st.markdown(f"**Rationale**: *{plan.rationale}*")
        st.write("---")
        st.markdown("**Plan Steps**:")
        for step in plan.steps:
            deps = f" (depends on {step.depends_on})" if step.depends_on else ""
            st.markdown(f"**Step {step.step_number}**: `{step.tool.value}`{deps}")
            st.caption(f"{step.description}")
            if step.parameters:
                st.json(step.parameters, expanded=False)
    else:
        st.info("Ask a question to view the agent's analytical execution plan.")

    if st.session_state.current_tool_results:
        st.write("---")
        st.markdown("**Tool Trace Outputs**:")
        for tr in st.session_state.current_tool_results:
            status_icon = "✅" if tr.success else "❌"
            with st.expander(f"{status_icon} Step {tr.step_number}: {tr.tool.value}"):
                if tr.error:
                    st.error(tr.error)
                elif isinstance(tr.data, list):
                    st.dataframe(tr.data, use_container_width=True)
                else:
                    st.json(tr.data)

# Left column: Conversation & Interaction
with col_chat:
    st.subheader("💬 Conversation")

    # Display historical chat messages
    for msg in st.session_state.messages:
        role_label = "user" if msg.role == Role.USER else "assistant"
        with st.chat_message(role_label):
            st.markdown(msg.content)

    # Render latest charts in conversation stream if available
    for chart_dict in st.session_state.current_charts:
        fig = go.Figure(chart_dict)
        st.plotly_chart(fig, use_container_width=True)

    # Chat input
    if prompt := st.chat_input("Ask a question about sales revenue, profit, categories, or trends..."):
        # Display user message immediately
        with st.chat_message("user"):
            st.markdown(prompt)

        # Build clean initial state for this turn while preserving message history
        initial_state = create_initial_state(
            query=prompt,
            history=st.session_state.messages,
        )

        with st.spinner("Analyzing dataset & executing plan..."):
            try:
                # Initialize LLM & Graph
                llm = get_llm()
                graph = build_graph(llm)

                final_state = graph.invoke(initial_state)

                # Update session state with completed turn results
                st.session_state.messages = final_state.get("messages", [])
                st.session_state.current_plan = final_state.get("plan")
                st.session_state.current_tool_results = final_state.get("tool_results", [])
                st.session_state.current_charts = final_state.get("chart_artifacts", [])

                st.rerun()

            except Exception as exc:  # noqa: BLE001
                st.error(f"Execution Error: {exc}")
