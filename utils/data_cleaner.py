"""
utils/data_cleaner.py
---------------------
Generalized, algorithmic data cleaning engine for DuckDB.

Responsibilities:
  - Text normalization: TRIM and Title-casing (INITCAP).
  - Algorithmic typo clustering using frequency-weighted Levenshtein distance.
  - Categorical null coalescing (e.g. 'Unassigned').
  - Dynamic updates to the active 'dataset' view while preserving immutable 'raw_dataset'.
"""

from __future__ import annotations

import logging
from typing import Any

import duckdb

from models.schemas import CANONICAL_COLUMNS, CATEGORICAL_COLUMNS, DataCleanRequest

logger = logging.getLogger(__name__)


def levenshtein_distance(s1: str, s2: str) -> int:
    """Compute the Levenshtein edit distance between two strings."""
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)

    if len(s2) == 0:
        return len(s1)

    previous_row = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row

    return previous_row[-1]


def build_fuzzy_cluster_mapping(
    conn: duckdb.DuckDBPyConnection,
    table: str,
    column: str,
    threshold: int = 1,
) -> dict[str, str]:
    """Identify typo variants and map them to their dominant parent cluster.

    Algorithm:
      1. Fetch all distinct non-null values ordered by frequency DESC.
      2. Title-case and trim candidate values as the baseline.
      3. For each low-frequency value, test edit distance against higher-frequency canonical parents.
      4. If Levenshtein(v_low.lower(), v_high.lower()) <= threshold, cluster v_low -> v_high.

    Args:
        conn: Active DuckDB connection.
        table: Source table or view (e.g. 'raw_dataset').
        column: Categorical column name.
        threshold: Maximum allowed edit distance for merging (default 1).

    Returns:
        Mapping dictionary: {raw_value: canonical_value}.
    """
    sql = f"SELECT {column}::VARCHAR, COUNT(*) AS cnt FROM {table} WHERE {column} IS NOT NULL GROUP BY {column} ORDER BY cnt DESC"
    rows = conn.execute(sql).fetchall()
    if not rows:
        return {}

    # Initial frequency list of (raw_val, count, normalized_title_val)
    freq_list: list[tuple[str, int, str]] = []
    for raw_val, count in rows:
        clean_title = str(raw_val).strip()
        if clean_title:
            # Standardize casing to Title Case (e.g. 'NORTH' -> 'North', 'south' -> 'South')
            clean_title = clean_title.title()
        freq_list.append((str(raw_val), int(count), clean_title))

    # Identify canonical parent values by summing counts of title-cased representations
    canonical_counts: dict[str, int] = {}
    for _, cnt, title_val in freq_list:
        canonical_counts[title_val] = canonical_counts.get(title_val, 0) + cnt

    # Sort canonical parents by total frequency descending
    sorted_canonicals = sorted(canonical_counts.keys(), key=lambda k: canonical_counts[k], reverse=True)

    mapping: dict[str, str] = {}

    for raw_val, _, title_val in freq_list:
        # Step 1: Case normalization
        matched_target = title_val

        # Step 2: Fuzzy cluster matching against higher-frequency canonical targets
        for parent in sorted_canonicals:
            if parent.lower() == title_val.lower():
                matched_target = parent
                break
            # Check Levenshtein distance on lowercased strings
            dist = levenshtein_distance(title_val.lower(), parent.lower())
            if dist <= threshold:
                logger.info(
                    "Fuzzy typo cluster matched: '%s' -> '%s' (edit distance %d)",
                    title_val,
                    parent,
                    dist,
                )
                matched_target = parent
                break

        mapping[raw_val] = matched_target

    return mapping


def apply_cleaning_to_duckdb(
    conn: duckdb.DuckDBPyConnection,
    req: DataCleanRequest,
) -> dict[str, Any]:
    """Construct and execute a dynamic cleaning view update in DuckDB.

    Recreates the active 'dataset' view from 'raw_dataset' applying all requested
    cleaning transformations (casing, fuzzy deduplication, and null filling).

    Args:
        conn: Active DuckDB connection.
        req: Validated DataCleanRequest.

    Returns:
        Structured audit dictionary summarizing before/after metrics.
    """
    target_columns = req.columns
    operations = req.operations
    fill_null_val = req.fill_null_value
    threshold = req.similarity_threshold

    # Collect before metrics
    distinct_before: dict[str, int] = {}
    distinct_after: dict[str, int] = {}
    cluster_mappings: dict[str, dict[str, str]] = {}
    nulls_replaced_counts: dict[str, int] = {}

    select_expressions: list[str] = []

    for col in CANONICAL_COLUMNS:
        if col not in target_columns or col not in CATEGORICAL_COLUMNS:
            # Preserve column as-is
            select_expressions.append(col)
            continue

        # Measure distinct count and nulls before
        b_distinct = conn.execute(f"SELECT COUNT(DISTINCT {col}) FROM raw_dataset").fetchone()
        distinct_before[col] = int(b_distinct[0]) if b_distinct else 0

        b_nulls = conn.execute(f"SELECT COUNT(*) FROM raw_dataset WHERE {col} IS NULL").fetchone()
        nulls_replaced_counts[col] = int(b_nulls[0]) if b_nulls else 0

        # Build fuzzy cluster mapping if requested
        col_mapping = {}
        if "fuzzy_deduplicate" in operations or "standardize_casing" in operations:
            col_mapping = build_fuzzy_cluster_mapping(
                conn, "raw_dataset", col, threshold=threshold if "fuzzy_deduplicate" in operations else 0
            )
            cluster_mappings[col] = col_mapping

        # Construct CASE WHEN expression
        when_clauses: list[str] = []
        for raw_val, clean_val in col_mapping.items():
            escaped_raw = raw_val.replace("'", "''")
            escaped_clean = clean_val.replace("'", "''")
            when_clauses.append(f"WHEN {col} = '{escaped_raw}' THEN '{escaped_clean}'")

        if when_clauses:
            case_expr = f"CASE {' '.join(when_clauses)} ELSE {col} END"
        else:
            case_expr = col

        if "fill_nulls" in operations:
            escaped_null = fill_null_val.replace("'", "''")
            col_sql = f"COALESCE({case_expr}, '{escaped_null}') AS {col}"
        else:
            col_sql = f"{case_expr} AS {col}"

        select_expressions.append(col_sql)

    # Recreate the active 'dataset' view from 'raw_dataset'
    projection_sql = ",\n    ".join(select_expressions)
    create_view_sql = f"CREATE OR REPLACE VIEW dataset AS SELECT\n    {projection_sql}\nFROM raw_dataset"
    logger.info("Updating active 'dataset' view with cleaning projection:\n%s", create_view_sql)
    conn.execute(create_view_sql)

    # Measure distinct count after
    for col in target_columns:
        if col in CATEGORICAL_COLUMNS:
            a_distinct = conn.execute(f"SELECT COUNT(DISTINCT {col}) FROM dataset").fetchone()
            distinct_after[col] = int(a_distinct[0]) if a_distinct else 0

    return {
        "status": "success",
        "columns_cleaned": target_columns,
        "operations_applied": operations,
        "distinct_before": distinct_before,
        "distinct_after": distinct_after,
        "nulls_replaced": nulls_replaced_counts,
        "cluster_mappings": cluster_mappings,
        "message": f"Successfully cleaned columns {target_columns}. Active 'dataset' view updated in DuckDB.",
    }
