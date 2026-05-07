import json
from typing import Optional

from config.cache import apply_cache
from config.db import DatabaseEngine
from utils.errors import AppError
from utils.responses import STREAM_PREFIX, STREAM_SUFFIX
from utils.sorting import SortingConfig, get_order_by_clause


def _build_query(
    area: Optional[str],
    keyword: Optional[str],
    page: Optional[int],
    per_page: Optional[int],
    sorting: SortingConfig,
    project_ids: Optional[list[str]] = None,
    company: Optional[str] = None,
) -> tuple[str, list, str | None, list, str]:
    """
    Returns: (select_sql, select_params, count_sql | None, count_params, exists_sql)

    count_sql and exists_sql are built from the WHERE clause only — no ORDER BY — so the
    database never sorts rows just to count or check existence. This is the main perf fix:
    wrapping an ORDER BY query in COUNT(*) forces a full sort before counting.

    Indexes that should exist for acceptable performance on large datasets:
        project_area_map(area)          — area equality filter
        project_area_map(project_id)    — JOIN to projects
        projects(company_id)            — JOIN to companies
        companies(company_name)         — company equality filter
        projects(project_start)         — default sort column
    LIKE '%keyword%' always causes a full scan regardless of indexes; that path is
    intentionally delegated to Elasticsearch. SQLite fallback is acceptable only for
    small datasets or when ES is unavailable.
    """
    base = """
        SELECT DISTINCT
            p.project_id,
            p.project_name,
            p.project_start,
            p.project_end,
            c.company_name   AS company,
            p.description,
            p.project_value,
            pam.area
        FROM projects p
        INNER JOIN companies c        ON c.company_id  = p.company_id
        INNER JOIN project_area_map pam ON pam.project_id = p.project_id
    """
    where_clauses = []
    params: list = []

    # If project_ids are provided (from Elasticsearch), we skip the direct keyword/area
    # filters because ES has already handled them with its advanced engine.
    if project_ids is not None:
        if not project_ids:
            where_clauses.append("1 = 0") # Force empty result
        else:
            placeholders = ",".join(["?"] * len(project_ids))
            where_clauses.append(f"p.project_id IN ({placeholders})")
            params.extend(project_ids)

            # Preserve the order provided by Elasticsearch
            order_cases = " ".join([f"WHEN ? THEN {i}" for i in range(len(project_ids))])
            order_sql = f"CASE p.project_id {order_cases} END"
            params.extend(project_ids)
            select_sql = f"{base} WHERE {' AND '.join(where_clauses)} ORDER BY {order_sql}"
            exists_sql = f"SELECT 1 FROM ({base} WHERE {' AND '.join(where_clauses[:1])}) LIMIT 1"
            return select_sql, params, None, [], exists_sql
    else:
        # Standard strict search for fallback mode
        if area:
            where_clauses.append("LOWER(pam.area) = LOWER(?)")
            params.append(area.strip())

        if company:
            where_clauses.append("LOWER(c.company_name) = LOWER(?)")
            params.append(company.strip())

        if keyword:
            kw_pattern = f"%{keyword.strip()}%"
            where_clauses.append(
                "(LOWER(p.project_name) LIKE LOWER(?) OR LOWER(p.description) LIKE LOWER(?))"
            )
            params.extend([kw_pattern, kw_pattern])

    if where_clauses:
        base += " WHERE " + " AND ".join(where_clauses)

    # Save the unordered base for COUNT(*) and EXISTS — ORDER BY is useless for both
    # and forces SQLite to sort the full result set before counting.
    base_for_count = base

    project_sort_columns = {
        "project_id": "p.project_id",
        "project_name": "p.project_name",
        "project_start": "p.project_start",
        "project_end": "p.project_end",
        "company": "c.company_name",
        "project_value": "p.project_value",
        "area": "pam.area",
    }

    order_sql = get_order_by_clause(
        sorting,
        allowed_columns=project_sort_columns,
        default_order_sql="p.project_start DESC",
        deterministic_fallback="p.project_name ASC"
    )
    select_sql = base + f" ORDER BY {order_sql}"

    # exists_sql: check for any matching row without sorting or fetching all columns
    exists_sql = f"SELECT 1 FROM ({base_for_count}) LIMIT 1"

    count_params = params

    if page is not None and per_page is not None:
        count_sql = f"SELECT COUNT(*) AS cnt FROM ({base_for_count}) sub"
        paginated_sql = select_sql + " LIMIT ? OFFSET ?"
        offset = (page - 1) * per_page
        return paginated_sql, params + [per_page, offset], count_sql, count_params, exists_sql

    return select_sql, params, None, [], exists_sql

