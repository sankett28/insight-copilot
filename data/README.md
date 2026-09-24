# Data Directory

This directory houses the authoritative business datasets and runtime caches for Insight Copilot.

## Canonical Dataset: `Sales_Dataset_2024.xlsx`

The repository includes a bundled canonical enterprise dataset (`Sales_Dataset_2024.xlsx`) containing 2,000 transactions across full-year 2024.

### Canonical Schema (10 Fields)

| Column | Data Type | Semantic Role | Analytical Role |
|---|---|---|---|
| `Date` | TIMESTAMP | Time | Temporal aggregations (day, week, month, quarter, year) |
| `Region` | VARCHAR | Dimension | Geographic sales territory (`North`, `South`, `East`, `West`) |
| `Product` | VARCHAR | Dimension | Product name / catalog identifier |
| `Salesperson` | VARCHAR | Dimension | Account executive identifier |
| `Category` | VARCHAR | Dimension | Product taxonomy category (`Electronics`, `Furniture`, `Clothing`, etc.) |
| `Units_Sold` | DOUBLE | Metric | Unit transaction volume |
| `Unit_Price` | DOUBLE | Metric | Per-unit selling price |
| `Revenue` | DOUBLE | Metric | Total transaction revenue |
| `Cost` | DOUBLE | Metric | Recorded transaction cost |
| `Profit` | DOUBLE | Metric | Net transaction profit |

## Data Layer Architecture

- **Bronze Layer (`raw_dataset`)**: Immutable in-memory DuckDB view created directly from the canonical Excel file. Never mutated by data cleaning operations.
- **Silver Layer (`dataset`)**: Active working view queried by analytical tools (`metrics`, `trends`, `profitability`, `compare`, `charts`). Interactive cleaning operations apply mutations strictly to this view.
- **Session Reset**: Calling `reset_to_raw_dataset()` restores the Silver layer from the Bronze layer in <5ms.

## Runtime Parquet Generation

On application launch, `utils/data_loader.py` automatically converts the Excel workbook into high-performance Apache Parquet format (`data/sales_dataset.parquet`).
If deleted, the Parquet cache is safely re-generated on next execution.
