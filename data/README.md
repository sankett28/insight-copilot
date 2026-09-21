# Data Directory

Place your dataset file here before starting the application.

## Supported formats

| Format  | Extension       |
|---------|-----------------|
| CSV     | `.csv`          |
| Parquet | `.parquet`      |
| Excel   | `.xlsx`, `.xls` |

## Notes

- Dataset files are excluded from version control via `.gitignore`.
- Update `DATASET_PATH` in your `.env` file to point to your file.
- The `data_loader` utility will register the file as a DuckDB table named `dataset`.
