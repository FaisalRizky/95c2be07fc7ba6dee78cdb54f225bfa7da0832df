from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from utils.responses import BaseResponse


class AppError(Exception):
    """Raised anywhere in the service/router layer to produce a structured error response."""

    def __init__(self, status_code: int, error_code: str, message: str):
        self.status_code = status_code
        self.error_code = error_code
        self.message = message


def _json(status_code: int, response: BaseResponse) -> JSONResponse:
    response.status_code = status_code
    return JSONResponse(status_code=status_code, content=response.model_dump())


def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return _json(exc.status_code, BaseResponse.fail(exc.error_code, exc.message))


def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    # Flatten FastAPI's nested validation errors into a single readable string.
    messages = "; ".join(
        f"{' → '.join(str(loc) for loc in err['loc'])}: {err['msg']}"
        for err in exc.errors()
    )
    return _json(422, BaseResponse.fail("validation_error", messages))


def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    detail = exc.detail
    if isinstance(detail, str):
        return _json(exc.status_code, BaseResponse.fail("http_error", detail))
    # If detail is already a dict (e.g. from slowapi), surface it as-is under "message".
    return _json(exc.status_code, BaseResponse.fail("http_error", str(detail)))


def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    print(f"Unhandled Exception: {exc}")  # Replace with Sentry/Datadog in production.
    return _json(500, BaseResponse.fail("internal_error", "An unexpected error occurred."))


def register_exception_handlers(app) -> None:
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(Exception, generic_exception_handler)
