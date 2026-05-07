from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse

from config.db import DatabaseEngine, get_db
from services.project_service import (
    get_all_areas,
    get_all_companies,
    get_paginated_projects,
    get_project_by_id,
    stream_all_projects,
)
from utils.errors import AppError
from utils.rate_limit import limiter
from utils.responses import BaseResponse, paginated_response

router = APIRouter()

DEFAULT_PAGE = 1
DEFAULT_PER_PAGE = 20
STREAM_THRESHOLD = 1000  # per_page above this switches to cursor-based streaming


@router.get("/projects", summary="List construction projects")
@limiter.limit("60/minute")
def list_projects(
    request: Request,
    area: Optional[str] = Query(default=None, description="Filter by area (case-insensitive exact match)"),
    keyword: Optional[str] = Query(default=None, description="Search across name, description(case-insensitive)"),  # noqa: E501
    page: Optional[int] = Query(default=None, description="Page number (1-based); defaults to 1 if omitted", ge=1),
    per_page: Optional[int] = Query(default=None, description="Items per page; defaults to 20 if omitted; above 1000 triggers streaming", ge=1),  # noqa: E501
    sort_by: Optional[str] = Query(default=None, description="Sort column: project_id|project_name|project_start|project_end|company|project_value|area"),  # noqa: E501
    order: Optional[str] = Query(default="desc", pattern="^(asc|desc)$", description="asc or desc (default: desc)"),
    company: Optional[str] = Query(default=None, description="Filter by company (case-insensitive exact match)"),
    db: DatabaseEngine = Depends(get_db),
) -> BaseResponse:
    """
    Return construction projects with pagination.

    - Missing `page` defaults to 1; missing `per_page` defaults to 20.
    - Default sort: `project_start DESC` — most recent projects first.
    - `per_page` > 1000 switches to cursor-based streaming (prevents OOM on bulk exports).

    > ⚠️ Requesting `per_page` above ~100 in Swagger UI may freeze the browser tab.
    > Use curl or Postman for large result sets.
    """
    effective_page = page if page is not None else DEFAULT_PAGE
    effective_per_page = per_page if per_page is not None else DEFAULT_PER_PAGE

    # Large per_page → stream all matching rows to avoid loading everything into RAM.
    if effective_per_page > STREAM_THRESHOLD:
        stream_gen = stream_all_projects(db, area, keyword, sort_by, order, company=company)
        if stream_gen is None:
            return BaseResponse.ok(data=[])
        return StreamingResponse(stream_gen, media_type="application/json")

    total, projects = get_paginated_projects(
        db, area, keyword, effective_page, effective_per_page, sort_by, order, company=company
    )
    return paginated_response(projects, effective_page, effective_per_page, total)


@router.get("/projects/{project_id}", summary="Get a single project by ID")
@limiter.limit("60/minute")
def get_project(
    request: Request,
    project_id: str,
    db: DatabaseEngine = Depends(get_db),
) -> BaseResponse:
    """Return full detail for a single project. Returns 404 if the ID does not exist."""
    project = get_project_by_id(db, project_id)
    if project is None:
        raise AppError(404, "not_found", f"Project '{project_id}' not found.")
    return BaseResponse.ok(data=project)


@router.get("/areas", summary="List all known areas")
@limiter.limit("30/minute")
def list_areas(request: Request, db: DatabaseEngine = Depends(get_db)) -> BaseResponse:
    return BaseResponse.ok(data=get_all_areas(db))


@router.get("/companies", summary="List all known companies")
@limiter.limit("30/minute")
def list_companies(request: Request, db: DatabaseEngine = Depends(get_db)) -> BaseResponse:
    return BaseResponse.ok(data=get_all_companies(db))
