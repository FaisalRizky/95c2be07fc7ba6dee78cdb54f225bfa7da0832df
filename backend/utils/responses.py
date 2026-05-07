from __future__ import annotations

import math
from typing import Any, Generic, Optional, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class PaginationMeta(BaseModel):
    page: int
    per_page: int
    total: int
    total_pages: int


class ErrorDetail(BaseModel):
    code: str
    message: str


class BaseResponse(BaseModel, Generic[T]):
    """
    Canonical API envelope for every endpoint.

    Success:  {"success": true,  "status_code": 200, "data": <T>,  "pagination": <meta|null>, "error": null}
    Failure:  {"success": false, "status_code": 404, "data": null, "pagination": null,        "error": {"code":"...", "message":"..."}}
    """

    success: bool
    status_code: int = 200
    data: Optional[T] = None
    pagination: Optional[PaginationMeta] = None
    error: Optional[ErrorDetail] = None

    @classmethod
    def ok(cls, data: Any, pagination: Optional[PaginationMeta] = None) -> BaseResponse:
        return cls(success=True, status_code=200, data=data, pagination=pagination)

    @classmethod
    def fail(cls, code: str, message: str) -> BaseResponse:
        return cls(success=False, error=ErrorDetail(code=code, message=message))


# Streaming responses bypass Pydantic serialization and manually emit the same
# JSON envelope shape. Used when per_page exceeds STREAM_THRESHOLD in the router.
STREAM_PREFIX = '{"success":true,"status_code":200,"data":['
STREAM_SUFFIX = '],"pagination":null,"error":null}'


def paginated_response(data: list, page: int, per_page: int, total: int) -> BaseResponse:
    total_pages = math.ceil(total / per_page) if per_page and total else 0
    meta = PaginationMeta(page=page, per_page=per_page, total=total, total_pages=total_pages)
    return BaseResponse.ok(data=data, pagination=meta)

