"""Map domain and validation failures to one JSON error shape."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.services.exceptions import (
    DuplicateEmailError,
    IdempotencyConflictError,
    IdempotencyInProgressError,
    InvalidIdempotencyKeyError,
)

logger = logging.getLogger(__name__)


def error_json(
    status_code: int,
    code: str,
    message: str,
    details: list[dict[str, Any]] | None = None,
) -> JSONResponse:
    error: dict[str, Any] = {"code": code, "message": message}
    if details is not None:
        error["details"] = details
    return JSONResponse(status_code=status_code, content={"error": error})


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(DuplicateEmailError, _duplicate_email)
    app.add_exception_handler(IdempotencyConflictError, _idempotency_conflict)
    app.add_exception_handler(IdempotencyInProgressError, _idempotency_in_progress)
    app.add_exception_handler(InvalidIdempotencyKeyError, _invalid_idempotency_key)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(HTTPException, _http_error)
    app.add_exception_handler(Exception, _unhandled)


async def _duplicate_email(request: Request, exc: Exception) -> JSONResponse:
    return error_json(409, "duplicate_email", "A customer with this email already exists.")


async def _idempotency_conflict(request: Request, exc: Exception) -> JSONResponse:
    return error_json(
        409,
        "idempotency_payload_conflict",
        "This idempotency key was already used with a different request payload.",
    )


async def _idempotency_in_progress(request: Request, exc: Exception) -> JSONResponse:
    return error_json(
        409,
        "idempotency_in_progress",
        "A request with this idempotency key has not finished yet.",
    )


async def _invalid_idempotency_key(request: Request, exc: Exception) -> JSONResponse:
    return error_json(
        400,
        "invalid_idempotency_key",
        "Idempotency-Key must be 1 to 255 visible ASCII characters.",
    )


async def _validation_error(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, RequestValidationError):
        raise exc
    details = [
        {
            "loc": [str(part) for part in error.get("loc", ())],
            "message": str(error.get("msg", "")),
            "type": str(error.get("type", "")),
        }
        for error in exc.errors()
    ]
    return error_json(422, "validation_error", "Request validation failed.", details)


async def _http_error(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, HTTPException):
        raise exc
    message = exc.detail if isinstance(exc.detail, str) else "Request failed."
    return error_json(exc.status_code, "http_error", message)


async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("unhandled_error method=%s path=%s", request.method, request.url.path)
    return error_json(500, "internal_error", "An unexpected error occurred.")
