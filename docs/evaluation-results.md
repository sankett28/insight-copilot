# Insight Copilot Automated Evaluation Report

- **Timestamp**: 2026-09-22 11:33:20 UTC
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
| `eval_01` | single_tool_metrics | ✅ | ✅ | ✅ | ✅ | 32.5ms |
| `eval_02` | single_tool_metrics | ✅ | ✅ | ✅ | ✅ | 14.4ms |
| `eval_03` | single_tool_metrics | ✅ | ✅ | ✅ | ✅ | 15.3ms |
| `eval_04` | single_tool_metrics | ✅ | ✅ | ✅ | ✅ | 14.5ms |
| `eval_05` | single_tool_trends | ✅ | ✅ | ✅ | ✅ | 15.3ms |
| `eval_06` | single_tool_trends | ✅ | ✅ | ✅ | ✅ | 16.5ms |
| `eval_07` | single_tool_profitability | ✅ | ✅ | ✅ | ✅ | 15.9ms |
| `eval_08` | single_tool_profitability | ✅ | ✅ | ✅ | ✅ | 26.4ms |
| `eval_09` | single_tool_compare | ✅ | ✅ | ✅ | ✅ | 16.5ms |
| `eval_10` | single_tool_compare | ✅ | ✅ | ✅ | ✅ | 14.4ms |
| `eval_11` | single_tool_contribution | ✅ | ✅ | ✅ | ✅ | 18.3ms |
| `eval_12` | single_tool_contribution | ✅ | ✅ | ✅ | ✅ | 13.8ms |
| `eval_13` | single_tool_variance | ✅ | ✅ | ✅ | ✅ | 18.4ms |
| `eval_14` | single_tool_variance | ✅ | ✅ | ✅ | ✅ | 20.9ms |
| `eval_15` | single_tool_data_query | ✅ | ✅ | ✅ | ✅ | 17.7ms |
| `eval_16` | single_tool_data_profile | ✅ | ✅ | ✅ | ✅ | 39.2ms |
| `eval_17` | multi_tool_visualization | ✅ | ✅ | ✅ | ✅ | 245.2ms |
| `eval_18` | multi_tool_visualization | ✅ | ✅ | ✅ | ✅ | 38.7ms |
| `eval_19` | multi_tool_visualization | ✅ | ✅ | ✅ | ✅ | 44.3ms |
| `eval_20` | multi_tool_visualization | ✅ | ✅ | ✅ | ✅ | 37.6ms |
| `eval_21` | advanced_statistical | ✅ | ✅ | ✅ | ✅ | 16.8ms |
| `eval_22` | advanced_statistical | ✅ | ✅ | ✅ | ✅ | 19.1ms |
| `eval_23` | advanced_statistical | ✅ | ✅ | ✅ | ✅ | 15.9ms |
| `eval_24` | advanced_statistical | ✅ | ✅ | ✅ | ✅ | 14.0ms |
| `eval_25` | advanced_statistical | ✅ | ✅ | ✅ | ✅ | 15.1ms |
| `eval_26` | advanced_statistical | ✅ | ✅ | ✅ | ✅ | 15.8ms |
| `eval_27` | data_cleaning | ✅ | ✅ | ✅ | ✅ | 18.5ms |
| `eval_28` | data_cleaning | ✅ | ✅ | ✅ | ✅ | 21.9ms |
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