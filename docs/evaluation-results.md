# Insight Copilot Automated Evaluation Report

- **Timestamp**: 2026-09-24 12:31:22 UTC
- **Total Benchmark Cases**: 35
- **In-Domain Analytical Queries**: 31
- **Meta & Out-of-Domain Queries**: 4

## Aggregate Benchmark Metrics

| Metric | Target | Result | Status |
|---|---|---|---|
| **Planner Intent Accuracy** | $\ge 90\%$ | **100.0%** | ✅ PASS |
| **Tool Selection Match** | $\ge 90\%$ | **100.0%** | ✅ PASS |
| **Parameter Schema Validity** | $100\%$ | **100.0%** | ✅ PASS |
| **Deterministic Execution Success** | $100\%$ | **100.0%** | ✅ PASS |

## Benchmark Case Breakdown

| ID | Category | Intent Match | Tools Match | Params Valid | Exec Success | Duration |
|---|---|:---:|:---:|:---:|:---:|---:|
| `eval_01` | single_tool_metrics | ✅ | ✅ | ✅ | ✅ | 43.8ms |
| `eval_02` | single_tool_metrics | ✅ | ✅ | ✅ | ✅ | 21.3ms |
| `eval_03` | single_tool_metrics | ✅ | ✅ | ✅ | ✅ | 18.7ms |
| `eval_04` | single_tool_metrics | ✅ | ✅ | ✅ | ✅ | 18.1ms |
| `eval_05` | single_tool_trends | ✅ | ✅ | ✅ | ✅ | 18.7ms |
| `eval_06` | single_tool_trends | ✅ | ✅ | ✅ | ✅ | 19.4ms |
| `eval_07` | single_tool_profitability | ✅ | ✅ | ✅ | ✅ | 19.1ms |
| `eval_08` | single_tool_profitability | ✅ | ✅ | ✅ | ✅ | 17.3ms |
| `eval_09` | single_tool_compare | ✅ | ✅ | ✅ | ✅ | 21.9ms |
| `eval_10` | single_tool_compare | ✅ | ✅ | ✅ | ✅ | 17.5ms |
| `eval_11` | single_tool_contribution | ✅ | ✅ | ✅ | ✅ | 16.3ms |
| `eval_12` | single_tool_contribution | ✅ | ✅ | ✅ | ✅ | 16.0ms |
| `eval_13` | single_tool_variance | ✅ | ✅ | ✅ | ✅ | 22.0ms |
| `eval_14` | single_tool_variance | ✅ | ✅ | ✅ | ✅ | 22.9ms |
| `eval_15` | single_tool_data_query | ✅ | ✅ | ✅ | ✅ | 20.5ms |
| `eval_16` | single_tool_data_profile | ✅ | ✅ | ✅ | ✅ | 55.1ms |
| `eval_17` | multi_tool_visualization | ✅ | ✅ | ✅ | ✅ | 460.7ms |
| `eval_18` | multi_tool_visualization | ✅ | ✅ | ✅ | ✅ | 46.5ms |
| `eval_19` | multi_tool_visualization | ✅ | ✅ | ✅ | ✅ | 56.5ms |
| `eval_20` | multi_tool_visualization | ✅ | ✅ | ✅ | ✅ | 41.0ms |
| `eval_21` | advanced_statistical | ✅ | ✅ | ✅ | ✅ | 20.0ms |
| `eval_22` | advanced_statistical | ✅ | ✅ | ✅ | ✅ | 21.5ms |
| `eval_23` | advanced_statistical | ✅ | ✅ | ✅ | ✅ | 15.2ms |
| `eval_24` | advanced_statistical | ✅ | ✅ | ✅ | ✅ | 15.3ms |
| `eval_25` | advanced_statistical | ✅ | ✅ | ✅ | ✅ | 21.4ms |
| `eval_26` | advanced_statistical | ✅ | ✅ | ✅ | ✅ | 18.1ms |
| `eval_27` | data_cleaning | ✅ | ✅ | ✅ | ✅ | 22.3ms |
| `eval_28` | data_cleaning | ✅ | ✅ | ✅ | ✅ | 35.8ms |
| `eval_29` | meta_system | ✅ | ✅ | ✅ | ✅ | 0.0ms |
| `eval_30` | meta_system | ✅ | ✅ | ✅ | ✅ | 0.0ms |
| `eval_31` | meta_system | ✅ | ✅ | ✅ | ✅ | 0.0ms |
| `eval_32` | adversarial_out_of_domain | ✅ | ✅ | ✅ | ✅ | 0.0ms |
| `eval_33` | adversarial_out_of_domain | ✅ | ✅ | ✅ | ✅ | 0.0ms |
| `eval_34` | adversarial_out_of_domain | ✅ | ✅ | ✅ | ✅ | 0.0ms |
| `eval_35` | adversarial_out_of_domain | ✅ | ✅ | ✅ | ✅ | 0.0ms |

## Evaluation Methodology
1. **Intent & Tool Selection**: Validates whether the planner selects the correct high-level intent and exact capability execution sequence.
2. **Parameter Validity**: Enforces strict Pydantic model validation against the authoritative Capability Registry contracts.
3. **Deterministic Execution**: In-memory session DuckDB execution ensuring clean zero-error computation across all 13 analytical capabilities.