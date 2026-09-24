# Insight Copilot Automated Evaluation Report

- **Timestamp**: 2026-09-23 19:37:20 UTC
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
| `eval_01` | single_tool_metrics | ✅ | ✅ | ✅ | ✅ | 33.2ms |
| `eval_02` | single_tool_metrics | ✅ | ✅ | ✅ | ✅ | 16.7ms |
| `eval_03` | single_tool_metrics | ✅ | ✅ | ✅ | ✅ | 16.0ms |
| `eval_04` | single_tool_metrics | ✅ | ✅ | ✅ | ✅ | 18.4ms |
| `eval_05` | single_tool_trends | ✅ | ✅ | ✅ | ✅ | 21.5ms |
| `eval_06` | single_tool_trends | ✅ | ✅ | ✅ | ✅ | 21.5ms |
| `eval_07` | single_tool_profitability | ✅ | ✅ | ✅ | ✅ | 17.7ms |
| `eval_08` | single_tool_profitability | ✅ | ✅ | ✅ | ✅ | 20.2ms |
| `eval_09` | single_tool_compare | ✅ | ✅ | ✅ | ✅ | 14.2ms |
| `eval_10` | single_tool_compare | ✅ | ✅ | ✅ | ✅ | 15.4ms |
| `eval_11` | single_tool_contribution | ✅ | ✅ | ✅ | ✅ | 15.3ms |
| `eval_12` | single_tool_contribution | ✅ | ✅ | ✅ | ✅ | 14.2ms |
| `eval_13` | single_tool_variance | ✅ | ✅ | ✅ | ✅ | 19.6ms |
| `eval_14` | single_tool_variance | ✅ | ✅ | ✅ | ✅ | 26.5ms |
| `eval_15` | single_tool_data_query | ✅ | ✅ | ✅ | ✅ | 17.0ms |
| `eval_16` | single_tool_data_profile | ✅ | ✅ | ✅ | ✅ | 40.9ms |
| `eval_17` | multi_tool_visualization | ✅ | ✅ | ✅ | ✅ | 307.7ms |
| `eval_18` | multi_tool_visualization | ✅ | ✅ | ✅ | ✅ | 41.5ms |
| `eval_19` | multi_tool_visualization | ✅ | ✅ | ✅ | ✅ | 49.8ms |
| `eval_20` | multi_tool_visualization | ✅ | ✅ | ✅ | ✅ | 46.0ms |
| `eval_21` | advanced_statistical | ✅ | ✅ | ✅ | ✅ | 21.0ms |
| `eval_22` | advanced_statistical | ✅ | ✅ | ✅ | ✅ | 21.1ms |
| `eval_23` | advanced_statistical | ✅ | ✅ | ✅ | ✅ | 17.8ms |
| `eval_24` | advanced_statistical | ✅ | ✅ | ✅ | ✅ | 14.1ms |
| `eval_25` | advanced_statistical | ✅ | ✅ | ✅ | ✅ | 18.0ms |
| `eval_26` | advanced_statistical | ✅ | ✅ | ✅ | ✅ | 16.9ms |
| `eval_27` | data_cleaning | ✅ | ✅ | ✅ | ✅ | 24.9ms |
| `eval_28` | data_cleaning | ✅ | ✅ | ✅ | ✅ | 28.8ms |
| `eval_29` | meta_system | ✅ | ✅ | ✅ | ✅ | 0.1ms |
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