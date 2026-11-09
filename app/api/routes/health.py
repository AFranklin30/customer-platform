"""Process and database health probe."""

from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, Response
from pydantic import BaseModel
from sqlalchemy import text

from app.database import engine

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


class HealthStatus(BaseModel):
    status: Literal["ok", "unavailable"]
    database: Literal["ok", "unavailable"]


def _database_reachable() -> bool:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception as exc:
        logger.warning("database_health_check_failed error_type=%s", type(exc).__name__)
        return False
    return True


@router.get("/health", response_model=HealthStatus, summary="Application and database health")
def health(response: Response) -> HealthStatus:
    """Report whether this process can run and reach PostgreSQL.

    The body never includes the database URL, host, username, or driver error.
    """

    if _database_reachable():
        return HealthStatus(status="ok", database="ok")
    response.status_code = 503
    return HealthStatus(status="unavailable", database="unavailable")
