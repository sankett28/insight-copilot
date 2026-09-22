"""
utils/capability_registry.py
----------------------------
Authoritative registry of all analytical capabilities in Insight Copilot.

This module is the single source of truth for:
  1. Capability metadata and categorization.
  2. Input validation contracts (Pydantic models).
  3. Prompt generation for the LLM Planner node.
  4. Node mapping for the conditional Router.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Type

from pydantic import BaseModel

from models.schemas import (
    AnomalyRequest,
    ChartRequest,
    CompareRequest,
    ContributionRequest,
    CorrelationRequest,
    DataCleanRequest,
    DataProfileRequest,
    DataQueryRequest,
    MetricsRequest,
    ProfitabilityRequest,
    SegmentationRequest,
    ToolName,
    TrendsRequest,
    VarianceRequest,
)


@dataclass(frozen=True)
class Capability:
    """Defines an analytical capability in the system."""

    name: str
    category: str  # "DATA_ACCESS" | "CORE_ANALYSIS" | "ADVANCED" | "PRESENTATION"
    description: str
    input_schema: Type[BaseModel]
    output_description: str
    deterministic: bool
    independent: bool
    consumes_previous_results: bool
    node_name: str


# Authoritative capability map
REGISTRY: dict[str, Capability] = {
    ToolName.DATA_QUERY.value: Capability(
        name=ToolName.DATA_QUERY.value,
        category="DATA_ACCESS",
        description="Retrieve raw or filtered rows with column selection, sorting, and limit.",
        input_schema=DataQueryRequest,
        output_description="List of row dictionaries matching the query filters.",
        deterministic=True,
        independent=True,
        consumes_previous_results=False,
        node_name="data_query",
    ),
    ToolName.DATA_PROFILE.value: Capability(
        name=ToolName.DATA_PROFILE.value,
        category="DATA_ACCESS",
        description="Comprehensive dataset overview, row/column counts, date range, numeric stats, and data quality checks.",
        input_schema=DataProfileRequest,
        output_description="Single dictionary summarizing dataset health, distributions, and warnings.",
        deterministic=True,
        independent=True,
        consumes_previous_results=False,
        node_name="data_profile",
    ),
    ToolName.DATA_CLEAN.value: Capability(
        name=ToolName.DATA_CLEAN.value,
        category="DATA_ACCESS",
        description="Interactively standardize casing, fix typos using fuzzy clustering, and fill null values in dataset dimensions.",
        input_schema=DataCleanRequest,
        output_description="Audit dictionary summarizing before/after distinct counts, typo cluster mappings, and filled nulls.",
        deterministic=True,
        independent=True,
        consumes_previous_results=False,
        node_name="data_clean",
    ),

    ToolName.METRICS.value: Capability(
        name=ToolName.METRICS.value,
        category="CORE_ANALYSIS",
        description="Compute aggregated metrics (sum, avg, min, max, count, median) grouped by dimension.",
        input_schema=MetricsRequest,
        output_description="List of aggregated metric records ordered by value.",
        deterministic=True,
        independent=True,
        consumes_previous_results=False,
        node_name="metrics",
    ),
    ToolName.TRENDS.value: Capability(
        name=ToolName.TRENDS.value,
        category="CORE_ANALYSIS",
        description="Analyse numeric metric aggregated over time (day, week, month, quarter, year).",
        input_schema=TrendsRequest,
        output_description="List of period-aggregated time-series dictionaries.",
        deterministic=True,
        independent=True,
        consumes_previous_results=False,
        node_name="trends",
    ),
    ToolName.COMPARE.value: Capability(
        name=ToolName.COMPARE.value,
        category="CORE_ANALYSIS",
        description="Compare a metric across two distinct entities/periods with absolute and percentage delta.",
        input_schema=CompareRequest,
        output_description="Dictionary containing side-by-side values, absolute delta, and percentage delta.",
        deterministic=True,
        independent=True,
        consumes_previous_results=False,
        node_name="compare",
    ),
    ToolName.CONTRIBUTION.value: Capability(
        name=ToolName.CONTRIBUTION.value,
        category="CORE_ANALYSIS",
        description="Calculate the absolute and percentage contribution of each dimension value to a total.",
        input_schema=ContributionRequest,
        output_description="List of dimension values with their aggregate and percentage share of total.",
        deterministic=True,
        independent=True,
        consumes_previous_results=False,
        node_name="contribution",
    ),
    ToolName.PROFITABILITY.value: Capability(
        name=ToolName.PROFITABILITY.value,
        category="CORE_ANALYSIS",
        description="Compute revenue, cost, profit, and derived profit margin (Profit / Revenue * 100).",
        input_schema=ProfitabilityRequest,
        output_description="List of dimension groups with financial metrics and profit margin percentages.",
        deterministic=True,
        independent=True,
        consumes_previous_results=False,
        node_name="profitability",
    ),
    ToolName.VARIANCE.value: Capability(
        name=ToolName.VARIANCE.value,
        category="CORE_ANALYSIS",
        description="Compute period-over-period metric variance (absolute change and percentage change).",
        input_schema=VarianceRequest,
        output_description="Time series containing previous values, absolute deltas, and percentage growth rates.",
        deterministic=True,
        independent=True,
        consumes_previous_results=False,
        node_name="variance",
    ),
    ToolName.CHARTS.value: Capability(
        name=ToolName.CHARTS.value,
        category="PRESENTATION",
        description="Render a Plotly visual chart (bar, line, scatter) from tabular data produced by a preceding step.",
        input_schema=ChartRequest,
        output_description="Plotly figure dictionary suitable for visualization.",
        deterministic=True,
        independent=False,
        consumes_previous_results=True,
        node_name="charts",
    ),
    ToolName.ANOMALY_DETECTION.value: Capability(
        name=ToolName.ANOMALY_DETECTION.value,
        category="ADVANCED",
        description="Detect statistical outliers (IQR or Z-Score) in numeric metrics across the dataset or groups.",
        input_schema=AnomalyRequest,
        output_description="Dictionary containing detected anomaly records, statistical bounds, and counts.",
        deterministic=True,
        independent=True,
        consumes_previous_results=False,
        node_name="anomaly_detection",
    ),
    ToolName.CORRELATION.value: Capability(
        name=ToolName.CORRELATION.value,
        category="ADVANCED",
        description="Calculate the Pearson correlation coefficient between two numeric fields (with non-causation caveat).",
        input_schema=CorrelationRequest,
        output_description="Dictionary containing Pearson r coefficient, sample size, and analytical caveats.",
        deterministic=True,
        independent=True,
        consumes_previous_results=False,
        node_name="correlation",
    ),
    ToolName.SEGMENTATION.value: Capability(
        name=ToolName.SEGMENTATION.value,
        category="ADVANCED",
        description="Perform multi-dimensional 2D cross-tabulation of a metric across two distinct categorical dimensions.",
        input_schema=SegmentationRequest,
        output_description="List of combined dimension records with aggregated metric values.",
        deterministic=True,
        independent=True,
        consumes_previous_results=False,
        node_name="segmentation",
    ),
}


def get_capability(name: str) -> Capability:
    """Retrieve capability by canonical name."""
    if name not in REGISTRY:
        raise KeyError(f"Capability '{name}' is not registered. Available: {list(REGISTRY.keys())}")
    return REGISTRY[name]


def get_planner_context() -> str:
    """Generate structured summary of all capabilities for LLM planner prompt context."""
    lines = ["Available Capabilities and Request Schemas:"]
    for cap in REGISTRY.values():
        lines.append(f"- {cap.name} [{cap.category}]: {cap.description}")
        lines.append(f"  Input Schema: {cap.input_schema.model_json_schema()['properties']}")
    return "\n".join(lines)


def get_node_map() -> dict[ToolName, str]:
    """Return map from ToolName enum to LangGraph node name."""
    return {ToolName(cap.name): cap.node_name for cap in REGISTRY.values()}
