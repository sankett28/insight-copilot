"""
models/schemas.py
-----------------
Pydantic data contracts for Insight Copilot.

These schemas act as the authoritative definition of every structured object
that moves between components (planner → router → tools → synthesizer).
Keeping them in a dedicated module avoids circular imports and makes the
contracts easy to unit-test in isolation.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal
from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Canonical Dataset Schema Constants
# ---------------------------------------------------------------------------

DATE_COLUMN = "Date"

CATEGORICAL_COLUMNS = ["Region", "Product", "Salesperson", "Category"]

NUMERIC_COLUMNS = ["Units_Sold", "Unit_Price", "Revenue", "Cost", "Profit"]

CANONICAL_COLUMNS = [DATE_COLUMN] + CATEGORICAL_COLUMNS + NUMERIC_COLUMNS


# ---------------------------------------------------------------------------
# Dataset Metadata Schemas
# ---------------------------------------------------------------------------


class ColumnMetadata(BaseModel):
    """Metadata description of a single dataset column."""

    name: str
    data_type: str = Field(..., description="Data type, e.g., 'datetime', 'str', 'float64'.")
    semantic_role: Literal["time", "dimension", "metric"] = Field(
        ..., description="Role of the column in analytical operations."
    )
    can_group: bool = Field(default=True, description="Whether column can be used in GROUP BY.")
    can_metric: bool = Field(default=False, description="Whether column can be aggregated as a metric.")
    can_time: bool = Field(default=False, description="Whether column can be used for temporal trends.")


class DatasetSchema(BaseModel):
    """Authoritative description of the dataset structure exposed to the planner."""

    dataset_name: str = "Sales_Dataset_2024"
    total_rows: int = 2000
    columns: list[ColumnMetadata] = Field(default_factory=list)

    def to_prompt_summary(self) -> str:
        """Format a clear, concise text description for the LLM planner prompt."""
        lines = [f"Dataset: {self.dataset_name} ({self.total_rows} rows)"]
        lines.append("Available Columns:")
        for col in self.columns:
            lines.append(
                f"- {col.name} ({col.data_type}, role: {col.semantic_role}) | "
                f"groupable: {col.can_group}, metric: {col.can_metric}, temporal: {col.can_time}"
            )
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class Intent(str, Enum):
    """High-level analytical intent inferred by the planner."""

    DATA_QUERY = "data_query"
    METRICS = "metrics"
    TREND = "trend"
    CHART = "chart"
    COMBINED = "combined"
    UNKNOWN = "unknown"


class ToolName(str, Enum):
    """Canonical names for executable tools in the agent."""

    # Phase 1 — deterministic data tools
    DATA_QUERY = "data_query"
    METRICS = "metrics"
    TRENDS = "trends"
    CHARTS = "charts"

    # Phase 2 — extended analytical capabilities
    DATA_PROFILE = "data_profile"
    COMPARE = "compare"
    CONTRIBUTION = "contribution"
    PROFITABILITY = "profitability"
    VARIANCE = "variance"

    # Phase 3 — advanced statistical capabilities
    ANOMALY_DETECTION = "anomaly_detection"
    CORRELATION = "correlation"
    SEGMENTATION = "segmentation"


# ---------------------------------------------------------------------------
# Typed Tool Request Contracts
# ---------------------------------------------------------------------------


class MetricsRequest(BaseModel):
    """Structured parameter contract for the metrics tool."""

    metric: str = Field(
        ...,
        description="Target numeric column (Units_Sold, Unit_Price, Revenue, Cost, Profit).",
    )
    aggregation: Literal["sum", "average", "avg", "count", "min", "max", "median"] = Field(
        default="sum",
        description="Aggregation operation to apply.",
    )
    group_by: str | list[str] | None = Field(
        default=None,
        description="Categorical column(s) or Date to group by.",
    )
    filters: dict[str, Any] | None = Field(
        default=None,
        description="Column equality filters (e.g. {'Region': 'North'}).",
    )
    limit: int | None = Field(
        default=20,
        ge=1,
        le=500,
        description="Maximum number of rows to return.",
    )
    sort: Literal["asc", "desc"] = Field(
        default="desc",
        description="Sort direction by the aggregated metric value.",
    )

    @field_validator("metric")
    @classmethod
    def validate_metric_column(cls, v: str) -> str:
        # Case-insensitive match against canonical numeric columns
        for valid in NUMERIC_COLUMNS:
            if v.lower() == valid.lower():
                return valid
        raise ValueError(f"Invalid metric '{v}'. Must be one of {NUMERIC_COLUMNS}.")


class TrendsRequest(BaseModel):
    """Structured parameter contract for the trends tool."""

    metric: str = Field(
        ...,
        description="Target numeric column to analyze over time.",
    )
    date_column: str = Field(
        default="Date",
        description="Temporal date column.",
    )
    granularity: Literal["day", "week", "month", "quarter", "year"] = Field(
        default="month",
        description="Time aggregation granularity.",
    )
    group_by: str | None = Field(
        default=None,
        description="Optional additional categorical grouping dimension.",
    )
    filters: dict[str, Any] | None = Field(
        default=None,
        description="Optional filters applied before trend aggregation.",
    )

    @field_validator("metric")
    @classmethod
    def validate_metric_column(cls, v: str) -> str:
        for valid in NUMERIC_COLUMNS:
            if v.lower() == valid.lower():
                return valid
        raise ValueError(f"Invalid metric '{v}'. Must be one of {NUMERIC_COLUMNS}.")

    @field_validator("date_column")
    @classmethod
    def validate_date_column(cls, v: str) -> str:
        if v.lower() != DATE_COLUMN.lower():
            raise ValueError(f"Invalid date_column '{v}'. Must be '{DATE_COLUMN}'.")
        return DATE_COLUMN


class DataQueryRequest(BaseModel):
    """Structured parameter contract for the data_query tool."""

    columns: list[str] | None = Field(
        default=None,
        description="Selected columns to return; None returns all canonical columns.",
    )
    filters: dict[str, Any] | None = Field(
        default=None,
        description="Equality or comparative filters.",
    )
    sort_by: str | None = Field(
        default=None,
        description="Column name to sort by.",
    )
    sort_order: Literal["asc", "desc"] = Field(
        default="desc",
        description="Sort order direction.",
    )
    limit: int = Field(
        default=20,
        ge=1,
        le=100,
        description="Maximum raw rows to return.",
    )


class ChartRequest(BaseModel):
    """Structured parameter contract for the charts tool."""

    chart_type: Literal["bar", "line", "scatter"] = Field(
        ...,
        description="Type of Plotly chart to render.",
    )
    x: str = Field(..., description="Column for the x-axis.")
    y: str = Field(..., description="Column for the y-axis.")
    color: str | None = Field(default=None, description="Optional column for color grouping.")
    title: str | None = Field(default=None, description="Optional chart title.")


class DataProfileRequest(BaseModel):
    """Structured parameter contract for the data_profile tool.
    
    No required parameters — profiles the full registered dataset view.
    """
    pass


class CompareRequest(BaseModel):
    """Structured parameter contract for the compare capability."""

    metric: str = Field(
        ...,
        description="Target numeric column to compare (Units_Sold, Unit_Price, Revenue, Cost, Profit).",
    )
    aggregation: Literal["sum", "average", "avg", "count", "min", "max"] = Field(
        default="sum",
        description="Aggregation operation to apply.",
    )
    dimension: str = Field(
        ...,
        description="Categorical dimension column to compare values within (e.g. 'Region', 'Category').",
    )
    value_a: str = Field(
        ...,
        description="First entity value to compare (e.g. 'North').",
    )
    value_b: str = Field(
        ...,
        description="Second entity value to compare (e.g. 'South').",
    )
    filters: dict[str, Any] | None = Field(
        default=None,
        description="Optional additional filters applied to both sides of the comparison.",
    )

    @field_validator("metric")
    @classmethod
    def validate_metric_column(cls, v: str) -> str:
        for valid in NUMERIC_COLUMNS:
            if v.lower() == valid.lower():
                return valid
        raise ValueError(f"Invalid metric '{v}'. Must be one of {NUMERIC_COLUMNS}.")

    @field_validator("dimension")
    @classmethod
    def validate_dimension_column(cls, v: str) -> str:
        for valid in CATEGORICAL_COLUMNS:
            if v.lower() == valid.lower():
                return valid
        raise ValueError(f"Invalid dimension '{v}'. Must be one of {CATEGORICAL_COLUMNS}.")


class ContributionRequest(BaseModel):
    """Structured parameter contract for the contribution capability."""

    metric: str = Field(
        ...,
        description="Target numeric column (Units_Sold, Unit_Price, Revenue, Cost, Profit).",
    )
    dimension: str = Field(
        ...,
        description="Categorical dimension column to break down contribution by (e.g. 'Region', 'Category').",
    )
    aggregation: Literal["sum", "avg", "count"] = Field(
        default="sum",
        description="Aggregation operation to apply.",
    )
    filters: dict[str, Any] | None = Field(
        default=None,
        description="Optional column equality filters.",
    )
    limit: int | None = Field(
        default=None,
        ge=1,
        le=50,
        description="Optional limit on number of items returned.",
    )

    @field_validator("metric")
    @classmethod
    def validate_metric_column(cls, v: str) -> str:
        for valid in NUMERIC_COLUMNS:
            if v.lower() == valid.lower():
                return valid
        raise ValueError(f"Invalid metric '{v}'. Must be one of {NUMERIC_COLUMNS}.")

    @field_validator("dimension")
    @classmethod
    def validate_dimension_column(cls, v: str) -> str:
        for valid in CATEGORICAL_COLUMNS:
            if v.lower() == valid.lower():
                return valid
        raise ValueError(f"Invalid dimension '{v}'. Must be one of {CATEGORICAL_COLUMNS}.")


class ProfitabilityRequest(BaseModel):
    """Structured parameter contract for the profitability capability."""

    dimension: str = Field(
        ...,
        description="Categorical dimension column to group by (e.g. 'Product', 'Region', 'Category', 'Salesperson').",
    )
    filters: dict[str, Any] | None = Field(
        default=None,
        description="Optional column equality filters.",
    )
    limit: int = Field(
        default=20,
        ge=1,
        le=100,
        description="Maximum number of rows to return.",
    )
    sort_by: Literal["profit_margin_pct", "Revenue", "Profit", "Cost"] = Field(
        default="profit_margin_pct",
        description="Metric or calculated margin by which to sort the results.",
    )

    @field_validator("dimension")
    @classmethod
    def validate_dimension_column(cls, v: str) -> str:
        for valid in CATEGORICAL_COLUMNS:
            if v.lower() == valid.lower():
                return valid
        raise ValueError(f"Invalid dimension '{v}'. Must be one of {CATEGORICAL_COLUMNS}.")


class VarianceRequest(BaseModel):
    """Structured parameter contract for the variance capability."""

    metric: str = Field(
        ...,
        description="Target numeric column to analyze period-over-period variance for.",
    )
    granularity: Literal["day", "week", "month", "quarter", "year"] = Field(
        default="month",
        description="Time period granularity for variance calculations.",
    )
    group_by: str | None = Field(
        default=None,
        description="Optional additional categorical grouping dimension.",
    )
    filters: dict[str, Any] | None = Field(
        default=None,
        description="Optional filters applied before variance calculation.",
    )

    @field_validator("metric")
    @classmethod
    def validate_metric_column(cls, v: str) -> str:
        for valid in NUMERIC_COLUMNS:
            if v.lower() == valid.lower():
                return valid
        raise ValueError(f"Invalid metric '{v}'. Must be one of {NUMERIC_COLUMNS}.")

    @field_validator("group_by")
    @classmethod
    def validate_group_by(cls, v: str | None) -> str | None:
        if v is None:
            return None
        for valid in CATEGORICAL_COLUMNS:
            if v.lower() == valid.lower():
                return valid
        raise ValueError(f"Invalid group_by dimension '{v}'. Must be one of {CATEGORICAL_COLUMNS}.")


class AnomalyRequest(BaseModel):
    """Structured parameter contract for the anomaly_detection capability."""

    metric: str = Field(
        ...,
        description="Target numeric column (Units_Sold, Unit_Price, Revenue, Cost, Profit).",
    )
    method: Literal["iqr", "zscore"] = Field(
        default="iqr",
        description="Statistical outlier detection method: 'iqr' (Interquartile Range) or 'zscore'.",
    )
    threshold: float = Field(
        default=1.5,
        ge=0.5,
        le=5.0,
        description="Multiplier for IQR (default 1.5) or Z-score cut-off threshold (default 2.5 or 3.0).",
    )
    group_by: str | None = Field(
        default=None,
        description="Optional categorical dimension to detect anomalies within groups.",
    )
    filters: dict[str, Any] | None = Field(
        default=None,
        description="Optional equality filters.",
    )

    @field_validator("metric")
    @classmethod
    def validate_metric_column(cls, v: str) -> str:
        for valid in NUMERIC_COLUMNS:
            if v.lower() == valid.lower():
                return valid
        raise ValueError(f"Invalid metric '{v}'. Must be one of {NUMERIC_COLUMNS}.")

    @field_validator("group_by")
    @classmethod
    def validate_group_by(cls, v: str | None) -> str | None:
        if v is None:
            return None
        for valid in CATEGORICAL_COLUMNS:
            if v.lower() == valid.lower():
                return valid
        raise ValueError(f"Invalid group_by dimension '{v}'. Must be one of {CATEGORICAL_COLUMNS}.")


class CorrelationRequest(BaseModel):
    """Structured parameter contract for the correlation capability."""

    field_a: str = Field(
        ...,
        description="First target numeric column.",
    )
    field_b: str = Field(
        ...,
        description="Second target numeric column.",
    )
    group_by: str | None = Field(
        default=None,
        description="Optional dimension to calculate correlation across subsets.",
    )
    filters: dict[str, Any] | None = Field(
        default=None,
        description="Optional equality filters.",
    )

    @field_validator("field_a")
    @classmethod
    def validate_field_a(cls, v: str) -> str:
        for valid in NUMERIC_COLUMNS:
            if v.lower() == valid.lower():
                return valid
        raise ValueError(f"Invalid field_a '{v}'. Must be one of {NUMERIC_COLUMNS}.")

    @field_validator("field_b")
    @classmethod
    def validate_field_b(cls, v: str) -> str:
        for valid in NUMERIC_COLUMNS:
            if v.lower() == valid.lower():
                return valid
        raise ValueError(f"Invalid field_b '{v}'. Must be one of {NUMERIC_COLUMNS}.")


class SegmentationRequest(BaseModel):
    """Structured parameter contract for the segmentation capability."""

    metric: str = Field(
        ...,
        description="Target numeric column.",
    )
    dimension_primary: str = Field(
        ...,
        description="Primary categorical axis (e.g. 'Region', 'Category', 'Salesperson').",
    )
    dimension_secondary: str = Field(
        ...,
        description="Secondary categorical axis (e.g. 'Category', 'Product').",
    )
    aggregation: Literal["sum", "average", "avg", "count", "min", "max"] = Field(
        default="sum",
        description="Aggregation function.",
    )
    filters: dict[str, Any] | None = Field(
        default=None,
        description="Optional equality filters.",
    )
    limit: int = Field(
        default=50,
        ge=1,
        le=200,
        description="Maximum combinations returned.",
    )

    @field_validator("metric")
    @classmethod
    def validate_metric(cls, v: str) -> str:
        for valid in NUMERIC_COLUMNS:
            if v.lower() == valid.lower():
                return valid
        raise ValueError(f"Invalid metric '{v}'. Must be one of {NUMERIC_COLUMNS}.")

    @field_validator("dimension_primary")
    @classmethod
    def validate_dim_primary(cls, v: str) -> str:
        for valid in CATEGORICAL_COLUMNS:
            if v.lower() == valid.lower():
                return valid
        raise ValueError(f"Invalid dimension_primary '{v}'. Must be one of {CATEGORICAL_COLUMNS}.")

    @field_validator("dimension_secondary")
    @classmethod
    def validate_dim_secondary(cls, v: str) -> str:
        for valid in CATEGORICAL_COLUMNS:
            if v.lower() == valid.lower():
                return valid
        raise ValueError(f"Invalid dimension_secondary '{v}'. Must be one of {CATEGORICAL_COLUMNS}.")


# ---------------------------------------------------------------------------
# Execution Plan Schemas
# ---------------------------------------------------------------------------


class PlanStep(BaseModel):
    """A single step in the execution plan containing structured parameters."""

    step_number: int = Field(..., ge=1, description="1-based position in the plan.")
    tool: ToolName = Field(..., description="The tool to invoke at this step.")
    description: str = Field(
        ...,
        description="Human-readable description of what this step does.",
    )
    parameters: dict[str, Any] = Field(
        default_factory=dict,
        description="Structured tool parameters matching the target tool's request contract.",
    )
    depends_on: list[int] = Field(
        default_factory=list,
        description="List of step_numbers that must complete before this step can run.",
    )


class AnalysisPlan(BaseModel):
    """Structured plan produced by the Planner node."""

    intent: Intent = Field(
        ...,
        description="Classified analytical intent of the user query.",
    )
    rationale: str = Field(
        ...,
        description="Short (≤3 sentences) plain-English explanation of why this plan was chosen.",
    )
    steps: list[PlanStep] = Field(
        ...,
        min_length=1,
        description="Ordered list of execution steps.",
    )
    selected_tools: list[ToolName] = Field(
        ...,
        description="Flat list of tools referenced by this plan.",
    )


# ---------------------------------------------------------------------------
# Tool Result & Conversation Message
# ---------------------------------------------------------------------------


class ToolResult(BaseModel):
    """Encapsulates the output of a single tool execution."""

    tool: ToolName = Field(..., description="Which tool produced this result.")
    step_number: int = Field(..., ge=1, description="Corresponding plan step.")
    success: bool = Field(..., description="Whether the tool completed without error.")
    data: Any = Field(
        default=None,
        description="Serialisable payload returned by the tool.",
    )
    error: str | None = Field(
        default=None,
        description="Error message if success=False, otherwise None.",
    )


class Role(str, Enum):
    """Speaker role in the conversation history."""

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class Message(BaseModel):
    """A single turn in the conversation."""

    role: Role
    content: str
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Optional bag for attaching structured data to a message.",
    )

