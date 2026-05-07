from dataclasses import dataclass
from typing import Optional


@dataclass
class SortingConfig:
    sort_by: Optional[str]
    order: Optional[str]


def get_order_by_clause(
    sorting: SortingConfig,
    allowed_columns: dict[str, str],
    default_order_sql: str,
    deterministic_fallback: str = "",
) -> str:
    """
    Generates a safe SQL ORDER BY clause dynamically.

    Args:
        sorting: The requested sort parameters.
        allowed_columns: Dictionary mapping API fields to safe SQL column names.
        default_order_sql: The default SQL if no valid sorting is provided.
        deterministic_fallback: Appended to the end of custom sorts for deterministic pagination.
    """
    order_sql = default_order_sql

    if sorting.sort_by and sorting.sort_by in allowed_columns:
        sql_col = allowed_columns[sorting.sort_by]
        sort_dir = "ASC" if sorting.order == "asc" else "DESC"
        order_sql = f"{sql_col} {sort_dir}"

    # Stable ordering so pagination is deterministic
    if deterministic_fallback and deterministic_fallback not in order_sql:
        order_sql += f", {deterministic_fallback}"

    return order_sql
