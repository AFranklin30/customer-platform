"""FastAPI application entry point."""

from __future__ import annotations

import logging
from collections.abc import Callable
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.errors import register_exception_handlers
from app.api.routes.customers import router as customers_router
from app.api.routes.health import router as health_router
from app.config import get_settings
from app.logging_config import configure_logging

logger = logging.getLogger(__name__)

_IDEMPOTENCY_HEADER = "Idempotency-Key"


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("application_started")
    yield
    logger.info("application_stopped")


def _require_idempotency_key(schema: dict[str, Any]) -> None:
    """Mark the create header required without changing request handling.

    The dependency still defaults to None so a missing key is rejected by
    validate_idempotency_key as 400 invalid_idempotency_key. FastAPI would
    emit 422 if the header parameter itself were required.
    """

    operation = schema.get("paths", {}).get("/customers", {}).get("post", {})
    for parameter in operation.get("parameters", []):
        name = str(parameter.get("name", ""))
        if parameter.get("in") != "header" or name.lower() != _IDEMPOTENCY_HEADER.lower():
            continue
        parameter["required"] = True
        header_schema = parameter.get("schema")
        if isinstance(header_schema, dict) and "anyOf" in header_schema:
            parameter["schema"] = {
                key: value
                for key, value in header_schema.items()
                if key != "anyOf"
            }
            parameter["schema"]["type"] = "string"


def _openapi_with_required_idempotency_key(app: FastAPI) -> Callable[[], dict[str, Any]]:
    def openapi() -> dict[str, Any]:
        schema = FastAPI.openapi(app)
        _require_idempotency_key(schema)
        return schema

    return openapi


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)
    app = FastAPI(
        title="Customer API",
        version="0.1.0",
        summary="Create and read customer records.",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins(),
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "Idempotency-Key"],
        expose_headers=["Idempotency-Replayed"],
    )
    register_exception_handlers(app)
    app.include_router(health_router)
    app.include_router(customers_router)
    app.openapi = _openapi_with_required_idempotency_key(app)  # type: ignore[method-assign]
    return app


app = create_app()
