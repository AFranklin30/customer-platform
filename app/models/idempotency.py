"""Persisted idempotency keys for customer creation."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, Integer, String, UniqueConstraint, Uuid, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class IdempotencyKey(Base):
    """One logical create-customer request.

    The row is inserted in the same transaction as the customer. Callers
    cannot observe a key until that transaction commits, so a committed row
    always has both the request hash and the original response.
    response_code and response_body stay nullable so an incomplete row can be
    detected if one is ever committed outside this service.
    """

    __tablename__ = "idempotency_keys"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_idempotency_keys_key"),
        CheckConstraint(
            "(response_code IS NULL AND response_body IS NULL) OR "
            "(response_code IS NOT NULL AND response_body IS NOT NULL)",
            name="ck_idempotency_keys_response_complete",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    response_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_body: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
