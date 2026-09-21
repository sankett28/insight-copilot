"""
app.py
------
Streamlit application entry-point for Insight Copilot.

Run with:
    streamlit run app.py

At this skeleton stage the UI renders a placeholder chat interface.
Full implementation (dataset upload, chat, plan trace, chart rendering)
will be added in the next development phase.
"""

from __future__ import annotations

import streamlit as st

# ---------------------------------------------------------------------------
# Page configuration — must be the first Streamlit call.
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Insight Copilot",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

with st.sidebar:
    st.title("⚙️ Configuration")
    st.info(
        "Dataset upload and LLM configuration will appear here once the "
        "data layer is implemented."
    )
    st.divider()
    st.caption("Insight Copilot · Skeleton v0.1.0")

# ---------------------------------------------------------------------------
# Main content
# ---------------------------------------------------------------------------

st.title("🔍 Insight Copilot")
st.caption("A LangGraph-powered analytical assistant")

st.warning(
    "🚧 **Skeleton build** — agent, tools, and data layer are not yet connected. "
    "This UI will become functional in the next development phase.",
    icon="🚧",
)

# Placeholder chat area.
st.divider()
col_chat, col_trace = st.columns([2, 1])

with col_chat:
    st.subheader("💬 Conversation")
    st.info("Chat interface will render here.")

with col_trace:
    st.subheader("🗺️ Execution Plan")
    st.info(
        "The agent's structured plan and tool trace will be shown here "
        "after each query."
    )
