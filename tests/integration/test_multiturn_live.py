"""
tests/integration/test_multiturn_live.py
----------------------------------------
Live integration tests for multi-turn conversational agent workflows using StateGraph.

Requires GEMINI_API_KEY environment variable.
"""

import os
import pytest
from dotenv import load_dotenv

from agent.graph import build_graph
from agent.state import create_initial_state
from llm.factory import create_llm
from models.schemas import Message, Role

load_dotenv()

pytestmark = pytest.mark.skipif(
    not os.environ.get("GEMINI_API_KEY"),
    reason="GEMINI_API_KEY environment variable is required for live multi-turn tests.",
)


@pytest.fixture(scope="module")
def agent_graph():
    llm = create_llm()
    return build_graph(llm)


def test_live_multiturn_conversation(agent_graph):
    """Verify 3-turn interactive flow maintains context, executes tools, and generates answers."""
    messages_history: list[Message] = []

    # Turn 1: Initial query
    q1 = "What is the total revenue by region?"
    state1 = create_initial_state(query=q1, history=messages_history)
    out1 = agent_graph.invoke(state1)

    assert out1.get("final_answer") is not None
    assert len(out1.get("tool_results", [])) >= 1
    assert out1["tool_results"][0].success is True

    # Update conversation history
    messages_history.append(Message(role=Role.USER, content=q1))
    messages_history.append(Message(role=Role.ASSISTANT, content=out1["final_answer"]))

    # Turn 2: Follow-up query referencing context
    q2 = "Which of those regions has the highest profit?"
    state2 = create_initial_state(query=q2, history=messages_history)
    out2 = agent_graph.invoke(state2)

    assert out2.get("final_answer") is not None
    assert len(out2.get("tool_results", [])) >= 1
    assert out2["tool_results"][0].success is True
