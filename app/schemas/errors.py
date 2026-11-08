"""Error response schema shared by API exception handlers."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ErrorBody(BaseModel):
    code: str
    message: str
    details: list[dict[str, Any]] | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody = Field(
        examples=[
            {
                "code": "duplicate_email",
                "message": "A customer with this email already exists.",
            }
        ]
    )
