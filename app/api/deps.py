"""FastAPI dependencies."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Header
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.services.idempotency import validate_idempotency_key


def get_db() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def get_idempotency_key(
    idempotency_key: Annotated[
        str | None,
        Header(
            description=(
                "Optional retry key. The same key and payload return the original "
                "customer. The same key with a different payload returns 409."
            )
        ),
    ] = None,
) -> str | None:
    return validate_idempotency_key(idempotency_key)


DbSession = Annotated[Session, Depends(get_db)]
IdempotencyKeyHeader = Annotated[str | None, Depends(get_idempotency_key)]