def get_paginated_projects(
    db: DatabaseEngine,
    area: Optional[str],
    keyword: Optional[str],
    page: int,
    per_page: int,
    sort_by: Optional[str],
    order: Optional[str],
    company: Optional[str] = None
) -> tuple[int, list[dict]]:
    sorting = SortingConfig(sort_by=sort_by, order=order)

    # Try Search Engine (Elasticsearch) first
    from config.search import SearchProvider
    project_ids, es_total = SearchProvider.get_engine().search_projects(
        area, keyword, page, per_page, company=company,
        sort_by=sort_by, sort_order=order or "asc"
    )

    # In ES mode, we don't pass page/per_page to SQL because ES already paginated the IDs
    sql_page = page if project_ids is None else None
    sql_per_page = per_page if project_ids is None else None

    paginated_sql, paginated_params, count_sql, count_params, _ = _build_query(
        area, keyword, sql_page, sql_per_page, sorting, project_ids=project_ids, company=company
    )

    try:
        total = 0
        if count_sql:
            row = db.fetch_one(count_sql, count_params)
            total = row["cnt"] if row else 0
        elif project_ids is not None:
            # Successfully used Elasticsearch
            total = es_total

        projects = db.fetch_all(paginated_sql, paginated_params)
        return total, projects
    except Exception as e:
        raise AppError(500, "database_error", str(e))



def stream_all_projects(
    db: DatabaseEngine,
    area: Optional[str],
    keyword: Optional[str],
    sort_by: Optional[str],
    order: Optional[str],
    company: Optional[str] = None,
):
    sorting = SortingConfig(sort_by=sort_by, order=order)
    sql, params, _, _, exists_sql = _build_query(area, keyword, None, None, sorting, company=company)

    try:
        has_rows = db.fetch_one(exists_sql, params) is not None
    except Exception as e:
        raise AppError(500, "database_error", str(e))

    if not has_rows:
        return None

    def iter_projects():
        yield STREAM_PREFIX
        first = True
        for row in db.fetch_many_generator(sql, params, chunk_size=100):
            if not first:
                yield ","
            first = False
            yield json.dumps(row)
        yield STREAM_SUFFIX

    return iter_projects()


def get_project_by_id(db: DatabaseEngine, project_id: str) -> dict | None:
    sql = """
        SELECT DISTINCT
            p.project_id,
            p.project_name,
            p.project_start,
            p.project_end,
            c.company_name AS company,
            p.description,
            p.project_value,
            pam.area
        FROM projects p
        INNER JOIN companies c          ON c.company_id  = p.company_id
        INNER JOIN project_area_map pam ON pam.project_id = p.project_id
        WHERE p.project_id = ?
        LIMIT 1
    """
    try:
        return db.fetch_one(sql, [project_id])
    except Exception as e:
        raise AppError(500, "database_error", str(e))


@apply_cache(ttl_seconds=3600)
def get_all_areas(db: DatabaseEngine) -> list[str]:
    try:
        rows = db.fetch_all("SELECT DISTINCT area FROM project_area_map ORDER BY area")
        return [r["area"] for r in rows]
    except Exception as e:
        raise AppError(500, "database_error", str(e))

@apply_cache(ttl_seconds=3600)
def get_all_companies(db: DatabaseEngine) -> list[str]:
    try:
        rows = db.fetch_all("SELECT DISTINCT company_name FROM companies ORDER BY company_name")
        return [r["company_name"] for r in rows]
    except Exception as e:
        raise AppError(500, "database_error", str(e))

def get_projects_for_indexing(db: DatabaseEngine):
    """
    Service-level method to fetch data specifically for search indexing.
    This keeps SQL out of the utility layers.
    """
    sql = """
        SELECT
            p.project_id, p.project_name, p.description, p.project_value,
            pam.area, p.project_start, c.company_name AS company
        FROM projects p
        INNER JOIN project_area_map pam ON pam.project_id = p.project_id
        INNER JOIN companies c        ON c.company_id = p.company_id
    """
    return db.fetch_many_generator(sql, chunk_size=500)

def sync_projects_to_elasticsearch(db: DatabaseEngine):
    """
    Orchestrates the synchronization of project data to Elasticsearch.
    - Waits for ES to be ready using technical helpers.
    - Performs the business sync logic.
    """
    from config.elasticsearch import bulk_index_data, es_client, setup_elasticsearch
    from utils.es_helpers import wait_for_elasticsearch

    # 1. Wait for infrastructure to be ready
    if not wait_for_elasticsearch(es_client):
        print("[service] Skipping sync: Elasticsearch not reachable.")
        return 0

    # 2. Ensure Index is configured with analyzers
    setup_elasticsearch()

    # 3. Stream data from DB -> Infrastructure
    print("[service] Starting project synchronization...")
    data_stream = get_projects_for_indexing(db)
    success_count = bulk_index_data(data_stream, id_field="project_id")

    return success_count
