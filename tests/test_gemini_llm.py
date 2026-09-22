"""
tests/test_gemini_llm.py
------------------------
Unit tests for the GeminiLLM provider with mocked google-genai client.
"""

from unittest.mock import MagicMock, patch
import pytest

from llm.gemini import GeminiLLM
from models.schemas import AnalysisPlan, Intent


@pytest.fixture
def mock_genai():
    with patch("llm.gemini.genai") as mock_gen:
        mock_client = MagicMock()
        mock_gen.Client.return_value = mock_client
        yield mock_gen, mock_client


def test_gemini_initialization_with_key(mock_genai):
    mock_gen, mock_client = mock_genai
    llm = GeminiLLM(api_key="test-api-key", model="gemini-2.5-flash")
    mock_gen.Client.assert_called_once_with(api_key="test-api-key")
    assert llm.model_name == "gemini-2.5-flash"


def test_gemini_chat_session_flow(mock_genai):
    _, mock_client = mock_genai
    mock_response = MagicMock()
    mock_response.text = "Hello! I am your analyst."
    mock_client.models.generate_content.return_value = mock_response

    llm = GeminiLLM(api_key="test-api-key")
    messages = [
        {"role": "system", "content": "You are an assistant."},
        {"role": "user", "content": "What was the revenue?"},
    ]

    res = llm.chat(messages, temperature=0.2)
    assert res.content == "Hello! I am your analyst."
    mock_client.models.generate_content.assert_called_once()


def test_gemini_structured_chat(mock_genai):
    _, mock_client = mock_genai
    mock_response = MagicMock()
    mock_response.text = """
    {
        "intent": "metrics",
        "rationale": "Calculating total revenue.",
        "steps": [
            {
                "step_number": 1,
                "tool": "metrics",
                "description": "Sum revenue",
                "parameters": {"metric": "Revenue", "aggregation": "sum"}
            }
        ],
        "selected_tools": ["metrics"]
    }
    """
    mock_client.models.generate_content.return_value = mock_response

    llm = GeminiLLM(api_key="test-api-key")
    messages = [{"role": "user", "content": "Total revenue?"}]
    plan = llm.structured_chat(messages, AnalysisPlan)

    assert isinstance(plan, AnalysisPlan)
    assert plan.intent == Intent.METRICS
    assert len(plan.steps) == 1
    assert plan.steps[0].parameters["metric"] == "Revenue"
