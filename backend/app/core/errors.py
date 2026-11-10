"""Application errors and a single JSON error envelope.

Every error response has the shape:
    {"error": {"code": "...", "message": "...", "details": {...}}}
"""

import logging
from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("kaamsetu.errors")


class AppError(Exception):
    status_code: int = 400
    code: str = "bad_request"

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        status_code: int | None = None,
        details: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        if code:
            self.code = code
        if status_code:
            self.status_code = status_code
        self.details = details or {}
        self.headers = headers


class BadRequest(AppError):
    status_code, code = 400, "bad_request"


class Unauthorized(AppError):
    status_code, code = 401, "not_authenticated"

    def __init__(self, message: str = "Authentication required", **kw: Any) -> None:
        kw.setdefault("headers", {"WWW-Authenticate": "Bearer"})
        super().__init__(message, **kw)


class Forbidden(AppError):
    status_code, code = 403, "forbidden"


class NotFound(AppError):
    status_code, code = 404, "not_found"


class Conflict(AppError):
    status_code, code = 409, "conflict"


class Unprocessable(AppError):
    status_code, code = 422, "validation_error"


class TooManyRequests(AppError):
    status_code, code = 429, "rate_limited"


def error_body(code: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "details": details or {}}}


def _sanitize_validation_errors(errors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    # Drop the submitted input values so passwords and other fields are never echoed back.
    return [{"loc": list(e.get("loc", [])), "msg": e.get("msg", ""), "type": e.get("type", "")} for e in errors]


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=error_body(exc.code, exc.message, exc.details),
            headers=exc.headers,
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        try:
            phrase = HTTPStatus(exc.status_code).phrase
        except ValueError:
            phrase = "Error"
        code = phrase.lower().replace(" ", "_").replace("-", "_")
        message = exc.detail if isinstance(exc.detail, str) else phrase
        return JSONResponse(
            status_code=exc.status_code,
            content=error_body(code, message),
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=error_body(
                "validation_error",
                "Request validation failed",
                {"errors": _sanitize_validation_errors(list(exc.errors()))},
            ),
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        logger.exception(
            "Unhandled error",
            extra={"ctx": {"path": request.url.path, "request_id": getattr(request.state, "request_id", None)}},
        )
        return JSONResponse(status_code=500, content=error_body("internal_error", "An unexpected error occurred"))
