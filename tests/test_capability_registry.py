"""
tests/test_capability_registry.py
---------------------------------
Unit tests for the centralized Capability Registry.
"""

import pytest
from pydantic import BaseModel

from models.schemas import ToolName
from utils.capability_registry import (
    REGISTRY,
    Capability,
    get_capability,
    get_node_map,
    get_planner_context,
)


def test_phase1_capabilities_registered():
    """Verify that all Phase 1 capabilities are registered."""
    for tool_name in ["data_query", "metrics", "trends", "charts"]:
        assert tool_name in REGISTRY
        cap = get_capability(tool_name)
        assert isinstance(cap, Capability)
        assert cap.name == tool_name
        assert issubclass(cap.input_schema, BaseModel)


def test_phase2_capabilities_registered():
    """Verify that Phase 2 extended capabilities are present in the registry."""
    for tool_name in ["data_profile", "compare", "contribution", "profitability", "variance"]:
        assert tool_name in REGISTRY
        cap = get_capability(tool_name)
        assert isinstance(cap, Capability)
        assert cap.name == tool_name
        assert issubclass(cap.input_schema, BaseModel)


def test_phase3_capabilities_registered():
    """Verify that Phase 3 advanced capabilities are present in the registry."""
    for tool_name in ["anomaly_detection", "correlation", "segmentation"]:
        assert tool_name in REGISTRY
        cap = get_capability(tool_name)
        assert isinstance(cap, Capability)
        assert cap.name == tool_name
        assert cap.category == "ADVANCED"
        assert issubclass(cap.input_schema, BaseModel)


def test_get_capability_success():
    """Verify retrieving an existing capability returns proper attributes."""
    cap = get_capability("metrics")
    assert cap.name == "metrics"
    assert cap.category == "CORE_ANALYSIS"
    assert cap.deterministic is True
    assert cap.node_name == "metrics"


def test_get_capability_nonexistent():
    """Verify KeyError is raised for unregistered capability."""
    with pytest.raises(KeyError, match="not registered"):
        get_capability("nonexistent_tool_123")


def test_get_planner_context_format():
    """Verify get_planner_context outputs formatted text with schema keys."""
    context = get_planner_context()
    assert isinstance(context, str)
    assert "Available Capabilities" in context
    assert "metrics" in context
    assert "trends" in context
    assert "data_profile" in context
    assert "Input Schema" in context


def test_get_node_map_covers_all_tools():
    """Verify get_node_map produces valid ToolName enum mapping."""
    node_map = get_node_map()
    assert isinstance(node_map, dict)
    for tool_enum in ToolName:
        assert tool_enum in node_map
        assert isinstance(node_map[tool_enum], str)
