"""
utils/ui_helpers.py
-------------------
UI utility helpers including deterministic Streamlit chart key generation.
"""

from __future__ import annotations

import re
from typing import Any


def generate_chart_key(
    run_id: str | None = None,
    turn_idx: int | str = 0,
    step_num: int | str = 0,
    chart_idx: int = 0,
    context: str = "chat",
) -> str:
    """Generate a deterministic, unique Streamlit element key for a Plotly chart.

    Identifies the chart by:
        - context: UI rendering surface (e.g. 'chat_history', 'live_stream', 'inspector')
        - run_id / turn_idx: Execution turn identity
        - step_num: Plan step index (if applicable)
        - chart_idx: Position in chart artifacts list

    Example outputs:
        chart_chat_history_turn_0_step_1_idx_0
        chart_live_stream_91e25d25_step_2_idx_0
        chart_inspector_turn_1_step_2_idx_0
    """
    clean_context = re.sub(r"[^a-zA-Z0-9_]", "_", str(context)).lower()

    if run_id:
        clean_run = re.sub(r"[^a-zA-Z0-9_]", "_", str(run_id))
    else:
        clean_run = f"turn_{turn_idx}"

    clean_step = str(step_num) if step_num is not None else "0"
    clean_idx = str(chart_idx)

    return f"chart_{clean_context}_{clean_run}_step_{clean_step}_idx_{clean_idx}"


def is_plotly_figure_dict(obj: Any) -> bool:
    """Check if an object has the structure of a serialized Plotly figure dictionary."""
    return (
        isinstance(obj, dict)
        and "data" in obj
        and "layout" in obj
        and isinstance(obj.get("data"), list)
    )


def sanitize_markdown_currency(text: str) -> str:
    r"""Escape unescaped dollar signs ($) to prevent Streamlit KaTeX LaTeX math mode corruption.

    In Streamlit markdown rendering, unescaped '$' characters are interpreted as opening/closing
    inline LaTeX math blocks, which strips spaces, italicises text, and breaks number formatting.
    Replacing unescaped '$' with '\$' ensures dollar amounts (e.g. \$2,915,878.00) render cleanly
    in standard font layout.
    """
    if not text:
        return text
    return re.sub(r"(?<!\\)\$", r"\\$", text)
