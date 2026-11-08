"""Idempotency key table access."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.idempotency import IdempotencyKey


class IdempotencyRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, record: IdempotencyKey) -> IdempotencyKey:
        self._session.add(record)
        self._session.flush()
        return record

    def get_by_key(self, key: str) -> IdempotencyKey | None:
        statement = select(IdempotencyKey).where(IdempotencyKey.idempotency_key == key)
        return self._session.scalar(statement)
